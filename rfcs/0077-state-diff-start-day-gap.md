---
id: T-STATE-DIFF-START-DAY-GAP
state: done
filed_by: weekly-2026-11-06-090002
producer: scripts/weekly-analysis.sh:186
state_since: 2026-11-11
origin: gate
review-when: 週次の State Diff が窓の初日の commit を含むようになった、または State Diff の段が退役した
alignment: repair
title: 週次 State Diff の窓の初日の穴を閉じる（開始 commit を前週の終了 commit に揃える）
admitted-by: shimo4228 2026-11-07
---

## タスク

週次 materials の State Diff は、連続する 2 つの週の窓のあいだに穴がある。窓の初日に入った data repo の commit は、どちらの diff にも載らない。

- 開始 snapshot は「`START_DATE` の 23:59:59 以前で最後の commit」（`scripts/weekly-analysis.sh:186`）。前週の終了 snapshot は「前週 `END_DATE` の 23:59:59 以前で最後の commit」（`:191`）。既定では `END_DATE` = 昨日（`:83`）、`START_DATE` = END − 6（`:94`）なので、土曜の連続実行では日付の窓が隣接して重ならない。
- そのため `START_DATE` 当日の commit は、開始 commit 自身の変更も含めて、diff にも承認 join にも入らない。承認 join は `start < ts <= end` の半開区間（`scripts/value_layer_approval_join.py:127-132`）。
- 値層の変更を承認する土曜ゲートは、この `START_DATE` の日に走る。

変更案:

- 開始 commit を「`START_DATE` の前日 23:59:59 以前で最後の commit」に変え、前週の end commit と一致させる。
- 連続 2 窓で start(N) == end(N−1) を確かめるテストを足す。
- ADR-0099 の State Diff の記述に追補を入れる。

producer: `scripts/weekly-analysis.sh:186`

## 詳細

- 診断: `weekly-2026-11-06-findings.md` の F1.1。出典は同週の観察文書 Exceptions 2（被覆の穴）と Exceptions 1（`rules/` の 2 ファイル）。
  - Exceptions 1 の中身: 2 ファイルが承認行との一致を失った（承認 hash `0743f0887fcfdead` / `85ba74660869a761`、`audit.jsonl:60-61` → live `a039abe1217a8490` / `e6686955a88a5446`）。一方、窓の `rules/` diff は "No changes"。
- Source quote（materials、決定論）:
  - 前週の窓: knowledge snapshot `d44544a` @ 2026-10-24T05:30 JST → `b3b061e` @ 2026-10-30T05:30 JST。承認窓は 2026-10-23T20:30:10Z → 2026-10-29T20:30:14Z。
  - 今週の窓: `60adf4d` @ 2026-10-31T23:10 JST → `5a5432e` @ 2026-11-06T05:30 JST。承認窓は 2026-10-31T14:10:34Z → 2026-11-05T20:30:14Z（"exclusive of the start commit"）。
  - 2026-10-29T20:30:14Z..2026-10-31T14:10:34Z はどちらの窓にも入らない。
- whole-log の live-text reconciliation だけが穴の影響を受けない。今週の `rules/` 0 → 2 の上昇はこの経路でだけ見えたが、帰属させる diff が無い。
- 関連: ADR-0099、ADR-0012 / ADR-0050（承認 provenance join）

## 2026-11-07 triage 照合 (by: judge)

verdict: ask-owner

前提を確かめた: 開始 commit は `START_DATE` の 23:59:59 以前の最後の commit（`scripts/weekly-analysis.sh:186`）、前週の終了は前週 `END_DATE` の 23:59:59 以前（`:191`）。窓は日付で隣接するので、`START_DATE` 当日の commit はどちらの diff にも入らない。採否を digest で聞く。

## 2026-11-07 著者回答 (by: owner)

accepted（triage digest 2026-11-07 を推奨どおり承認）。開始 commit を `START_DATE` の前日 23:59:59 以前の最後の commit にし、前週の end commit と一致させるテストを 1 本足す。build は次の cycle。

## 2026-11-11 triage 照合 (by: judge)

verdict: dispatched

RFC-0078 と同じ build（S52、Agent build、packet `docs/plans/rfc-0077-s52-state-diff-gap-and-reply-share.md`）に出した。2 つの小さな script 修正で、commit は 2 本に分ける。

## 2026-11-11 検収 (by: judge)

S52（[packet](../docs/plans/rfc-0077-s52-state-diff-gap-and-reply-share.md)）を main に取り込んだ（`8ecaeda8`、ff-only）。開始 snapshot は `START_DATE` の前日 23:59:59 以前の最後の commit になり、既定の連続実行で週 N の開始 commit と週 N−1 の終了 commit が一致する（`test_consecutive_weeks_share_their_boundary_commit`）。ADR-0099 に日付つきの注記。判断役の verify exit 0、別プロセスの review で correctness の指摘 0 件。optional の 1 つ（materials の見出し `## Agent State Diff ($START_DATE -> $END_DATE)` が開始日を START_DATE と書いたまま）は記録だけ。
