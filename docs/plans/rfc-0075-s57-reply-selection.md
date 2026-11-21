# Kickoff packet — S57: RFC-0075 部品 2（返信も選ぶ — 相手のコメントを同じ採点にかけ、同じ相手 × 同じ post の往復に上限 + 選ばなかった返信の理由コード）

あなたは task-triage loop の build 役。cwd は `shimo4228/contemplative-agent` の git worktree。
最初に、この packet を `docs/plans/rfc-0075-s57-reply-selection.md` に置いて単独で commit する（`docs(plan): rfc-0075 S57 packet`）。
以後の commit はこのファイルを変えない。成果は branch 上の commit で返し、判断役が検収・review して main へ ff-only で取り込む。
境界は rule `boundary.md`、chain は skill `implementation-chain`（Review の行は判断役が回す。background の subagent は Agent tool を持たないので、調査は自分で行う）。

読むもの: `rfcs/0075-comment-quality-under-fifty.md`（2026-11-18 の著者回答が範囲を決めている: 部品 2 だけ。配分・間隔・返信と新規の配分（部品 3〜5）は入れない）、
`src/contemplative_agent/adapters/moltbook/reply_handler.py`（`run_cycle`、`_handle_notification`、`check_own_post_comments` / `_handle_post_comments`、`_process_reply` の宣伝文の検査）、
S54 の形（`docs/plans/rfc-0075-s54-feed-best-first.md`、`src/contemplative_agent/adapters/moltbook/feed_order.py`、`feed_manager.py` の `read_relevance_gate` と 2 段の `run_cycle`）、
`config/domain.json` の `relevance_score4`、CLAUDE.md の開発原則（Observability by default / テストの規約）、skill `replayable-audit-logs`（repo の `.claude/skills/`）、
関連度の判定を持つ判断の経緯（`grep -ln "relevance_score4" docs/decision-history/*.md`）、`docs/research/LOG.md`（2026-11-11 の feed comment order の行が書式の手本）、`docs/evidence/regimes/regimes.json` と README。

Effort: high — 本番の発話経路で、話しかけてきた相手に答えるかを変える

## Goal（決定可能な受入条件 — 判断役の既定。オーナーが digest で承認した版）
1. 返信の cycle を 2 段にする: (a) 採点段 — その cycle の返信の候補（通知の経路と自分の投稿のコメントを直接見る経路の両方）を、今と同じ停止条件（`end_time`、rate limit、read budget、breaker、fail-closed、既存の dedup）を守りながら、相手のコメント本文で `read_relevance_gate` と同じ score4 の判定にかける。(b) 返信段 — `relevance_score4` 以上の候補を P(top) の降順に `_process_reply` へ渡す。閾値は feed と同じ値を使い、新しい閾値を作らない
2. 往復の上限: 同じ相手 × 同じ post への返信は、直近 24 時間で 2 回まで（定数 1 つ、名前と理由をコメントで書く）。数えるのは自分の返信の記録（既存の自己書き込みの記録から引けるならそれ、無ければ新しいログ）で、上限に当たった候補は返信しない
3. 1 件ごとに採点を 2 回しない。relevance cache を使うなら、feed の post 用の entry と key が衝突しないこと（source を分けるなど）をテストで固定する。cache の書き手を 1 つに保つ規約（`read_relevance_gate` の docstring）を壊すなら、使わずに cycle 内の memo にする
4. 監査ログ（append-only JSONL、ADR-0075）: cycle ごとに候補 1 件 1 行で、comment id / post id（`log_safe_identifier` を通す）、経路（notification / own_post_scan）、P(top)、閾値、順位、理由コードを書く。理由コードは閉じた集合で、少なくとも `replied` / `below_threshold` / `thread_cap` / `promotional` / `already_replied` / `not_reached_end_time` / `not_reached_rate_limited` / `not_reached_read_budget` / `fail_closed` / `declined_downstream` を持つ。相手の名前・本文・タイトルは書かない。置き場所は feed-order と同じ命名の流儀（例: `logs/reply-order-{date}.jsonl`）で、`logs/episodes/` には置かない。`scripts/_census_registry.py` の `REGISTRY` に登録し `tests/test_instrument_census.py` を通す
5. テスト（`ChaosBackend` か requests 層の差し替え）: (i) 閾値以上の 3 件が P(top) の降順で返信されること (ii) 閾値未満は返信されず `below_threshold` が書かれること (iii) 同じ相手 × 同じ post の 3 件目が `thread_cap` になること (iv) `end_time` で返信段が切れたとき残りが `not_reached_end_time` になること (v) ログに相手の本文・名前が入らないこと
6. 関連度の判定を持つ判断の経緯と、session の段構成を書いている冒頭コメント（あれば）を同じ変更で更新する。判断の経緯は日付つきの注記 1〜2 文、`python3 scripts/adr_index.py` の生成物を同じ commit に入れる
7. 研究データの境目: `docs/research/LOG.md` に 1 行（2026-11-11 の行と同じ書式、日付は `YYYY-MM-DD` の placeholder — 判断役が merge の日を埋める）と、`docs/evidence/regimes/regimes.json` に境目 1 つ（README の規約どおり。日付は同じ placeholder の扱いで、placeholder にしたことを Report に書く）
8. `./.claude/verify.sh`（引数なし）が exit 0

## Premise（実装の前に再照合）
- `reply_handler.py:198-240` の `run_cycle` が通知を来た順に処理し、関連度の判定が無い（宣伝文の検査 `reply_handler.py:419` だけ）
- feed は S54 で 2 段になっている（`feed_manager.py` の `run_cycle`、`feed_order.py`）
崩れていたら、正しく直せる範囲なら直してその判断を Report の Premise に書く。直せなければ実装せず報告する。

## Must-not
- feed の経路（`feed_manager.py` の挙動）、上限（`scheduler.py`）、閾値の値（`config/domain.json`）、プロンプト（`config/prompts/`）を変えない
- 部品 3〜5（セッションへの配分・間隔・返信と新規の配分）を入れない
- 内部の `generate` を patch しない。runtime の依存を足さない
- 実際の `~/.config/moltbook` に触れない・agent を走らせない・Ollama を使わない
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json`（検査の正本 — 触った diff は検収に入らない）
- 名指ししていないテストの assertion を弱める・消す・設定で黙らせる
- push・merge・他の branch への commit、台帳（`rfcs/` の state）の編集、この packet のファイルの編集。`git add -A` を使わない
- time cap 90 分。超えたら打ち切り、そこまでの diff とテストの状況で報告する

## Report（最終 commit の message 本文 — session が閉じても残る証拠）
feat(reply): <summary> (RFC-0075)

Packet: S57
Plan: docs/plans/rfc-0075-s57-reply-selection.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Premise: <file:line 再照合の結果、反証があればそれと判断>
Fix: <what and why; 2 段の切り方、上限の数え方、cache か memo か、ログの置き場所を選んだ理由>
Regression: <test names>
Verify: <command exit / test counts>
Deviations: <packet から外れた点の名指しと理由 / none>
Risk: <とったリスク（例: 採点段の分だけ返信が遅れる・往復が切れる相手が出る）/ 戻し方>
Proposed tasks (最大 2 件): <各件: 何が壊れているか / 再現手順 / 決定可能な受入条件 / producer file:line — 無ければ none>
Out-of-diff findings: <severity + 1 行ずつ、HIGH は producer 付き / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・commit SHA・verify の結果・所要時間を書く。前提が崩れて実装しなかった
ときも同じ形で報告する。
