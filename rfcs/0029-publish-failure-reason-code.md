---
id: T-PUBLISH-FAILURE-REASON-CODE
state: accepted 2026-09-12
state_since: 2026-09-12
origin: gate
---

## タスク

publish 失敗の理由が、週次チェーンが読めるログのどこにも無い。`client_error_guard` は
`MoltbookClientError` を飲み込み、platform の message 全文を `logger.error` へ渡すだけで
（`publish.py:63`）、`exc.status_code` を見るのは 429 分岐だけ（:64）。選択記録側の publish 行は
`selection_id` / `comment_id` / `publish_status` / `ts` の 4 欄で理由を持たない
（`core/skill_selection.py:348-356`）。message 全文が残る唯一の場所は `logs/agent-launchd.log` で、
ここは CLAUDE.md と `~/.claude/hooks/_episode-log-common.sh` が読み取り禁止にしている。結果、
今週 Δ +16 で伸びた失敗クラスが、正規化署名 `{"statuscode":#,"message":"parent com` までしか見えず、
どの条件が発火したのか・修理が効いたのかを後のセッションが再現できない。

producer: `src/contemplative_agent/adapters/moltbook/publish.py:63`

## 詳細

診断 F1.2（`weekly-2026-09-11-findings.md`）。Source quote は Log Anomaly Sweep の 2 つの最大 delta:
`[error] failed to reply on #: api error #: {"statuscode":#,"message":"parent com` 20 (Δ +16) と
`[error] verification submission failed: api error #: {"statuscode":#,"message":"` 19 (Δ +12)。
前者の呼び出し元は `reply_handler.py:396-402`（`parent_id=comment_id or None` を渡す経路）。

扱い: publish outcome 行に、機械が分類できる事実だけを足す — HTTP status code と、client が
error から導く reason code（parent 参照の却下 / rate limit / transport 失敗 等）。

**platform の message 本文は入れない。** untrusted input なので、読めるログへ入れるとしても digest まで
（ADR-0083 の扱い）。ここを緩めると、ADR-0083 が閉じた面を観測性の名前で開け直すことになる。

- 所有: ADR-0075（observability by default、accepted / 2026-08-29 追補）の production 契約
- 記録の所有者: `rfcs/0028-skill-outcome-recording.md`（`state: done 2026-09-09`）が publish / unverified /
  id-unknown / failed の 4 出口を分けた。本件はその行に「failed のなぜ」を足す拡張で、同じ介入の
  台帳エントリは `rfcs/` にも旧台帳（git 履歴の `T-*` 系）にも無い
- 読めるもう一方のログ（`logs/api-audit.jsonl`）は envelope key のみで response body を記録しないため、
  そちらからは導出できない（materials の API Drift Scan の自己記述と一致）

副次: reason code が入れば「20 件の parent 却下」が feed 側の comment id の扱い（stale / 別 post 所属）
の問題なのかを次の窓で判定できる。今週の材料では判定できないので、この起票は記録面の修理に限る
（publish 挙動の変更は含めない）。

## 2026-09-12 triage 照合（無人 cycle）

`draft` 維持。premise を main HEAD（`347b913`）で再照合し成立（`publish.py::client_error_guard` は message 全文を logger.error へ渡すのみ / `com.moltbook.backup.plist` の PATH に `/usr/sbin` 無し、`/usr/sbin/lsof` 実在）。採否は著者判断（digest に提示）。

## 2026-09-12 決定（著者回答）

`draft` → `accepted`。S12 として dispatch（RFC-0034 と同梱、worktree `task/s12-audit-records`）。HTTP status + client 由来 reason code のみ、message 本文は入れない。

## 2026-09-12 build（S12、branch `task/s12-audit-records`）

Premise は main HEAD で再照合して成立（`publish.py::client_error_guard` は message 全文を
`logger.error` へ渡すだけ / publish 行は 5 欄 / `reply_handler.py` の `parent_id=comment_id or None`
経路）。

入れたもの:

- `core/skill_selection.py`: 閉じた語彙 `PUBLISH_FAILURE_{RATE_LIMITED,PARENT_REJECTED,TRANSPORT,UNKNOWN}`
  と `PUBLISH_FAILURE_REASONS`。`record_publish_outcome` が `http_status` / `failure_reason` を
  受け取り、**書き手側で再照合する**（語彙外は `unknown`、int でない・HTTP 範囲外の status は null）。
  publish_failed 以外の行は両方 null
- `adapters/moltbook/publish.py`: `PublishFailure`（frozen）と `publish_failure_of`。
  `client_error_guard` に `on_failure` を足し、`PublishOutcome.failed` が失敗行へ運ぶ。
  429 → rate_limited、message に `parent comment` → parent_rejected、status 無し + 自前の
  `Request failed:` 前置 → transport、他は unknown（status は別列にあるので情報は落ちない）
- 配線: reply 経路は `on_failure=outcome.failed`、comment 経路は guard が積む list を
  fallback 行が読む

**platform の message 本文は記録しない**（ADR-0083）。既存の `logger.error` 1 箇所だけが
全文の宛先で、そこから増やしていない。行に出るのは enum と int のみ。

読み手（`core/comment_outcomes.py` の週次読み / `scripts/skillsel_reading.py` /
`core/selection_metrics.py`）は新キー欠損の旧行で同じ数を報告する — 回帰は
`tests/test_selection_publish_link.py::TestLegacyPublishRowsStillRead`。

Doc sync: ADR-0106 の D3 に追補（en / ja）。段構成・ゲート・式は動かしていないので
`docs/diagrams/` と `graph.jsonld` は対象外（新規 ADR ノードを作っていない）。

Review（security-reviewer / `/code-review` medium、2026-09-12）で直したもの:

- 語彙ゲートが unhashable な値で `TypeError` を投げ、`record_publish_outcome` の
  「Never raises」契約（= 計器が publish 行動を落とさない）を破っていた → `isinstance` を先に置く
- comment 経路の fallback が `publish_status` を見ずに reason 列を載せられる形だった
  （published を名乗る行が失敗理由を持ちうる）→ `PUBLISH_FAILED` の行だけに限定（reply 経路と同形）
- `parent comment` の照合を 4xx に限定。5xx や transport の本文に同じ語が echo されても
  parent_rejected にしない。特定 code（400/404/422）まで絞らないのは、platform の code が
  未文書で、外すとこの reason code が数えたいクラス自体を落とすため
- 429 の rate limit フラグを `on_failure` より先に立てる（budget の判断が callback の後ろに来ない）
