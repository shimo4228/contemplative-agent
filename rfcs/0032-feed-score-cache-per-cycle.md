---
state: done 2026-09-12
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

## 2026-09-12 triage 照合（無人 cycle）

`draft` 維持（同日の simplify 走査で起票、premise は起票時点の main で検証済み）。採否は著者判断（digest に提示）。

## 2026-09-12 決定（著者回答）

`draft` → `accepted`。著者判断: 同一投稿の再採点はバグであり、再判定の系列を読む計器・消費者は無いので観察対象として残さない → メモ化する。S13 として dispatch（worktree `task/s13-feed-memo`）。

## 2026-09-12 build（S13、branch `task/s13-feed-memo`）

前提は `main` で再照合済み: `_FEED_CACHE_TTL = 600.0`（`feed_manager.py:47`）、
`base_cycle_wait = 60.0`（`config.py:113`）、`_gather_feed_posts` は id で重複を落とすので
同じ post dict が cycle ごとに 1 回ずつ `engage_with_post` に届く。

実装はセッション状態のメモ（`FeedManager._judged_posts`、`_upvoted_posts` と同じ寿命）。
`{post_id: _PostJudgment(score, post_text, note, engaged)}` を持ち、2 回目以降は
`score_relevance` / `_fetch_full_if_truncated` / `generate_internal_note` を再実行しない。

決めたこと 3 点:

- **鍵は post id のみ。content hash に落とす必要はない** — `engage_with_post` は
  `post_id` が空なら採点前に return するので、採点点に到達する投稿は必ず id を持つ。
  untrusted 本文を鍵に使わずに済む
- **集合でなく値を持つ**。後段の消費者がある: 判定が閾値を越えても
  `scheduler.can_comment()` が False なら comment は次サイクルに持ち越される（`_upvoted_posts`
  は upvote しか抑止しない）。集合で早期 return すると、この再挑戦が消えて挙動が変わる
- **`engaged` を持つ**のは engage bar（`min(upvote_only_threshold, threshold)`）が
  セッション内で下がりうるため（相手と交流すると `known_agent_threshold` に切り替わる）。
  bar が下がったときは本文 GET と note だけを補い、score は再計算しない。既定の
  `domain.json` では `known_agent == upvote_only == 0.70` なのでこの枝は発火しない

監査は新しい JSONL を作らず 2 経路: skip 1 回につき理由コード `already_judged` を含む INFO 行、
セッション終了 episode（`session` / `event: end`）に `feed_rejudges_skipped` の件数。

回帰は `tests/test_feed_judgment_memo.py`（feed cache TTL 内に同じ投稿を 3 サイクル通し、
LLM と GET の呼び出し回数を数える）。

**失敗は memo しない**（`/code-review` の指摘 2 件、同セッションで修正）。判定の 3 部分は
どれも「正しく見える値」で失敗する — `score_relevance_detailed` は 0.0 を 4 通りの理由で返し
判定なのは `scored` だけ、`_fetch_full_if_truncated` は本文が取れないとき preview に落ち、
`generate_internal_note` は失敗時に `""` を返す。これらを固めると、Ollama の一時停止が触れた
投稿はセッション中ずっと 0.0 で blacklist され、budget 不足で preview のまま固まった本文が
後のサイクルで comment に渡る（weekly-2026-06-21 F1.1 の再来）。memo するのは全部が本物の
答えのときだけで、そうでなければ次サイクルが memo 前とまったく同じに再計算する。
そのため feed の採点呼び出しは `score_relevance` から `score_relevance_detailed` に移した
（`submolt_scan` と同じ seam。テスト側の patch 先も同じ名前に揃えた）。

## 2026-09-12 merge（判断役の検収 → 著者の merge 語）

`accepted` → `done`。S13 `3876d2f` を main へ ff merge。判断役の再検収: worktree / main とも `verify.sh` exit 0。diff 外 LOW 2 件は commit body に残す（起票なし）。
