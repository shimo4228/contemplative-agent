# Kickoff packet — S55: RFC-0071（P1-06.1 契約キットの runtime 実行 + P1-04.11 eval baseline の smoke 1 行）

あなたは task-triage loop の build 役（measurement）。cwd は `contemplative-agent` の git worktree で、branch は main の先頭から切られている。
最初に、この packet を `docs/plans/rfc-0071-s55-contract-kit-eval-smoke.md` に置いて単独で commit する（`docs(plan): rfc-0071 S55 packet`）。
以後の commit はこのファイルを変えない。成果は branch 上の commit で返し、判断役が検収・review して main へ ff-only で取り込む。
境界は rule `boundary.md`、chain は skill `implementation-chain`（Review の行は判断役が回す。background の subagent は Agent tool を持たないので、調査は researcher を起動せず自分で検索する）。
書いてよいのは読みメモ 2 本（`docs/evidence/rfc-0071/contract-kit-runtime-2026-11-18.md` と `docs/evidence/rfc-0071/eval-smoke-2026-11-18.md`）と、runtime 段に probe が要るときの最小の実行用ファイル（下の Premise 2）だけ。判定（「動かす / 据え置き」）はしない — 判断役とオーナーがする。

読むもの: `rfcs/0071-mac-lab-readings-calibration.md`（「詳細」の実行規則と 2026-11-14 の著者回答）、`docs/plans/roadmap-2026-10/STATUS.md` の P1-06.1 / P1-04.11 の行（注記の原文コマンド）、`docs/plans/roadmap-2026-10/ROADMAP.md` の `##### P1-06.1` と `##### P1-04.11`、`src/contemplative_agent/testing/`、`docs/runbooks/sibling-backend-conformance.md`、`evals/README.md`、`evals/baselines/README.md`、`docs/evidence/rfc-0071/source-pattern-age-2026-11-11.md`（同じ RFC の前の読みメモの形）。

## 時刻と共有資源（最初に守る）

- 本番機の Ollama を使う。**Ollama を叩く作業は 19:00 JST 以降にだけ始め、22:45 JST までに終える**（JST 0 / 6 / 12 / 18 時のスケジュールセッションと重ねない — CLAUDE.md「実行機」）。始める前に毎回 `date`、`pgrep -fl "contemplative-agent run"`（空であること）、`ollama ps`（gemma4:e4b 以外が載っていないこと）を確かめ、結果をメモに書く。
- 19:00 より前に起動されたら、Ollama 不要の準備（コードを読む、コマンドを組む、メモの骨格を書く）だけを先にする。
- gemma と別のモデルを同時に載せない。2 つの計測は直列に回す（P1-06.1 → P1-04.11）。
- 22:45 JST を過ぎたら、終わっていない計測は止め、そこまでで報告する。

## Goal（決定可能な受入条件）

1. P1-06.1: 契約キットを本番の Ollama backend に対して runtime の段で 1 回流し、使ったコマンド・exit code・各 check の結果（PASS / FAIL / SKIP と ID）・Ollama の版・モデル名・日時を `docs/evidence/rfc-0071/contract-kit-runtime-2026-11-18.md` に書く。FAIL があっても直さない（数と ID を書く）。
2. P1-04.11: eval の smoke を 1 行（`--samples 1` 相当）回し、使ったコマンド・exit code・run id・各 check の verdict の数・`check_staleness.py` の出力（09-12 baseline が STALE と出るか）を `docs/evidence/rfc-0071/eval-smoke-2026-11-18.md` に書く。生成文・judge の evidence の本文は untrusted な LLM 出力なのでメモに写さない（数と run id と sha256 だけ）。
3. 新しい baseline を `evals/baselines/` に置かない（baseline の承認は人間の操作 — `evals/baselines/README.md`）。承認に回せる run があれば、その run id と `evals/results/` の絶対パスを Report の `Needs from judge` に書く。`evals/results/` は gitignored で worktree と一緒に消えるので、run の出力ディレクトリは main tree の `~/MyAI_Lab/contemplative-agent/evals/results/` 側に置く（`--out` 等の引数があればそれで、無ければ実行後に main tree の同じ場所へ copy）。
4. `uv run pytest tests/ -q` と `.claude/verify.sh` が exit 0（読みメモと実行用ファイルを足しただけで既存の木が変わっていないこと）。

## Premise（実装の前に再照合）

- `src/contemplative_agent/core/llm/ollama.py:166` に `class OllamaBackend` がある（ROADMAP の P1-06.1 は「実装 0」と書いた時点の記述）。STATUS の注記のコマンドは `python -m contemplative_agent.testing --backend contemplative_agent.core.llm.ollama:OllamaBackend --require runtime`。
- 2: `python -m contemplative_agent.testing --help` は「Levels above 'static' need a probe, which the CLI cannot supply — use a test file」と書く。runtime の段に probe が要るなら、`testing/` の公開 API と `docs/runbooks/sibling-backend-conformance.md` の手順どおりの最小の実行用ファイルを使う。置き場所は repo の外（scratchpad）を既定にし、repo に残す価値があると判断したときだけ `scripts/` に置いて理由を Report に書く。日常の `verify.sh` / pytest から実行される場所（`tests/`）には置かない（sibling・本番の Ollama を叩くので — CLAUDE.md「Backend 契約の正本」）。
- 3: eval の judge は `claude -p`（サブスクリプション）。judge のモデルを指定する引数があっても Fable を選ばない（既定のままか sonnet）。
- 4: ROADMAP の P1-04.11 は「D-P3-01-2 / D-P1-04-3（2027-02-06）の後」と書くが、2026-11-14 のオーナーの承認は今回 smoke 1 行を取ることだった。full run（約 19 分）と fixture の再 snapshot はしない。
崩れていたら、正しく直せる範囲なら直してその判断を Report の Premise に書く。直せなければ計測せず報告する。

## Must-not

- `src/`・`tests/`・`evals/` の既存ファイル、`config/`、`evals/baselines/`、`evals/fixtures/` を変えない
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json`（検査の正本 — 触った diff は検収に入らない）
- 名指ししていないテストの assertion を弱める・消す・設定で黙らせる
- push・merge・他の branch への commit、台帳（`rfcs/` の state）の編集、この packet のファイルの編集
- エピソードログ（`~/.config/moltbook/logs/episodes/`）と `agent-launchd.log` を読まない
- 22:45 JST を過ぎたら打ち切り、そこまでの diff とテストの状況で報告する

## Report（最終 commit の message 本文 — session が閉じても残る証拠）

docs(evidence): <summary> (RFC-0071)

Packet: S55
Plan: docs/plans/rfc-0071-s55-contract-kit-eval-smoke.md
Needs from judge: <baseline 承認に回せる run id と絶対パス / none>
Premise: <file:line 再照合の結果、反証があればそれと判断>
Fix: <何を回したか、probe をどこに置いたかとその理由>
Regression: none（計測）
Verify: <command exit / test counts>
Deviations: <packet から外れた点の名指しと理由 / none>
Approval ledger: none
Risk: <とったリスク / 戻し方>
Proposed tasks (最大 2 件): <各件: 何が壊れているか / 再現手順（branch の tip で走る 1 コマンド — repo のテスト実行器で名指ししたテスト、または読み取りのみ）/ 決定可能な受入条件 / producer file:line — 無ければ none>
Out-of-diff findings: <severity + 1 行ずつ、HIGH は producer 付き / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・commit SHA・verify の結果・所要時間・Ollama を使った時刻の範囲（JST）を書く。前提が崩れて計測しなかったときも同じ形で報告する。
