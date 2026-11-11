# Kickoff packet — S54: RFC-0075 部品 1（フィードの候補を先に全部採点し、P(top) の高い順にコメントする + 選ばなかった候補の理由コード）

あなたは task-triage loop の build 役。cwd は `shimo4228/contemplative-agent` の git worktree で、branch は main の先頭から切られている。
最初に、この packet を `docs/plans/rfc-0075-s54-feed-best-first.md` に置いて単独で commit する（`docs(plan): rfc-0075 S54 packet`）。
以後の commit はこのファイルを変えない。成果は branch 上の commit で返し、判断役が検収・review して main へ ff-only で取り込む。
境界は rule `boundary.md`、chain は skill `implementation-chain`（Review の行は判断役が回す。background の subagent は Agent tool を持たないので、調査は自分で行う）。

読むもの: `rfcs/0075-comment-quality-under-fifty.md`（2026-11-07 の著者回答が範囲を決めている: 部品 1 と監査ログだけ。返信の選び方・配分・間隔は入れない）、
`src/contemplative_agent/adapters/moltbook/feed_manager.py`（`run_cycle`、`_gather_feed_posts`、`engage_with_post`、`read_relevance_gate`、`relevance_cache`）、
`src/contemplative_agent/adapters/moltbook/agent.py:904-922`（session の順序）、`config/domain.json` の `relevance_score4`、
CLAUDE.md の開発原則（Observability by default — 監査ログは機能と同じ PR / テストの規約 — LLM は `ChaosBackend` か requests 層でだけ差し替える）、skill `replayable-audit-logs`（repo の `.claude/skills/`）、
関連度の判定を持つ判断の経緯（`grep -ln "relevance_score4" docs/decision-history/*.md` で探す）。

Effort: high — 本番の発話経路の順序を変える

## Goal（決定可能な受入条件 — 判断役の既定。オーナーが digest で承認した版）
1. `run_cycle` を 2 段にする: (a) 採点段 — `_gather_feed_posts` の候補を、今と同じ停止条件（`end_time`、rate limit、read budget、breaker、fail-closed）を守りながら全部 `read_relevance_gate` にかける（30 日 cache が効く）。(b) 関与段 — 閾値（`relevance_score4`）以上の候補を P(top) の降順に `engage_with_post` の関与部分へ渡す。閾値の足切りと、閾値未満に関与しないことは今のまま
2. 1 件ごとに採点を 2 回しない（採点段の読みを関与段がそのまま使う）。`engage_with_post` が他から呼ばれていれば、その経路の挙動は変えない
3. 新しい上限・件数の配分・間隔の変更は入れない（RFC-0075 の部品 2〜5 は範囲外）
4. 監査ログ（append-only JSONL、ADR-0075）: cycle ごとに候補 1 件 1 行で、post id（`log_safe_identifier` を通す）、source（following / submolt）、P(top)、閾値、順位、理由コードを書く。理由コードは閉じた集合で、少なくとも `commented` / `below_threshold` / `not_reached_end_time` / `not_reached_rate_limited` / `not_reached_read_budget` / `fail_closed` / `declined_downstream`（関与段に渡したが既存の判定で書かなかった）を持つ。投稿本文・タイトルは書かない。置き場所は既存の `logs/` の自己書き込みログの命名に合わせ、`logs/episodes/` には置かない
5. テスト: `ChaosBackend` か requests 層の差し替えで、(i) 閾値以上の 3 件が P(top) の降順で関与されること (ii) 閾値未満は関与されず `below_threshold` が書かれること (iii) `end_time` で関与段が切れたとき残りが `not_reached_end_time` で書かれること (iv) ログに本文が入らないこと、を固定する
6. 関連度の判定を持つ判断の経緯と、session の段構成を書いている冒頭コメント（あれば）を同じ変更で更新する（CLAUDE.md の鮮度規約）。判断の経緯は日付つきの注記 1〜2 文で足し、`python3 scripts/adr_index.py` を走らせて生成物を同じ commit に入れる
7. `docs/research/LOG.md` に、コメントの順序が変わる境目を 1 行（日付は merge の日、判断役が merge 時に埋めるので `YYYY-MM-DD` の placeholder でよい — placeholder にしたことを Report に書く）
8. `./.claude/verify.sh`（引数なし）が exit 0

## Premise（実装の前に再照合）
- `feed_manager.py:291-310` 付近の `run_cycle` が、候補を来た順に 1 件ずつ採点して即関与している
- 返信の経路（`reply_handler`）は関連度で選んでいない（今回は触らない）
- 30 日の relevance cache（RFC-0046 S38）が採点段で効く
崩れていたら、正しく直せる範囲なら直してその判断を Report の Premise に書く。直せなければ実装せず報告する。

## Must-not
- 返信の経路（`reply_handler.py`）、上限（`scheduler.py`）、閾値の値（`config/domain.json`）、プロンプト（`config/prompts/`）を変えない
- 内部の `generate` を patch しない（テストの規約）
- runtime の依存を足さない（`tests/test_dependency_floor.py`）
- 実際の `~/.config/moltbook` に触れない・agent を走らせない・Ollama を使わない
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json`（検査の正本 — 触った diff は検収に入らない）
- 名指ししていないテストの assertion を弱める・消す・設定で黙らせる
- push・merge・他の branch への commit、台帳（`rfcs/` の state）の編集、この packet のファイルの編集。`git add -A` を使わない
- time cap 90 分。超えたら打ち切り、そこまでの diff とテストの状況で報告する

## Report（最終 commit の message 本文 — session が閉じても残る証拠）
feat(feed): <summary> (RFC-0075)

Packet: S54
Plan: docs/plans/rfc-0075-s54-feed-best-first.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Premise: <file:line 再照合の結果、反証があればそれと判断>
Fix: <what and why; 2 段の切り方、停止条件の扱い、ログの置き場所を選んだ理由>
Regression: <test names, RED→GREEN の確認方法>
Verify: <command exit / test counts>
Deviations: <packet から外れた点の名指しと理由 / none>
Risk: <とったリスク（例: 採点段が時間を食って関与が減る）/ 戻し方>
Proposed tasks (最大 2 件): <各件: 何が壊れているか / 再現手順 / 決定可能な受入条件 / producer file:line — 無ければ none>
Out-of-diff findings: <severity + 1 行ずつ、HIGH は producer 付き / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・commit SHA・verify の結果・所要時間を書く。前提が崩れて実装しなかった
ときも同じ形で報告する。
