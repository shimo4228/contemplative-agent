---
id: T-PUBLISH-ROW-REPLY-TARGET
state: done 2026-10-03
state_since: 2026-10-03
origin: gate
---

## タスク

返信の publish 失敗行（`skill-selection-*.jsonl` の `kind: "publish"`）に、返信先を名指す列が無い。そのため
RFC-0038（`parent_rejected` の返信キーを終端印にする修理、done 2026-09-19）が効いたかどうかを、どの自己
書き込みログからも再生できない。`PublishOutcome._record` が `record_publish_outcome` に渡すのは、作成された
comment の id（失敗時は null）・状態・`http_status`・`failure_reason` だけ。返信経路の `reply_key` と親
`comment_id` は `publish_outcome(...)` を開く地点（`reply_handler.py:462`）では手元にあるのに、行には届かない。
変更案: 返信経路が対象を `publish_outcome` に渡し、writer は id 形の列（例: `reply_key` の sha256 と、
printable に絞った親 comment id）として記録する。返信以外の経路では RFC-0029 の列と同じく明示的な null に
する。スキーマを持つ ADR-0106 D3 に同じ PR で追補を入れる。挙動の修理（終端印の持ち方）はこの列が読めて
から決める。

producer: `src/contemplative_agent/adapters/moltbook/publish.py:222`

## 詳細

- 診断: `weekly-2026-10-02-findings.md` の F1.1。出典は同週の観察文書の Exceptions 1 項目目と、台帳行 O-014（changed）
- Source quote（自己書き込みログ、決定論）: 窓内（2026-09-26..10-02）の `publish_failed` は 23 行で、全部が
  `http_status 404, failure_reason parent_rejected`。同じ窓の `moltbook.reply` で `prompt_norm_sha256 2f5352151363`
  （482 文字、RFC-0038 が名指した digest）を持つ行は 09-26 / 27 / 29 / 30 / 10-01 に 4 / 5 / 7 / 6 / 1 本で、
  合計 23。修理後も 09-22 に 1 本出ている
- `api-audit.jsonl` では 404 が隣接行の 3 連として出る（56699-56701、57167-57169、58312-58314、58373-58375、
  58687-58689）。間に他の request は無いので、各 3 連は 1 回取得した comment tree の中で起きている。同じ
  セッション内では、印の付いた key は `_reply_dedup` が弾く（`reply_handler.py:249-250, 295`）。したがって
  3 連は dedup 台帳がその時点で持っていない別々の list entry に向かったことになる
- 説明は 2 つ残り、どちらかで修理が変わる。(a) 本文が byte 単位で同一の別 comment id が来続けている
  （終端印は key 単位なので効かない）。(b) 終端印がセッションをまたいで残らない（ADR-0106 D3 と
  `memory_repos.py:436-445` が書いている cold rebuild の穴）。今の行の列（`kind, ts, selection_id, comment_id,
  publish_status, http_status, failure_reason, run_id, session_id`）ではどちらとも判定できない
- 2026-09-25 の findings は窓内 1 行を見て「修理は保っている」と読んだが、その判定もこの列が無い以上は決定できていなかった
- 関連: ADR-0106 D3（2026-09-12 / 09-19 追補）、ADR-0075（「どのログが理由に答えるか」）、`rfcs/0038`、`rfcs/0029`

## 2026-10-03 triage 照合（無人 cycle、stocktake 併走）

premise を照合: `adapters/moltbook/publish.py:218-228` の `_record` が `record_publish_outcome` に渡すのは `comment_id` / `publish_status` / `http_status` / `failure_reason` だけで、返信先は渡らない。`reply_handler.py:462` の `publish_outcome(selection_id)` も引数は selection_id のみ — 成立。採否は著者 → digest。

## 2026-10-03 著者回答（triage digest）

`draft` → `accepted`（著者: 2a）。返信の publish 行に返信先の列（`reply_key` の sha256 と printable に絞った親 comment id、返信以外は明示的な null）を足し、ADR-0106 D3 に追補。build S37 へ dispatch。

## 2026-10-03 merge（S37、判断役の検収）

`done`。`a7fa263`: `record_publish_outcome` が `reply_key_sha256`（key の sha256、utf-8 surrogatepass）と `parent_comment_id`（`is_valid_id` を通る id のみ、通らなければ null — 切り詰めない）を書く。返信経路は published / id 不明 / unverified / failed / declined の全行、他の経路は明示的な null（RFC-0029 と同じ流儀）、キーの無い行は RFC-0049 以前。通知経路は top-level 投稿なので親は null。挙動（dedup・終端印・呼び出し順）は不変。ADR-0106 D3 に 2026-10-03 追補（en + ja）。census は `_is_id_field` が拾うので登録変更なし。検収: verify を worktree（rebase 後）と main で再実行し exit 0、`/code-review` medium で指摘なし、security-reviewer の MEDIUM（孤立サロゲートで writer が例外を出し、published 経路で dedup 印を飛ばす）は再現の上 surrogatepass で修正済み。逸脱 2 件は名指しあり（親 id の検査を `is_valid_id` に / declined 行にも列）。次: 列が溜まったら `parent_rejected` を返信先ごとに数え、説明 (a) 同一本文の別 comment か (b) 終端印がセッションをまたいで残らないかを決める（RFC-0038 の修理の当否）。
