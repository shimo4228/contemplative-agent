---
title: shadow 憲法計器の読み値を次回改正ゲートで消費する
state: accepted
state_since: 2026-10-31
admitted-by: unrecorded
review-when: 次回の憲法改正ゲート（目安 2026-11）で shadow 憲法の読み値を消費した、または shadow-constitution 計器（ADR-0092）が退役した
alignment: instrument
---

## タスク

**shadow 憲法計器の読み値を次回 amend-constitution ゲートで消費する**（ADR-0092、2026-08-11 出荷）。`shadow-constitution` を手動で **2 回以上**（同一コーパスで連続 2 回 = 計器自身のノイズ床、＋できれば数週おいて 1 回 = トレンド）実行し、`logs/constitution-shadow.jsonl` の cosine と乖離条項を読む。次回改正ゲート（`pipeline/value-layer/value-layer-*.json` の `constitution.due` が true になる頃 — ADR-0091 の 83 日間隔、last_adopted 2026-08-09 + 83 日 = 2026-10-31）で diff / IPD ベンチ（ADR-0090）と並ぶ第 3 の材料として使い、その時点で weekly チェーンへの月次配線の採否もデータで決める。JST 0/6/12/18 のセッション窓は避けて実行

## 着手条件

再開条件: 次回の憲法改正ゲートが開く（ADR-0091 の 83 日間隔、2026-10-31）
照合先:   `pipeline/value-layer/value-layer-*.json` の `constitution.due`（weekly packet は ADR-0098 で退役済み）
成立時:   accepted（計器側の予約読み値は取得完了済み。残るは diff / IPD ベンチと並ぶ第 3 の材料としての消費のみ）

## 詳細

[ADR-0092](../docs/adr/0092-shadow-constitution-instrument.md) Decision 5。**run 1+2: 2026-08-11 完了**（08:11 / 08:19 JST、同一コーパス 50 本、両方 verdict ok）— cosine 0.814 / 0.798（ノイズ床 0.016）、セクション目録は 4 公理と完全乖離しつつ 4 テーマは両 run で安定、Boundless Care 両 run 不在（摩擦バイアス再現）。evidence: docs/evidence/adr-0092/。**IPD 合成読み値も取得済み**（2026-08-11、現行 vs shadow run 1: no readable signal — care 公理欠落でも協調効果は保存、Δeffect +0.01/+0.02/+0.06 全て床内。ipd-shadow-reading.md）。**床アンカー測定済み**（2026-08-11: 無関係床 0.42–0.49、同ジャンル帯 0.66–0.75、shadow 0.798/0.814 = 同ジャンル帯上限 +0.05〜0.06 — 形の共有だけでは説明できない内容収束。evidence の shadow-run-1-reading.md §Floor anchor）。**計器側の予約読み値は全て取得完了** — 残るは次回改正ゲートでの消費のみ

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-19、改正ゲート目安 2026-11。dead-band。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。改正ゲート目安 2026-11。dead-band。

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。改正ゲート目安 2026-11。dead-band。

旧 ID: T-SHADOWCONST（非公開の作業台帳から 2026-08-25 移送）。

## 2026-08-26 triage 照合（無人 cycle）

未成立 → `blocked` 維持。改正ゲート目安 2026-11。dead-band。

## 2026-08-29 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`value-layer-2026-08-28.json` の `constitution.due` = `false`（改正ゲート目安 2026-11）。dead-band。

## 2026-09-02 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`value-layer-2026-08-28.json` の `constitution.due` = `false`（改正ゲート目安 2026-11）。dead-band。

## 2026-09-05 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`value-layer-2026-09-04.json` の `constitution.due` = `false`（改正ゲート目安 2026-11）。dead-band。

## 2026-09-09 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`value-layer-2026-09-04.json` の `constitution.due` = `false`（days_since 26 / interval 83、改正ゲート目安 2026-11）。dead-band。

## 2026-09-12 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`value-layer-2026-09-11.json` の `constitution.due` = `false`（days_since 33 / interval 83、改正ゲート目安 2026-11）。dead-band。

## 決定の記録

記録時点の経過（現在の state は frontmatter の `state:`）。

blocked 2026-08-16 — 計器側の予約読み値（run 1+2 / IPD 合成 / 床アンカー）は 2026-08-11 に取得
完了し、残るは次回憲法改正ゲートでの消費のみ（2026-08-25）。直近の照合 2026-08-24 も
dead-band。

## Next action

- 再開条件: 次回の憲法改正ゲートが開く（ADR-0091 の 83 日間隔、2026-10-31）
- 照合先: `pipeline/value-layer/value-layer-*.json` の `constitution.due`
- 次の照合日: 2026-10-31（`state: done` は、そのゲートで shadow 読みが実際に消費された記録が `docs/evidence/adr-0092/` に入ってから。事前登録は [RFC-0055](0055-amendment-outcome-preregistration.md)）
- 計器側: [ADR-0092](../docs/adr/0092-shadow-constitution-instrument.md) の Review-when / Consumption plan（読み手 = 2026-10-31 の改正ゲート、2027-Q1 までに改正が無ければ計器ごと撤去）と系列表 `docs/evidence/adr-0092/shadow-series.md`
- 成立時: accepted（diff / IPD ベンチと並ぶ第 3 の材料としての消費のみ）

## 2026-09-16 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`value-layer-2026-09-11.json` の `constitution.due` = `false`（days_since 33 / interval 83、reason NOT_DUE、改正ゲート目安 2026-11）。次の weekly 走行（2026-09-18）まで読み値は変わらない。dead-band。

## 2026-09-19 triage 照合（無人 cycle、stocktake 併走）

未成立 → `blocked` 維持。`value-layer-2026-09-18.json` の `constitution.due` = `false`（days_since 40 / interval 83、NOT_DUE、改正ゲート目安 2026-11）。dead-band。

## 2026-09-23 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`constitution.due` の最新読み値は 2026-09-18 走行ぶん（NOT_DUE、改正ゲート目安 2026-11）。次の weekly 走行は 2026-09-25。dead-band。

## 2026-09-26 triage 照合（無人 cycle、stocktake 併走）

未成立 → `blocked` 維持。`pipeline/value-layer/value-layer-2026-09-25.json` の `constitution` = due false（days_since 47 / interval 83、NOT_DUE）。dead-band。

## 2026-09-28 triage 照合（対話 cycle）

未成立 → `blocked` 維持。最新の weekly 走行は 2026-09-25（読み値は 09-26 照合で NOT_DUE）、次は 2026-10-02。dead-band。

## 2026-09-30 triage 照合（無人 cycle）

dead-band。最新の読み値は `value-layer-2026-09-25.json`（NOT_DUE 47 / 83）、次の weekly 走行は 2026-10-02。

## 2026-10-03 triage 照合（無人 cycle、stocktake 併走）

dead-band。`value-layer-2026-10-02.json` の `constitution` = due false（days_since 54 / interval 83、NOT_DUE）。

## 2026-10-07 triage 照合（無人 cycle）

dead-band。最新は `value-layer-2026-10-02.json`（NOT_DUE、54 / 83）。

## 2026-10-12 triage 照合（無人 cycle、stocktake 併走）

dead-band。`value-layer-2026-10-09.json` の `constitution` = NOT_DUE（61 / 83 日、ロードマップの due 目安は 10-31）。

## 2026-10-14 triage 照合（無人 cycle）

dead-band。最新は `value-layer-2026-10-09.json` のまま（`constitution` NOT_DUE、61 / 83 日）。次の読みは 10-16 の weekly。

## 2026-10-17 triage 照合（無人 cycle、stocktake 併走）

dead-band。`value-layer-2026-10-16.json` の `constitution` = NOT_DUE（68 / 83 日、due は 10-31 頃）。

## 2026-10-21 triage 照合（無人 cycle）

dead-band。最新は `value-layer-2026-10-16.json` のまま（`constitution` NOT_DUE、68 / 83 日、due は 10-31 頃）。次の読みは 10-23 の weekly。

## 2026-10-24 triage 照合（無人 cycle、stocktake 併走）

dead-band。`value-layer-2026-10-23.json` の `constitution` = NOT_DUE（75 / 83 日、due は 10-31 頃）。次の読みは 10-30 の weekly。

- 10-31 の既定: D-P0-07-1 = B（オーナー、2026-10-24）— 読むだけで改正は起動しない。A（起動）は、shadow 系列（4 点以上）と事前登録 RFC-0055 が 10-31 までに両方そろった場合のみ。D-P0-07-2（配線 / 手動 / 撤去）は 10-31 のデータまで未決

## 2026-10-31 土曜ゲート（by: owner）

- D-P0-07-1 = **A**（起動）。A の条件（shadow 系列 4 点 = `docs/evidence/adr-0092/shadow-series.md` 行 1–4、RFC-0055 accepted 2026-10-28）が揃った。10-24 の B 既定を置き換える。改正は `docs/runbooks/constitution-amendment.md` に沿って別セッションで起動し、採択は改めて人間ゲート
- D-P0-07-2 = **A**（手動のまま）。10 月 2 run（0.813 / 0.769）は 8 月（0.814 / 0.798）と同一コーパスの揺れ 0.044 の内
- 本 RFC は改正セッションで shadow の読み値を第 3 の材料として消費した時点で done にする

## 非公開ノート参照の扱い（P3-02.5、2026-10-24 の棚卸し）

- 旧 ID の行の「非公開の作業台帳から移送」: 台帳は 2026-08-25 に公開 `rfcs/` へ移送済み（本ファイルがその昇格先）。元の置き場は不要 — **失われてよい**。

## 2026-10-31 triage 照合 (by: judge)

verdict: accepted（語彙の整理: `blocked` → `accepted`）

再開条件が成立した。照合先は 2 つ: `value-layer-2026-10-30.json` の `constitution` は 82 / 83 日で NOT_DUE だが、due の日付（2026-08-09 + 83 日 = 10-31）は今日で、土曜ゲートが `gate_record`（`run_id` gate-2026-10-30）の `constitution_amendment` に「D-P0-07-1=A: 改正を runbook に沿って別セッションで起動」と記録した。成立時の規定どおり `accepted`。build には出さない — 消費は改正セッション（値層の人間ゲート）の中で起き、`done` はその記録が `docs/evidence/adr-0092/` に入ってから。
