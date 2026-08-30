---
state: withdrawn 2026-08-30
state_since: 2026-08-16
---

## タスク

任意実験: 公理除去 A/B（旧 promptfoo evals/ は ADR-0072 で削除。[ADR-0089](../docs/adr/0089-llm-behavioral-eval-layer-on-deepeval.md) が evals/ を comment 面で再建したので足場は復活したが、この実験に要る **distill 面**は未実装 — Face B として後送中）

## 着手条件

再開条件: `evals/` の distill 面（Face B）が実装されること
照合先:   `evals/` 配下に distill 面の足場が在るか（ADR-0089 が再建したのは comment 面のみ）
成立時:   accepted（公理あり/なしの A/B。`get_distill_system_prompt()` が単一レバーで insight にも自動波及）

旧条件「§B1 窓明けと同時期」は **2026-06-17 に成立済み**（`T-B1` 参照）だが実 blocker では
なかった — この実験は公理の有無を distill 出力で比較するので、comment 面だけの足場では走らない。
2026-08-16 の棚卸しで、成立済みの条件が blocker として居座っていたのを実 blocker へ差し替えた。

## 詳細

handoff T3（`.notes/handoff-2026-07-03-adr-0072-phase3.md`）

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`evals/datasets/` は `comment_golden.jsonl` のみ、`evals/baselines/` も comment_golden 系のみ — distill 面（Face B）の足場は無い。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`evals/datasets/` は `comment_golden.jsonl` のみ、`evals/baselines/` も comment_golden 系 3 本のみ — distill 面の足場は無い。

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。`evals/datasets/` は `comment_golden.jsonl` のみ — distill 面の足場は無い。

旧 ID: T-C1（.notes/tasks から 2026-08-25 移送）。
本文中の `.notes/…` はローカルの作業ノート（gitignored、clone 先には存在しない）を指す。

## 2026-08-26 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`evals/datasets/` は `comment_golden.jsonl` のみ — distill 面の足場は無い。

## 2026-08-29 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`evals/datasets/` は `comment_golden.jsonl` のみ、`evals/baselines/` も comment_golden 系 3 本のみ — distill 面（Face B）の足場は無い。

## 2026-08-30 withdrawn（著者判断 — 発火源が誰の予定にもない）

`blocked` を解いて終端化する。

再開条件は「`evals/` の distill 面（Face B）が実装されること」だが、**ADR-0089 自身が
distill 面を明示的に scope 外と宣言している**（`docs/adr/0089-llm-behavioral-eval-layer-on-deepeval.ja.md:37`
「その distill 面は引き続き scope 外である」、`:679`「distill face は予約済み」）。予約は
予定ではない。この行は、誰も着手を計画していない仕事の完了を待ち続けていた。

本文自身も「任意実験」と位置づけている。公理の有無を distill 出力で比較したくなったら、
`get_distill_system_prompt()` が単一レバーであること（insight にも自動波及する）は本文に
残るので、Face B が実際に建った時点で起票し直す方が安い。

## Status

blocked — 公理除去 A/B は `evals/` の distill 面（Face B）が未実装のため走らない
（2026-08-25）。直近の照合 2026-08-24 も未成立（`evals/datasets/` は `comment_golden.jsonl`
のみ）。

## Next action

- 再開条件: `evals/` の distill 面（Face B）が実装されること
- 照合先: `evals/` 配下に distill 面の足場が在るか（ADR-0089 が再建したのは comment 面のみ）
- 成立時: accepted（公理あり/なしの A/B。`get_distill_system_prompt()` が単一レバーで insight
  にも自動波及）
