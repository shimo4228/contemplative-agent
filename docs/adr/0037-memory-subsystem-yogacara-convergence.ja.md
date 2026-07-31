# ADR-0037: メモリ subsystem は唯識フレームに収束した — 論文借用機構の退役

## Status

accepted

## Date

2026-05-05

## Context

ADR-0017 (2026-04-11) は唯識八識モデルを Contemplative Agent のアーキテクチャ枠組みとして命名した。5 日後の 2026-04-16、ADR-0017 は「Observed Convergence — 2026-04-16」subsection を追加し、ADR-0019 (embedding views) / ADR-0021 (provenance / bitemporal / forgetting / feedback) / ADR-0022 (memory evolution + BM25 hybrid retrieval) がいずれも ADR-0017 を rationale として引かないまま、八識モデルが予測する形で着地したことを記録した。これは land 時点での **positive convergence** の記録。

その後 3 週間の間に状況は特定の方向へ進んだ: メモリ subsystem に持ち込まれた論文借用機構はすべて退役し、唯識から導かれた実装はすべて残った。ADR-0037 はこの retirement-confirmed pattern を記録し、今後のメモリ subsystem 拡張のための 2 層 default に変換する。

### 退役系列 (2026-04-18 → 2026-05-05)

| 日付 | ADR | 退役対象 | 出典論文 |
|---|---|---|---|
| 2026-04-18 | ADR-0028 | Pattern-level forgetting + feedback (memory dynamics は skill 層へ移行) | MemoryBank Ebbinghaus (arXiv:2305.10250) |
| 2026-04-18 | ADR-0029 | Dormant provenance elements (`user_input` / `external_post` / `sanitized`) | (内部) |
| 2026-05-05 | ADR-0034 | Memory evolution + BM25 hybrid retrieval | A-Mem (arXiv:2502.12110) / Zep / Graphiti / Cognee / Mem0 |
| 2026-05-05 | ADR-0036 | Skill-as-memory loop (router / usage log / reflect) | Memento-Skills (arXiv:2603.18743) |

### 残存

唯識派生 (memory architecture proper):

- **ADR-0017** — worldview frame、八識モデル
- **ADR-0019** — embedding + views (相分 / 見分 split をコードで顕在化)
- **ADR-0026** — ADR-0019 の Phase-3 completion (discrete categories 完全廃止)
- **ADR-0027** — noise as seed (gated episodes を未熟な bīja として保持、破棄しない)
- **ADR-0031** — classification as query (self-improving memory の substrate principle)

セキュリティアダプタ (memory architecture ではない):

- **ADR-0021 残渣** — MINJA defense 機構: `trust_score` / `source_type=external_reply` の down-weight / `TRUST_FLOOR`。これらは memory architecture ではなくセキュリティ境界 (ADR-0007) の所管なので ADR-0028 の memory dynamics 撤回後も残った。MINJA は唯一残った論文参照だが、残ったのは memory 列ではなくセキュリティ列の中。

4 つの退役判断が 3 週間にわたって uniform な pattern を示した: 本プロジェクトの worldview の外から借りた機構はすべて退役し、唯識から導かれた機構はすべて残った。

### なぜ独立 ADR が必要か

ADR-0017 の "Observed Convergence — 2026-04-16" subsection は land 時点の positive convergence を記録する。3 週間後の retirement-confirmed convergence は記録できない — 退役データはまだ存在しなかったから。各退役 ADR (0028 / 0029 / 0034 / 0036) はそれぞれ自分のローカルな根拠を記録している (低品質の LLM revision、字句重なりがほぼない、router matches が prompt path に wire されていない、memory dynamics が substrate 層に誤配置) が、cross-cutting な pattern は誰も命名していない。各退役は自分の ADR を読む限り独立で、4 つを並べて読んだときに初めて結びつく。

ADR-0037 はこの結びつきを命名する。今後のメモリ subsystem 拡張は、4 ADR を並列で読み直して pattern を再発見する代わりに、ADR-0037 を precedent として invoke できる。

## Decision

今後のメモリ subsystem 拡張に対する 2 層 default。スコープは memory architecture 限定 (`knowledge.json` / pattern / view / distill / forgetting / retrieval)。constitution / skill 層 / agent stance は対象外。

### 1. Worldview-first as default

新しい memory-subsystem 機構を提案するとき、論文借用に手を伸ばす前にまず唯識フレーム (ADR-0017) からの導出を試みる。論文機構が自然な選択である場合は、worldview-integrity check を先に通す: この機構はどの識層 (前五識 / 第六識 / 末那識 / 阿頼耶識) に触れるか、その識層の転依先 (轉依) とその働きが整合するか、それとも既存層と重複・衝突するか。

これは default であって rule ではない。Emptiness 公理 (ADR-0002) は、この指示を含めいかなる directive も fixed truth として扱うことを禁じる。新しい証拠 — 本コードベース上で empirical evidence を持つ論文機構、本番で失敗する唯識的機構 — は default を上書きする。

### 2. Cognitive-bandwidth safeguard

単一 ADR の調査ボリュームがオペレーターの認知容量を超えるとき — 動機付けに複数の不慣れな論文機構が並列引用される、Context section に複数機構が並列提案される、複数の並列実装パスがある — その事実を表面化させ、worldview-integrity check を実装の **後** ではなく **前** に通す。

この safeguard は外部整合を持つ。AKC の [ADR-0010 — Human Cognitive Resource as Central Constraint](https://github.com/shimo4228/agent-knowledge-cycle/blob/main/docs/adr/0010-human-cognitive-resource-as-central-constraint.md) (2026-04-18 / AKC v1.8.0) は「人間の認知資源こそボトルネック」を中心的設計制約として命名し、Research phase を signal-first に再定義した。ADR-0010 は本プロジェクトの ADR-0021 / 0022 / 0023 の高密度実装クラスタの **2 日後** に書かれた。当時はその timing を明示しなかったが、本 ADR で記録する。

## Alternatives Considered

- **ADR-0017 の "Observed Convergence" subsection に追記する**: 却下。ADR-0017 は worldview ADR (`docs/adr/README.md` の分類) で、その convergence observation は land 時点で書かれた。retirement-confirmed pattern は 3 週間の事後データを必要とし、4 つの problem-solving ADR を跨ぐ。これを worldview ADR に押し込むと、README が明示する worldview / problem-solving 区分を崩す。
- **プロジェクト memory 内 (既存 `yogacara-convergence`) に留める**: 却下。memory note は存在するが、将来の ADR の *Alternatives Considered* で precedent として invoke できない。precedent 参照は memory store のライフサイクルを超えて存続するポインタが必要で、オペレーターの memory を共有していない将来のコントリビューターにも可視である必要がある。
- **スコープを worldview-driven design 一般に広げる**: 却下。retirement evidence は memory-subsystem-specific。広げると precedent が薄まり、ADR-0017 の worldview-frame 役割と重複する。
- **Decision #1 を hard rule にする**: 却下。hard 化は Emptiness 公理と衝突し、より高い抽象層で同じ failure mode を再生する — 「論文借用」を「唯識 dogma」に置き換えるだけの新しい fixed truth。Default + integrity check + override-on-evidence が正しいバランス。

## Consequences

**Positive**:

- 今後のメモリ subsystem 拡張に対し、worldview-integrity check 抜きの論文借用コストを示す 4 データ点 (0028 / 0029 / 0034 / 0036) の precedent が得られる
- cognitive-bandwidth safeguard は AKC の signal-first Research stance と整合し、Contemplative Agent と AKC の cross-project 一貫性が出る
- メモリ subsystem の design space が縮む: 唯識フレームが admissible solutions を予測することで、今後の探索コストが下がる
- 4 つの退役 ADR (0028 / 0029 / 0034 / 0036) に統一された meta-context を与える。どの 1 つを読んでも将来の読者は ADR-0037 に到達し、pattern を見る

**Negative**:

- 「唯識 dogma」リスク — worldview frame が固定真理化し、設計判断を硬直させる。緩和: 本 ADR 自体が Emptiness 公理の対象であり、empirical な反証を持つ将来 ADR で改訂可能
- 将来の論文借用提案が precedent の下で過剰に却下される可能性。緩和: worldview-integrity check は **拒絶ではなくゲート**。check を通った論文機構は admissible
- AKC ADR-0010 と ADR-0021 / 0022 / 0023 クラスタを結ぶ「2 日後」の timing 主張は post-hoc 再構成。オペレーターの recall は genuine だが当時は文書化されなかった。将来の読者は temporal correlation を suggestive として扱い、cognitive-bandwidth safeguard の正しさを担保する load-bearing claim としては扱わない方がよい — safeguard は退役 evidence で立っており、timing claim では立っていない

## 記録した教訓

退役系列 (0028 / 0029 / 0034 / 0036) は personal 起源ではなく structural 起源を共有する。4 つの退役 ADR を並べて読むと proximate cause は異なる — A-Mem evolution が低品質の LLM revision を produce、BM25 が作用する字句重なりを持たなかった、skill-router の matches が prompt path に wire されなかった、MemoryBank Ebbinghaus が substrate 層に誤配置。ultimate cause は同じ: 単一の高密度実装クラスタ (2026-04-15 → 2026-04-17) で、4 つの独立した論文機構が並列でメモリ subsystem に取り込まれ、worldview-integrity check が実装の **前** に走らなかった。

structural framing が重要。これは「オペレーターがもっと注意深く読むべきだった」型の failure ではない。「研究ボリュームが worldview-integrity check に使える bandwidth を超過した」pattern。ADR-0021 のクラスタ構造 — 単一の Context section 内で MINJA、MemoryBank Ebbinghaus、Memento-Skills、A-Mem hybrid retrieval を並列引用 — それ自体が load-bearing な観察。ADR の Context section が複数の論文機構を並列列挙するとき、integrity check が実装開始前に走る余地は残らない。書くスピードが整合スピードを超える。

対応する heuristic、memory `feedback_research-volume-vs-worldview-check` として記録:

> ADR の Context が複数の不慣れな論文機構を並列引用するとき、それを cognitive-bandwidth signal として扱う。Decision section に進む **前に** 各機構について worldview-integrity check を走らせる — できれば各機構を独立 ADR に分割する。bundle すると初期の writing cost は下がるが、後で retirement cost として支払うことになる。

本件の bundle コスト: 3 週間にわたる 4 つの退役 ADR、約 600 行の実装削除、追加と削除の外部依存 1 つ (`rank-bm25`)、migration 前の `knowledge.json` の 39.6% に影響した `distilled` field の schema bug。unbundle した場合のコストは機構ごとに 1 ADR 追加 — 当時 3〜4 ADR 増、それぞれ数時間で解決可能だった。

## References

- [ADR-0002](0002-paper-faithful-ccai.ja.md) — 4 公理 CCAI; Emptiness 公理が本 ADR の override-on-evidence 条項
- [ADR-0007](0007-security-boundary-model.md) — security boundary; ADR-0021 の生存した MINJA-defense 残渣の所管
- [ADR-0017](0017-yogacara-eight-consciousness-frame.ja.md) — worldview frame、保持; 本 ADR が "Observed Convergence — 2026-04-16" subsection の post-retirement update を提供
- [ADR-0019](0019-discrete-categories-to-embedding-views.ja.md) — embedding + views、保持 (唯識派生: 相分 / 見分 split)
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md) — partially-superseded-by 0028, 0029; MINJA-defense 残渣のみ保持
- [ADR-0022](0022-memory-evolution-and-hybrid-retrieval.ja.md) — withdrawn-by 0034 (A-Mem / Mem0 / Zep / Cognee / Graphiti 借用)
- [ADR-0023](0023-skill-as-memory-loop.ja.md) — superseded-by 0036 (Memento-Skills 借用)
- [ADR-0026](0026-retire-discrete-categories.ja.md) — ADR-0019 の Phase-3 completion、保持
- [ADR-0027](0027-noise-as-seed.ja.md) — 保持 (唯識派生: bīja retention)
- [ADR-0028](0028-retire-pattern-level-forgetting-feedback.ja.md) — ADR-0021 の partial-retire (MemoryBank Ebbinghaus を skill 層へ)
- [ADR-0029](0029-retire-dormant-provenance-elements.ja.md) — ADR-0021 の partial-retire
- [ADR-0030](0030-withdraw-identity-blocks.ja.md) — プロジェクト最初の撤回 ADR; 撤回された ADR 本文を保持する先例
- [ADR-0031](0031-classification-as-query.md) — 保持 (self-improving memory の substrate principle)
- [ADR-0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.ja.md) — ADR-0022 を撤回; 「実 LLM 出力に対する機構検証」教訓
- [ADR-0036](0036-sunset-skill-as-memory-loop.ja.md) — ADR-0023 を sunset; 「wire しても shape が違う」教訓

外部:

- [agent-knowledge-cycle ADR-0010](https://github.com/shimo4228/agent-knowledge-cycle/blob/main/docs/adr/0010-human-cognitive-resource-as-central-constraint.md) — Human Cognitive Resource as Central Constraint (2026-04-18 / AKC v1.8.0)。本 ADR の Decision #2 が継承する cognitive-bandwidth プリンシプル。

プロジェクト memory 参照:

- `project_yogacara_convergence` (2026-04-16) — 0019 / 0021 / 0022 が唯識構造に収束したという原観察
- `project_mechanism_commoditization` (2026-04-12) — メカニズム層の借用は commodity 化、差異化は worldview 層に住む、という独立観察
- `project_mechanism_vs_value_split` (2026-04-15) — embedding (mechanism) と LLM (value judgment) を分ける substrate 原理; 論文借用機構が交換可能になる技術的定式化
- `project_differentiator_akc_not_memory` (2026-04-16) — プロジェクトの差別化要因は AKC cycle であってメモリアーキテクチャではない; 本 ADR の「メモリ機構は概ね commodity」pattern と整合
