# Kickoff packet — S59: RFC-0012（採択後の shadow 憲法の読みを 2 本取る — measurement）

あなたは task-triage loop の build 役。cwd は `contemplative-agent` の git worktree で、branch は main の先頭から切られている。
最初に、この packet を `docs/plans/rfc-0012-s59-post-amendment-shadow-pair.md` に置いて単独で commit する（`docs(plan): rfc-0012 S59 packet`）。
以後の commit はこのファイルを変えない。成果は branch 上の commit で返し、判断役が検収・review して main へ ff-only で取り込む。
境界は rule `boundary.md`。これは measurement で、判定はしない — 判断役と 12-12 の土曜ゲートのオーナーがする。書いてよいのは `docs/evidence/adr-0092/shadow-series.md` の表の行と、その下の短い節 1 つだけ。

読むもの: `rfcs/0012-shadow-constitution-reading-consumption.md`（2026-11-18 の著者回答の Next action）、`docs/evidence/adr-0092/shadow-series.md`（表の列と「The 2026-11-14 amendment session」節 — 改正後の行は行 1〜4 と連続した系列として読まず、改正後の 2 本以上の収束としてだけ読む）、`docs/evidence/adr-0092/shadow-run-1-reading.md`（同一コーパスの対の読み方）、`rfcs/0055-amendment-outcome-preregistration.md` の (b) 行。

## Goal（決定可能な受入条件）
1. `uv run --no-sync contemplative-agent shadow-constitution` を **直列に 2 回**（同じコーパス = 改正後のノイズ床の対）走らせ、`~/.config/moltbook/logs/constitution-shadow.jsonl` に 2 行が増えている（実行前後の `wc -l` を Report に書く）。
2. `docs/evidence/adr-0092/shadow-series.md` の表に行 6・7 を足す（既存の列の形で: 日付 UTC、cosine shadow↔live、section inventory（見出しと、Boundless Care 系の語 care / compassion / suffering / kindness の出現数）、コーパス、live 憲法の hash（計器が記録する `current_sha256`）、run_id の先頭 8 文字）。行 5 の「not run」はそのまま残す。
3. 表の下に「Post-amendment pair (2026-11-25)」節を 3〜6 行で足す: 2 本の cosine、対の差（改正後の床）、比べる live の本文が amendment 4（sha256 `937fad4b…`）であること、行 1〜4 と比べない理由（1 行）。判定文（「収束した」「配線すべき」など）は書かない。
4. `./.claude/verify.sh` が exit 0。

## Premise（実装の前に再照合）
- Ollama を使う。**実行前に毎回**: `date`（JST 19:00〜22:45 の間であること）、`launchctl list com.moltbook.agent` に PID が無い（18:00 の定時 session が終わっている）、`ollama ps` に gemma4:e4b 以外のモデルが載っていない。どれかが満たされなければ 5 分おきに最大 6 回確かめ、満たされなければ実行せず報告する。22:45 JST を過ぎたら 2 本目は走らせない。
- 改正後の live 憲法の hash が amendment 4（`937fad4b…`）であることを計器の出力の `current_sha256` で確かめる。違っていたら書かずに報告する。
- shadow 計器の出力（`constitution-shadow.jsonl`）は自己書き込みの計器ログで、untrusted 由来の本文は b64 収納（CLAUDE.md）。生成された shadow 憲法の本文は表に引用しない — 見出しと語の数だけ。
- 崩れていたら、正しく直せる範囲なら直してその判断を Report の Premise に書く。直せなければ実行せず報告する。

## Must-not
- 変えてよいのは `docs/evidence/adr-0092/shadow-series.md` だけ（と packet の commit）
- 値層（`MOLTBOOK_HOME` の constitution / identity / skills / rules）への書き込み、`adopt-staged`・`amend-constitution` などの承認ゲート付きコマンドの実行
- Ollama のモデルを 2 つ同時に載せる、他の Ollama 計測と並べる
- `logs/episodes/` と `logs/agent-launchd.log` を読む
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json`
- push・merge・他の branch への commit、台帳（`rfcs/` の state）の編集、この packet のファイルの編集
- 120 分を超えたら打ち切り、そこまでの読みで報告する

## Report（最終 commit の message 本文 — session が閉じても残る証拠）
docs(evidence): <summary> (RFC-0012)

Packet: S59
Plan: docs/plans/rfc-0012-s59-post-amendment-shadow-pair.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Premise: <実行時刻 JST、agent の PID 確認、ollama ps、current_sha256>
Fix: <2 本の run_id 先頭 8 文字・cosine・所要時間>
Regression: n/a（measurement）
Verify: <command exit / test counts>
Deviations: <packet から外れた点の名指しと理由 / none>
Risk: none（read-only の計器と evidence 1 ファイル）
Proposed tasks (最大 2 件): <none か、各件: 何が壊れているか / 再現手順 / 受入条件 / producer file:line>
Out-of-diff findings: <severity + 1 行ずつ / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・commit SHA・verify の結果・所要時間を書く。実行しなかったときも同じ形で報告する。
