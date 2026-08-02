# ADR-0068: コール単位の `think` フラグと、推論トレースのエピソードログへの保存

## Status

accepted (amended 2026-08-02)

**2026-08-02 追補**: 決定 2 と決定 3 は think の**要求**とトレース取得の fallback 順を記録したが、
要求したトレースが実際に届いたかは何も記録していなかった。トレースを要求して何も得られなかった
呼び出しが、`think: true` と書かれたテレメトリ行と `reasoning.md` の無いスナップショットを
理由なしで並べうる — [ADR-0075](./0075-observability-by-default.md) 決定 3 が禁じた silent fallback。
末尾の [追補: 取得結果を観測可能にする](#追補-2026-08-02--取得結果を観測可能にする) を参照。
決定 2 と決定 3 は**当初の決定時点**の記述として読むこと。追補は両者を拡張する。
取得順そのものは変更していない。

## Date

2026-06-28

## Context

LLM 生成経路は、どのバックエンドでも thinking を **off** にハードコードしていた:
Ollama のペイロードは `"think": False` を送り
（[`core/llm.py` (now `core/llm/`)](../../src/contemplative_agent/core/llm/) の `_post_ollama`）、
MLX バックエンドは `chat_template_kwargs={"enable_thinking": False}` を送っていた
（`core/mlx_backend.py` (retired to contemplative-agent-mlx, [ADR-0070](0070-retire-mlx-to-sibling-repo-and-remove-docker.md))）。
コール単位で推論トレースを有効化する手段はなく、仮にモデルがトレースを出力しても
`_sanitize_output` → `_strip_thinking` がそれを破棄し、`generate()` は公開テキストのみを
返していた。

変更を動機づけたのは 2 つのニーズである。第一に、来たる thinking モデルの **A/B 比較**
（Gemma 4 E4B の think-on 対 think-off 対 現行の think-off baseline）には、think を
コール単位で制御できること **かつ** think の状態を記録して 2 条件をテレメトリ上で区別できる
ことが要る。第二に、thinking が on のとき、その推論の **内容** は残す価値のある研究材料だが、
コール単位のテレメトリレコード（`logs/llm-calls-*.jsonl`）に入れてはならない。同レコードは
契約上メタデータのみである（[ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md):
"never the prompt body"）。untrusted なモデル出力をそのファイルに書き込むと、契約を破ると
同時に、分析セッションがテレメトリを読み戻す際の第二のプロンプトインジェクション経路を作って
しまう。

エピソードログは既に、エージェント生成コンテンツ（comment / reply / post）と
`internal_note`（[ADR-0045](./0045-pre-action-internal-note.md)）を、確立された untrusted
レジーム（直読み禁止、蒸留済み成果物を消費）の下で保存している。よってトレースの置き場としては
ここが適切である — 新規ではなく既存の成果物の再利用である。

## Decision

1. **コール単位の `think: bool = False` パラメータを追加する。** `generate` →
   `_generate_full` → `_generate_impl` → `_post_ollama` / `_generate_via_backend` を
   貫いて通し、`LLMBackend` Protocol の `generate()` の keyword-only グループにも追加する。
   `MlxLmBackend` は `chat_template_kwargs={"enable_thinking": think}` 経由でこれを尊重する。
   デフォルトの False が本番の振る舞い。本変更ではどの呼び出し箇所も有効化しない。

2. **テレメトリには `think` を真偽フラグとしてのみ記録する。** *(2026-08-02 拡張 — 追補を参照。
   このフラグは要求を記録する。結果は 2 つの出所フィールドが記録するようになった。
   メタデータのみの契約は不変 — トレース本文は依然として入らない。)* `tel` レコードは `"think"`
   フィールド（`model` / `temperature` と同様のメタデータ）を得る。トレースの *内容* はそこに
   一切書かれない。これは ADR-0065 のテレメトリ契約をフィールド 1 つ分だけ拡張し、分析側が
   think-on の行と think-off の行を区別できるようにする（A/B 等のため）。

3. **トレースを捕捉し、publish seam を通じて表に出す。** *(2026-08-02 拡張 — 追補を参照。
   取得順は不変。その各段が、どのチャネルを使ったか・なぜ次に落ちたかを記録するようになった。)* 新たな frozen な
   `GenerationOutput(text, thinking)` を、共有コア（`_generate_full`）と `generate_for_api`
   が返す。`generate()` は引き続き `Optional[str]` を返す（`.text` に射影する）ので、publish で
   ない 14 箇所の呼び出しは無傷である。トレースは Ollama 専用の `thinking` レスポンスフィールド
   （または `BackendResult.thinking` / インラインの `<think>` フォールバック）から読み、
   secret をスクラブ（`_scrub_secrets`、`_sanitize_output` から抽出）するが、`<think>` 除去も
   長さキャップもしない。保存するのであって公開しないからである。

4. **トレースをエピソードに保存し、レポートにレンダリングする。** `generate_comment` /
   `generate_reply` / `generate_cooperation_post` と `ContentManager.create_*` は
   `GenerationOutput` を返す。publish 経路（`feed_manager`、`reply_handler`、`post_pipeline`）は、
   `comment` / `reply` / `post` の `activity` エピソードに、`internal_note` の隣へ `thinking`
   フィールドを付加する。`report.py` はそれを `**Thinking:**` ブロックとしてレンダリングする
   （他の全フィールドと同様に URL を defang し、空のときは隠す）。

デフォルトの `think=False` の下ではトレースは None なので、呼び出し側がオプトインする
（A/B の結果次第に先送り）まで、エピソード・レポート・本番の振る舞いは変わらない。

## Alternatives Considered

### トレースの内容をテレメトリレコードに直接書き込む

却下: `logs/llm-calls-*.jsonl` の ADR-0065 メタデータのみ契約に違反し、テレメトリを第二の
untrusted コンテンツストア / インジェクション経路にしてしまう。真偽フラグはテレメトリに残し、
内容はエピソードログへ送る。

### 新たな `logs/llm-thinking-*.jsonl` 成果物を作る

single-responsibility としてはきれいだが、エピソードログが既に確立されたトラストレジームの下で
エージェント生成コンテンツを保存している状況で、新規ファイルと新規の untrusted-content
ライフサイクルを管理対象として増やす。エピソードログの再利用（著者の明示的な選好）が、より表面積の
小さい選択である。

### `generate()` 自体を `(text, thinking)` を返すよう変更する

却下: `Optional[str]` を消費する 14 箇所の内部呼び出しをすべて壊す。戻り値の型変更を publish
seam（`generate_for_api` と comment/reply/post ラッパー）に限定すれば、blast radius を
エピソードを記録する 4 経路に閉じ込められる。

## Consequences

### Positive

- thinking がコール単位で制御可能かつテレメトリで観測可能になり、区別可能なレコードを伴う
  think-on/off の A/B が可能になる。
- 推論トレースが、既存の untrusted レジームの下、新規成果物なしで、エピソードログと comment
  レポートに研究材料として保存される。
- テレメトリのメタデータのみ契約とトラスト境界の双方が保たれる（内容はテレメトリに入らない、
  トレースは永続化前に secret スクラブされる）。
- デフォルト off は、意図的なオプトインまで本番の振る舞い変更がゼロであることを意味する。

### Negative

- `think` は Protocol 契約の変更である: すべての `LLMBackend` 実装（sibling の
  `contemplative-agent-cloud` を含む）が、トレース捕捉を得るにはこの keyword を受理しなければ
  ならない。更新するまで、これを省くバックエンドは新 kwarg で例外を投げる（生成失敗として捕捉
  される）。in-repo のバックエンドと全テストダブルは更新済み。
- publish seam の戻り値の型が変わった（`Optional[str]` → `GenerationOutput`）ため、
  comment/reply/post ラッパー、`ContentManager`、3 箇所のエピソード記録呼び出し、およびそれらの
  テストの更新が必要だった。

### Neutral / Follow-ups

- まだどの呼び出し箇所も `think=True` を設定していない。comment 生成を think に配線すること
  （および thinking モデルを採用するという判断）は A/B の結果次第に先送り。初回の A/B run
  （gemma4:e4b think-on/off 対 qwen3.5:9b、2026-06-28）:
  [`docs/evidence/adr-0068/gemma-e4b-think-ab-20260628.md`](../evidence/adr-0068/gemma-e4b-think-ab-20260628.md)
  — codex ブラインドジャッジは gemma_think > gemma_nothink > qwen とランク付け。gemma の
  think-OFF はより速く高品質な swap 候補。think-ON の品質優位は 2.2× のレイテンシに対して小さい。
- sibling の `contemplative-agent-cloud` バックエンドは、cloud 経路でトレース捕捉を得るために
  `think` keyword を追加し `BackendResult.thinking` を埋めるべきである。**この修理の前半こそが
  2026-08-02 追補を急がせた理由である** — kwarg だけ受け取ってフィールドを埋めない backend は、
  9 つの think-ON 呼び出し箇所を一斉に degrade させる。

## 追補 (2026-08-02) — 取得結果を観測可能にする

決定 2 と決定 3 は要求と fallback 順を作り、記録したのは要求だけだった。`_finalize_ok` は
`BackendResult.thinking` → インライン `<think>` → `None` と解決していたが、その末尾の `None` は
どこにも書かれない — `tel["think"]` は `true` のまま、`outcome` は `ok` のままだった。
**2 つの出所フィールドと 3 語の理由コード語彙でこれを閉じる。取得順そのものは動かさない。**

**フラグは、問われていた問いとは別の問いに答えていた。** `think: true` はこの呼び出しが何を
**要求した**かの陳述である。下流の消費者はすべて — スナップショット manifest
（[ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md) 決定 5）、
`reasoning.md` の書き手（決定 4）、`llm-calls-*.jsonl` を読む分析者 — それを呼び出しが何を
**産出した**かの陳述として読んでいた。両者が一致するのは、全 backend が flag を honor する間だけである。

**実データでの測定。** 100 の snapshot run のうち 6 件が `"think": true` を宣言し、そのうち 1 件
（`skill-stocktake_20260710T114758325173Z`）に `reasoning.md` が無い。その run が think-ON 呼び出しを
1 度もしなかったのか、したが何も返らなかったのかは、ディスク上のどこからも復元できない。
6 分の 1 は稀なケースではなく、その 2 つを区別するのに必要な記録が存在していなかった。

**なぜ backend が実際に honor しなくなる前に着手するか。** 露出は 1 タスク先にある。
`contemplative-agent-cloud` は現在 Protocol 非適合で、**大きな音を立てて**失敗する
（`think` は必須 kwarg なので `TypeError` → `error_kind="backend_exception"`）。最小の修理は
kwarg を受け取ることであり、その時点で「`think=True` を受け取って `thinking=None` を返す backend」
になる。そして ADR-0069 決定 3 の 9 つの think-ON 呼び出し箇所が一斉に無言で degrade する。
その修理の後に記録を作るのは、それが検出したはずの障害の最中に記録を作ることになる。

**語彙と、意図的に外にあるもの。** 3 コード。`core/llm/backend.py` の ADR-0087 の対の隣に置く:

| コード | 意味 |
|---|---|
| `trace_absent` | どちらのチャネルも何も運ばなかった |
| `trace_blank` | チャネルは内容を運んだが、サニタイズ後に何も残らなかった |
| `trace_type` | 専用フィールドが `str` でなかった |

`trace_blank` を `trace_absent` から分けるのは意図的である。前者はモデルの挙動、後者はフィールドを
一度も埋めない backend であり、修理の内容が違う。**`think=False` はこの語彙に入れない** —
ADR-0087 が counter の不在について述べた規律（「不在は既定であって、何かからの fallback ではない」）
と同じであり、ここでは逆向きに load-bearing である。呼び出し単位の**要求**があるからこそ非提供が
fallback になるので、要求しなかった呼び出しには記録すべきものが無い。`MAX_THINKING_CHARS` の上限
（宣言済みの契約）も、success tail に到達しない行（`outcome` が既に答えている）も同様に外。

決定的に重要な点として、どのコードも backend の**性質**については何も述べない。すべて 1 回の
呼び出しで観測された事実の陳述である。これが、将来 capability marker が入っても
（`T-BACKEND-CONTRACT-KIT`）語彙が有効であり続ける理由である — marker はトレースを産出すると
主張したことのない backend について `trace_absent` を**引き算する**だけで、コードも消費者も変わらない。

**verdict だけでなく source を記録する**（ADR-0087 決定 8）。dense な `thinking_source` は
**どの**チャネルがトレースを届けたかを記録する — `field` / `inline` / `absent` — ガードが走らな
かったときは `None`。理由の言い換えではない: 型の誤ったフィールドの後にインラインブロックで拾えた
場合、`thinking_source="inline"` **かつ** `thinking_fallback_reason="trace_type"` になる。この行が、
テキスト埋め込みトレースへ静かに fail over している backend と、正常に動いている backend とを分ける。

**同じ 3 行で塞いだ第 2 の欠陥。** `data.get("thinking")` は型検査なしで `_sanitize_thinking` に
届いていた（4 行上の `eval_count` には `isinstance(..., int)` ガードがある）。非 `str` は
`_scrub_secrets` の内部で `AttributeError` を投げる — しかも `outcome="ok"` を刻む行の**後**なので、
テレメトリは成功を主張し呼び出し側は例外を受ける。型ガードは値が最初に到達する位置に置き、
ログには型名のみを出して値は決して出さない: その値は**トレースそのもの**、すなわち untrusted な
モデル出力でありうるうえ、そのストリームは `log_anomaly_sweep.py` に読まれて週次分析プロンプトに
渡る（[ADR-0083](./0083-episode-logs-enter-the-weekly-prompt-as-hashes-only.md)。2026-08-01 の
`agent-launchd.log` 汚染はこの側路から来た）。

**空判定をどこで行うか、そしてそれが見た目の場所ではない理由。** クロスモデルレビュー
（codex、2026-08-02）が、最初の実装で空白のみの専用フィールドが使えるインラインブロックを覆い隠すことを
検出した: フィールドは**真**なのでチャネル選択に勝ち、fallback が飛ばされ、サニタイザは、テキストのすぐ
そこにあるトレースに対して `trace_blank` を報告していた。追補前のコードも同じ挙動だった
（`reasoning or _extract_inline_thinking(text)` — Python では `"   "` は真）ので退行ではない。
修正に値するのは、追補がそれについての**主張**を追加するからであり、誤った理由コードは理由なしより悪い。
空判定は、チャネルが選ばれた後ではなく、各チャネルを読む場所で行うようになった。空白のフィールドは
不在のフィールドと同じく次へ落ち、それでも `trace_blank` を記録する — それが `field` → `inline` の
格下げを説明する。`trace_type` の場合と同じ形である。`think_blank_inline` で pin。

同じレビューが、警告文が **run** のスナップショットに `reasoning.md` が無いと主張していることも指摘した。
1 つの run は複数の think-ON 呼び出しを行う（rules-distill 2、stocktake 4）ので、1 つのトレース欠落は
ファイル欠落を意味しない — 観測性の経路の内側から誤った診断を配ることになる。警告は自分の呼び出しについて
だけ述べるようになった。run がどの成果物を得たかは `_write_reasoning` が言うことである。

**採点はせず、記録のみ。** トレース欠落は `outcome` を `ok` / `truncated_kept` のままにし、
circuit breaker に触れない。生成は成功しており、欠けているのは研究用の成果物である。これを採点すると
非 thinking backend が breaker を開いて健全な生成を抑止しうる — counter fault（ADR-0087 決定 7）と
予算超過スキップを breaker から外しているのと同じ理由である。

**同じ沈黙の CLI 側。** `_write_reasoning` は 2 つの状況に対して early return が 1 つしかなかった。
「そのコマンドは think-ON 呼び出しをしなかった」（`reason=no_think_calls`、INFO — fault ではなく
判断。マージ対象の無い `skill-stocktake`）と「呼び出しは走り、全トレースが空だった」
（`reason=all_traces_empty`、WARNING）を分ける。これらはローカル定数であって core のコードでは**ない**:
この層は空文字しか見えず `trace_absent` と `trace_blank` を区別できないので、core のコードを再利用すると
この層が支持できる以上の主張を付けることになる。`llm-calls-*.jsonl` へのポインタが join である。

**意図的に触らなかったもの:**

- **スナップショット manifest。** ADR-0069 決定 5 は、そこの `think` を run の**入力**生成設定と
  定義しており、LLM 呼び出しの前に書かれる。これを「トレースが取得できたか」の意味にすると出力側の
  事実を入力の記録に折り込むことになり、その決定を覆す。しかも得るものが無い — テレメトリ行が既に
  その事実を持ち、`audit.jsonl`（`snapshot_path` と `run_id` の両方を持つ）経由で snapshot に join できる。
- **`LLMBackend` / capability marker。** `think` は既に必須 kwarg なので、ADR-0087 に別 Protocol
  `TokenCountingBackend` を強いた structural typing の圧力がここには存在しない。`thinking` の不在を
  契約上**有意味にする**のは Protocol 契約の判断（`T-BACKEND-CONTRACT-KIT` / `T-FINISHREASON-GATE`）で
  あり、**観測可能にする**のはそうではない — ADR-0087 の追補が `finish_reason` を切り出したときと同じ切り方。
- **中間の carrier**（`rules_distill._combine_traces` / `stocktake._generate_with_trace`）。各呼び出しは
  LLM 層で既に計上済みで、ここで警告すると 1 つの事実に対して N 個の警告が、集約が仕事の関数から出る。

**Fault 列**（ADR-0077）: `tests/test_llm_chaos.py` の `TestThinkingTraceFaultsF8`。注入は
`tests/chaos.py` の新設 `ThinkingChaosBackend`。共有 `FAULT_VOCABULARY` のメンバーではなく
**独自語彙を持つ別サブクラス**にした — 共有語彙は distill と insight の property テストが反復して
おり、新メンバーを足すと fault ごとの集計を導出し直す羽目になる。また基底 `ChaosBackend` が
`.thinking` を埋めないままであることで、既存スイートが no-trace 経路を踏み続ける。7 つの fault
（`think_ok` / `think_inline` / `think_missing` / `think_blank` / `think_type` / `think_type_inline` /
`think_blank_inline`）を期待される `thinking_source` と `thinking_fallback_reason` に対応づけ、
parametrize したテストが schedule だけから期待値を計算する。hypothesis は使わない: `count_tokens`（1 回の `generate()` 内で
2 呼び出しが相互作用）と違い、トレース取得には呼び出しをまたぐ状態が無いので、6 メンバーの
parametrize が網羅的である。`test_vocabulary_has_no_dead_codes` は、宣言された全理由が注入可能な
fault で到達可能であることを assert する — どの fault からも出せないコードは、ゲートのふりをした
ドキュメントである。両ガードとも一時的な違反注入で発火を実証した（理由コード撤去で 8 失敗、
型ガード撤去で 9 失敗）。

### 本追補の Consequences

#### Positive

- `think: true` の行が自己完結するようになった: 要求・チャネル・非提供の理由が 1 行に揃い、
  `audit.jsonl` 経由で snapshot に join できる。ADR-0075 の Verify 質問（「どのログが理由に答え、
  オフラインでリプレイできるか」）に grep で答えられる。
- `-cloud` の修理を、無言の degrade 窓を作らずに着地できるようになった。`think` を受け取って
  `thinking` を埋めない backend は、全 `reasoning.md` を静かに空にする代わりに毎行で自己申告する。
- `outcome="ok"` と自己申告していたクラッシュ経路を閉じた。
- `thinking_source` により、**インラインチャネルが実際にどれだけ効いているか**の初回の読みが得られる —
  決定 3 が fallback を作りながら、それが発火するのを見る手段を持たなかった問い。

#### Negative / 受け入れるリスク

- 全行に dense フィールドが 1 つ増える（`thinking_source`）。2 日でこのレコードに追加された 2 つ目の
  フィールドである。メタデータのみの契約は保たれているが、行はもう小さくない。そして
  `tests/test_llm_telemetry.py` の `EXPECTED_FIELDS` は完全一致ロックなので、今後の全フィールドが
  ここを通ることになる。
- トレース欠落の WARNING は run 単位でなく呼び出し単位で出る。honor しない backend の下では 9 つの
  think-ON 呼び出し箇所が 1 つの状態に対して 9 個の警告を出す。その状態は現在本番で到達不能であり、
  到達したときこそ大きな音を立てるべき事象なので許容と判断した — ただし常態化したら、正しい修理は
  ログを静かにすることではなく run 単位の要約にすることである。
- `field` / `inline` / `absent` の区別では、「この backend はそもそもトレースを出せない」と
  「この backend は出せるが今回モデルが出さなかった」を分離できない。この曖昧さは意図的に残した
  （*意図的に触らなかったもの* 参照）。`model` 列での集計という別経路で答える。
