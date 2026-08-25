---
state: candidate
state_since: 2026-08-24
origin: idea
---

## タスク

**週次レポート A–E の中身そのものを再設計する**（著者指示 2026-08-24、ADR-0098 の再設計討議中に
「そもそもレポートの内容が微妙」と明言）。ADR-0098 は配管（誰がいつどう生成するか）だけを
変え、節定義 `config/prompts/weekly-analysis.md`（A–E の構成・quote 規約・E 中心の設計）は
意図的に無変更のまま新 skill `/weekly-report` に引き継いだ。内容の再設計はこのタスクで別途行う。

観測の材料: 直近 3 週の F1 が 11 中 8 件配管起因でエージェント本体への知見をほぼ産んでいない
（`.notes/pipeline-substrate-survey-2026-08-22.md`）— レポートが「読む価値のある観察」を
出せているかから問い直す。

## 詳細

`config/prompts/weekly-analysis.md`（節定義の正本）、`config/prompts/principles.md`、
[ADR-0040]（A–E / F 分離の原型）、[ADR-0098]（配管の再設計 — 内容は scope 外と明記）。
採否・スコープはオーナー判断（candidate 止まり）。

旧 ID: T-REPORT-CONTENT（.notes/tasks から 2026-08-25 移送）。
本文中の `.notes/…` はローカルの作業ノート（gitignored、clone 先には存在しない）を指す。

## Status

candidate（≈ draft） — 週次レポート A–E の中身の再設計は著者指示 2026-08-24 で起票され、採否・
スコープはオーナー判断待ち（2026-08-25）。ADR-0098 は配管だけを変え、節定義
`config/prompts/weekly-analysis.md` は無変更のまま引き継いだ。

## Next action

- 採否判断待ち（本文が「採否・スコープはオーナー判断（candidate 止まり）」と明記）
- 判断材料: 節定義の正本 `config/prompts/weekly-analysis.md` と、直近 3 週の F1 が 11 中 8 件
  配管起因という観測（`.notes/pipeline-substrate-survey-2026-08-22.md`）
