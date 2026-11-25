# Kickoff packet — S58: RFC-0080（見張り役のログ末尾判定を、生成文でなくログの行の形で見る）

あなたは task-triage loop の build 役。cwd は `contemplative-agent` の git worktree で、branch は main の先頭から切られている。
最初に、この packet を `docs/plans/rfc-0080-s58-watchdog-log-line-shape.md` に置いて単独で commit する（`docs(plan): rfc-0080 S58 packet`）。
以後の commit はこのファイルを変えない。成果は branch 上の commit で返し、判断役が検収・review して main へ ff-only で取り込む。
境界は rule `boundary.md`、chain は skill `implementation-chain`（種別 fix。Review の行は判断役が回す。background の subagent は Agent tool を持たないので、調査は researcher を起動せず自分で検索する）。

読むもの: `rfcs/0080-watchdog-log-tail-false-alarm.md`（受入 (i)〜(iv) が完了条件）、`scripts/pipeline_watchdog.sh`（冒頭コメントと `log_healthy`）、`tests/test_pipeline_watchdog_shell.py`（テストの流儀）。

## Goal（決定可能な受入条件）
1. `log_healthy` のログ末尾の判定が、行の中身でなく行の形で失敗を見る。生成文の中に `error:` / `Error:` / `traceback` という語を含むが失敗ではないログ末尾（RFC-0080 の Motivation の形: 完了行の後に生成済みの JSON が続き、その 1 文に「structural error: the conflation …」がある）で ✅（OK 行）になるテストが通る。
2. 失敗の形のログ末尾 — 少なくとも `Traceback (most recent call last):` で始まる行、`[ERROR]` を含むログ行、行頭の `ERROR` — で ❌（FAIL 行）のままになるテストが通る。どの形を失敗と数えるかは、次の Premise 2 で実際のログから確かめた形で決める。
3. `scripts/pipeline_watchdog.sh` の冒頭コメントか `log_healthy` の直前のコメントに、判定が見る行の形を 1〜3 行で書く（CLAUDE.md の鮮度規約: 判定を変える変更は同じ変更で冒頭コメントを更新する）。
4. `./.claude/verify.sh` が exit 0。

## Premise（実装の前に再照合）
- 判定は `scripts/pipeline_watchdog.sh:127` の `tail -n 30 "$log" | grep -qiE 'traceback|^ERROR|error:'`。`-i` があり、`error:` は行頭に縛られていない。同じ関数を distill / insight / backup ほかの job が使う。
- 各 job のログで実際に出た失敗の形を確かめる: `ls ~/.config/moltbook/logs/*-launchd.log` の各ファイル（**`agent-launchd.log` は読まない** — 他エージェント由来の本文が残っている。CLAUDE.md のセキュリティ方針。`logs/episodes/` も読まない）を `grep -nE 'Traceback|\[ERROR\]|^ERROR|error:'` で数え、失敗の行がどういう形で出ているか（Python の logging の書式、Traceback、CLI の `error:` 行など）を Report の Premise に件数つきで書く。行の中身（生成文）を Report に引用しない — 形と件数だけ。
- 生成文がログの末尾に出る経路（distill が stdout に生成済みの気づきの JSON を出している）は、どこで出ているかを `file:line` で確かめて Report に書く。出力の側は変えない（RFC-0080: 理由が分からないまま消さない）。変えるべきだと判断したら Proposed tasks に回す。
- 崩れていたら、正しく直せる範囲なら直してその判断を Report の Premise に書く。直せなければ実装せず報告する。

## Must-not
- 変えてよいのは `scripts/pipeline_watchdog.sh`、`tests/test_pipeline_watchdog_shell.py`（新しいテストを足す。既存の assertion は弱めない）、必要なら `docs/TROUBLESHOOTING.md` の該当行だけ
- script の HARD CONSTRAINT（pure bash + BSD の date/stat/df/awk と read-only の launchctl。python / uv / claude を呼ばない）を守る
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json`（検査の正本 — 触った diff は検収に入らない）
- 名指ししていないテストの assertion を弱める・消す・設定で黙らせる
- push・merge・他の branch への commit、台帳（`rfcs/` の state）の編集、この packet のファイルの編集
- launchd の job・plist・本番の `MOLTBOOK_HOME` への書き込み（テストは一時ディレクトリの home で回す）
- 60 分を超えたら打ち切り、そこまでの diff とテストの状況で報告する

## Report（最終 commit の message 本文 — session が閉じても残る証拠）
fix(scripts): <summary> (RFC-0080)

Packet: S58
Plan: docs/plans/rfc-0080-s58-watchdog-log-line-shape.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Premise: <file:line 再照合の結果。各ログの失敗の形と件数。生成文がログに出る経路の file:line>
Fix: <what and why; どの形を失敗と数えたかとその根拠>
Regression: <test names, RED→GREEN の確認方法>
Verify: <command exit / test counts>
Deviations: <packet から外れた点の名指しと理由 / none>
Risk: <拾わなくなる失敗の形 / 戻し方>
Proposed tasks (最大 2 件): <各件: 何が壊れているか / 再現手順（branch の tip で走る 1 コマンド）/ 決定可能な受入条件 / producer file:line — 無ければ none>
Out-of-diff findings: <severity + 1 行ずつ、HIGH は producer 付き / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・commit SHA・verify の結果・所要時間を書く。前提が崩れて実装しなかったときも同じ形で報告する。
