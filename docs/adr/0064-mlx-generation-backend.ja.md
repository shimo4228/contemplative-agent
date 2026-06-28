# ADR-0064: Apple Silicon で生成を host-local の mlx_lm.server 経由にする

## Status

superseded-by ADR-0070（MLX backend を main から退役し sibling repo へ移設）

## Date

2026-06-27

## Context

エージェントのデフォルト LLM トランスポートは [`core/llm.py`](../../src/contemplative_agent/core/llm.py)
の組み込み Ollama HTTP 経路で、ローカルの Ollama デーモン（テキストは `/api/generate`、埋め込みは
`/api/embed`）に接続する。メンテナの主ホスト（M1 Mac・16GB ユニファイドメモリ）では、本番モデル
`qwen3.5:9b`（Q4_K_M、ディスク 6.6GB、KV キャッシュ込みで常駐 ~8.6GB）が日常的にスワップを誘発し、
デコードも遅い。

同一ホスト・同一重みでの統制ベンチ（[evidence](../evidence/adr-0064/benchmark-ollama-vs-mlx.md)、
thinking off・temperature 0・256 トークン上限・3 回中央値）で 2 ランタイムを比較した:

| 指標 | Ollama (Metal / GGUF Q4_K_M) | mlx_lm.server (MLX 4bit) |
|---|---|---|
| 生成速度 | 6.8–7.0 tok/s | 12.1–12.7 tok/s（**約 1.8x**） |
| 常駐 / ピークメモリ | 8.6 GB | 5.2 GB（**−3.4 GB**） |

速度差は交絡（スワップ圧）でなく本質的と確認: Ollama を低スワップ下で再測定しても ~7 tok/s。
Apple の MLX ランタイムは Apple Silicon で速い経路であり、その小さいフットプリントが 16GB 機の
スワップ圧を緩和する。

採用の形は 3 つの制約で決まる:

1. **mlx_lm.server は生成専用**。OpenAI `/v1/chat/completions` 形式を出すが、**埋め込み endpoint なし**、
   **トークンレベルの構造化出力モードなし**（Ollama `format=` / OpenAI `response_format` 相当なし）。
   埋め込み（`nomic-embed-text`）は Ollama に残す必要がある。
2. **Apple Silicon の Docker では Metal パススルー不可**のため、[ADR-0006](./0006-docker-network-isolation.md)
   のネットワーク分離 compose スタック内ではなく**ホスト上**で動かす。
3. **`format=` を使う呼び出しは正確に 1 箇所**（`distill._distill_one`、`{"patterns": [...]}`）で、
   `_parse_refined_patterns` に既存の JSON→bullet フォールバックがある。

エージェントは既に `LLMBackend` Protocol と `configure(backend=...)` 注入口を持つ（仮想のクラウド
バックエンド用に追加済み）ため、~12 箇所の呼び出し元を触らずに生成だけ再ルートできる。

## Decision

**生成のみ**を host-local の mlx_lm.server 経由にし、埋め込みは Ollama に残す **opt-in の MLX 生成
バックエンド**を追加する。

1. **`core/mlx_backend.py` — `MlxLmBackend(LLMBackend)`**: `{MLX_BASE_URL}/v1/chat/completions` に
   POST、OpenAI レスポンスを `BackendResult` にマップ、`chat_template_kwargs={"enable_thinking": false}`
   で per-request に thinking off（Ollama `think:false` 既定と一致）、`format` スキーマはプロンプト
   指示にレンダリング（mlx_lm.server に native 構造化出力なし。distill の JSON→bullet フォールバックが
   ドリフトを吸収）。

2. **`LLMBackend` Protocol を拡張**（`core/llm.py`）: `generate()` は keyword `temperature` を取り、
   戻り値を `Optional[str]` から `Optional[BackendResult]`（`text` + `finish_reason` + `eval_count`）に
   変更。これにより注入経路が per-call の temperature（決定論的 verification は 0.0、外向き生成は 1.3）
   を尊重でき、`drop_truncated` の fail-closed ゲート（audit M2）を backend ではなく**呼び出し元**が
   `finish_reason` から適用し、意図的 drop を circuit success として計上する Ollama 経路と同じ会計になる。

3. **`cli.py` 合成ルートで env ゲート**: `LLM_BACKEND=mlx` のとき `MlxLmBackend(MLX_BASE_URL, MLX_MODEL)`
   を注入。未設定や他の値はデフォルトの Ollama 生成経路を維持するので、env 1 つを外せば戻る。

4. **埋め込みは不変**: `OLLAMA_BASE_URL`（デフォルト `:11434`）が `nomic-embed-text` を提供し続ける。
   MLX host は共有 `validate_trusted_url()` ガード経由で既存の `OLLAMA_TRUSTED_HOSTS` SSRF allowlist を
   再利用する（`localhost:8080` は設定なしで通る。ポートは host 検証の対象外）。

目標トポロジは 2 つの host-local LLM サービス: mlx_lm.server（生成、`:8080`、~5.2GB）と Ollama
（埋め込み、`:11434`、`nomic-embed-text` ~0.3GB）。`scripts/serve-mlx.sh` がサーバを起動する。
`mlx-lm` は `uvx` / `uv tool` で実行し、**プロジェクト依存にはしない** — エージェントは HTTP を叩く
だけなので `pyproject.toml` は `requests` + `numpy` のまま。

## Alternatives Considered

### `OLLAMA_BASE_URL` を mlx_lm.server に向け直す（設定のみ）

却下。生成と埋め込みが `_get_ollama_url()` を共有するため、base URL を向け直すと埋め込みリクエストも
mlx_lm.server に行き、`/api/embed` がないので distill/retrieval が壊れる。バックエンド注入なら埋め込み
URL は不変。

### `format` 拘束 distill を Ollama に残す（自動フォールバック）

検討の上で見送り。バックエンドが唯一の `format=` 箇所だけ Ollama に戻せばトークンレベルの JSON 拘束を
保てる。初手で却下した理由: distill-on-Ollama こそ 16GB で最もスワップする 8.6GB 経路であり、distill を
mlx に載せることがメンテナの原初の痛みを解消する。`{"patterns": [...]}` という単純スキーマ + 既存 bullet
フォールバックでプロンプトレベルの JSON は十分。採用は pattern 生成数の比較でゲートする（Consequences
参照）。yield が大きく落ちれば env でコード変更なしに distill を Ollama に戻せる。

### mlx をコンテナで動かす

却下。Apple Silicon の Docker は Metal パススルーがなく、コンテナ内 MLX ランタイムは遅い CPU 推論に
落ちる。mlx_lm.server はホストで動かす。[ADR-0006](./0006-docker-network-isolation.md) の分離モデルは
Ollama サービスに引き続き適用される。

### デフォルト化する（opt-in にしない）

却下。MLX 経路はホスト・プラットフォーム固有（Apple Silicon、別管理のサーバプロセス）。デフォルト
Ollama / opt-in MLX のゲートにすれば zero-config 経路がどこでも動き、切替も自明に reversible で、
[ADR-0007](./0007-security-boundary-model.md) の reversibility 姿勢と整合する。

## Consequences

### Positive

- 同一モデルで、メンテナの M1/16GB ホストで生成 約 1.8x 速・メモリ 約 3.4GB 減 — 動機だったスワップ圧を
  直接緩和。
- 呼び出し元の変更ゼロ: ~12 の生成呼び出しが注入バックエンド経由で不変に動く。`temperature` と
  `drop_truncated` が両トランスポートで一律に効くようになった（従来、注入経路は temperature を黙って
  捨てていた）。
- 完全に reversible: `LLM_BACKEND` を外せば Ollama 生成に戻る。mlx_lm.server クラッシュは既存の circuit
  breaker を発火させ、運用者が戻せる。
- ついでにセキュリティガードを強化: `validate_trusted_url()` は非 HTTP スキームも拒否するようになり、
  両トランスポートで共有。Ollama 経路も `allow_redirects=False` を得て一貫した。

### Negative / Risks

- **2 サービスの運用**。ホストは mlx_lm.server（生成）と Ollama（埋め込み）の両方を上げ続ける必要がある。
  運用グルーは `scripts/serve-mlx.sh`（launchd plist は今後）。
- **MLX 経路にトークン拘束の構造化出力なし**。distill はプロンプト指示 + JSON→bullet フォールバックに
  依存。distill の採用は dry-run pattern 生成数の比較（同一 episode 窓で mlx vs Ollama）でゲートし、
  yield が後退すれば env で Ollama に戻す。
- **量子化はバイト等価でない**（GGUF Q4_K_M ≠ MLX 4bit）ため、出力品質が Ollama 基準と微妙に異なりうる。
  本 ADR の範囲外（速度・メモリのみ）。品質ドリフトが出たら `mlx-community/Qwen3.5-9B-OptiQ-4bit`
  （混合精度、Q4_K_M に近い）が後続候補。

### Verification

- 最高リスク経路を確認: verification チャレンジソルバ（temperature 0、`drop_truncated=True`、投稿を
  ゲートする）が MLX バックエンド経由で end-to-end に正答。
- 新規 21 の単体/統合テスト（`tests/test_mlx_backend.py`）、全スイート green、python-reviewer と
  security-reviewer 双方 PASS（CRITICAL/HIGH なし）。
- ライブ episode 窓での distill dry-run が MLX 上でスワップ thrashing なく完走（観測スワップは
  Ollama-distill 基準より低位に留まる）。pattern 生成数の比較が distill-on-MLX 維持の明示的な採用ゲート。
