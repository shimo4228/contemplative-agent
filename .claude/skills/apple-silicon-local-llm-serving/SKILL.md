---
name: apple-silicon-local-llm-serving
description: Apple Silicon (M1–M5) でローカル LLM の推論ランタイムを選ぶ・足す・最適化するときの判断軸。mlx_lm.server は Ollama 比 ~1.8x 速だが生成専用（埋め込み endpoint なし・response_format/JSON schema 拘束なし）なので埋め込みは Ollama に残す2サーバ構成になる点、ユニファイドメモリは VRAM 容量でなくメモリ帯域律速で MoE は RAM を節約しない点、コンテナは Metal 非対応な点を扱う。Use when 「Mac でもっと速く / 大きいモデルを動かしたい」「mlx-lm / MLX を入れたい」「Ollama から乗り換え / 併用したい」「16GB で実用的なモデルは」を検討するとき、生成を MLX に寄せて埋め込みの扱いで詰まったとき、ローカル LLM のベンチ A/B でメモリ圧の交絡を疑うとき。NVIDIA 前提（VRAM の壁・量子化・MoE オフロード）の知識を Apple Silicon に翻訳する必要があるとき。
origin: shimo4228
user-invocable: true
---

# Apple Silicon ローカル LLM serving: mlx_lm.server vs Ollama

Apple Silicon で「もっと速く / もっと大きいモデルを」運用したくなったとき、NVIDIA 前提の知識（VRAM の壁・量子化ラベル・MoE オフロード）はそのまま当てはまらない。Ollama から MLX (`mlx_lm.server`) に寄せる際は、**非自明な3つの制約**（埋め込み非対応・構造化出力非対応・コンテナ不可）で詰まりやすい。このスキルはその判断軸と落とし穴を持つ。

Contemplative Agent では ADR-0064 でこの判断を実装している（`LLM_BACKEND=mlx` で生成のみ mlx_lm.server、埋め込みは Ollama 据え置き）。以下は実測・ソース精読で確定した汎用知見。

## ランタイム選択

- **mlx_lm.server（Apple 純正 MLX ランタイム）は同一重みで速い・軽い**。M1/16GB・Qwen 9B 実測で **Ollama (Metal/GGUF) 比 生成 ~1.8x 速・メモリ 8.6→5.2GB**。差は本質的（後述の交絡チェックで確認済み）。API は OpenAI `/v1/chat/completions` 形式。
- **ただし生成専用。2つの「無い」に注意**:
  1. **埋め込み endpoint が無い** → 埋め込み（nomic-embed-text 等）は **Ollama (`/api/embed`) に残す**。結果は「生成 = mlx_lm.server :8080 / 埋め込み = Ollama :11434」の**2サーバ併走**になる。
  2. **`response_format` / JSON schema 拘束が無い**（Ollama の `format=` 相当が無い）→ 構造化出力は **プロンプト指示 + パース fallback** で代替する。単純スキーマ（`{"items":[...]}` 等）なら instruct モデルは十分クリーンな JSON を返す（実測でフォールバック発動0）。複雑スキーマで崩れるなら、その呼び出しだけ Ollama に残す。
- **thinking 系モデルの thinking off** は per-request `chat_template_kwargs={"enable_thinking": false}`（または起動時 `--chat-template-args '{"enable_thinking": false}'`）。
- **mlx-lm を依存に入れない**: アプリは HTTP を叩くだけなので `uvx --from mlx-lm` / `uv tool install mlx-lm` で server を回し、アプリの依存は increase させない。

## ユニファイドメモリの効き方（NVIDIA 知識の翻訳）

- **「VRAM 容量の壁」→「メモリ帯域の問い」に変わる**。CPU/GPU が同一メモリプールをゼロコピー共有するので容量制約は緩いが、**生成（デコード）は帯域律速**: 生成 tok/s ≈ メモリ帯域 ÷ モデルサイズ。無印 M1=68GB/s は Pro(200)/Max(400) の数分の一で、これが tok/s の天井を直接決める。プロンプト処理（プリフィル）は計算律速。
- **MoE は Apple Silicon では RAM を節約しない**。トークン毎に一部エキスパートしか活性化しなくても**全エキスパート重みが常駐必須**（別 VRAM プールが無いので NVIDIA のエキスパート CPU オフロード手法は無効）。「8GB GPU で 120B」式の MoE オフロードは Apple Silicon に移植できない。
- **16GB で重みに使えるのは実用 ~11GB**（Metal の `recommendedMaxWorkingSetSize` が物理 RAM の ~67–75% にソフト制限）。`sudo sysctl iogpu.wired_limit_mb` で引き上げ可（ハード上限ではない）。9–10GB の重み + KV キャッシュ + OS で枠を超えればスワップする。
- **コンテナ不可**: macOS Docker は Metal パススルー非対応で、コンテナ内 MLX/Ollama は CPU 推論に落ちて 3–5x 遅い → **推論サーバはホスト実行**（→ `docker-local-llm-tradeoff` 参照）。

## ベンチ A/B の落とし穴

- **メモリ圧（スワップ）の交絡**: 重いモデルを 16GB で測ると、片方がスワップ中・もう片方が低スワップだと差が不当に出る。**疑わしい arm を低スワップ条件に揃えて再測定**し、速度差がランタイム本質か資源圧の副産物かを切り分ける（今回 Ollama を低スワップで再測定し、~7 tok/s で不変 → MLX の優位は本質と確定した）。
- **公平性の統一**: thinking ON/OFF・temperature・max_tokens・量子化ビットを両 arm で揃える。特に thinking 不一致はトークン数と速度を別物にする。ウォームアップ1回を捨て、3回の中央値を取る（初回はモデルロードと Metal シェーダコンパイルが混ざる）。
- **量子化は arm 間でバイト等価でない**（GGUF Q4_K_M ≠ MLX 4bit）。速度比較は妥当だが、品質差はランタイムでなく量子化方式の差が混ざる。品質を測るなら量子化を近づける（混合精度の OptiQ 系など）。

## When to Use

- Apple Silicon でローカル LLM ランタイム（Ollama / mlx-lm / LM Studio）を選ぶ・併用するとき
- mlx_lm.server を既存 Ollama 構成に足すとき（埋め込み・構造化出力で詰まる前に）
- 「16GB でもっと速く / 大きいモデルを」を NVIDIA 前提（VRAM の壁・MoE オフロード）で考えてしまったとき
- ローカル LLM のベンチ A/B が腑に落ちないとき（メモリ圧の交絡を疑う）
