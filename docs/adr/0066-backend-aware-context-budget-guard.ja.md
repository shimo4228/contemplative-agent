# ADR-0066: `LLMBackend.context_window` 契約による backend-aware なコンテキスト予算ガード

## Status

accepted

## Date

2026-06-27

## Context

MLX バックエンド修正セッション（コミット `ebc227e` / `30f7e39` / `b3d0599`）は sampler 欠落バグを
塞いだ。MLX payload が `temperature` だけ送って `top_p`/`top_k` を落としていたため、外向きの
`COMMENT_TEMPERATURE=1.3` で Qwen3.5-9B が退行的繰り返しループに陥り、EOS を出さず `num_predict`
上限まで暴走して投稿を妨げ、16GB ホストを swap に追い込んでいた。修正では
[`core/llm.py`](../../src/contemplative_agent/core/llm.py) に `SAMPLING_TOP_P`/`SAMPLING_TOP_K` を
単一の出所として切り出し、組み込みの Ollama 経路と注入された `MlxLmBackend` の双方が import する形に
した。

本 ADR は、その後続の**パラメータ共通化監査**を記録する。Ollama 経路（`_post_ollama`）と MLX
バックエンド（`MlxLmBackend.generate`）の間で、他に drift している生成パラメータが無いかを全パラメータ
について棚卸しした。コード変更を要した監査結果は `num_ctx` だけだった。

**穴 — injected-backend 経路がコンテキスト予算ガードをバイパスする。** `core/llm.py` はトークン予算の
プリフライト（audit C2）を持つ。推定 `system + prompt + num_predict` がコンテキストウィンドウを超える
場合、呼び出しを送らずに skip（`None` 返却）する。さもないと Ollama が system プロンプトの value 層
（identity / axioms）を silent に front-truncate するためだ。だがガードは backend dispatch の**後ろ**に
あった。`_generate_impl` は `if _backend is not None: return _generate_via_backend(...)` を実行し、ガード
には `_backend is None`（Ollama）経路でしか到達しなかった。注入された backend（MLX、および sibling の
`contemplative-agent-cloud`）は一切ガードされていなかった。

MLX にとってこれは理論上ではなく実害のある穴である。`mlx_lm.server` は context / kv-size フラグを
**持たず**（Apple `ml-explore/mlx-lm` issue #615 は open）、ウィンドウ超過プロンプトを front-truncate
**しない** — ホストが swap / OOM するまで KV キャッシュを膨張させる。Qwen3.5-9B の native ウィンドウは
262144（`Qwen/Qwen3.5-9B` の `config.json`）だが、16GB の M1（重み約 5GB、KV キャッシュは
`--prompt-cache-size 2` で抑制）における実効上限は、モデルの訓練ウィンドウではなく**メモリ律速で
おおよそ 32k トークン**である。したがってウィンドウ超過時の挙動こそ、MLX 作業が防ごうとした swap 事件
そのものだ。

**Phase 0 外部調査**（`/search-first` → scout）で、成熟ライブラリが「backend 能力非統一」をどう扱うかを
調べた。LiteLLM の `drop_params` + `get_supported_openai_params` + `model_prices_and_context_window.json`
registry（`get_max_tokens`）、および LlamaIndex のオブジェクト単位 `LLMMetadata.context_window` property
である。前のセッションでは、`GenerationParams` DTO（`temperature`/`top_p`/`top_k`/`num_predict`/`format`）
を `LLMBackend.generate()` Protocol に通して「sampling 方針を全 backend で共有する」案に暫定合意していた。
だが監査と調査により、これは誤った抽象だと判明した。`top_p=0.95`/`top_k=20` は Qwen3.5 固有のチューニング
値であり、universal Protocol は cloud backend も実装する。すると cloud に Qwen の `top_k` が渡ってしまう
（OpenAI は `top_k` を一切サポートしない）。sampler 方針は *model-identity* の関心事であって、
*provider-capability* の関心事ではない。

## Decision

1. **`LLMBackend` Protocol に read-only の `context_window: int` を追加する。**
   [ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md) の `model` property と並ぶ
   形だ。`MlxLmBackend` は `context_window = 32768` を宣言する — モデルの 262k native ウィンドウではなく、
   16GB ホストでのメモリ律速の値 — を dataclass フィールドとして（値フィールドが Protocol property を
   満たすのは `model` と同じ形）。cloud backend は自プロバイダの実際の上限を報告する。

2. **予算ガードを backend-aware にし、dispatch の前へ移す。** `_generate_impl` は今や
   `ctx_window = getattr(_backend, "context_window", None) if _backend is not None else NUM_CTX` を計算し、
   プリフライトを先に実行する。ウィンドウ超過の推定は、HTTP リクエストの前に、*どの* backend でも呼び出しを
   skip する（`outcome="budget_exceeded"`）。property を省略する backend は `None` にフォールバックして
   非ガードとなり、従来どおり委譲する。よって未更新の外部 backend も動き続ける（graceful degrade）。
   `getattr` は falsy なデフォルトではなく `None` sentinel を使うので、判定は曖昧でない。

3. **sampler 方針（`top_p`/`top_k`）を Protocol パラメータではなく共有モジュール定数のまま保つ。**
   監査により、`SAMPLING_TOP_P`/`SAMPLING_TOP_K` — Qwen を出す 2 つのローカル backend が import する —
   が正しい seam だと確認された。同じモデルを出す箇所だけで共有される model-local な sampling であり、
   cloud backend には決して押し付けられない（`generate()` のパラメータでないため渡らない）。
   `GenerationParams`-through-Protocol 案は明示的に却下する。

4. **capability-window パターンを借用し、LiteLLM は採用しない。** Phase 0 の Verdict は Build だった。
   3 つの backend は全て OpenAI 互換 HTTP を話すため、LiteLLM の主価値（プロバイダ形式変換）はここでは
   冗長。その context-window registry にローカルモデルのエントリは無く（各々 `register_model` の手動登録が
   必要 = 同じ dict を手で書くだけ）、~28MB / 12 core 依存のフットプリントは、数行に還元できる capability
   には不釣り合いだ。LlamaIndex 流の「ウィンドウを backend オブジェクトに co-locate する」を精神的に
   そのまま借用する。

監査の完全な parity 結果（以下はコード変更なし）: `temperature` は全 backend に per-call で届く（parity OK）;
`num_predict` は MLX で `max_tokens` に写る（parity OK）; `format` は意図的差分（Ollama native vs MLX
プロンプト注入、[ADR-0064](./0064-mlx-generation-backend.md)）; think は両者で off だが機構が違う
（`think:False` vs `enable_thinking:False`、parity OK）。

5. **`_estimate_tokens` を両文字クラスで真の上限へハードニングする。** ガードが今や MLX 経路にとって
   load-bearing なので、その tokenizer-free 推定は under-count してはならない。非 ASCII / CJK は今や
   2 tokens/char で数える（Qwen3.5 の実コストは ~1.5-2）。従来は 1 で数えており CJK を 33-50% 過小評価して
   いた — CJK 主体のプロンプト（エージェントは untrusted な外部コンテンツを読み、それは日本語 / 中国語で
   ありうる）がガードをすり抜け、まさに防ぐべき front-truncation / KV OOM に落ちるに十分だった。ASCII は
   ~3 chars/token のまま。これは skip ガードにとって安全な（過大評価の）方向であり、関数を「conservative
   upper bound」という文書化された契約と整合させる。`MlxLmBackend` は併せて非正の `context_window` を
   construction で弾く（ゼロウィンドウは全呼び出しを skip する silent な生成 blackout になる）。既存の
   fail-fast な URL 検証と同じ要領だ。

## Alternatives Considered

### `GenerationParams` DTO（`top_p`/`top_k` 込み）を `LLMBackend.generate()` に通す

前セッションの方向。却下: Qwen 固有の sampler 値を cloud backend に押し付け（OpenAI に `top_k` は無い）、
cloud backend の `generate()` signature を変え、model-identity の関心事を universal interface と混同する。
急性の `top_p`/`top_k` drift は定数共有（`30f7e39`）で既に解消済みであり、2 つのローカル backend 間での
再発防止に Protocol 変更は不要。むしろ Protocol 変更は cloud に対し新たで意味的に誤った結合を持ち込む。

### LiteLLM を multi-backend 抽象として採用する

却下: 形式変換が冗長（全 backend が既に OpenAI 形式か独自 adapter を持つ）、context-window registry に
ローカルモデルのエントリが無い（どのみち手動 `register_model`）、そして数個の dict と関数で済む需要に対し
不釣り合いな依存フットプリント（~28MB、`tiktoken`/`tokenizers`/`openai`/`pydantic`/…）。

### backend × model 単位の静的 context-window registry テーブル

`(backend, model) → window` をマップするモジュールレベルのテーブルを backend オブジェクトと別に持つ案。
却下: ウィンドウを backend オブジェクト（自身のホスト制約を唯一知る主体）に co-locate する方を選ぶ。
既存の `model` property および LlamaIndex の `LLMMetadata.context_window` パターンと整合する。

### `mlx_lm.server` 側でウィンドウを設定する

不可能なので却下: `mlx_lm.server` は context / kv-size の起動フラグを公開しない（issue #615;
`--max-tokens` は生成長の上限でありコンテキストではない）。client 側のプリフライトが唯一のレバー。

### MLX 経路を非ガードのまま放置する（現状維持）

却下: ウィンドウ超過プロンプトは 16GB ホストが swap / OOM するまで MLX の KV キャッシュを膨張させる —
MLX 作業が防ごうとした失敗そのもの。injected-backend を除外していたのは、仮想の cloud backend しか
存在しなかった頃の意図的な「ウィンドウ不明」判断であり、in-repo の MLX backend がウィンドウを既知にし、
穴を具体化した。

## Consequences

### Positive

- MLX backend（およびウィンドウを宣言する任意の backend）が予算ガードされる。ウィンドウ超過プロンプトは
  HTTP 呼び出しの前に skip され、KV キャッシュ OOM / swap を防ぐ。
- `context_window` は `LLMBackend` Protocol で型強制される。`model` が served-model-id を明示したのと
  同じ要領で、将来の backend は実際の serving 上限を宣言する。
- sampler 方針は model-local に留まる。cloud backend は Qwen 固有の `top_k`/`top_p` を決して渡されない。
- 新規依存はゼロ。capability-window パターンは 28MB の依存ではなく、LiteLLM / LlamaIndex 調査から借りた
  数行である。
- 完全に可逆: backend は env ゲート（`LLM_BACKEND`）であり、property を省略する backend に対してガードは
  従来挙動に degrade する。

### Negative

- `context_window` は Protocol の契約変更であり、全 `LLMBackend` 実装が宣言する必要がある。in-repo の
  backend と全テストダブル（`FakeBackend`、テスト内 stub）は更新済み。sibling の
  `contemplative-agent-cloud` backend はガードを得るために 1 行の property を追加する必要がある。それまでは
  省略した backend が silent に非ガードになる — cloud のコンテキストウィンドウは大きいので許容範囲だが、
  「両 repo を更新する」実務上の義務であることは事実。
- MLX のウィンドウ値（32768）はホストメモリのヒューリスティックであって測定された hard limit ではない。
  より大容量 RAM のホストならより大きくしても安全であり、この値はまだ利用可能メモリから自動導出されない。

### Neutral / Follow-ups

- sibling の `contemplative-agent-cloud` backend は `context_window`（自プロバイダのコンテキスト上限を返す）
  を追加してガードを得るべき。follow-up として記録、ここでは未実施。
- 同じハンドオフの Task 2 — 両 backend に共通で fail-closed な `verify_solve` の ~13% truncation — は
  parity とは無関係で deferred のまま。
