# ADR-0032: Stance — Contemplative Agent はランタイムエージェントである (撤回 2026-04-27)

## Status

**withdrawn (2026-04-27)** — 同日内に articulate および撤回。

## 撤回理由

本 ADR の中核フレーミング — 「ランタイムエージェント」を 4 つのホストカテゴリ (コーディングエージェント、オーケストレーター、汎用ホスト、GUI エージェント) と並ぶ第 5 のカテゴリとして立て、本プロジェクトをそのカテゴリの artifact として位置づける — は、本プロジェクトが [ADR-0002](0002-paper-faithful-ccai.ja.md) で参照している contemplative axioms (Laukkonen et al. 2025, Appendix C) と居心地の悪い tension を抱える。

具体的に 3 点が気になった:

**1. categories の固定化。** Emptiness 公理は概念的フレームワークを provisional に保ち、rigidly reify しないことを示唆する。Original 本文の Distinction table は「この区別はスペクトラムでも成熟度の段階でもない」と書き、5 カテゴリを本質的に異なる種として提示している。このフレーミングが促す方向は、Emptiness が促す lightness の方向と逆向きに見える。

**2. self / other の境界線。** Non-Duality 公理は self / other を rigid に分離しないことを示唆する。「本プロジェクト (ランタイムエージェント) は、コーディングエージェント、オーケストレーター、汎用ホスト、GUI エージェントとは別種の artifact」という主張は、その境界線を引くこと自体が主張の核になっている。

**3. adversarial な配置。** 「カテゴリ間違い」「ホストカテゴリの drift」を事故の構造的源泉として描く配置は、本プロジェクトの設計を corrective self、他のカテゴリ実装を failing other として暗黙に対比する構造を持つ。Original Consequences の Negative-4 でこのリスクは自覚されているが、framing 自体は変わらない。

これらは表層の言い回しではなく、本 ADR の load-bearing claim そのものに含まれている。tone を和らげても tension は解消しない。tension に気づいた以上、本 ADR を維持し続けると軋みが消えない感覚があった。

ここで取りうる選択肢は複数あった: tension を抱えたまま ADR を維持する、condition-based (カテゴリ identity ではなく特定の execution condition への応答として描く) に書き直す、撤回する。axioms 自体も provisional に保つ姿勢からは、tension を抱えた ADR を持ち続けることも理論的にはあり得た — 公理を絶対化して「違反だから消すしかない」と扱うのは、それ自体が axioms の reification (Emptiness が拒否するもの) になる。

ただ、tension が気になって lightly に手放したい、という個人的な感覚がまさり、撤回を選んだ。「公理に反するから撤回せざるを得ない」のではなく、「tension に気づいて、ADR を持ち続ける必要がそれほど強くない」と感じたという軽い motivation。業界に向けた「ランタイムエージェント」用語提唱は、必要なら記事やエッセイの場でやればいい。

書き直しではなく撤回とした理由はそれだけ。

## 教訓

これは本プロジェクト 2 件目の撤回 ADR となる ([ADR-0030](0030-withdraw-identity-blocks.ja.md) が ADR-0024 / ADR-0025 を supersede し「1 artifact 1 責務」を残したのが 1 件目)。

ハードな rule にしてしまうと公理を reify する向きに行きがちなので、観察として記録しておく程度にとどめる:

worldview ADR を書く時は、公理との関係 — 整合的か、tension があるか、無関係か — に注意を向けると有用な場合がある。tension があるとき、それを抱えたまま進むのも、書き直すのも、撤回するのも、どれもありうる。tension の存在を後から気づくことより、その時点で観察する方が判断が楽になる、という程度のこと。

ADR-0032 の場合は、tension の観察が merge 後に来た。それ自体は失敗ではない (axioms との整合は最初から義務ではないので)。merge 前に観察できていれば、より早く同じ判断、または別の判断 (tension 抱えたまま維持) に到達していたかもしれない、という事実だけ残しておく。

もう 1 つの観察: 本 ADR を撤回するこの行為自体が、Emptiness 公理が示唆する「hold objectives lightly, remaining open to revision」の例になっている。撤回の事実と original 本文の保存により、この例が見えやすくなる。これも体現と言い切らず、例として残しておく程度に。

## 撤回後に残るもの

- 30 本の先行 ADR (0001 〜 0031) は影響を受けない。それぞれ独自の正当化で立っており、本 ADR のフレーミングが妥当である必要は元々なかった。original 本文が「明示する」と主張した暗黙の「姿勢」は、それら ADR にとって最初から load-bearing ではなかった
- dev.to エッセイ ["Do Autonomous Agents Really Need an Orchestration Layer?"](https://dev.to/shimo4228/do-autonomous-agents-really-need-an-orchestration-layer-33j9) のホスト信頼フレーミング (「共生する設計とはホストを信頼する設計である」) は残るが、エッセイのコンテンツとしてであって、ADR で anchor された worldview claim としてではない
- 「ランタイムエージェント」という記述語は、「1 アクションごとの人間レビューなしで本番タスクを実行するエージェント」を指す便宜的な短縮表現としては引き続き使える。load-bearing な category boundary として扱わなければよい
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) との関係は本 ADR 以前と変わらない。AAP は attribution distribution に関する 8 judgments を保持し、本プロジェクトはそれが発見された実装文脈である。両側のいずれにも新しい ADR レベルの主張は不要
- コード変更は不要。実装の commit のいずれも本 ADR のフレーミングに依存していない。実装は本 ADR より数ヶ月先行する

## 撤回後に採用された framing

実装は **Python CLI agent** (`pip install contemplative-agent`、`contemplative-agent ...`) として ship される — execution-environment という意味での「runtime」ではない、と意図的に区別する。CLI form は usage を制約しない: standalone、coding agent (Claude Code, Cursor, Aider) の中、general-purpose host (OpenClaw, OpenCode, MCP host) の中、orchestrator に組み込まれて、Unix tooling で pipe、GUI agent から叩かれて、いずれも等しく welcome。「CLI agent」は executable-action のニュアンスを保ちつつ、撤回したラベルが背負っていた host-category boundary の荷物を引き継がない。industry も CLI 形態に収束しており (Claude Code, Gemini CLI, GitHub Copilot CLI, Aider)、CLI が現状最も摩擦の低い integration surface になっている。README / llms.txt が Contemplative Agent を「host-agnostic Python CLI agent」と記述しているのも、撤回した「runtime」ラベルをそこで再導入しないため。

## References (撤回後)

- [ADR-0002](0002-paper-faithful-ccai.ja.md) — contemplative axioms (Laukkonen et al. 2025, Appendix C) の正式採用。本 ADR のフレーミングが衝突した values 層
- [ADR-0030](0030-withdraw-identity-blocks.ja.md) — 本プロジェクト 1 件目の撤回 ADR、「1 artifact 1 責務」の教訓
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) — attribution distribution に関する 8 judgments。本撤回の影響を受けない

---

## Original Articulation (preserved as historical record)

以下の本文は、上記の撤回前に 2026-04-27 に accepted された original ADR である。撤回に至った推論を将来の読者が再構成できるよう、また Emptiness 公理 (新しい証拠を受けて改訂する) の体現自体が可視化されるよう、変更を加えずに保存する。original 本文を本セクションに入れ子にするため heading level を 1 段下げているが、それ以外のテキストは改変していない。

### Original Status

accepted — コードベース全体に既に実現されている設計姿勢の post-hoc articulation

`docs/adr/README.md` の定義による **worldview ADR**: 新しい問題を解決するのではなく、本プロジェクトの他の ADR が legible になる設計姿勢を名指す。本プロジェクトの禁止事項とゲートの多くは、この姿勢の下でだけコストに見合う。この姿勢の外では over-engineering になる。

### Original Date

2026-04-27

### Original Context

増えつつある AI エージェントの事故 (公開済みのランタイム脆弱性、プロンプトインジェクション escape、shell 実行の暴走、意図しない adapter を通じた連鎖書き込み) の少なからぬ部分が、1 つのカテゴリ間違いに遡れる: あるエージェントカテゴリの設計前提 (変更ごとの同期的な人間ゲート、許容される非決定性、プロンプトレベルの権限調整、ホスト提供のオーケストレーション) を、別のカテゴリ (1 アクションごとのレビューなしで本番タスクを実行) に持ち込んでいる。

コーディングエージェントはカテゴリとしては安全でない訳ではない。各 diff で開発者が loop に入っているからだ。汎用 LLM ホストもカテゴリとしては安全でない訳ではない。ユーザーがどのツールをインストールするかを決めるからだ。同じ capability surface を持ったまま、対応する human-in-the-loop なしでランタイムに出荷されたエージェントは安全上の問題になる — 各 diff をレビューする開発者もいなければ、ツールを curate するユーザーもいないからだ。

しかし、ホストカテゴリ自体が、実際に受けている監督に対して不釣り合いに広い capability surface を持って出荷されることが多い。コーディングエージェントは広範な shell アクセスと「すべての変更を accept」フローをデフォルトにしており、原理上は review 可能だが、その threat model が想定する粒度では review されないことが多い。汎用ホストはユーザーが任意ツールをインストールできるが、それはユーザーが実際にツールを curate するという前提に依存する — 多くはしない。オーケストレーターはノードごとに permission のつまみを露出するが、デフォルトから tune されることは稀。「自身の文脈では安全」という主張を額面通り受け取ると、その文脈自体が侵食されつつある事実が隠れる — 設計が依存している人間ゲートが、ランタイム文脈に置かれる以前から、すでに実態として失われつつある。

本プロジェクトの設計判断 — 網域ロックされたネットワークアクセス、shell 実行なし、任意のファイル走査なし、1 プロセス 1 外部アダプタ、コードに固定された 3 段階自律レベル、不変なエピソードログ、再生可能な pivot snapshot、行動を変更する書き込みのための承認ゲート — はランタイム文脈 (ホスト保証が設計上不在) への応答であると同時に、非ランタイム文脈におけるホスト保証の侵食 (実態として不在) への応答でもある。コーディングエージェント、オーケストレーター、汎用ホスト、GUI エージェントのいずれにおいても、これら禁止事項のどれも必要ない — **そのホストカテゴリが、自分の設計が前提とする監督パターンを実際に保持しているならば**。多くは保持していない。それが本 ADR が対処する事故の構造的源泉である。

これまでこの姿勢は **暗黙** だった。30 本の先行 ADR はそれぞれの設計選択をそれぞれの観点で正当化してきたが、その下にある「これはランタイムエージェントであり、それゆえ他のカテゴリがホストから受け取るもの — あるいは受け取るべきもの — を自分の内部で提供しなければならない」という前提が、それ自体として 1 つの姿勢として述べられたことはない。この暗黙性は 2 つの繰り返される混乱の源である:

1. **外部読者** がホストカテゴリのいずれかの慣習 (コーディングエージェントの開発者使い勝手、汎用ホストの capability の幅、オーケストレーターの framework 柔軟性) で Contemplative Agent を評価し、過度に restrictive と判断する — 制限が存在するのはまさにランタイム文脈ではホスト側の保証が不在で、非ランタイム文脈においても実態として不在になりつつあるからだ、ということを見ずに
2. **内部の議論** で新機能追加の是非を考えるとき、ランタイムエージェント直感 (「どんなゲートで、どんな audit trail で、どんな failure semantics で、どのホストもこれらを信頼できる形で提供してくれない前提で?」) ではなくホストカテゴリ直感 (「エージェントが〜できるべきだ」) がデフォルトになる

特に目立つ失敗モードは、コーディングエージェント型の ReAct ループ (広範な tool surface、prompt 駆動の推論、自律的な tool 呼び出し) をランタイム文脈に展開すること。ループの設計は反復ごとの開発者判断を前提とする。展開はその判断を取り除く。結果として生じるハイブリッドは、汎用ホストの広範な capability surface、コーディングエージェントの自律決定ループ、ランタイムエージェントの無人デプロイを継承する — それらカテゴリが設計の前提とした安全保証はどれ 1 つ継承せずに。各カテゴリの監督パターン (変更ごとの開発者レビュー、ツールごとの user curation、決定ごとの制度的アカウンタビリティ) は、他のカテゴリが補ってくれることを暗黙に前提することで bypass される — どれも実際には補わないのに。

本 ADR は姿勢を明示することで、両方の混乱を源から解消する。また、Contemplative Agent の初期 README iteration に存在し、その後の slim 化で失われたフレーミング — **ランタイムエージェントは他のエージェントカテゴリの中で動かせる存在であって、それらを置き換える存在ではない** — を復活させる。

### Original Decision

本実装は明示的に **ランタイムエージェント** であり、それらを包含するのではなく **他のエージェントカテゴリ (コーディングエージェント、オーケストレーター、汎用ホスト、GUI エージェント) の中で動く** よう設計されている。

**ランタイムエージェント** とは、1 アクションごとの人間レビューなしで本番タスクを実行するエージェント。例: 自律的な SNS 参加 (本プロジェクトの最初のアダプタ)、監視・アラートエージェント、スケジュールされた自動化ジョブ、自律トレーディングエージェント、臨床・法務ワークフローに組み込まれたエージェント。人間の関与は、promotion 境界での承認ゲート、事後レビュー用の例外ログ、エピソード単位の audit という形を取る — 各アクションへの同期的な人間承認ではない。

ランタイムエージェントは真空中で動かない。1 つ以上のホストカテゴリの **中で** 動く — 開発・改修するコーディングエージェント、組み立てるオーケストレーター、実行する汎用ホスト、操作する GUI エージェント。各ホストカテゴリは監督パターン (変更ごとの開発者レビュー、framework user 設計のグラフ、user curate のツールレジストリ、画面上の user 監督) で *定義* される。各ホスト *実装* は、その監督パターンを実際に実現していることもいないこともある。ランタイムエージェントの設計は、ホストが提供しないものを引き受けなければならない — そのホストカテゴリが元々設計上提供しないはずの保証も、現状のホスト実装が信頼できる形で保持しなくなった保証も両方。

この姿勢はどのホストカテゴリもカテゴリとして本質的に安全でないとは言わない — 各々が文脈として意味を持つ。しかし、それらカテゴリの現状実装が、実際に受けている人間監督に対して不釣り合いに広い capability surface を持って出荷されることが多く、この不釣り合いそれ自体が本 ADR が対処する事故の構造的源泉である、と観察する。AAP 型のアカウンタビリティ制約、security-by-absence、本プロジェクトの 30 本の先行 ADR で採用された禁止事項は、ホストが保証できないこと、そして次第に保証しなくなりつつあることへのランタイムエージェントの応答である。

### Original 区別 — ランタイムエージェントとホストカテゴリ

| 軸 | コーディングエージェント | オーケストレーター | 汎用ホスト | GUI エージェント | ランタイムエージェント |
|----|-------------------------|-------------------|-----------|----------------|----------------------|
| 用途 | 設計・実装の補助 | 複数エージェント / ステップを組み立て | 任意 LLM + ツールを動かす | UI 経由で他のソフトを操作 | 本番タスクの実行 |
| 人間の関与 (設計意図) | 変更ごとの開発者レビュー | framework user がグラフを設計 | user がツールを curate、出力を監視 | user が画面を見る | promotion での承認ゲート + 例外ログ |
| 人間の関与 (現状実態) | skim-review か「すべて accept」が多い | デフォルトから tune されない | ツール curation の audit が稀 | 長セッションで注意が drift | 設計意図と同じ |
| 非決定性 | 許容 (人間が修正) | 許容 (replan / retry) | 許容 (user が inspect) | 許容 (user が介入) | 隔離・監査必須 |
| 例外処理 | 「やってみる」が許される | retry / replan 分岐 | user-mediated | user-mediated | 停止 + ログが必須 |
| 権限境界 | プロンプトで調整 | ノードごとに設定 | ツールごとに設定 | OS レベル sandboxing | コード上の制約で固定 |
| 責任帰属 | 開発者 | framework user | host operator | operating user | 決裁ルート / 制度的 |
| 例 | Claude Code, Aider, Cursor | LangChain, LangGraph, AutoGen | OpenClaw, Open WebUI, MCP host | Computer Use, Operator | Contemplative Agent, 監視エージェント, 自律トレーディング |

この区別はスペクトラムでも成熟度の段階でもない。最初の 4 カテゴリはランタイムエージェントが中で動ける **ホスト** であり、5 つ目は実際に本番タスクを実行する層。ランタイムエージェントは「ハーデニングされたコーディングエージェント」でも「制約されたオーケストレーター」でもない — ホストが供給できない、または実態として供給しないものを内部で持たなければならないという理由で区別される、別種類の artifact である。

「人間の関与」の 2 行 — 設計意図 vs 現状実態 — は意図的に分離してある。Context section で議論した事故の多くは、両者のギャップに住む。ホストが設計意図を実現していると仮定するランタイムエージェントはそのギャップを継承する。自分の制約を自分で持つランタイムエージェントは継承しない。

### Original ランタイムエージェントを動かせるホストカテゴリ

ランタイムエージェントはホストを置き換えない。ホストの中で動く。各ホストカテゴリはランタイムエージェントがホストされる別の surface を提供する:

- **ホストとしてのコーディングエージェント** (Claude Code, Cursor, Aider) — ランタイムエージェントのコードを開発・改修・レビューする。ランタイムエージェントはコーディングエージェントを開発者向けの surface として扱うが、特定レベルの review が実際に行われるとは前提しない
- **ホストとしてのオーケストレーター** (LangChain, LangGraph, AutoGen) — ランタイムエージェントを他のエージェントやステップと組み合わせる。ランタイムエージェントは大きなグラフ内のノードとして現れるが、framework user が周囲ノードの permission を tune したとは前提しない
- **ホストとしての汎用ホスト** (OpenClaw, MCP host, Open WebUI) — LLM、ツールレジストリ、実行ループを提供する。ランタイムエージェントは多くのうちの 1 つのツールまたは capability だが、host operator がツールレジストリの残りを curate したとは前提しない
- **ホストとしての GUI エージェント** (Computer Use, Operator) — ランタイムエージェントをその surface (CLI、Web UI、ファイル編集) を通じて、他のソフトと同じように駆動するが、画面上の継続的監督は前提しない

このフレーミングの起源は Contemplative Agent の設計に関する初期 dev.to 記事:

> "A symbiotic design is a design that trusts its host."
> — *Do Autonomous Agents Really Need an Orchestration Layer?*

ランタイムエージェントは各ホストカテゴリにそのカテゴリが得意なことを期待し、ホストが提供できないものだけを自分で提供する。期待は *カテゴリ* に対するものであり、特定ホスト実装に対するものではない — だからランタイムエージェントの禁止事項は、各カテゴリ内のベストケースのホストではなく、最悪ケースのホストに合わせて書かれる。これは、「自律エージェント」が自分の開発環境、自分のオーケストレーション、自分のホストランタイム、自分の UI まで包含しようとする一般的なパターンの反転 — それこそが上記記事で批判される bloat。

カテゴリ関係としてのフレーミングは Contemplative Agent の初期 README iteration に存在し、その後の slim 化で失われた。本 ADR は、プロジェクトの他の ADR で採用された禁止事項の構造的前提として、それを復活させる。

### Original ランタイム文脈の失格要因 — ホストカテゴリが埋めないギャップ

以下の各エントリは、上記のホストカテゴリが一様には提供しない性質を名指す — 設計上 (カテゴリの監督パターンが元々それを enforce する意図がない) または drift により (現状実装が enforcement を弱めた) のいずれか。ランタイムエージェントはそれを自分で持たなければならず、列挙された ADR がプロジェクトの応答である。

1. **コードレベルで固定された capability surface**。コーディングエージェントは capability をプロンプトで調整、オーケストレーターはノードごとに設定、汎用ホストは user にツール curation を任せ、GUI エージェントは OS レベル sandboxing に依存する。いずれもランタイムでの不変な capability surface を保証せず、現状実装はしばしば原理上は review 可能だが実態として review されないほど広いデフォルトを出荷する。ランタイムエージェントは自分で持たなければならない: 網域ロックされたネットワークアクセス、shell 実行なし、任意ファイル走査なし — そのコードがコードベースに存在しない ([ADR-0007](0007-security-boundary-model.ja.md))
2. **audit 付きの停止-on-例外**。コーディングエージェントは「やってみる」を許容、オーケストレーターは retry や replan、ホストと GUI エージェントは user の介入に依存する。いずれも想定外の状態に対する決定論的な停止-and-ログを保証しない。ランタイムエージェントは自分で持たなければならない: 不変エピソードログ、行動を変更する書き込みに対する [Human Approval Gate](0012-human-approval-gate.ja.md)、黙って迂回するパスなし
3. **プロンプトで再交渉不可能な capability surface**。コーディングエージェントと汎用ホストは意図的にプロンプトレベルの capability 交渉を受け入れる。ランタイムエージェントはそれを拒否しなければならない: 3 段階自律 (`--approve` / `--guarded` / `--auto`) はプロセス起動時に固定され、いかなる入力によっても調整できない。1 プロセス 1 外部アダプタ、プロセス起動時に固定 ([ADR-0015](0015-one-external-adapter-per-agent.ja.md))
4. **決定粒度の audit trail**。ホストは audit 対応がまちまちで、よく計装されたものでもホストの粒度 (どのプロンプトが送られたか、どのツールが呼ばれたか) で audit する。エージェントの決定粒度 (どの view が発火したか、どの constitution 条項がどのヒューリスティックを上書きしたか) では audit しない。ランタイムエージェントは決定粒度の audit を自分で持たなければならない: 30 本の ADR、不変エピソードログ、推論時の全コンテキスト (views、constitution、prompts、skills、rules、identity、embeddings、thresholds) を捕捉する再生可能な [pivot snapshot](0020-pivot-snapshots-for-replayability.ja.md)
5. **trust が分離された層構造メモリ**。ホストは典型的には単一の会話または context バッファを露出する。ランタイムエージェントは層構造メモリを自分で持たなければならない: 生のエピソードログは不変、中間蒸留出力は再生成可能、正本 state (identity、constitution、skills、rules) は承認ゲートを通してのみ書かれる。view ベース分類 ([ADR-0019](0019-discrete-categories-to-embedding-views.ja.md)、[ADR-0031](0031-classification-as-query.ja.md)) が分類軸変更時に substrate を保存。identity は 1 種類の concern のみを持つ ([ADR-0030](0030-withdraw-identity-blocks.ja.md))

### Original AAP との関係

[Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) は、自律 AI エージェントに対する **普遍的なアカウンタビリティ分配原則** を articulate する — コーディングエージェント、オーケストレーター、汎用ホスト、GUI エージェント、ランタイムエージェントすべてにまたがって成立するように定式化された原則。Security Boundary Model、One External Adapter Per Agent、Human Approval Gate、prohibition-strength hierarchy、causal traceability コミットメントはどの 1 つのエージェントカテゴリにも特化していない。各カテゴリがそれらを別の形で適用する。

本 ADR は AAP の普遍原則の **ランタイム文脈における application** である。本プロジェクトで採用された禁止事項 (コード上の security-by-absence、プロセス起動時に固定された capability surface、不変エピソードログ、決定粒度 audit、3 段階自律) は、エージェントが他のホストカテゴリの中で動くランタイムエージェントである場合に AAP の普遍原則が要求するもの。コーディングエージェントは同じ AAP 原則を変更ごとの開発者アカウンタビリティと review 可能な diff として適用する。オーケストレーターは framework user 設計の permission グラフとして、汎用ホストは user curate のツールレジストリとして、GUI エージェントは画面上の監督と OS レベル sandboxing として適用する。原則は同じ、実現はエージェントのカテゴリで形作られる。

この関係により、Contemplative Agent は **AAP のランタイム文脈参考実装** となる。他のエージェントカテゴリの参考実装が存在する (または開発される) かもしれないが、それと並ぶ位置。依存は一方向: AAP が普遍原則を定義し、本 ADR が application context がランタイムである場合にそれが何を要求するかを示す。AAP は本 ADR によって狭められない。例示されるだけ。

> **Note (撤回後追記):** 本セクションのフレーミング — 「AAP は普遍的なアカウンタビリティ分配原則」— は撤回に至った不正確さの 1 つ。AAP の self-description は「8 judgments, not a fixed framework」であり、load-bearing な概念は accountability ではなく attribution、accountability はその下流の outcome。original 本文は historical fidelity のため変更せず保存する。修正された理解は上の「撤回理由」セクションと AAP repo 自体に記載されている。

### Original Alternatives Considered

- **ランタイム / ホストカテゴリ区別について中立を保つ**。却下: その中立性こそ本 ADR が対処する業界の混乱の原因。「tool-agnostic ランタイム姿勢」は形容矛盾 — ランタイム制約は *ランタイム文脈と、ランタイムエージェントが中で動くホストカテゴリの組み合わせ* から発生し、どちらも名指さずに制約だけ articulate しても制約は宙に浮く
- **本プロジェクトを "secure agent" や "hardened agent" としてフレーミングする**。却下: それらの語は汎用エージェントに追加された製品機能としてのセキュリティを示唆する。ここでの姿勢は構造的 — 危険な capability はコードベースに存在しない。「制限されている」「ハーデニングされている」のではない。absence をハーデニング機能として記述するのは設計を誤って描写し、存在しない設定スイッチをユーザーに期待させる
- **本プロジェクトを自己完結的 (オーケストレーション、ホスティング、UI を包含) としてフレーミングする**。却下: これは上記 dev.to 記事で批判されているまさにそのパターン。自己完結エージェントは escape しようとしている bloat を再生産する。既存ホストカテゴリの中で動くことこそ構造的代替
- **対比を binary (runtime vs coding のみ) としてフレーミングする**。却下: これはオーケストレーター、汎用ホスト、GUI エージェントを「coding ではない」に collapse させる — 不正確。各々が自身の監督パターンと、意図と実態の間の自身のギャップを持つ別個のホストカテゴリ。本 ADR の earlier draft はこの間違いを犯していた。本改訂はそれを訂正する
- **ホストカテゴリを「自身の文脈では安全」と無条件に扱う**。却下: これは earlier draft のフレーミングであり、寛容すぎた。各カテゴリは文脈として意味を持つが、現状実装はそれら文脈が想定する監督パターンから drift しており、その drift こそランタイムエージェントの禁止事項が存在する理由の一部。姿勢は読者に正直版を負う
- **OpenClaw / Claude Code / 特定製品への批判としてフレーミングする**。却下: これはカテゴリ drift についての正直な観察を伴うカテゴリ区別であって、製品批判ではない。各ホストカテゴリは監督パターンが実現されている限り自身の文脈をうまく serve しており、本 ADR が名指す失敗モードはカテゴリ drift とカテゴリを混ぜることから生じ、特定実装からは生じない

### Original Consequences

**Positive**:

- いずれのホストカテゴリの operator も本プロジェクトを読んで、姿勢が自分の用途に適用されるかを正しく判断できる — 自分の文脈で禁止事項を over-engineering と誤読せずに
- ランタイムエージェント operator は基底の前提を逆解析せずに、設計判断を直ちに自分に関連するものとして認識できる
- 30 本の先行 ADR の暗黙の前提が明示され引用可能になる
- 将来の ADR はランタイム制約をケースごとに再正当化する代わりに本姿勢を参照できる
- AAP との接続が構造的になる: AAP が普遍的アカウンタビリティ分配原則を保持し、本プロジェクトの禁止事項は application context がランタイムである場合にそれら原則が要求するもの。他のエージェントカテゴリ (コーディングエージェント、オーケストレーター、汎用ホスト、GUI エージェント) は同じ AAP 原則を別の形で適用する — それらカテゴリの参考実装は AAP 自体を再交渉せずに追加できる
- Contemplative Agent の初期 README iteration に存在したホストカテゴリフレーミングが復活し、付随的な言い回しではなく構造的選択として明示される
- 区別 table の「設計意図 vs 現状実態」2 行分割により、ホストカテゴリの drift が別途批判ドキュメントなしに見えるようになる

**Negative**:

- 「ランタイムエージェント」という語は既存業界用法の "runtime" (例: LangChain runtime、OpenAI runtime、エージェント実行ランタイム) と重複する。読者は当初、姿勢を特定の実行フレームワークと混同する可能性がある。Distinction table で両者を分離している
- 一度 articulate されると、本姿勢はホストカテゴリ設計には合うがランタイムエージェント設計には合わない capability 提案に対して引用される。これは意図された結果だが、将来の機能追加のハードルを上げる
- ホストカテゴリフレーミングは、ホストがそのカテゴリが提供するよう設計されているものを提供し続けることに依存する。「設計意図 vs 現状実態」の分割は drift を見えるようにするが、coupling を除去するわけではない — degrade したホストから継承するランタイムエージェントは degrade を継承する。ただし degrade に名前が付いた状態で
- 本姿勢は一度 articulate されると、capability surface が想定された監督パターンを overgrow したホストカテゴリ実装への暗黙批判としても機能する。変更ごとの review を強制しなくなったコーディングエージェント、広範なデフォルトツールで出荷される汎用ホスト、permissive なノード設定を持つオーケストレーターはすべて、自身が出自とした文脈からの drift として legible になる。これは特定製品への批判ではないが、姿勢を現状の出荷デフォルトに対して読めば緊張が露呈する

**Neutral**:

- 既存 ADR (0001 〜 0030) は内容に変更なし。本 ADR はそれらの上に、それらが集合的に表現する姿勢として位置する
- 本姿勢それ自体は本プロジェクトに新しい制約を課さない。それが名指す制約はすべてどこかで既に強制されており、本 ADR はそれら全制約がなぜ一緒に属するかの理由を articulate するだけ — それらは、ランタイムエージェントが中で動くホストカテゴリが提供しないために自分で持たなければならないものであり、ホストカテゴリが実際に届けてくる最悪ケースに合わせてサイズされる

### Original References

- [ADR-0007](0007-security-boundary-model.ja.md) — security-by-absence、不変な capability surface の構造的形態
- [ADR-0012](0012-human-approval-gate.ja.md) — promotion 境界での承認ゲート
- [ADR-0015](0015-one-external-adapter-per-agent.ja.md) — プロセスレベルでの固定された外部 surface
- [ADR-0019](0019-discrete-categories-to-embedding-views.ja.md) — 分類軸変更時の substrate 保存
- [ADR-0020](0020-pivot-snapshots-for-replayability.ja.md) — 決定粒度での再生可能な audit
- [ADR-0030](0030-withdraw-identity-blocks.ja.md) — 1 artifact 1 責務
- [ADR-0031](0031-classification-as-query.ja.md) — 自己改善メモリの substrate 原則
- [Do Autonomous Agents Really Need an Orchestration Layer?](https://dev.to/shimo4228/do-autonomous-agents-really-need-an-orchestration-layer-33j9) — ホスト信頼フレーミングの起点 (「共生する設計とはホストを信頼する設計である」)
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) — 自律 AI エージェントに対する普遍的アカウンタビリティ分配原則。本 ADR はそのランタイム文脈 application
