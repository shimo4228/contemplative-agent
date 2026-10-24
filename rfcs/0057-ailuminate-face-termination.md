---
title: AILuminate 安全面（探索面）を終端し、runbook から外してローカル judge の面だけを残す
state: accepted
state_since: 2026-10-24
review-when: 憲法を第三者 judge に送る実験が別の RFC で承認される（D-P3-03-4 / D-P1-11-4）、または共著者の harness が repo 内の手順として取り込まれる
admitted-by: shimo4228 2026-10-24
alignment: instrument
---

## Summary

2026-08-09 の改正 run で付けた AILuminate 安全面（探索面、T-CONST-SAFETY-FACE）を終端する。runbook から外し、ローカル judge での置換もしない。

## Motivation

[ADR-0090](../docs/adr/0090-ipd-two-arm-instrument-for-constitution-amendments.md) の Negative に書いたとおり、この面は (1) 未較正（null pair が無く、run 間の揺れは共著者の 4 run の約 1.6 ポイントしか手がかりが無い）、(2) 両憲法テキスト（値層）を第三者 API に送り、security by absence と衝突する、(3) repo 内に再実行の手順が無い（harness は共著者の repo `aelwood/contemplative_alignment`）。この追跡タスクは RFC 台帳へ移送した時に孤児になり、RFC に ailuminate / SAFETY-FACE の項目が 0 件のまま runbook は「任意の探索面」と書き続けていた。放置すると、次の改正で手で再び走る。

D-P3-03-2 = A（オーナー、2026-10-24）: 正式に退役する。

## Reference-level explanation

### 決定事項

- runbook `docs/runbooks/constitution-amendment.md` から AILuminate 面を外し、終端を一行で書く（同じ変更）。ADR-0090 に dated amendment（同じ変更）
- 2026-10-31 のゲートでも以後も走らせない。ローカル judge の refusal セットで置換することもしない（置換案は取らなかった）
- 2026-08-09 の報告書（`docs/evidence/adr-0090/ailuminate-two-arm-report.md`）は日付つきの観察として残す。数字は observation で signal ではない（judge 失敗 9/300・15/300、較正なし）

### 装置の記録（再現する人のために）

harness `aelwood/contemplative_alignment@5242e74`、test モデル Haiku 4.5、n=50、seed 42、judge は claude-sonnet-5（元の judge が 404 になり、`temperature` 固定の scorer が使えなくなったため差し替え。絶対値は共著者の 2026-04-13 の表と比較できない）。

### 生出力の所在と再配布（open、オーナー確認待ち）

生出力 `detailed_evaluations_20260809_210315.json` / `..._210405.json` は `docs/evidence/adr-0090/` の 9 ファイルに含まれず、報告書が名前を引くだけ。本体の sandbox にも無い（共著者 harness の clone にも無い）。決めること:

1. どのマシンのどのパスにあるか（Mac 側で `find` して所在を本 RFC に書く）
2. AILuminate のプロンプト本文を含むなら再配布しない（ライセンス確認が先）。含まないなら evidence に置いてよい
3. 所在が確認できない場合は「紛失、報告書の数字のみが残る」と書く

## Falsification / consumption (ADR-0101)

計器の追加ではなく終端なので消費計画は不要。再開条件は review-when のとおり。
