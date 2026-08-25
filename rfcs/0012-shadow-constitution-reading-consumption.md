---
state: blocked
state_since: 2026-08-16
---

## タスク

**shadow 憲法計器の読み値を次回 amend-constitution ゲートで消費する**（ADR-0092、2026-08-11 出荷）。`shadow-constitution` を手動で **2 回以上**（同一コーパスで連続 2 回 = 計器自身のノイズ床、＋できれば数週おいて 1 回 = トレンド）実行し、`logs/constitution-shadow.jsonl` の cosine と乖離条項を読む。次回改正ゲート（weekly packet §8 の constitution_due が鳴る頃、目安 2026-11 — ADR-0091 の 84 日間隔）で diff / IPD ベンチ（ADR-0090）と並ぶ第 3 の材料として使い、その時点で weekly チェーンへの月次配線の採否もデータで決める。JST 0/6/12/18 のセッション窓は避けて実行

## 着手条件

再開条件: 次回の憲法改正ゲートが開く（ADR-0091 の 84 日間隔、目安 2026-11）
照合先:   weekly packet §8 の `constitution_due`
成立時:   ready（計器側の予約読み値は取得完了済み。残るは diff / IPD ベンチと並ぶ第 3 の材料としての消費のみ）

## 詳細

[ADR-0092](../docs/adr/0092-shadow-constitution-instrument.md) Decision 5。**run 1+2: 2026-08-11 完了**（08:11 / 08:19 JST、同一コーパス 50 本、両方 verdict ok）— cosine 0.814 / 0.798（ノイズ床 0.016）、セクション目録は 4 公理と完全乖離しつつ 4 テーマは両 run で安定、Boundless Care 両 run 不在（摩擦バイアス再現）。evidence: docs/evidence/adr-0092/。**IPD 合成読み値も取得済み**（2026-08-11、現行 vs shadow run 1: no readable signal — care 公理欠落でも協調効果は保存、Δeffect +0.01/+0.02/+0.06 全て床内。ipd-shadow-reading.md）。**床アンカー測定済み**（2026-08-11: 無関係床 0.42–0.49、同ジャンル帯 0.66–0.75、shadow 0.798/0.814 = 同ジャンル帯上限 +0.05〜0.06 — 形の共有だけでは説明できない内容収束。evidence の shadow-run-1-reading.md §Floor anchor）。**計器側の予約読み値は全て取得完了** — 残るは次回改正ゲートでの消費のみ

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-19、改正ゲート目安 2026-11。dead-band。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。改正ゲート目安 2026-11。dead-band。

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。改正ゲート目安 2026-11。dead-band。

旧 ID: T-SHADOWCONST（.notes/tasks から 2026-08-25 移送）。

## Status

blocked（≈ issue-tracker 標準の blocked。RFC 標準に state 語彙は無い） — 計器側の予約読み値（run 1+2 / IPD 合成 / 床アンカー）は 2026-08-11 に取得
完了し、残るは次回憲法改正ゲートでの消費のみ（2026-08-25）。直近の照合 2026-08-24 も
dead-band。

## Next action

- 再開条件: 次回の憲法改正ゲートが開く（ADR-0091 の 84 日間隔、目安 2026-11）
- 照合先: weekly packet §8 の `constitution_due`
- 成立時: ready（diff / IPD ベンチと並ぶ第 3 の材料としての消費のみ）
