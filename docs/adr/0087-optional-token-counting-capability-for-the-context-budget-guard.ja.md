# ADR-0087: コンテキスト予算ガードに任意の `count_tokens` capability を足す

## Status

accepted — [ADR-0066](./0066-backend-aware-context-budget-guard.ja.md) を拡張する

本 ADR は ADR-0066 が作ったガードに測定源を足す。**ADR-0066 のどの決定も変えない** —
`_estimate_tokens` は §5 が硬めた定数のまま、`MIN_CLAMPED_NUM_PREDICT` は値のまま、
`context_window` は `LLMBackend` の member のまま。ADR-0066 は書かれたとおり `accepted` で残る。
その先例に従わない唯一の点 — 新しい member を `LLMBackend` に置かないこと — は決定 1 と
最初の Alternative で論じてあり、前提にはしていない。

## Date

2026-08-01

## Context

[ADR-0066](./0066-backend-aware-context-budget-guard.ja.md) は C2 コンテキスト予算 pre-flight を
backend-aware にし、その §5 で `_estimate_tokens` を両文字クラスで真の上限値に硬めた —
ASCII は約 3 chars/token、非 ASCII / CJK は **2 tokens/char**。当時の問題設定に対してはこれが
正しい判断だった。ガードの仕事は窓を超える入力を拒むことだけで、**under-count** こそが CJK 主体の
プロンプトを Ollama の front-truncation や MLX の KV キャッシュ超過へ滑り込ませる故障であり、
そして実トークナイザは手元に無かった（この repo は `requests` + `numpy` しか積んでいない）。

**新しいのは実測である。** 2026-08-01、推定器が初めて実トークナイザ — macOS 26.6 の
`apple-fm-sdk` `SystemLanguageModel.token_count` — と突き合わされた。対象はこのエージェント自身の
コーパス:

| 入力 | `_estimate_tokens` | 実測 | 倍率 |
|---|---|---|---|
| `identity.md` | 232 | 134 | 1.73x |
| `constitution/` | 867 | 453 | 1.91x |
| `rules/` | 516 | 264 | 1.95x |
| `skills/`（37 件） | 31,009 | 17,958 | 1.73x |
| patterns 10 件 | 479 | 263 | 1.82x |

この過大評価は欠陥ではない。文書化された契約が設計どおり働いた結果であり、CJK ルールから直接
説明がつく — このエージェントの価値層は日本語主体であり、実測の約 1.1 に対して 2 tokens/char で
数えていることが倍率の出どころである。

**この表の根拠は保全されておらず、それはこの記録の欠陥である。** プローブは再起動で消える
scratchpad で走ったため、リンクすべき `docs/evidence/adr-0087/` は無く、再実行できるスクリプトも
無い — 「証拠が要る ADR は `docs/evidence/adr-XXXX/` に置く」というこの repo 自身の規約に反する。
入力の両側は独立に動く（コーパスは毎週育ち、Apple のランタイムは OS と一緒に更新される）ので、
読者はこの比率を再現できないどころか、どのファイルを対象に測ったのかも特定できない。この表は
**桁の見当が正しい一度きりの観測**として扱うこと。再現可能な測定ではない。以下の決定が実際に
依拠しているのは、表よりも弱く、しかし長持ちする 2 点である — 推定器が CJK を構造的に過大評価
すること、そしてその誤差の大きさは backend のトークナイザの性質であって、この repo が知りうる
ものではないこと。数値を取り直す人は、プローブを `docs/evidence/adr-0087/` に書き出してここから
リンクすること。

**その安全マージンのコストは窓の大きさに反比例して効いてくる。** ガードは、入力が
`MIN_CLAMPED_NUM_PREDICT`（2048）未満の出力予算しか残さないとき呼び出しごと skip する。4,096
トークン窓の backend では、実効入力天井が 2,048 *推定* トークン ≒ **1,140 実トークン、窓の 28%**
になる。残りを食っているものは独立に 2 つあり、混同してはいけない:

| | 4,096 窓での入力天井 | 窓に対する割合 |
|---|---|---|
| 推定器（現状） | 約 1,140 実トークン | 28% |
| 実測（本 ADR） | 4096 − 2048 − 64 = **1,984** 実トークン | 48% |
| 出力の床も 0 だった場合 | 4,096 | 100% |

つまり推定器の過大評価が食っているのは約 **21 ポイント**で、残り約 50% は
`MIN_CLAMPED_NUM_PREDICT` の出力予約 — 本 ADR が意図的に動かさない別の変数である（決定 9）。
実測が取り戻すのは前者だけで、後者ではない。使える入力はおおむね **2 倍**になる。やる価値は
あるが、素の差が示唆するほどではない。32,768 の Ollama 路でも同じ倍率でハードウェアの要求より
早く `num_predict` を clamp しているが、それで抑止された呼び出しは観測されていない。

**なぜ組み込みの Ollama 路をそのまま直せないか。** 独立した理由が 2 つあり、いずれも仮定でなく
確認した:

1. Ollama はトークナイズ endpoint を公開していない。稼働中の 0.30.11 で `/api/tokenize` と
   `/api/detokenize` はどちらも 404 を返す。上流の
   [ollama#12030](https://github.com/ollama/ollama/pull/12030) は 2025-08-22 に出て未マージのまま
   （最終更新 2026-06-04）、要望 issue [ollama#12031](https://github.com/ollama/ollama/issues/12031)
   も open。依存追加の可否以前に、**呼べる API が無い**。
2. `/api/generate` は実入力トークン数 `prompt_eval_count` を返すが、それは呼び出しの **後**
   でしかない。pre-flight は参照できない。

Phase 0 の外部調査で、成熟したライブラリが同種の非一様性をどう表現しているかを調べた。LangChain の
`BaseLanguageModel.get_num_tokens(text) -> int` は近似の既定実装を持ち、model 固有の subclass が
override する — 本 ADR が必要とする優先順位そのもので、継承で表現されている。LlamaIndex は
capability を LLM object 上の **nullable field** として持つ
（`OpenAILike.tokenizer: Union[Tokenizer, str, None] = None`、"If left as None, then this disables
inference of max_tokens" と文書化）— capability が無ければ依存する推論だけが degrade し、他は
影響を受けない。ADR-0066 が `context_window` を借りたのと同じ object である。LiteLLM の
`token_counter` は model 固有トークナイザが無いとき tiktoken へ fallback し、fallback 前提が業界
標準であることを裏づけるが、その fallback 先が実トークナイザである点だけはここでは模倣できない。

## Decision

1. **`count_tokens(text: str) -> int` を別の任意 capability Protocol として足す。**
   `TokenCountingBackend(LLMBackend, Protocol)` であり、`LLMBackend` の member にはしない。
   Protocol は structural なので、`LLMBackend` に宣言した member は既定の body の有無に関わらず
   全 implementer に要求される。そこに置けば、sibling の `contemplative-agent-cloud` /
   `contemplative-agent-mlx` は、どちらも honor できない capability のせいで型検査上 非適合に
   なる。分離すれば、数えられる backend には pyright が検証する型付きの的ができ、数えられない
   backend は従来どおり有効な `LLMBackend` のままでいられる。これは ADR-0066 が `LLMBackend` に
   置いた `context_window` より一段ゆるい。`context_window` は現に「両 repo を更新する義務」を
   生んでいる（ADR-0066 の Consequences / Negative）。トークナイザは 1 行の property ではないので、
   その義務はここでは不適切である。

2. **capability の実行時解決は structural に行う**:
   `counter = getattr(_backend, "count_tokens", None)` を取り、`callable(counter)` のときだけ使う。
   ADR-0066 の `getattr(..., None)` sentinel idiom を踏襲し、callable 検査を足した — 属性は
   メソッドでなくても存在しうるため。runtime-checkable Protocol への `isinstance` は使わない
   （callable でない属性を通してしまう）。

3. **backend の計数を優先するが、盲信はしない。** `_measure_input_tokens` は frozen な
   `_InputTokenMeasurement`（`system` / `prompt` / `source` / `fallback_reason`）を返す。返り値は
   次のとき棄却され `_estimate_tokens` に落ちる: plain な `int` でない（`bool` は `int` の
   subclass なので明示的に除外する — 壊れた backend が `True` を返しうる）、負、あるいは中身の
   あるテキストに対する `0`。この非対称は意図的である。over-count は予算を無駄にするだけだが、
   under-count はガードが防ぐために存在する front-truncation / KV 超過へ、窓を超えた入力を送り
   込む。ゆえに不自然な計数は「計数なし」として扱う。

4. **shape だけでなく magnitude も束縛する**（`MAX_CHARS_PER_TOKEN = 50`）。shape の検証だけでは、
   well-typed で正で、しかし桁違いに小さい計数が通ってしまう — 50,000 文字のプロンプトに `5` を
   返す backend は決定 3 の検査をすべて通過し、そのうえでガードに「入力はほぼ無料だ」と告げる。
   現実的な出どころは悪意ではなく、開発途上の sibling backend にある**較正のずれた
   トークナイザ**（単位違い・除数違い・桁のバグ）であり、それゆえにこのガードが黙って破られる
   最も起こりやすい経路である。束縛は推定器との比率ではなく**トークン化の密度**で表現する —
   実運用の語彙に 50 文字級のトークンは存在しないので、それより長い平均トークンを含意する計数は、
   トークンでない何かを報告している。推定器との比率は検討して却下した — 繰り返しの多いテキストの
   正当に効率的なトークン化を誤棄却し、fault でないものを fault としてテレメトリに溜めてしまう
   うえ、任意の入力に対して成り立つべき検査に、このコーパスで測った 0.51〜0.58 の帯を焼き込む
   ことになる。空白のみのテキストは対象外 — 過少報告されうる中身が無い。

5. **実測で数えたときは framing 分の余白を残す**（`BACKEND_FRAMING_RESERVE = 64`）。
   `count_tokens` が測るのは 2 つのテキストだが、backend はそれらを chat template へ描画し、
   その role separator や制御トークンは呼び出し側のどの計数にも見えない。`num_predict` を実測の
   残余ちょうどに clamp すると、入力 + 出力が `context_window` にぴったり張り付き、その framing
   のぶんが残らない。本 ADR が救おうとしている小窓 backend では、それだけで超過に転ぶ。この
   reserve は **backend 計数の経路にのみ**適用し、推定器の経路は算術を一字一句そのままにする —
   1.73〜1.95x の過大評価がすでに桁違いに大きな reserve だからである。Ollama 路の clamp 値が
   変わらないのもこれによる（決定 10）。

6. **両方を測り、後から検証し、採るか棄てるかは一緒に決める。** 実測した system プロンプトと
   推定した user プロンプトを混ぜた予算は、どちらの姿も表していない。両方の計数は常に試行される
   （途中で打ち切らない）ので、fault テストから見た呼び出し列も決定論的になる。両方が失敗した
   場合は system 側の理由を報告する — 最後に走った方ではなく、リプレイが予測できる安定した選択。

7. **計数の故障は circuit breaker に触らない。** 呼び出しを *測れなかった* ことは、呼び出しが
   失敗したことではない。これを failure に数えると、壊れたトークナイザが breaker を開かせて健全な
   生成まで抑止しうる — over-budget skip を breaker から外しているのと同じ論理である。

8. **判定だけでなく出所を記録する。** テレメトリに dense なフィールドを 2 本足す —
   `token_count_source`（`"backend"` / `"estimator"` / ガード未実行なら `None`）と
   `input_tokens`（ガードが実際に使った合計）。加えて sparse な `token_count_fallback_reason` を
   固定語彙（`counter_exception` / `counter_none` / `counter_type` / `counter_negative` /
   `counter_degenerate` / `counter_implausible`）から立てる。counter の**不在はこの語彙に入れない** — それは既定であって
   何かからの fallback ではなく、理由を立てれば本物の故障がノイズに埋もれる。出所が無ければ
   clamp 値はオフラインで読めない。このエージェントの入力では 2 つの測り方が最大 1.95x 食い違う
   ためである（ADR-0075）。

9. **`MIN_CLAMPED_NUM_PREDICT` には触らない。** clamp の床は別の未決の問い（入力を実測するように
   なった後も 2048 が正しい床か）の対象である。測定と床を 1 回の変更で動かすと、どちらが効いたか
   判別できなくなる — 実験衛生「パイプラインの変数は一度に一つ」
   （[ADR-0053](./0053-importance-encoding-time-significance.ja.md)、適用例は
   [ADR-0056](./0056-retire-importance-llm-scoring.ja.md)）。床はここでは値も意味も据え置く。

10. **Ollama 路は無改変。** 手を伸ばせる counter が無い（Context 参照）ので推定器に解決され、
   テレメトリはそれを明示的に述べる — 読者に推測させない。

fault column は同じ変更で出荷する（[ADR-0077](./0077-chaos-tdd-fault-injection.ja.md)）:
`tests/chaos.py` の `TokenCountingChaosBackend` が各故障モードをスケジュールで注入し、hypothesis
戦略が返り値の型を fuzz する。基底の `ChaosBackend` は意図的に capability を持たないままにし、
既存スイートが推定器の経路を検査し続けるようにしている。

## Alternatives Considered

### `context_window` と同様に `count_tokens` を `LLMBackend` 本体へ置く

一見対称で、「`context_window` の規律に揃える」と言われて最初に思いつく選択肢。型レベルの帰結を
理由に却下した — structural な適合が全 backend にトークナイザの供給を要求することになり、それが
できない sibling 2 つを含んでしまう。ADR-0066 が `context_window` でこの義務を受け入れたのは、
コンテキスト窓が backend が常に知っていて 1 行で宣言できる定数だからである。トークナイザは
そのどちらでもない。規律の実行時側 — `getattr` して不在を許容する — は完全に踏襲し、静的な要求
だけを落とす。

### Protocol member に既定の body を持たせて省略可能にする

Protocol の働きを誤解した案として却下。既定の body は明示的な subclass に対して member を
非抽象にするだけで、structural な適合は依然その member を要求する。`configure(backend=...)` で
注入される外部 backend は structural なので、これは案 1 とまったく同じように壊れる — 壊れない
ように見えるぶん、より悪い。

### 代わりに推定器を固定の係数で補正する（例: CJK を 1.1 tok/char に）

考えうる限り最も安い変更で、日本語入力で無駄になっている予算の大半を取り戻せる。却下した理由:
補正係数は model 固有であり（1.73〜1.95x の帯は gemma4 ではなく Apple のトークナイザに対する
実測）、任意の untrusted 入力ではなくこのエージェントの現在のコーパスで測られており、そして
**安全側の境界を標本に合わせて締める**ことこそ、ADR-0066 が塞いだ under-count 故障を開け直す
やり方である。自分のトークナイザを知っている backend が正しい権威であって、平均値はそうではない。
推定器は「それより良いものが何も無い場合」のための保守的な契約を保持する。

### 組み込み Ollama 路で `/api/tokenize` を呼ぶ

望ましくないからではなく、**利用できない**ため却下 — endpoint は 0.30.11 で 404 を返し、上流 PR は
未マージ（Context 参照）。切り捨てるのではなく、明示的な発火条件つきの follow-up として記録する。

### 何もしない — 推定器のみのガードを維持し、マージンを受け入れる

現状維持はそれ自体として筋が通っており、本 ADR が上回るべき相手である。1.73〜1.95x の過大評価は
今日の時点で観測可能なコストを生んでいない。Ollama 路は 32,768 で動いており、マージンは
`num_predict` を必要より早く clamp するが、それで抑止された本番呼び出しは一度も無い。現存する
backend はすべて大きな窓を持つ。無駄になっている 72% は、小窓 backend が出るまでは完全に仮想で
ある。対して本変更は現実の機構を足す — 2 つ目の Protocol、まだ存在しないシステムについて主張する
定数 2 つ、テレメトリ 2 フィールド、chaos backend。しかもコミット前のレビューは、この変更が
見た目より微妙であることを示した（ガードは名前の無い安全マージンに依存しており、実測への切り替えが
それを黙って取り去っていた）。

却下する。ただし「seam が先でなければならない」より狭い根拠による。厳密には seam と Apple
backend は 1 つの変更で同時に入れられる。この順序を強制するものは無い。順序が買っているのは、
**backend の実測が backend についての実測になる**ことである。`T-APPLE-FM-BACKEND` は Apple の窓を
**4,096** と実測し、推定器のままでは実効天井がその 28% になることを示したが、その数字は一部が
この repo の過大評価で一部が Apple の窓であり、そのタスクの内側からは切り分けられない。seam を
先に出せば、以降の読み値は帰属可能になる。これは実在する利得だが、控えめな利得である。

この却下が**主張していないこと**が 2 つある。現状に観測可能なコストがあるとは主張しない — 無い。
このマージンで抑止された本番呼び出しは存在しない。そして Apple のコメント生成が解除されるとも
主張しない: 出力の床が不変なので 4,096 での入力天井は 1,984 実トークン、対して実測した日本語
コメントプロンプトは約 4,202 である。この用途には床の問い（`T-NUMPREDICT-FLOOR`）か 8,192 の窓が
要り、どちらもここには無い。天秤の反対側に正直に載るのは、先送りが「ガードが名前の無いマージンに
依存していた」という**発見**も先送りすることであり、その発見は 1 回の読み直しではなくレビュア
2 人を要したという事実である。

### `BackendResult.prompt_tokens` で推定器を較正する

`prompt_tokens` / `prompt_eval_count` は実入力トークン数であり、すでに記録されている。しかし
呼び出しの後に届くので pre-flight には使えない。その用途は read-only の較正計器であり、これは
clamp 床の問いに属するため、ここでは意図的に作らない。ただし決定 6 が足す `input_tokens` は、
ガードの数値を `prompt_eval_count` と同じテレメトリ行に並べるので、その計器は後から既存の行を
読むだけの作業になる。

## Consequences

### Positive

- 実トークナイザを持つ backend は、実際に持っている窓を使えるようになる。4,096 トークン窓の
  backend では、実効入力天井が約 1,140 実トークン（窓の 28%）から「窓 − clamp 床」へ動く。
- 既存の外部 backend は無変更。何も実装しなければ従来の挙動がそのまま維持され、回帰テストが
  それを固定する（capability を持たない `ChaosBackend` は推定器の判定に到達しなければならず、
  callable でない `count_tokens` 属性は無視されなければならない）。
- ガードは弱くならない。棄却経路はすべて保守的な推定器へ落ちるので、壊れた counter は天井を
  無効化するのではなく従来の挙動へ degrade する — counter が毎回 raise する場合も含め、故障系統
  ごとに assert している。
- テレメトリが「この clamp はどちらの測り方で出たか」にオフラインで答え、`input_tokens` が
  `prompt_eval_count` と同じ行に並ぶ。

### Negative

- 同じ量に対する測定経路が 2 つ存在し、最大 1.95x 食い違う。行をまたいで `input_tokens` を
  比較する読み手は `token_count_source` を必ず併読しなければならない。フィールドを dense に
  したのはまさにこれを飛ばせなくするためだが、分析側の負担が増えるのは事実である。
- backend のトークナイザが、ガードされる全呼び出しのクリティカルパスに乗る。遅い `count_tokens`
  は毎回の生成に latency を足すが、本変更はそれを一切束縛していない — capability は安価
  （in-process）と仮定している。`SystemLanguageModel.token_count` については真だが、HTTP 越しの
  counter では成り立たない。
- `TokenCountingBackend` は同じ object を覆う 2 つ目の Protocol である。将来 capability を足す
  人には 3 つ目の前例ができたことになり、1 メソッド capability Protocol が乱立すれば、
  ADR-0066 が前提していた単一インターフェースより悪くなる。
- 決定 4 と 5 が持ち込む 2 つの数値は、このシステムの**実測ではなく他システムについての判断**で
  ある。`MAX_CHARS_PER_TOKEN = 50` は実運用のトークナイザ語彙が何を含むかについての主張であり、
  `BACKEND_FRAMING_RESERVE = 64` は chat template のオーバーヘッドについての主張である。どちらも
  現実的な値から十分離して置いてあるので多少外れても無害で、外れ方は従来の挙動側に倒れる。だが
  どちらも、実際に影響を受ける backend に対して測ってはいない — その backend がまだ存在しない
  からである。

### Provenance

決定 4 と 5 は承認された plan には無く、コミット前のレビュー回で入った。独立した 2 人のレビュアが
別方向から同じ構造的な穴に到達した。cross-model レビュア（Codex）は framing のオーバーヘッドを
指摘した — `system` と `prompt` を別々に足すと `generate()` がその周りに付けるものが漏れ、しかも
ガードは残余ちょうどに clamp する。security レビュアは magnitude を指摘した — shape の検証は
「shape が妥当な」計数をすべて受け入れるので、50,000 文字に対する `5` が信用される。両者は同じ
根に行き着く: 過大評価する推定から実測へ切り替えたことで、ガードが名指ししないまま依存していた
安全マージンが黙って消えていた。それが load-bearing だったことは、消えて初めて見えた。

### Neutral / Follow-ups

- **Ollama の実計数**（上流待ち）: `ollama#12030` がマージされ稼働版に載れば、同じ seam が
  ガード本体を変えずに受け入れる。ただし生成ごとに HTTP 往復が 1 回増えるので、採用は endpoint の
  存在ではなく無人スケジュール上の latency 実測を待つべきである。
- **clamp 床**（`MIN_CLAMPED_NUM_PREDICT`）は未決のまま、ただし入力は良くなった: 行が
  `input_tokens` を `prompt_eval_count` の隣に持つようになれば、推定器の実世界での比率を
  一度きりのコーパス標本ではなく本番テレメトリから読める。
- **`core/insight_novelty.py`** は依然 `_estimate_tokens` で judge chunk を packing している。
  意図的に放置する: ガードが緩むということは packer が pre-flight より **きつい** 側に来ると
  いうことであり、それは packer 自身の契約が明言している安全な方向である（"packing tighter than
  the preflight is safe"）。packer を追随させるのは別の変更。
