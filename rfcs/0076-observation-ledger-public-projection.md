---
title: 観察台帳の公開用の写しを公開データ repo に置くか決める
state: draft
state_since: 2026-11-05
review-when: RFC-0067 の S47 が main に入り、毎朝の sync が reports/analysis/ を公開しなくなった
origin: idea
alignment: repair
---

## Summary

RFC-0067 で毎朝の sync が `reports/analysis/` を公開しなくなると、観察台帳 `reports/analysis/observation-ledger.jsonl` は公開データ repo に一切出なくなる。公開用の写し（たとえば `pipeline/` 配下）を置くか、置くならどの欄を出すかを決める。

## Motivation

由来: build 提案 (S47)

- S47（branch `claude/task-jeyn3u`、未 merge）は daily sync の rsync に `--exclude=/reports/analysis/` を足し、土曜のゲートが週次レポートの md を 1 本ずつ promote する形にする。promote できるのは md だけで、台帳の jsonl は対象外。
- 再現（S47 の報告）: 台帳を変えた home で sync を 2 回走らせると、データ repo の写しは 2026-11-04 より前の行で止まる。
- 公開データ repo（`shimo4228/contemplative-agent-data`）の `reports/analysis/observation-ledger.jsonl` は、外の読み手が週次の観察を追える唯一の機械可読の面だった。

## Unresolved questions

- 台帳の行に、他エージェントの投稿の文（D-P3-05-7 = A で公開しないと決めたもの）が入っているか。入っていれば、写しはその欄を落とす。
- 置き場所（`pipeline/` か別か）と、更新の経路（毎朝の sync か、土曜の promote か）。

## Status

draft — 2026-11-05 起票（オーナーの承認、対話セッション）。S47 の merge 待ち。

## Next action

S47 が merge された後の土曜のゲートで、台帳の行の中身を確かめてから採否を決める。

## 2026-11-07 triage 照合 (by: judge)

verdict: ask-owner

review-when が成立した（S47 は `e2ba431d` で main に入った）。台帳を確かめた: 観察行の本文には相手の入力を引いた語がある（例: O-004 は相手の短い入力をそのまま引く）。一方、週次文書は `## Ledger` 節に各観察を 1 行ずつ持ち、今日から promote で公開される（`weekly-2026-11-06.md:56`）。機械可読の写しを足すかを digest で聞く。
