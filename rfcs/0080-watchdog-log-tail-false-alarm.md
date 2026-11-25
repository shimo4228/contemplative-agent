---
title: 見張り役の「ログ末尾に error がある」判定を、生成文でなくログの行の形で見る
state: done
state_since: 2026-11-25
review-when: 判定を直した後、distill / insight / backup の成功した回が ❌ にならない週が 4 週続いた、または見張り役の判定が別の方式（終了コードや完了行）に置き換わった
origin: incident
alignment: repair
admitted-by: shimo4228 2026-11-21
---

## Summary

`scripts/pipeline_watchdog.sh` の `log_healthy` が、ログ末尾 30 行に `error:` という文字列があるだけで ❌ にする判定を、ログの行の形（`[ERROR]` の行・`Traceback` の行頭）に絞り、成功した回が誤報にならないことをテストで固定する。

## Motivation

- 2026-11-21 の土曜ゲートの Step 0 で、`reports/PIPELINE-STATUS.md` が distill を ❌（「ran for 2026-11-20 but the log tail shows errors」）にした。実際の run は最後まで終わっていた（`logs/distill-launchd.log` の最後の記録行が `Distill complete: 157 added, 12 updated` と `Distill ledger: 78/78 episodes recorded`、2026-11-21 04:03 JST）。
- 当たったのは、distill が完了行の後にログへ書き出す生成済みの気づきの JSON（約 350 行）の 1 文に含まれる「structural error: the conflation …」という言い回しだった。判定 `grep -qiE 'traceback|^ERROR|error:'`（`scripts/pipeline_watchdog.sh:127`）の `error:` は行頭に縛られていないので、生成文の中身に当たる。
- 誤報が続くと ❌ が信用されなくなり、本当の失敗を見落とす入口になる。ゲートは ❌ を承認より先に読む（weekly-gate Step 0 (c)）。

## Reference-level explanation

- producer: `scripts/pipeline_watchdog.sh:127`（`log_healthy` の末尾 30 行の判定）。同じ関数を distill / insight / backup ほかの job が使う。
- 生成文がログ末尾に出る経路（distill の stdout に生成済みの気づきの JSON が出ている）は、この RFC では判定の側で扱う。出力の側を止めるかは build が経路を確かめて Report に書く（stdout に出ている理由が分からないまま消さない）。
- 受入: (i) 生成文の中に `error:` を含む成功ログの末尾で ✅ になるテスト (ii) `[ERROR]` の行か `Traceback` の行頭がある末尾で ❌ のままになるテスト（`tests/test_pipeline_watchdog_shell.py` の流儀）(iii) script の冒頭コメントの判定の記述を同じ変更で直す (iv) `./.claude/verify.sh` が exit 0。

## Drawbacks

- 行の形に絞ると、形の違う失敗（例: 小文字の `error:` で始まる CLI の出力）を拾わなくなる。各 job のログで実際に出た失敗の形を確かめてから絞る。

## Status

done 2026-11-25 — S58（[packet](../docs/plans/rfc-0080-s58-watchdog-log-line-shape.md)、`ed1fe7c7`）。2026-11-21 の triage digest で起票を承認（土曜ゲートの alert 由来）。

## Next action

なし（review-when の 4 週の読みは見張り役の ✅ が持つ）。

## 2026-11-25 triage 照合 (by: judge)

verdict: ready

起票時の Next action どおり packet に切り、S58 として Agent build（worktree、opus）に出した（packet は branch の最初の commit で `docs/plans/rfc-0080-s58-watchdog-log-line-shape.md`）。前提: 判定は今も `scripts/pipeline_watchdog.sh:127` の `grep -qiE 'traceback|^ERROR|error:'`。Ollama を使わない。

## 2026-11-25 検収 (by: judge)

S58 を取り込んだ（[packet](../docs/plans/rfc-0080-s58-watchdog-log-line-shape.md)、`ed1fe7c7`、ff-only、差し戻しなし）。`log_healthy` の末尾 30 行の判定は、大文字小文字を区別し行頭に固定した 4 つの形（`Traceback (most recent call last):`、`XxxError:` / `XxxException:` の最終行、ログ書式の `[ERROR]` / `[CRITICAL]` 行、`ERROR` / `Error:` / `error:` / `fatal:` の行頭）だけを失敗と数える（`scripts/pipeline_watchdog.sh` の `LOG_FAILURE_LINE` とその直前のコメント）。テストは `tests/test_pipeline_watchdog_shell.py::TestLogTailLineShape`（成功 1 件は旧判定で赤、失敗 8 件は ❌ のまま）。build の照合: distill の 171 回分で旧判定が反応したのは 11-21 の誤報 1 回だけ、新判定は 0 回。生成文がログに出る経路は `cli/memory_cmds.py:89` の `print(result)`（出力側は変えていない — commit 本文に LOW 1 行）。判断役の verify は rebase 後の先頭で exit 0（6543 passed）。別プロセスの review は correctness の指摘 0 件。optional 3 件（`prog: error:` の CLI 行、名前が Error / Exception で終わらない例外の最終行、字下げされた ExceptionGroup の行）は採らない: プロセスが失敗で終われば launchctl の LastExitStatus が ❌ にし、行の形を絞ることは Drawbacks が想定した範囲。
