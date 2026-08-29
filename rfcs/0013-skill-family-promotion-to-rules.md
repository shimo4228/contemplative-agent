---
state: withdrawn
state_since: 2026-08-26
---

## タスク

**常時選択 skill の rule 昇格**（AKC Promote の CA 適用、2026-07-25 発案）: 選択がほぼ無条件な skill（shadow 14 日で上位 3 が judged の 8 割超、enforced 後も同分布）は「状況トリガー」でなく「常時作用する原則」= B 層 rule の性質。rules-distill で Practice/Rationale へ蒸留し skill 側は merge/退役 → 常時注入分の軽量化 + selector の判断対象を真に状況依存な skill に絞る両取り。**順序注意**: 先に description 監査（ADR-0081 で stocktake に実装済み）で過広 description を締め、それでも常時選択が残る skill のみ昇格（過広なだけの skill の誤ルール化を防ぐ）。判定材料は stocktake usage 次元（選択頻度・出現日数）。**2026-07-25 追記**: insight 78 件レビューで「構造へのピボット」族の飽和が可視化（候補の 6 割 + 既存 6 件）。description 監査の第一標的はこの族。**2026-07-26 追記**: SkillResolve-Bench (arXiv 2606.10388) の *same-capability ambiguity*（同一機能ファミリーの「危険な兄弟スキル」を選んでしまう）は、ほぼ同文の description 6 件から選ばされている現状と同型。**兄弟を減らすこと自体がセレクタ改善**になるので、本タスクは整理整頓でなく選択精度の施策。対抗手法 SkillResolve は機能ファミリーごとに代表 1 件を選ぶ設計（HSR@3=0） — `constraint-shift-analysis-pivot-point-identificati` / `detecting-abstract-to-operational-constraint-shift` / `anchoring-abstraction-to-measurable-constraints` / `structure-authority-tracing` / `scope-failure-diagnosis` / `mapping-epistemic-boundaries`（candidate review 2026-07-25 §3（`.notes/insight-candidate-review-2026-07-25.md`））。ADR-0081 で却下した static tiering とは別物（注入層の恒久固定でなく人間ゲート付きの層再配置）

## 着手条件

再開条件: `T-CONSOLIDATOR-REDESIGN` の結論が出ること（resolved）
照合先:   `.notes/archive/tasks/T-CONSOLIDATOR-REDESIGN.md（ローカル記録、2026-08-25 archive）` の `state:`
成立時:   draft（REDESIGN の結論次第で「skill → rule 昇格」という手自体の採否を再判断。CADENCE と同じ形）

**2026-08-16 の棚卸しで発見**: 条件は前日に成立している。監査で過広 description が締まらなかった
（0 mismatch）のに寡占が残っているので、「過広なだけの skill の誤ルール化」を防ぐ順序規約は
既に満たされた形になる。次に触るとき、まずその解釈が正しいかを確認する。

## 詳細

skillsel 初回読み §2/§6（`.notes/skillsel-reading-2026-07-24.md`）、[ADR-0081](../docs/adr/0081-skill-selection-two-pass-injection-enforcement.md)、skill 選択研究の参照ノート（`.notes/ref-skill-selection-research-2026-07-26.md`）

## 2026-08-17 triage（オーナー承認済み）

旧条件（description 監査後も寡占が残る）は 08-15 に成立していたが、本タスクが使う `rules-distill` は REDESIGN が問い直す統合器 3 本の 1 つなので、REDESIGN の結論を待つ条件に書き換えた。実行時は `--stage` 境界で人間ゲート。

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。照合先 `T-CONSOLIDATOR-REDESIGN` の `state:` = `accepted`（未着手）。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。照合先 `T-CONSOLIDATOR-REDESIGN` の `state:` = `accepted`（オーナー専用セッションが 2026-08-22 に claim、結論未記録）。

## 2026-08-22 再定義（ADR-0097 Decision 7 の形 A′）

**draft** — 親の結論が出た。昇格の基準「family の any-of 選択率 ≥ 0.75 が互いに素な ≥ 500 judged の窓 2 つ以上」は「制約」family で既に成立（07-25 以降 4 窓で 0.78 / 0.74 / 0.72 / 0.81）。形は A′: gemma が family の共通の姿勢を `stocktake_merge_rules.md`（共有する核の合成）で Practice / Rationale に描画 → 人間ゲート → `rules/` へ。**member の 6 skill は store に残す**（各冊は固有の手順を持つ。co-selection は add-on 関係。「代表をそのまま移す」は 5 冊の手順を落とすので撤回）。選ばれなくなった member は never-selected の出口で退役。入口 `promote-family`（family 名 → 合成 → staging）はスライス 2 で実装。実行後の観測: ≥ 100 judged で member の選択が減り selected_count p50 が下がること。rules 層は小さく保つ（Instruction Stacking Collapse）。`rules-distill` はもう無い。

## 2026-08-22 ADR-0097 で手が決まった（本文の手順は失効）

再開条件（REDESIGN が resolved）は成立。**本文が使う `rules-distill` は退役したので、そこに書いた
手順はもう実行できない。** 手は ADR-0097 Decision 7 の **形 A′** に確定した:

- 昇格するのは family の**共通の姿勢だけ**。gemma が既存 `stocktake_merge_rules.md`（共有する核を
  1 本に合成する prompt）で Practice/Rationale に描画 → 人間ゲート
- **member skill は store に残す。** 本文の「skill 側は merge/退役」と「代表 1 件を選ぶ」は
  **セッション中に撤回した** — 6 冊の Solution を読むと各冊が固有の手順を持ち、co-selection は
  代替でなく add-on 関係だった。同じ案を再提示しない
- 選ばれなくなった冊は出口の読み値（packet §10 strict、ADR-0097 D5）で退役する。昇格と退役は
  別の変数として別々に動かす

**判定基準は既に満たしている**（D8 の表）: 「制約」family の any-of ≥ 0.75 が互いに素な ≥ 500 judged
の窓 2 つ以上 — 07-25 以降の 4 窓で 0.78 / 0.74 / 0.72 / 0.81（deconstruct family も 0.83 / 0.85 /
0.80 / 0.72）。数値は `scripts/coselection_families.py`（2026-08-22 出荷、read-only）で再取得できる
（同スクリプトは 2026-08-29 に退役 — commit `a06c6be`。再測定するならその commit から復元する）。
ADR の Context の下位ケース対 11 組は支持数の床を宣言していない探索値で、計器は 16 組と読む（同 ADR 注記）。

**実行後に読むもの（≥ 100 judged ≈ 1–2 日）**: 昇格した rule の member 名が `selected` から消え、
selected_count の p50 が下がる（6 → 5 前後）。**これは挙動が変わる変更**なので、archive とは同じ週に
動かさない（ADR-0056 は暦でなく観測量で守る — 先に読み値が出た方から）。

旧 ID: T-SKILL-PROMOTE（.notes/tasks から 2026-08-25 移送）。
本文中の `.notes/…` はローカルの作業ノート（gitignored、clone 先には存在しない）を指す。

## 2026-08-26 triage 照合（無人 cycle）

`draft` 維持。再開条件（親 `T-CONSOLIDATOR-REDESIGN` = `decided` 2026-08-22）は成立済みで、手は ADR-0097 Decision 7 の形 A′ に確定している。残るのは採否のみ = オーナー判断。本 cycle で Slack digest に 1 件として送付。

## Status

withdrawn 2026-08-26 — オーナー決定（triage セッション、ADR-0080 追補と同日）。
提案の欠陥ではなく、上流の再設計が先という判断:

1. co-selection family は頻度キーの抽出が変奏を量産した**症状**であり、ADR-0080
   追補（代謝の質）はその producer（摂取装置に新規性の器官が無いこと）を直接
   名指しした。認可された経路は摂取側の修理であって下流の層再配置ではない
2. 昇格の前提「共通の姿勢がある」は「selector が識別できていない」と観測上
   区別がつかない。摂取の再設計がその判別実験そのもの — 先に昇格すると永久に
   切り分け不能になる
3. ADR-0097 自身の「rules 層は小さく保つ」と、ADR-0080 の審査基準
   （修理か、能力動機の拡大か）に照らして通らない

**再提起条件**: 摂取装置が新規性の器官を得た後（RFC-0016 の復元または後継の
新規性判定の出荷後）、≥ 500 judged の互いに素な窓 2 つ以上で co-selection
family の any-of ≥ 0.75 が**なお**残存したら、「共通の姿勢」説が判別実験を
生き残った証拠として再提案してよい。

## Next action

- なし（終端）。再提起条件は Status 節を参照
