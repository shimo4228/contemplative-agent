---
id: T-REPLY-PARENT-REJECTED-REQUEUE
state: draft
state_since: 2026-09-19
origin: gate
---

## タスク

プラットフォームが parent 参照を拒否した返信先（4xx `parent_rejected`）が、返信キューから出る経路を
持たない。返信キーを「処理済み」にするのは verify 済み publish の後だけで（`reply_handler.py:440`
の in-session set と `:446` の永続 cache）、`client_error_guard` が握りつぶす失敗出口では何も
記録しない。そのため次の走査（`_handle_post_comments`、`:545-548`）が同じコメントを未処理と
判定し、internal_note / skill_selection / reply の 3 コールと comment のペーシング枠 1 つ、404 が
返る POST 1 本を毎回使う。変更案: 分類済みの失敗が parent 参照の拒否だったとき、返信キーを
終端済みとして記録する（`_reply_dedup` が読む場所に）。一時的な失敗（rate_limited / transport /
unknown）と `unverified` 出口は今の挙動のまま残す。

producer: `src/contemplative_agent/adapters/moltbook/reply_handler.py:440`

## 詳細

- 診断: `weekly-2026-09-18-findings.md` の F1.1。出典は同週の観察文書 Exceptions 1 行目
- Source quote（自己書き込みログ、決定論）: `prompt_norm_sha256 = 2f5352151363`（482 文字の同一
  プロンプト）の `moltbook.reply` が 2026-09-13 → 09-18 に 7 セッションで 11 回生成された
  （`llm-calls-2026-09-1{3,4,5,7,8}.jsonl`）。毎回 45 秒以内に `api-audit.jsonl` の
  `POST /posts/{id}/comments` 404 と、skill-selection publish 行 `publish_status: publish_failed,
  http_status: 404, failure_reason: parent_rejected` が続く。窓内の publish_failed 12 件のうち
  11 件がこの 1 件の繰り返し
- 分類は既にある: `publish.py:103-117`（`publish_failure_of` → `PUBLISH_FAILURE_PARENT_REJECTED`）。
  記録面は `rfcs/0029`（done 2026-09-12）が足したが、その RFC は publish 挙動の変更を明示的に
  対象外にしている
- 共有状態の確認: `record_commented` / `has_commented_on` は `feed_manager.py:439,652` も素の
  `post_id` キーで使う。返信キーは `reply:{post}:{comment}` で名前空間が別なので、終端印が
  フィードのコメントを抑止することはない
- 関連: ADR-0106 D3、ADR-0075
