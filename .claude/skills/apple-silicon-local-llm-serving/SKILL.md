---
name: apple-silicon-local-llm-serving
description: Apple Silicon (M1–M5) でローカル LLM の推論ランタイムを選ぶ・足す・最適化する、および「この作業がそのランタイムに載るか」を判定するときの判断軸。3 択（Ollama / mlx_lm.server / OS 内蔵 Foundation Models）それぞれの非自明な制約を持つ — mlx_lm.server は Ollama 比 ~1.8x 速だが生成専用（埋め込み endpoint なし・response_format/JSON schema 拘束なし）、Foundation Models は常駐メモリを増やさない代わりに context 窓が read-only の天井（macOS 26 で 4,096）で埋め込み・finish_reason・reasoning が無く top-k/top-p も排他、ユニファイドメモリは VRAM 容量でなくメモリ帯域律速で MoE は RAM を節約せず、コンテナは Metal 非対応。Use when 「Mac / iPhone でこのエージェントを動かせるか」「iOS / macOS の Foundation Models・Apple Intelligence・apple-fm-sdk を使えるか」「mlx-lm / MLX を入れたい」「Ollama から乗り換え / 併用したい」「16GB で実用的なモデルは」「もっと速く / 大きいモデルを動かしたい」を検討するとき、候補ランタイムの context 窓に自分のプロンプトが収まるか測るとき、生成を MLX に寄せて埋め込みの扱いで詰まったとき、ローカル LLM のベンチ A/B が腑に落ちないとき（メモリ圧の交絡・合成入力での測定ミスを疑う）。NVIDIA 前提（VRAM の壁・量子化・MoE オフロード）の知識を Apple Silicon に翻訳する必要があるとき。
origin: shimo4228
user-invocable: true
---

# Apple Silicon ローカル LLM serving: Ollama vs mlx_lm.server vs Foundation Models

Apple Silicon で「もっと速く / もっと大きいモデルを」運用したくなったとき、NVIDIA 前提の知識（VRAM の壁・量子化ラベル・MoE オフロード）はそのまま当てはまらない。Ollama から MLX (`mlx_lm.server`) に寄せる際は、**非自明な3つの制約**（埋め込み非対応・構造化出力非対応・コンテナ不可）で詰まりやすい。OS 内蔵の **Foundation Models** はさらに別の制約集合（窓が天井・埋め込みなし・切り詰め検出なし・reasoning なし）を持つ。このスキルはその判断軸と落とし穴を持つ。

問いは 2 種類ある。**「どれを選ぶか」**（速度・メモリ）と、**「そもそも自分の作業が載るか」**（context 窓に収まるか・必要な機能があるか）。後者は Foundation Models のように窓が固定のランタイムでは決定的で、**選定より先に測る**。

Contemplative Agent では ADR-0064 でこの判断を実装している（`LLM_BACKEND=mlx` で生成のみ mlx_lm.server、埋め込みは Ollama 据え置き）。以下は実測・ソース精読で確定した汎用知見。

## ランタイム選択

- **mlx_lm.server（Apple 純正 MLX ランタイム）は同一重みで速い・軽い**。M1/16GB・Qwen 9B 実測で **Ollama (Metal/GGUF) 比 生成 ~1.8x 速・メモリ 8.6→5.2GB**。差は本質的（後述の交絡チェックで確認済み）。API は OpenAI `/v1/chat/completions` 形式。
- **ただし生成専用。2つの「無い」に注意**:
  1. **埋め込み endpoint が無い** → 埋め込み（nomic-embed-text 等）は **Ollama (`/api/embed`) に残す**。結果は「生成 = mlx_lm.server :8080 / 埋め込み = Ollama :11434」の**2サーバ併走**になる。
  2. **`response_format` / JSON schema 拘束が無い**（Ollama の `format=` 相当が無い）→ 構造化出力は **プロンプト指示 + パース fallback** で代替する。単純スキーマ（`{"items":[...]}` 等）なら instruct モデルは十分クリーンな JSON を返す（実測でフォールバック発動0）。複雑スキーマで崩れるなら、その呼び出しだけ Ollama に残す。
- **thinking 系モデルの thinking off** は per-request `chat_template_kwargs={"enable_thinking": false}`（または起動時 `--chat-template-args '{"enable_thinking": false}'`）。
- **mlx-lm を依存に入れない**: アプリは HTTP を叩くだけなので `uvx --from mlx-lm` / `uv tool install mlx-lm` で server を回し、アプリの依存は increase させない。
- **Foundation Models（OS 内蔵、第3の選択肢）は「メモリを食わない」が「窓が狭い」**。OS がモデルを所有するので**常駐メモリを一切増やさない** — 16GB 機で Ollama/MLX が RAM を奪い合う問題に対して、他2者と質の違う答えになる。公式 Python バインディング `apple-fm-sdk`（`pip install apple-fm-sdk`、macOS 26.0+、Apple Intelligence 有効が前提）があるので Swift shim は不要。**iOS では使えない** — SDK は macOS 専用で、位置づけも「Swift アプリの挙動を開発機で eval する道具」。iOS アプリに載せるなら Swift 移植。
- **Foundation Models の4つの「無い」**:
  1. **窓が可変でない** — `SystemLanguageModel.context_size` は read-only の getter（native の `FMSystemLanguageModelGetContextSize` を読むだけ）。macOS 26.x 実測 **4,096**（OS 27 世代は 8,192）で、`use_case` × `guardrails` の全組合せで不変。**Ollama の `num_ctx` のような「低い既定値」ではなく天井**なので、送って広げることができない。超過は `ExceededContextWindowSizeError`。
  2. **埋め込みが無い** — MLX と同じく生成専用。埋め込みは Ollama 据え置きの2サーバ構成になる。
  3. **`finish_reason` / usage が無い**（Python SDK 0.2.1 時点）— `respond()` は素の `str` を返すので**切り詰めがサイレント**。ただし `token_count()`（macOS 26.4+）で再構成できる: 切り詰め出力は `maximum_response_tokens + 一定オフセット` に着地する（実測 +8。cap 12→20 / 40→48 / 120→128、自然終了は下回る）。**オフセットは焼き込まず起動時に較正する** — SDK/OS 更新でずれたら黙って誤判定に変わる。
  4. **reasoning が無い** — on-device に thinking 相当が無い（Private Cloud Compute 側にはある）。think-ON 前提の経路は黙って無効化されるので、think を選定根拠にした ADR があるなら明示的に再評価する。
- **sampling は片肺しか選べない。選ぶなら top-p** — `SamplingMode.random(top=..., probability_threshold=...)` は**排他**（`ValueError: Cannot specify both`）。top-k と top-p を両掛けする運用からは移せない。`seed` はあるのでテストの決定論性は取りやすい。**どちらを残すかは実測で決着済み**（2026-08-01、temp 1.3・実投稿 30 件・各 arm n=30）: `probability_threshold=0.95` 単独は 4-gram 反復率が最大 0.126 で 0.05 超えも 1/30 件、`top=20` 単独は 3/30 件が 0.05 超え・**1 件が 0.467**（出力の約半分が反復＝退化）。**片肺なら `probability_threshold`**。なお `mlx_lm.server` + Qwen で「両方必須」だった知見は**そのまま転移しない** — 退化はモデルとサンプラの実装依存なので、ランタイムを変えたら測り直す。品質そのものは 2 択で差がつかなかった（盲検の平均順位 2.39 vs 2.40）ので、この選択は品質でなく**退化事故の確率**を選ぶ判断。
- **`maximum_response_tokens` は省略可 = 上限なし**（省略と 3000 指定で出力同一を実測）。対して **Ollama の `num_predict` は省略すると既定 128 で切られる**（`-1` 無制限 / `-2` fill context、ソース側で 10×ctx に丸め）。**逆なので移植時に取り違えない**。どちらも「何も確保しない停止条件」で、窓から予算を切り出すわけではない。
- **OS 更新直後は `MODEL_NOT_READY`** — `is_available()` が False を返す期間がある（実測 ~5 分）。この間も `context_size` は値を返すが**信用してはいけない**。`token_count()` は macOS 26.4 未満では status 255 で失敗する（back-deploy の下限）。

## ユニファイドメモリの効き方（NVIDIA 知識の翻訳）

- **「VRAM 容量の壁」→「メモリ帯域の問い」に変わる**。CPU/GPU が同一メモリプールをゼロコピー共有するので容量制約は緩いが、**生成（デコード）は帯域律速**: 生成 tok/s ≈ メモリ帯域 ÷ モデルサイズ。無印 M1=68GB/s は Pro(200)/Max(400) の数分の一で、これが tok/s の天井を直接決める。プロンプト処理（プリフィル）は計算律速。
- **MoE は Apple Silicon では RAM を節約しない**。トークン毎に一部エキスパートしか活性化しなくても**全エキスパート重みが常駐必須**（別 VRAM プールが無いので NVIDIA のエキスパート CPU オフロード手法は無効）。「8GB GPU で 120B」式の MoE オフロードは Apple Silicon に移植できない。
- **16GB で重みに使えるのは実用 ~11GB**（Metal の `recommendedMaxWorkingSetSize` が物理 RAM の ~67–75% にソフト制限）。`sudo sysctl iogpu.wired_limit_mb` で引き上げ可（ハード上限ではない）。9–10GB の重み + KV キャッシュ + OS で枠を超えればスワップする。
- **コンテナ不可**: macOS Docker は Metal パススルー非対応で、コンテナ内 MLX/Ollama は CPU 推論に落ちて 3–5x 遅い → **推論サーバはホスト実行**（→ `docker-local-llm-tradeoff` 参照）。

## ベンチ A/B の落とし穴

- **メモリ圧（スワップ）の交絡**: 重いモデルを 16GB で測ると、片方がスワップ中・もう片方が低スワップだと差が不当に出る。**疑わしい arm を低スワップ条件に揃えて再測定**し、速度差がランタイム本質か資源圧の副産物かを切り分ける（今回 Ollama を低スワップで再測定し、~7 tok/s で不変 → MLX の優位は本質と確定した）。
- **公平性の統一**: thinking ON/OFF・temperature・max_tokens・量子化ビットを両 arm で揃える。特に thinking 不一致はトークン数と速度を別物にする。ウォームアップ1回を捨て、3回の中央値を取る（初回はモデルロードと Metal シェーダコンパイルが混ざる）。
- **量子化は arm 間でバイト等価でない**（GGUF Q4_K_M ≠ MLX 4bit）。速度比較は妥当だが、品質差はランタイムでなく量子化方式の差が混ざる。品質を測るなら量子化を近づける（混合精度の OptiQ 系など）。
- **合成入力で予算を測らない**（窓に載るか判定するとき）。「典型的な入力」を自作して測ると、**入力の言語・長さの思い込みがそのまま結論になる**。2026-08-01 に実測: 日本語の投稿を仮定して「窓超過・OS 更新必須」と結論したが、実際のエージェント出力は **ASCII 比 0.9962（実質英語）**で、本番分布（`reports/comment-reports/` n=2,366）で測り直すと**逆に余裕で収まった**。同じ字数でも日本語は英語の約 2.5 倍のトークンになるので、言語の思い込みだけで 2 倍以上ずれる。**入出力の分布は保存済みの本番ログから取る**（→ skill `read-only-instruments`）。
- **部品の合計で system prompt を測らない**。実際に組み立てたプロンプトを測る。CA では `configure_skill_selection()` を呼び忘れると `selected_skills_block()` が**黙って空文字を返し**、skill 抜きのプロンプトを測ってしまう（実測で一度踏んだ。system 2,900 tok を 437 tok と誤読した）。憲法ファイル名の取り違えでも同じことが起きる。**組み立て結果の文字数が想定と桁で合うかを先に見る。**
- **推定器と実トークナイザを混ぜない**。上振れ推定器（CJK を 2 tok/char で数える類）は実トークナイザ比 **1.73–1.95x 過大**（実測）。窓の余裕を推定器で測ると、**窓の 7 割を使わずに捨てる**ことがある。候補ランタイムが `token_count()` 相当を持つなら、判定はそちらで行う。
- **代表プロンプト 1 本で「載る」と言わない — プロンプトを縮める機構がある場合、その発火率まで含めた本番分布で測る**。プロンプトサイズが上流の削減機構（skill/文書の選別、RAG の再ランク、プロンプト圧縮）に依存するなら、**測るべきは削減後のサイズではなく「削減が効いた回の割合 × そのサイズ」**。削減が失敗したときのフォールバックはたいてい「全部入れる」なので、**外れ値ではなく多数派が最悪ケースになりうる**。2026-08-01 に実測: 組み立て済みプロンプト 1 本は 2,900 tok で 4,096 に収まったが、本番 30 日ぶん（n=8,772）で見ると削減が効いたのは **9.3%** だけで、残り 90.7% は 16,990 tok のフル注入に戻っていた。結果、窓に収まる割合は **6.7%**。1 本の測定は嘘ではなく、**母集団の 1 割を正しく記述していた**。窓が固定のランタイムではこの差が採否をそのまま反転させる。
- **固定窓ランタイムでは「呼べる」と「まともな長さの答えが返る」を別の数として出す**。入力が収まることと、出力の予算が残ることは別条件。前者だけ見ると「動く」と読め、実際には毎回途中で切れる。判定は 2 本立てる（呼び出しが成立する下限 / 完成した答えが入る下限）。
- **レイテンシを「小さいプロンプトでの 1 回」で見積もらない**。オンデバイス小型モデルは prefill が支配的なので、identity だけ（134 tok）の呼び出しが 1.15s でも、実運用の system prompt（2,910 tok）では **p50 28.7s** になった（同一機・同一モデル、25 倍）。**比較相手も統制する** — 既存ランタイムの「論文値」でなく、**同じ期間の本番テレメトリの分布**と比べる。ADR の統制 A/B（n=4）では現行 16.5s だったが、本番 30 日（n=1,213）では p50 37.2s で、どちらと比べるかで結論が逆転した。
- **プロンプトを縮めると遅くなることがある（プレフィックスキャッシュ）**。同一機・同一モデルで、**毎回バイト同一の巨大 system prompt（p50 28.3s）より、呼び出しごとに中身が変わる縮小版（p50 56.1s）の方が 2 倍遅い**という層別が出た（n=604/609）。固定プレフィックスは prefill を再利用できるが、動的に選別したプレフィックスは毎回コールドになるため。**トークン削減は壁時計の削減と同義ではない** — 削減機構を入れるなら、トークンでなく所要時間でも測る。
- **品質は「実際に本番が出した成果物」を対照にすると無料で測れる**。新ランタイムを本番プロンプトで走らせ、**過去に実際に公開した出力**と盲検で比べる（順序ランダム化・別モデル系列の judge）。対照 arm の生成コストがゼロになり、しかも合成ベースラインでなく本物と比べられる。実例: 実投稿 30 件で現行が 27/30 件 1 位（平均順位 1.17 対 2.39）。

## When to Use

- Apple Silicon でローカル LLM ランタイム（Ollama / mlx-lm / Foundation Models / LM Studio）を選ぶ・併用するとき
- **「この repo / エージェントを X で動かせるか」を判定するとき**（速度でなく実現可否の問い。Foundation Models・Apple Intelligence・`apple-fm-sdk`・iOS / macOS が話に出たら必ず）
- **候補ランタイムの context 窓に自分のプロンプトが収まるか測るとき**（測り方の罠は「ベンチ A/B の落とし穴」節）
- mlx_lm.server を既存 Ollama 構成に足すとき（埋め込み・構造化出力で詰まる前に）
- 「16GB でもっと速く / 大きいモデルを」を NVIDIA 前提（VRAM の壁・MoE オフロード）で考えてしまったとき
- ローカル LLM のベンチ A/B が腑に落ちないとき（メモリ圧の交絡・合成入力での測定ミスを疑う）
