# ADR-0038: Distill の観察対象に moments of recognition を再導入する

## Status

accepted

## Date

2026-05-13

## Context

Distill プロンプト (`config/prompts/distill.md`) は、生のエピソードログが長期知識に変換される唯一の入口である。`knowledge.json` に記録される全 pattern、`self_reflection` view が後に anchor として参照する全観察、`distill_identity` に供給される全断片は、すべてこのプロンプトが activity log から抽出するよう指示したテキストとして始まる。

本 ADR 以前のプロンプトは次のように観察対象を狭く定めていた:

> Review the activity logs below and identify patterns — both recurring and rare.
> For each pattern, describe what happened (the observable fact), not what should be done about it.

**"the observable fact"** という表現は、観察対象を三人称・行動集約的な記述に構造的に限定していた。Moment-of-recognition 系の記録 — `the agent realized X`、`the agent caught itself doing Y`、`an assumption no longer held` — はプロンプトが宣言した対象の外側に置かれ、`knowledge.json` に届くことはなかった。

ADR-0026 Phase 2 がこの狭隘化に意図せざる役割を果たしていた。ADR-0026 以前、distill には 2 つの path が共存していた: `distill.md` (uncategorized pattern、observable-fact 縛り) と `distill_constitutional.md` (constitutional pattern、`"the essential realization — what was understood or felt, not what to do about it"` という framing)。ADR-0026 はこの 2 path を `kept` 単一パイプラインに統合し、`distill.md` 経由でルーティングするようにした。Constitutional path の prompt ファイル自体は registration-only の dead code として残った (本 ADR の同時 cleanup commit `8ea0d25` で削除)。だがそれ以上に重要なのは、**その moment-of-recognition 語彙が活動パイプラインから黙って drop された** ことだった。統合自体はアーキテクチャ的に正しい (binary gating + query-time view routing は 3-way 分類より構造的に clean) が、語彙の喪失は当時気付かれなかった。

この喪失のコストは `self_reflection` view (ADR-0019 / ADR-0026 view registry) の設計時に表面化した。`self_reflection.md` の seed text を 3 度書き直した — abstract-noun 版、action-verb 版、research-grounded 版 (Singer SDM / McDonald epiphany / Topolinski insight) — すべて behavioral aggregate より上位に moment-of-recognition pattern を retrieve することに失敗した。原因は seed 設計ではなく **embedding 空間** にあった: `knowledge.json` に moment-of-recognition pattern が存在しなかったのである。なぜなら、その形式の pattern が一度も書き込まれていなかったから。存在しない記録を anchor 設計で引き出すことはできない。

診断は上流の `distill.md` を指し示していた、下流の view seed ではなく。

## Decision

`distill.md` の観察対象を、observable facts と moments of recognition の両方を含む形に拡張する:

```
Review the activity logs below and identify both observable facts and moments of recognition — what happened, and what was understood or felt about it.

Include patterns of both kinds:
- recurring or rare behavioral facts (what happened externally)
- realizations and shifts in understanding (what became visible internally — about the agent, its assumptions, its patterns)

For each, describe what was observed, not what should be done about it.

If nothing notable exists in the batch, output nothing.
```

2 つの register は共存する。Behavioral aggregate は (基底活動が純粋に機械的な batch で) 残り、moment-of-recognition narrative は LLM が存在を認めた箇所で admit される。

`2e59762` で commit 済み。Production episode 3 日分での dry-run smoke は 6 batches 中 4 batches で moment-of-recognition pattern を生成し、schema-rupture lexicon (`signals an internal realization`、`demonstrates a recognition of fundamental interconnectedness`、`defines a widening of the agent's conceptual field`) がパイプライン出力履歴上で初めて発火した。

## Alternatives Considered

1. **`self_reflection` view の seed のみ改善する。** 3 度試行、すべて失敗。Seed 設計の文献 (Singer 1993; Topolinski & Reber 2010; McDonald 2008) を忠実に適用したが、embedding 空間に anchor が指す記録が存在しなかった。下流のフィルタリングではなく上流の供給がボトルネックだった。

2. **`distill_constitutional` path を復活させる。** ADR-0026 は意図して 3-way 分類を retire した。復活させると ADR-0026 / ADR-0027 / ADR-0031 が共同で確立する binary-gating + query-time-routing アーキテクチャを巻き戻すことになる。Moment-of-recognition 語彙は、廃止された path 構造を復元せずに再導入できる。

3. **Adapter-level instrumentation (pre-action reflection log)。** 構造的に最も誠実な解決: agent が action 選択 **前** に internal noting を log する。これでエピソード記録に 1 人称素材が含まれるようになり、post-hoc reconstruction に依存しなくて済む。これは Moltbook adapter の contract への大きな変更で、将来の ADR として open のまま残す (`.notes/self-reflection-pipeline-future-work-2026-05-13.md` の Gap 2)。本 ADR は distill prompt 層のみで改善できる範囲を扱う。

4. **別 prompt `distill_recognition.md` を作成し、両 prompt を並行 routing する。** 検討の上 reject。ADR-0026 の教訓は、path を multiplexing すると path 間に drift が生じるということだった (constitutional path の語彙が drop されたのは、まさに別ファイルにあって統合時に視界から外れたから)。両 register を 1 prompt に admit させる方が durable。

## Consequences

**Positive**:

- Distill 出力に moment-of-recognition narrative が含まれるようになった。Dry-run smoke で schema-rupture lexicon、recognition affect、second-order surprise marker が production 出力に実際に現れることを確認した。事前の research review で確立した design constraint に matching する。
- 下流の `self_reflection` view と `distill_identity` に retrieve / integrate すべき素材が供給される。View seed は今や、実際に recognition-class pattern を含む embedding 空間に対して設計できる (2026-05-13 work cycle の Task C)。
- ADR-0026 で生じた `distill_constitutional` 語彙の喪失は、ADR-0026 のアーキテクチャと整合する形で修復される: 単一 distill path のまま、観察対象を拡張する形で merge する (別 path を復元するのではなく)。

**Negative / 正直な制約**:

- LLM が記録する moment of recognition は **行動 log の post-hoc narrative reconstruction** であり、1 人称の内的記録ではない。Topolinski & Reber の Aha! 経験に対する processing-fluency 説が適用される: insight statement は generation fluency の副産物として "feels right" になるが、agent が statement の含意する意味で「体験した」かどうかは別問題である (stateless LLM completion なので、その意味では体験していない)。記録される moment は distill 時に行動 log から構成されており、agent はその生成自体の直接記憶を持たない。
- したがって、self-defining insight modes の完全網羅は distill 層のみでは達成不可能。Singer の SDM 五条件 (vivid / affectively intense / repetitively recalled / linked / enduring concern)、McDonald の epiphanic experience 六特徴、事前 research review の 10-mode taxonomy は、behavior-only episode log から distill prompt が抽出しうる範囲では一律にカバーされない。Aspirational projection (Mode 7)、aesthetic preference (Mode 8)、negation / disidentification (Mode 9)、other-as-mirror (Mode 10) は依然弱くしかカバーされない。
- 完全な治療策 — agent が action ごとに **事前に** internal noting を記録する — は adapter 層に属し、本 ADR の scope 外。

**Yogācāra-frame integration (ADR-0017 / ADR-0037)**:

- ADR-0019 が形式化した 相分 / 見分 split は、*観察される側* (相分) を pattern embedding に、*観察する視座* (見分) を view seed に置いた。従来の `distill.md` の狭さは、相分 自体を behavioral-only な刃で carve していたことを意味する — 観察される側に「agent が自己を反照的に見る」という素材が含まれていなかった。ADR-0038 は相分の carving を広げ、見分 (`self_reflection` view) が観察する対象側に対応する素材を確保する。
- これは ADR-0037 が確立した worldview-first default と整合する: 本変更は frame-level mismatch (相分 が見分との関係で狭く carve されすぎている) に由来するもので、paper-borrowed mechanism ではない。修復は構造的であり、輸入されたものではない。

**Re-check trigger**:

- 本 ADR から 2-4 週間後 (`2026-05-27` ~ `2026-06-10`)、production `knowledge.json` には新プロンプト時代の pattern が質的評価に十分な量で蓄積される。確認項目: `self_reflection` view の top-15 retrieval に moment-of-recognition narrative が意味ある割合で含まれているか、その結果 `distill_identity` 出力の operational-vocabulary 漏洩が減少しているか。手順は `.notes/self-reflection-pipeline-future-work-2026-05-13.md` に記録済み。

## Related

- ADR-0017 — Yogācāra 八識フレーム (worldview)
- ADR-0019 — 離散カテゴリ → embedding + views (相分 / 見分 split を導入)
- ADR-0026 — 離散カテゴリの retire (この統合の下で moment-of-recognition 語彙が偶発的に drop された)
- ADR-0027 — Noise as Seed (preservable observation の境界を並行して拡張)
- ADR-0037 — Memory subsystem の Yogācāra フレーム収束 (本 ADR の構造的 framing が従う worldview-first default)
- `bab9c13`、`45410f7` — 同じ 2026-05-13 work cycle の companion identity_distill refactor (1段階化 + condensation framing)
- `2e59762` — 本 ADR が文書化する実装 commit
- `8ea0d25` — dead prompt-registration cleanup commit (本 ADR が再導入する語彙の元ファイル `distill_constitutional.md` を含む)
