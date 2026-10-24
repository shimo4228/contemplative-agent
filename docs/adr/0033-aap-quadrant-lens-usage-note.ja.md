# ADR-0033: Note — AAP の 4 象限レンズを usage description として借用

## Status

accepted (note) — narrow / observational。category commitment ではない。象限語が usage observation から category claim に drift し始めたら ADR-0030 / ADR-0032 と同じ pattern で撤回する (original 本文を保存する形)。

**Corrected 2026-05-01 (same-day)**: original の Observations section に 2 つの factual error があった。(1) `skill-stocktake` と `dialogue` を「LLM Workflow ↔ Autonomous Agentic Loop 境界に座る」と描いていたが、コード再読すると両方とも fixed control flow + bounded LLM role per call (frozen prompt template、fixed output schema、tool 呼び出しなし、LLM driven の next-step decision なし) で、境界ではなく LLM Workflow そのもの。`core/stocktake.py` は pair-level LLM judging を意図的に廃して embedding clustering + 1-shot merge に帰着させたと明記しており、これは LLM Workflow の構造形そのもの (ReAct ではない)。(2) `meditate` を「LLM 不使用なので象限軸の外」と描いていたが、象限軸は LLM 専用ではない。`meditate` は exploratory action space 上の deterministic POMDP belief update (numpy のみ、runtime に LLM 呼び出しなし) で、(2) Algorithmic Search セルそのもの。Observations section を下記の通り書き直す。Decision / Self-check / Alternatives / Consequences / References は変更なし。

## Date

2026-05-01

## Context

[Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) は 2026-04-29 から、attribution に関する 10 本の ADR の上に **4 象限のルーティング診断レンズ** を articulate している。AAP の framing では、レンズは **routing diagnostic** — ある業務に対して accountability が分配可能か、それともランタイムで複数判断要素がブレンドされ事後に責任引受者を特定できない *attribution gap* を引き受けることになるか、を切る道具。

4 象限は 2 つの独立な軸から得られる:

- **横軸**: 決定論で書ける vs LLM の意味判断が必要
- **縦軸**: ワークフローが事前定義可能 vs 探索的 (次の手順をランタイム観察に基づいて決める必要がある)

この 2 軸から:

- **Script** — 決定論 × 定義可
- **Algorithmic Search** — 決定論 × 探索的
- **LLM Workflow** — 意味判断 × 定義可
- **Autonomous Agentic Loop** — 意味判断 × 探索的

(4) Autonomous Agentic Loop を選ぶことは、AAP の framing では、deploy 側組織が **除去できない attribution gap** を引き受ける commitment になる。**Phase (design / operation)** は AAP の第 3 の独立 dimension で、象限ではない。

レンズは AAP の 10 ADR と直交する別レイヤー。10 ADR は「何を制約・誰が責任」を答える。レンズは「業務がそもそも accountability が分配可能な regime で動いているか」を答える。両者は独立し、「この業務は AAP の制約が意味を持つ regime にあるか?」という問いで交わる。

本 repo の外部読者は zenn 記事 13 / 14 / 15 (2026-04 → 2026-04-30) を経由してこの語彙に既に触れており、その vocabulary を携えて README に到達する。語彙は既に project の surface area に流入しているので、本 ADR は「どういう条件で借用しているか」を記録する。

## Decision

4 象限レンズを本リポジトリの `README.md` / `README.ja.md` / `llms.txt` / `llms-full.txt` / `docs/glossary.md` の **usage-description aid** として借用する。各 placement は「ある CLI コマンドが典型的にどう動作しているか」の観察 (description) であって、type ではない。

本 ADR は **明示的に以下を行わない**:

- Contemplative Agent に単一の象限 identity を割り当てない
- どの象限も project が内側にいる category boundary として扱わない
- 他の象限を failing-other mode として framing しない。それらは本 project が現状 route していない別形の work

**Phase (design / operation)** は象限軸ではなく、独立した observation として記録する。CLI コマンドの output が design-phase artifacts (skills / rules / identity) を revise する場合、それは別の象限 placement ではなく **Phase-crossing observation** として記述する。

## Observations

以下は各 CLI コマンドが「現状 typically どう動作しているか」の descriptive observation。コマンドの typical mode が shift すれば description も follow する; 本 ADR を書き直す必要はない。

- 大半の behaviour-modifying コマンド — `distill` / `distill-identity` / `insight` / `skill-reflect` / `rules-distill` / `amend-constitution` / `skill-stocktake` / `dialogue` — は **LLM Workflow** mode で typically 動作している。defined control flow + bounded LLM role per call (frozen prompt template、fixed output schema、tool 呼び出しなし、LLM driven の next-step decision なし) を持つ。Promotion を伴うものは semantic step の output を [Human Approval Gate](0012-human-approval-gate.ja.md) で deterministic boundary に着地させる — これが placement を honest に保つ構造機構。`dialogue` は multi-turn loop だが含まれる: loop は peer message 単位で、各 turn で LLM は固定 `DIALOGUE_PROMPT` + 固定 reply schema で 1 回呼ばれるだけで、LLM-driven な action selection はない。`core/stocktake.py` は pair-level LLM judging を意図的に廃して embedding clustering + 1-shot merge に帰着させたと明記しており、これは ReAct ではなく LLM Workflow の構造そのもの
- `adopt-staged` と一回性の migration (`embed-backfill` / `migrate-patterns` / `migrate-categories` / `migrate-identity`) は **Script** mode で typically 動作している。staging 済み artifacts を deterministic に promote するもので、実行時に semantic judgement は走らない
- `meditate` (実験的 Active Inference アダプタ) は **Algorithmic Search** で動作する。numpy で POMDP の決定論的 belief update — A (likelihood) / B (transition) / C (preference) / D (prior) 行列、temporal flattening、counterfactual pruning、convergence detection — を exploratory な action policy space 上で回す。runtime に LLM 呼び出しはない。control flow は exploratory (各 iteration が前 belief state に依存) だが各 step は deterministic、これが (2) セルそのもの。**象限軸は LLM 専用ではない**: LLM 不使用が即「象限軸の外」を意味しない
- **Autonomous Agentic Loop 象限は本 project の CLI が現状 route していない**。実装済みのどのコマンドも LLM に runtime tool selection や open-ended iteration を委ねない。これは usage observation であって、その象限自体や route する他 project への value judgement ではない。既存の承認ゲートと One External Adapter 原則の構造的帰結であって、別途の設計ルールではない

象限 placement と混同されやすい独立観察を 1 つ: `skill-stocktake` / `skill-reflect` / `distill` 系列の output は design-phase artifacts (skills / rules / identity / constitution) を revise する。これは **Phase-crossing observation** — Phase (design / operation) は AAP の第 3 dimension、象限とは独立。第 5 象限でも hybrid placement でもない。In-repo anchors: [ADR-0016](0016-insight-narrow-stocktake-broad.ja.md) (insight = narrow generator / stocktake = broad consolidator) と [ADR-0023](0023-skill-as-memory-loop.ja.md) (skill-as-memory ループ + usage log + reflective write)

## ADR-0032 撤回理由に対する self-check

[ADR-0032](0032-runtime-agent-stance.ja.md) は accept された同日に撤回された。理由は contemplative axioms との 3 点の tension: categories の固定化 (vs Emptiness)、self / other 境界線 (vs Non-Duality)、adversarial placement (他カテゴリを failing other として暗黙に対比)。本 Note ADR を同じ 3 点に対して照合する:

- **Categories を fix しているか**: Decision section に「placement は usage description であり category claim ではない」と verbatim で書いてある。本文に 4-cell grid は載せていない — 象限は prose 形式で記述し、placement は「is」ではなく「typically operates as」と書く
- **Self / other を redraw しているか**: Contemplative Agent vs 他象限の比較 table はない。各象限はそれ自体の用語で記述し、project を別種として対比していない
- **Adversarial placement になっているか**: Observations section で他象限を「本 project が現状 route していない別形の work」と明記しており、failing-other mode としては framing していない

実際の運用で、レンズが usage observation から category commitment に drift し始めた場合 — 例えば README が「Contemplative Agent *は* LLM Workflow エージェントである」と読まれるようになった場合 — 本 ADR は ADR-0030 / ADR-0032 と同じ pattern で撤回する: original 本文を保存し、Status を withdrawn に変え、撤回理由に rub を記録する。

## Review-when

期限なし（note。四象限のレンズは使い方の記述補助であって型体系ではない）。AAP が象限の定義を変えたときだけ再検討する。

## Alternatives Considered

- **Worldview ADR として書く (4 象限レンズを project worldview に正式採用)**: 却下。形は ADR-0032 の「5 カテゴリ」claim と構造的に同じで、Emptiness / Non-Duality / adversarial-placement の同じ tension を再発させる。2 ヶ月で 2 度の同日撤回は健全な pattern ではなく、その回避が本 ADR の存在理由の一部
- **Operational ADR として placement table を Decision に書く**: 却下。Decision section の table は load-bearing として読まれる; 一度 accept されると future readers はその table を project commitment として cite する。soft な table も category 読みに drift する。Prose observation の方が soft で、ADR amendment なしに revise できる
- **ADR を書かず README / llms.txt / glossary 更新のみ**: legibility 観点から却下。新 vocabulary が audit trail なしに facing docs に入ると、future readers (human / LLM) は commit message から借用の経緯を再構成しなければならない。ADR-0032 の撤回 note には「AAP attribution ADR / runtime context 関係には新 ADR 不要」と明記されているが、4 象限レンズは別レイヤー (ADR-0032 より後発で attribution ADR と直交する) なので、レンズに対する Note ADR はその先行判断に矛盾しない

## Consequences

- README / llms.txt / llms-full.txt / glossary に小さな entry が増え、象限レンズとその語彙の借用条件を名指す。コード変更なし
- 将来の機能議論で象限語彙を借りられる。project が象限 identity を負わない形で「この提案は Autonomous Agentic Loop 象限に work を route することになる; 本 project は現状その route を取っていない」と読める — worldview 違反にならない
- Autonomous Agentic Loop 象限は **本 project が現状 route していない象限** として残る。これは usage observation であって、その象限自体や、その象限に work を route する他 project への value judgement ではない
- 本 ADR は cheap に撤回できる。レンズは他のどの ADR にも load-bearing ではない; README / llms.txt / glossary の entry を removed して本 ADR を withdrawn にすれば、repo の残りは unchanged のまま

## References

- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) — 10 本の attribution ADR と 4 象限ルーティングレンズ
- [ADR-0002](0002-paper-faithful-ccai.ja.md) — contemplative axioms (Laukkonen et al. 2025, Appendix C)。上の self-check の対象 values 層
- [ADR-0012](0012-human-approval-gate.ja.md) — Human Approval Gate。LLM Workflow typical コマンドの placement を honest に保つ構造機構
- [ADR-0016](0016-insight-narrow-stocktake-broad.ja.md) — insight narrow / stocktake broad。Phase-crossing observation の in-repo anchor
- [ADR-0023](0023-skill-as-memory-loop.ja.md) — skill-as-memory ループ。design-phase artifacts が operation-phase output で revise される pattern の in-repo anchor
- [ADR-0030](0030-withdraw-identity-blocks.ja.md) — narrow / 統合 ADR の precedent
- [ADR-0032](0032-runtime-agent-stance.ja.md) — 撤回された worldview ADR。original を保存して撤回する pattern と、本 ADR が適用した axioms self-check の precedent
- zenn 記事 13 / 14 / 15 (2026-04 → 2026-04-30) — README "Development Records" 既出。本 ADR の Observations section の語彙はそれら記事と共有
