---
state: draft 2026-09-12
review-when: フィードキャッシュ TTL（600s）とサイクル間隔（60s）の比が 2 を下回ったら重複はほぼ消え、この提案は無効になる
---

## Summary

同じ投稿が 1 回のフィードキャッシュ期間に約 10 回 LLM 採点される。採点・全文 GET・
internal note をサイクル横断でメモ化するか、しない理由を決める。

## Motivation

`_FEED_CACHE_TTL` は 600 秒、`base_cycle_wait` は 60 秒。submolt フィードはキャッシュから
返るので、同じ投稿 dict が `_gather_feed_posts` を ~10 回通り、そのたびに
`score_relevance(post_text)`（Ollama コール）が走る。抑止しているのは
`_upvoted_posts` / `commented_posts` による**行動**の重複だけで、**判断**の重複は誰も
抑止していない。

閾値未満だが `upvote_only_threshold` 以上の帯（いちばん頻度の高い near-miss）では
さらに `_fetch_full_if_truncated`（実 GET、60/min の read クォータ）と
`generate_internal_note`（2 本目の LLM コール）が毎サイクル走り、結果は捨てられる。

## Guide-level explanation

投稿 id をキーに `{score, full_text, note}` を 1 サイクル or フィード TTL のあいだ持ち、
2 回目以降は再計算しない。投稿本文は不変なのでキャッシュは厳密。

## Reference-level explanation

置き場は `SessionContext`（`commented_posts` と同じ層）か `FeedManager` のセッション状態。
キー衝突を避けるなら id が無い投稿は content hash に落とす。

**これは単なる最適化ではない** — 採点は観察対象の一部で、ログには同じ投稿に対する
複数回の判定が残っている。メモ化するとその系列が消える。残すべきかは研究上の判断。

## Drawbacks

- 同一投稿への判定のばらつき（温度由来の非決定性）が観測できなくなる
- セッション状態が増える（現状 `_upvoted_posts` と同じ寿命なので新しい種類ではない）

## Rationale and alternatives

- **TTL を縮める**: 重複は減るが GET が増える。クォータのトレードが逆になるだけ
- **判定のばらつきを別途計器で取る**: 採点はメモ化しつつ、サンプリングで再採点だけ残す
- **何もしない**: Ollama は共有資源で、insight / distill と同じキューを食う

## Unresolved questions

- 重複判定の系列に研究上の価値があるか（ある場合は計器として明示的に取る形へ）
- キャッシュの寿命（サイクル / フィード TTL / セッション）

## Status

draft — 2026-09-12 の simplify 走査（adapters/moltbook 効率レビュー）で同定。未着手。

## Next action

「同一投稿の再判定を観測対象として残すか」の決定。残さないなら実装はセッション 1 本。
