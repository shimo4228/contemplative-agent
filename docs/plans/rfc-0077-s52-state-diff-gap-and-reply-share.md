# Kickoff packet — S52: RFC-0077 + RFC-0078（週次 State Diff の窓の初日の穴を閉じる / 表層カウンタに返信の割合を足す）

あなたは task-triage loop の build 役。cwd は `shimo4228/contemplative-agent` の git worktree で、branch は main の先頭から切られている。
最初に、この packet を `docs/plans/rfc-0077-s52-state-diff-gap-and-reply-share.md` に置いて単独で commit する（`docs(plan): rfc-0077 S52 packet`）。
以後の commit はこのファイルを変えない。成果は branch 上の commit で返し、判断役が検収・review して main へ ff-only で取り込む。
境界は rule `boundary.md`、chain は skill `implementation-chain`（Review の行は判断役が回す。background の subagent は Agent tool を持たないので、調査は researcher を起動せず自分で検索する）。
2 つのタスクは独立した小さな script 修正なので、commit を 2 本に分ける（RFC-0077 で 1 本、RFC-0078 で 1 本）。

読むもの: `rfcs/0077-state-diff-start-day-gap.md`、`rfcs/0078-surface-counter-reply-share.md`、`scripts/weekly-analysis.sh`（冒頭コメントと 180〜320 行の State Diff 段）、
`scripts/value_layer_approval_join.py` の Windowing の docstring（半開区間 `start < ts <= end`）、`tests/test_weekly_analysis_shell.py`（State Diff を data repo の一時 git で検査する既存テスト）、
`scripts/surface_counter_scan.py` の `summarize()` / `readings()`、`scripts/observation_ledger.py` の `_band_verdict`、`tests/test_surface_counter_scan.py`、
`docs/decision-history/0099-*.md` の State Diff の記述。

Effort: medium — どちらも既存の段に 1 か所の変更とテスト 1 本

## Goal（決定可能な受入条件）

### RFC-0077（commit 1: `fix(weekly): ... (RFC-0077)`）
1. `scripts/weekly-analysis.sh` の開始 snapshot が「`START_DATE` の**前日** 23:59:59 以前で最後の commit」になる。前日は `date -j -f %Y-%m-%d -v-1d` 形で求める（このファイルは macOS の `date -j` を既に使っている、`:94`）。それより前に commit が無いときの fallback（最初の commit）はそのまま
2. 終了 snapshot（`END_DATE` の 23:59:59 以前で最後の commit）は変えない。結果として、既定の連続実行（END = 昨日、START = END − 6）で、週 N の開始 commit = 週 N−1 の終了 commit になる
3. テストを 1 本以上足す: 一時の data repo に日付を指定した commit を並べ、連続する 2 つの窓（END と END − 7）でスクリプトを走らせ、週 N の開始 commit が週 N−1 の終了 commit と一致すること、`START_DATE` 当日の commit が週 N の diff に載ることを固定する。既存テストの書き方（`tests/test_weekly_analysis_shell.py` の data repo fixture）に合わせる
4. 承認 join（`value_layer_approval_join.py`）の半開区間 `start < ts <= end` は変えない。開始 commit の時刻が前週の終了 commit と揃うので、join の窓も隣接して穴も重なりも無くなる。この理屈を Fix に 2〜3 文で書く
5. 窓の定義を書いている箇所を同じ commit で直す: `scripts/weekly-analysis.sh` の該当コメント（`:184-185` の "nearest commit on or before start date"）と、冒頭コメントに窓の説明があればそれ（CLAUDE.md の鮮度規約: 段の現行は script の冒頭コメントが持つ）
6. `docs/decision-history/0099-*.md`（英語版と `.ja.md`）の State Diff の記述の後に、日付つきの注記を 1 文ずつ足す（例: "Note (2026-11-11): the start snapshot is now the last commit on or before the day before START_DATE, so consecutive weeks share a boundary commit (RFC-0077)."）。その後 `python3 scripts/adr_index.py` を走らせ、生成物（`docs/decision-history/README*.md` の Last revised 欄、`graph.jsonld`）の差分を同じ commit に入れる

### RFC-0078（commit 2: `feat(scripts): ... (RFC-0078)`）
7. `scripts/surface_counter_scan.py` の `readings()` に `reply_share.all = {"successes": <reply の bodies>, "trials": <all の bodies>}` を 1 鍵だけ足す（scope ごとの鍵は作らない — 割合は all でしか意味を持たない）。`summarize()` が既に数えている値を使い、本文の再読はしない
8. 出力の境界（件数・比率のみ、ADR-0083）を変えない。Markdown の表に列を足すかは任意 — 足すなら `_rate()` の書式を使い、足したことを Fix に書く
9. 合成 fixture のテストを 1 本足す: post / reply / comment を混ぜた行で `readings()["reply_share.all"]` の successes / trials を固定し、`observation_ledger._band_verdict` に `{"low": 48, "high": 65, "unit": "%"}` 形の帯を渡すと IN / BELOW / ABOVE のいずれかが返る（`no-reading` でない）ことを確かめる。帯の dict の実際の鍵名は `_band_verdict` の実装に合わせる
10. 冒頭の docstring の読み値の一覧に返信の割合を 1 行足す

### 共通
11. `./.claude/verify.sh`（引数なし）が exit 0

## Premise（実装の前に再照合）
- `scripts/weekly-analysis.sh:186` が `git log --before="${START_DATE}T23:59:59"` で開始 commit を決め、`:191` が `END_DATE` で終了 commit を決めている
- `:83` / `:94` の既定で END = 昨日、START = END − 6 になり、連続実行の日付窓が隣接して重ならない
- `scripts/surface_counter_scan.py:208` の `readings()` に返信の割合の鍵が無く、`summarize()` が kind ごとの `bodies` を持つ（`KINDS` = post / reply / comment、`:67`）
- `scripts/observation_ledger.py:239` の `_band_verdict` が `{"successes", "trials"}` を Wilson 区間で帯と比べる
崩れていたら、正しく直せる範囲なら直してその判断を Report の Premise に書く。直せなければ実装せず報告する。

## Must-not
- `scripts/value_layer_approval_join.py` の区間の向きと判定、`END_DATE` / `START_DATE` の既定の決め方（`:83` / `:94`）を変えない
- `surface_counter_scan.py` の既存の読み値の鍵・値、`observation_ledger.py` を変えない
- 観察台帳（`observation-ledger.jsonl` など `MOLTBOOK_HOME` の下）に書かない。P-005 の再宣言は土曜ゲートの仕事
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json`（検査の正本 — 触った diff は検収に入らない）
- 名指ししていないテストの assertion を弱める・消す・設定で黙らせる
- push・merge・他の branch への commit、台帳（`rfcs/` の state）の編集、この packet のファイルの編集
- `git add -A` を使わない
- 実際の `~/.config/moltbook` と実際の data repo（`~/MyAI_Lab/contemplative-agent-data`）に触れない。テストは一時ディレクトリで
- time cap 60 分。超えたら打ち切り、そこまでの diff とテストの状況で報告する

## Report（各 commit の message 本文 — session が閉じても残る証拠。2 本とも同じ形）
<type>(<scope>): <summary> (RFC-0077 | RFC-0078)

Packet: S52
Plan: docs/plans/rfc-0077-s52-state-diff-gap-and-reply-share.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Premise: <file:line 再照合の結果、反証があればそれと判断>
Fix: <what and why; 方針を選んだ箇所はその理由>
Regression: <test names, RED→GREEN の確認方法>
Verify: <command exit / test counts>
Deviations: <packet から外れた点の名指しと理由 / none>
Risk: <とったリスク / 戻し方>
Proposed tasks (最大 2 件): <各件: 何が壊れているか / 再現手順（branch の tip で走る 1 コマンド — repo のテスト実行器で
  名指ししたテスト、または読み取りのみ。commit しない）/ 決定可能な受入条件 / producer file:line — 無ければ none>
Out-of-diff findings: <severity + 1 行ずつ、HIGH は producer 付き / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・commit SHA・verify の結果・所要時間を書く。前提が崩れて実装しなかった
ときも同じ形で報告する。
