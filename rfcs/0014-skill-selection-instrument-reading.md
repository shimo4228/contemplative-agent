---
state: blocked
state_since: 2026-08-22
---

## タスク

skill 選択計器の定期読み — 次の読み窓 2026-09-05 まで selector を変更しない。

**第 2 読み完了（2026-08-08、[skillsel-reading-2026-08-08.md](../docs/evidence/adr-0081/skillsel-reading-2026-08-08.md)）— 窓 07-09〜08-08、30 日 / 9,357 レコード**。4 基準の読み: (1) **enforced は完全回復。ON 後 15 日連続で judged 1,316/1,316 = 100%** — 30 日窓の 51.5% は rollout 日跨ぎの希釈で、T-PLIST-FLAG-REVERT の「38% しか効いていない」は測定アーティファクトだった（同行に訂正を記録） (2) **fail-open 26 日連続 0**、窓内唯一は既知の 7/12 インシデント → T-FAILOPEN-OVERFLOW を (c) で決着 (3) **幻覚率は 0.5% → 2.2%（enforcement 後窓 3.95%）に上昇し、catalog サイズと相関** → T-SKILLSEL-HALLUC-CATALOG に分離 (4) **寡占は catalog 2.4 倍でも維持**（上位 3 = judged の 77.2/73.8/65.6%、selected/action は p50 5 のまま）→ description 過広の証拠強化。削減は ON 後 p50 87.0%。never-selected は 4 件だが露出で条件付けると 実質 1 件（`pre-processing-state-validation`、15 日 1,316 回でゼロ）。**読みから実装したもの**: フラグ退役（T-PLIST-FLAG-REVERT）、fail-open 仕様明記（T-FAILOPEN-OVERFLOW）、計器の欠落 3 点（enforced 比率 / 日次内訳 / never-selected 露出 — 今回 ad-hoc 2 本を要した理由）。**読みが許可しなかったもの**: selector 変更（幻覚の機構未確定）と description 監査の実行（値層介入なので T-CONST-AMEND / T-SKILLNAME-BACKFILL と同時に動かせない）。初回読み（2026-07-24、`.notes/skillsel-reading-2026-07-24.md`）と enforcement 実装・本番 ON の経緯はそちら参照

## 着手条件

再開条件: 次の読み窓 2026-08-22 に到達
照合先:   日付、および `logs/skill-selection-*.jsonl` の蓄積
成立時:   ready（読む対象は本文の (a)(b)(c)。それまで selector を変更しない）

## 詳細

[skillsel-reading-2026-08-08.md](../docs/evidence/adr-0081/skillsel-reading-2026-08-08.md)、[ADR-0081 Amendment 2026-08-08](../docs/adr/0081-skill-selection-two-pass-injection-enforcement.md)、[ADR-0076](../docs/adr/0076-skill-selection-shadow-instrument.md)、skill 選択研究の参照ノート（`.notes/ref-skill-selection-research-2026-07-26.md`）

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-19 < 読み窓 2026-08-22（次回 Sat 14:07 の cycle で成立見込み）。

## 2026-08-22 triage 照合（無人 cycle）

成立 → `ready`。日付 2026-08-22 = 読み窓到達。`logs/skill-selection-2026-08-21.jsonl` 等が継続蓄積（ファイル単位 76 行）。第 3 読み（窓 08-09〜08-22）を measurement として T-SKILLSEL-HALLUC-CATALOG と 1 packet で dispatch。selector 変更は packet で禁止。

## 2026-08-22 triage — 第 3 読み完了（S1 measurement、Opus agent、read-only）

読み: `.notes/skillsel-reading-2026-08-22.md`（窓 08-09〜08-22、judged 1,143）。判断役の検収: tracked 変更ゼロ、Ollama 不使用、b64 未 decode、前提 5 件成立（`core/skill_selection.py:449-506`）。
4 基準: enforced 100%（ON 後 29 日連続）/ fail-open 40 日連続 0 / judged-empty 0 / 幻覚 19.25%（前回窓 4.83%、4.0 倍 — T-SKILLSEL-HALLUC-CATALOG へ）/ selected p50 5→6 / 削減 p50 89.2%。corpus 最小 33,745 tok で全レコードが NUM_CTX 32,768 超（fail-open = skip 仕様の範囲内）。
(b) 寡占: 上位 3 平均シェア 55.7%→57.6% で不変。**台帳に無い不連続**: 08-15 の clean 段が上位 skill 3 本の frontmatter `name`（selector キー）を改名しており、統合だけを前提に読むと首位が 65.7%→32.2% に見えるが同一ファイルで 65.7%→66.4%。(c) `pre-processing-state-validation` は 29 日 2,459 回露出でゼロ継続、0 選択かつ全露出は 4→6 件。
前回 §7 の計器欠落 3 点 + 第 4 点は全部 report に載った（`skill_selection.py:904/926/998/948`）。
読みが出した起票候補（判断役は起票しない、オーナー判断）: selector キー改名の記録経路 / report の窓指定 + catalog 条件付け + 機構別幻覚率 / corpus トークン軸 / boundary-assumption-verification 3.6→28.8% の description 差分照合。diff 外 MEDIUM 1 / LOW 2 は読みメモ末尾に残し起票しない。

## 着手条件（2026-08-22 更新）

再開条件: 次の読み窓 2026-09-05 に到達（窓 08-23〜09-05、catalog 57 起点）
照合先:   日付、および `logs/skill-selection-*.jsonl` の蓄積
成立時:   ready（読む対象は読みメモ §7 の (a)(b)(c)。それまで selector を変更しない）

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。日付 2026-08-24 < 読み窓 2026-09-05。

旧 ID: T-SKILLSEL（.notes/tasks から 2026-08-25 移送）。
本文中の `.notes/…` はローカルの作業ノート（gitignored、clone 先には存在しない）を指す。

## Status

blocked（≈ issue-tracker 標準の blocked。RFC 標準に state 語彙は無い） — 第 3 読み（窓 08-09〜08-22、judged 1,143）は 2026-08-22 に完了し、次の読み窓
2026-09-05 まで selector を変更しない（2026-08-25）。直近の照合 2026-08-24 も未成立。

## Next action

- 再開条件: 次の読み窓 2026-09-05 に到達（窓 08-23〜09-05、catalog 57 起点）
- 照合先: 日付、および `logs/skill-selection-*.jsonl` の蓄積
- 成立時: ready（読む対象は読みメモ §7 の (a)(b)(c)。それまで selector を変更しない）
