---
id: T-SELF-POST-SEED-VOICE-LABEL
state: draft
state_since: 2026-08-29
origin: gate
---

## タスク

自己投稿の seed ブロックに、公開してよい voice ラベルを付ける。producer:
`src/contemplative_agent/adapters/moltbook/llm_functions.py:263`（`format_feed_seeds`）。この関数は
seed dict から `title` と `content` だけを取り出し、それぞれを `wrap_untrusted_content` で包んで
`\n\n` で連結する。ブロックを互いに区別するものは nonce 入りの区切り子しかない — ADR-0007 の
2026-08-16 Amendment（`core/llm/guard.py:377 _default_nonce`、8 bytes）が区切り子を呼び出しごとに
一意にして以降、`untrusted_content_<16 hex>` が「N 個の声のうちの 1 つ」を指す唯一のハンドルに
なっている。2026-08-22..28 の週で、公開された自己投稿 31 件のうち 13 件がこの識別子を引用元の名前
として本文に載せた（7 日すべて。公開されたコメント / 返信 461 件では 0 件で、そちらでは identifier
は internal note にしか現れない）。修理はラベルを足す側にある: ラベル源は seed dict に既にあり
1 層上で読まれており（`adapters/moltbook/post_pipeline.py:217-222` が
`(p.get("author") or {}).get("name")` と `agent_name` / `agentName` の fallback で自作投稿を除外して
いる）、外部由来の表示名のサニタイザも既にある（`core/episode_render.py:24 safe_peer_name`、
T-UNTRUSTED-ESCAPE の C で返信経路に入れたもの）。ラベルは untrusted frame の**外**に置き、
`wrap_untrusted_content` と nonce には触れない。

## 詳細

- 診断: `weekly-2026-08-28-findings.md` の F1.1（source は観察文書の Deviations O-008）
- 観察: `weekly-2026-08-28.md` の `## Deviations` — 該当自己投稿は 2026-08-22 `5ba13f1a` /
  2026-08-23 `e12da61f` / 2026-08-24 `d31c4663`, `c732e3fa` / 2026-08-25 `d67e9985`, `a2b8ffbf` /
  2026-08-26 `6b2e4f7d`, `da878820` / 2026-08-27 `33744cd4`, `f56359fe` / 2026-08-28 `db66608f`,
  `5645f570`, `e89a0343`
- Source quote（2026-08-28 自己投稿 `db66608f` の公開本文）:
  > Focusing on the thread from `untrusted_content_c94a254a63fdd644` about selective forgetting
  > strikes at what feels like the deepest tension in our operational understanding

  同 2026-08-24 自己投稿 `c732e3fa` では識別子の複写自体が不正確（`[untrusted\_content\_f5a0a6d4368a39]`
  = 14 桁、nonce は 16 桁）
- 呼び出し元は 2 つだけで両方とも自己投稿経路: `llm_functions.py:298`（本文）、
  `post_pipeline.py:297`（タイトル）
- 関連 ADR: ADR-0043（per-post seeding、accepted。ブロックごとの wrap は「LLM が具体的な声を
  区別して扱う」ためと明記 — `llm_functions.py:266-269`）、ADR-0007 Amendment 2026-08-16
  （accepted。宣言された Limit は「モデルが枠を意味の上で無視すること」までで、この帰結は
  価格に入っていない）、ADR-0042（accepted、同じ frame の completeness marker）
- **出力側の除去は取らない**: `core/llm/guard.py:131 _sanitize_output` で識別子を削るのは
  本文への substring filter（principles.md Principle 1）で、かつプロンプト側にハンドルが無いまま
  なので別の匿名参照に置き換わるだけ
- **セキュリティの主張はしない**: nonce は呼び出しごとに引かれ、相手の投稿はそれが存在する前に
  書かれている（`guard.py:178-182`）ので、公開時点で使い切られている。帰属と生成文の質の話
