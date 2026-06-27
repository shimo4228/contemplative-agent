# ADR-0067: 本番生成バックエンドを Ollama に固定する — 16GB Apple Silicon の無人連続運用では mlx_lm.server は不適

## Status

accepted — partially-supersedes ADR-0065（launchd 配線部分。served-model-id テレメトリ契約は存続）

## Date

2026-06-28

## Context

[ADR-0064](./0064-mlx-generation-backend.md) はオプトインの MLX 生成バックエンド
（`:8080` の `mlx_lm.server`、`LLM_BACKEND=mlx`）を追加した。メンテナの M1 / 16GB ホストで
Ollama 生成より約 1.8 倍速・約 3.4GB 軽いとベンチされた。続く
[ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md) はそのバックエンドを
本番の 2 つの launchd ジョブ — `agent.plist`（0/6/12/18 時のセッション）と
`distill.plist`（03:30）— に `scripts/run-with-mlx.sh` 経由のオンデマンドで配線し、あわせて
LLM テレメトリの `model` フィールドを `LLMBackend` Protocol 上の served-model-id 契約に一般化した。
[ADR-0066](./0066-backend-aware-context-budget-guard.md) は backend-aware な
context-budget guard（MLX の `context_window = 32768`）を追加した。

**2026-06-27（M1 / 16GB）の終日本番 A/B が decisive だった。** ADR-0065 によりテレメトリが
*実際の* served model id を記録するため、outcome 内訳は
`~/.config/moltbook/logs/llm-calls-2026-06-27.jsonl` から直接再計算できる:

| backend | calls | ok | circuit_open | error | truncated |
|---|---|---|---|---|---|
| MLX（`mlx-community/Qwen3.5-9B-4bit` / mlx_lm.server） | **21,224** | **107 (0.50%)** | 21,060 (99.2%) | 53 | 4 |
| Ollama（`qwen3.5:9b`）, 06-09..06-26 の 18 日 baseline | ~200–270 / 日 | **≈100%** | ~0 | ~0 | 稀 |

モデルは **load して動いた** — 実モデル id のコールが 21k 件記録されている。**故障は load 失敗
ではなく runtime 劣化**である。時間別プロファイルがその形を示す: 最初の ~81 コール（00:00–01:00
UTC）は 100% ok — サーバは load して動く — その後崩壊し、**09:00 UTC の 1 時間だけで 19,520 回
試行して ok は 2 件**、circuit-open + 反応的リトライのスピンに陥った。対照的に Ollama は同じ
ハーネス上、前後 18 日にわたり circuit breaker をほぼ一度も踏まない。

根本原因: **mlx_lm.server は OOM の graceful degradation を持たない。** Metal OOM はエラーを返さず
プロセスを abort するか生成を wedge させ（mlx-lm
[#854](https://github.com/ml-explore/mlx-lm/issues/854) /
[#883](https://github.com/ml-explore/mlx-lm/issues/883) クラス）、エージェントの circuit breaker を
trip させる。breaker が開くと反応的リトライ経路が空回りする。16GB ではこれを 2 つの機序が compound する:

- **非線形な prefill cliff。** `mlx-server.log` 上、同じ ~7.5k トークンの prompt が **load 直後は
  72 秒、その 11 分後には 58 分**（~75 倍）で prefill された — 同一プロセスで、変わったのはメモリ
  状況だけ。MLX の Metal 確保は wired / スワップ不可なので、メモリ圧縮下で graceful な page-out が
  できない（Ollama の mmap = file-backed / pageable な GGUF と対照的）。18:13 UTC には Metal OOM
  abort（prefill が 587/930 で停止）も観測。
- **prompt-cache churn。** ~7.6k の all-injected system prefix が `--prompt-cache-size 2` の下で
  reply / comment / score / internal_note の user prompt が回転するたびに evict され、ほとんどの
  生成がフルの cold prefill を払い、cliff をまともに浴びる。

上流 mlx-lm の障害モードを調べた独立サーベイ
（[evidence](../evidence/adr-0067/mlx-production-suitability-survey-2026-06.md)）も同じ結論に至る。
その caveat のうち 2 つは本環境には**当てはまらない**ため、本記録に凍結しないよう明示的に解消する:
(a)「`qwen3_5` はマルチモーダル VLM で mlx_lm.server に load できない」caveat は、実モデル id の
21k コールが反証する — テキストモデルは正常に load した。(b) truncation を MLX 固有の EOS-runaway と
する見方は、local の `verify_solve` A/B が反証する — MLX の truncation は n=5 のノイズで solver 設計の
性質であり MLX 固有ではない（[evidence](../evidence/adr-0067/a-b-telemetry-2026-06-27.md)）。よって
本 ADR は truncation ではなく **circuit-breaker カスケード**に立脚する。

## Decision

1. **本番生成バックエンドは Ollama（`qwen3.5:9b`）。** ADR-0065 の launchd 配線（`agent.plist` /
   `distill.plist` を `scripts/run-with-mlx.sh` 経由にする）を、直接 `contemplative-agent` を呼ぶ形に
   revert する（commit `b888840`、2026-06-28）。埋め込みは Ollama のまま無改変。

2. **ADR-0065 の served-model-id テレメトリ契約は存続させる。** これは backend 非依存であり、本決定の
   evidence を生んだ計器そのもの。ADR-0065 のうち supersede するのは launchd 配線部分のみ。

3. **MLX バックエンドのコードと全 opt-in 経路を温存する**（`LLM_BACKEND=mlx`、`/agent-run … mlx`、
   `scripts/serve-mlx.sh`）。何も削除しない。MLX は **対話 / 手動 / 短時間**の生成では引き続き有効な
   選択肢である — オペレータが観測でき、セッションが劣化 cliff に届くほど長く走らない場面。

4. **不適の主張を scope する** — *16GB Apple Silicon + `Qwen3.5-9B-4bit` + 無人連続運用*に限定する。
   「mlx_lm.server は本番に不適」とは意図的に一般化しない: decisive evidence は config 固有であり、
   ここで危険にしている上流 issue は OPEN だがモデル / ホスト / 負荷依存である。

## Alternatives Considered

### 緩和して MLX を本番配線のまま維持する

文書化済みの緩和策を当てる — 明示的な `stop` トークン、`--prompt-cache-bytes`、system prefix を
保持するための `--prompt-cache-size` 引き上げ、MLX wired limit の引き下げ、サーバを迂回する
in-process `mlx_lm.generate`、8-bit への移行。現時点では却下。いずれも対症療法であり、load-bearing
な根（graceful OOM 欠如 → プロセス死 → circuit-breaker スピン）は上流未修正 —
[#615](https://github.com/ml-explore/mlx-lm/issues/615)（kv-size フラグなし）、
[#854](https://github.com/ml-explore/mlx-lm/issues/854) /
[#883](https://github.com/ml-explore/mlx-lm/issues/883)（OOM abort）、いずれも **OPEN**。8-bit は
重みがおよそ倍で 16GB に headroom なし、bf16（~18GB）は載らない。Ollama が既に clean に走る以上、
無人本番のリスクに見合わない。

### 主張を broad に述べる（「mlx_lm.server は本番に不適」）

却下。evidence は config 固有で、over-broad な主張は brittle — 対話用途・大容量 RAM ホスト・標準的な
GQA テキストモデルで容易に falsify される — であり、contingent な結果をルールに reify する。これは
Emptiness 公理（目的を軽く保ち、新文脈で改訂する）に反する。

### MLX バックエンドのコードを削除する

却下。opt-in MLX は reversible で手動 / 対話作業に実利がある。ADR-0064 のベンチ（~1.8 倍速・~3.4GB
軽）は短時間セッションでは今も成立する。コード温存はコストゼロで、後述の再評価経路を残す。

### 16GB の headroom に収まる小型 MLX モデルに切り替える

scope 外。モデル downgrade は出力品質を、graceful OOM ハンドリングを依然欠くバックエンドと引き換えに
する。local-model-swap 実験は既に品質面で却下済み。

### cloud 生成バックエンド（`contemplative-agent-cloud`）

security-by-absence を研究目的でのみ緩める、独立した opt-in 経路。本番 default ではなく本 ADR の
scope 外。

## Consequences

### Positive

- 本番は Ollama で安定（revert 済み）。revert 後の baseline は circuit breaker をほぼ踏まない
  ≈100%-ok パターンを示す。
- 決定は reversible かつ self-instrumented: 存続させたテレメトリ契約が、将来の MLX 再試行を同じ
  metric で再計測する。
- MLX は opt-in のまま。オペレータは対話実行で `LLM_BACKEND=mlx` / `/agent-run … mlx` を使え、
  ADR-0064 の速度 / メモリ優位を安全な場面で利用できる。

### Negative / Neutral

- ADR-0065 の launchd 配線部分は superseded。served-model-id テレメトリ契約は存続。ADR-0064
  （opt-in backend）と ADR-0066（context guard）は無改変で、opt-in MLX 利用には今も適用される。
- ADR-0065 の「運用モデルに LLM サーバが 2 つ」という複雑さは本番では解消（Ollama のみ稼働）。
  opt-in MLX セッションのときだけ戻る。

### Reversal thresholds

*無人*本番に MLX を再検討するのは、以下が**すべて**満たされたときのみ:

1. `mlx_lm.server` に bounded KV / `--max-kv-size` が入る（mlx-lm
   [#615](https://github.com/ml-explore/mlx-lm/issues/615) /
   [#884](https://github.com/ml-explore/mlx-lm/issues/884) マージ）。固定 context のジョブが
   cache を OOM まで成長させられなくなる。
2. OOM-abort issue（[#854](https://github.com/ml-explore/mlx-lm/issues/854) /
   [#883](https://github.com/ml-explore/mlx-lm/issues/883)）が解決し、Metal OOM が HTTP 5xx を
   返してプロセスがカーネルパニックなく存続する。
3. ターゲットホストでの 24 時間 / 数万コールの run で、error と truncation の率が Ollama 同等
   （≈0）に収まる。

3 つすべてが満たされるまで、Ollama を本番生成バックエンドに据え置く。

## References

- [ADR-0064](./0064-mlx-generation-backend.md) — opt-in MLX backend。無改変、opt-in / 対話用途では今も有効
- [ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md) — 本 ADR により partially-superseded（launchd 配線は revert、テレメトリ契約は存続）
- [ADR-0066](./0066-backend-aware-context-budget-guard.md) — backend-aware context guard。無改変
- [ADR-0007](./0007-security-boundary-model.md) — reversibility 姿勢（env 1 つ / plist 1 つを戻せば安全な default に復帰）
- Evidence: [docs/evidence/adr-0067/](../evidence/adr-0067/) — A/B telemetry, prefill degradation, 上流障害モードサーベイ
- mlx-lm 上流 issue（2026-06 時点で OPEN）: [#615](https://github.com/ml-explore/mlx-lm/issues/615), [#854](https://github.com/ml-explore/mlx-lm/issues/854), [#883](https://github.com/ml-explore/mlx-lm/issues/883)
