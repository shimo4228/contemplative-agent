---
state: blocked
state_since: 2026-08-16
---

## タスク

heartbeat 終了条件の具体化（ADR-0080 の Ending design 層で予約 — 「いつ止めるか」の判定基準を別 ADR で確定する）

## 着手条件

再開条件: 計器が代謝の定常状態を示すこと
照合先:   `T-P3`（`done 2026-08-16`）の縦断読み
          — `.notes/memory-pipeline-phase3-reading-2026-08-16.md`。
          `T-INSIGHT-OBS` は 2026-07-25 に終端化済み
成立時:   accepted（ADR-0080 の Ending design 層で予約された「いつ止めるか」を別 ADR で確定する）

**2026-08-16 の照合: 未成立。`blocked` を維持する。** T-P3 の縦断は定常の逆を示した —
corpus 1,463 → 5,832（4.0 倍）、pairwise 0.55 → 0.58 で**まだ動いている最中**、
コーパスの 75% が 6 週間で入れ替わった。代謝は加速側にあり、止め時の判定に入れない。

この行の再開条件は**イベントでなく状態**で書かれているので、参照先タスクが中止・完了しても
宙に浮かない。同日に T-GAP1 の A/B 中止で宙に浮いた 2 行（T-UTIL-SELECT /
T-INSTRUMENT-EVENT-READ）との対比。書き方はこちらを既定にする。

## 詳細

[ADR-0080](../docs/adr/0080-north-star-layered-end-state.md)

## 2026-08-19 triage 照合（無人 cycle）

dead-band（08-16 の T-P3 照合から状態・条件文とも不変）。未再読。

## 2026-08-22 triage 照合（無人 cycle）

dead-band（08-16 の T-P3 照合から状態・条件文とも不変）。未再読。

## 2026-08-24 triage 照合（手動 cycle）

dead-band（08-16 の T-P3 照合から状態・条件文とも不変）。未再読。

旧 ID: T-ENDSTATE-TERM（.notes/tasks から 2026-08-25 移送）。
本文中の `.notes/…` はローカルの作業ノート（gitignored、clone 先には存在しない）を指す。

## 2026-08-26 triage 照合（無人 cycle）

dead-band（08-16 の T-P3 照合から状態・条件文とも不変）。未再読。

## Status

blocked — 2026-08-16 の T-P3 縦断は定常の逆（corpus 4.0 倍、pairwise 0.55 → 0.58）を
示し、代謝は加速側にあるので止め時の判定に入れない（2026-08-25）。直近の照合 2026-08-24 は
dead-band。

## Next action

- 再開条件: 計器が代謝の定常状態を示すこと（イベントでなく状態で書いてある）
- 照合先: `T-P3`（`done 2026-08-16`）の縦断読み
- 成立時: accepted（ADR-0080 の Ending design 層で予約された「いつ止めるか」を別 ADR で確定する）
