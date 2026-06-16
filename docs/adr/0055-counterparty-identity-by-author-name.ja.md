# ADR-0055: author name による counterparty 識別と activity/report スキーマの統一

## Status

accepted

## Date

2026-06-15

## Context

agent は他の agent の投稿と通知を Moltbook から読む。コードベースは、feed 投稿の `author` オブジェクトが `name` と `id` の両方を持つと想定していた — テストの fixture は `author: {id, name}` を使っていた。しかし production の live feed 投稿は `author.name` を持つが `author.id` を持たない: 代表的な一週間にわたって、271/271 件の comment interaction record で `agent_name` は populate されていた一方、`agent_id` は "unknown" だった。

いくつかの pipeline が author id を key にしており、その結果、無言のうちに劣化していた:

- comment activity record は `target_agent_id`（常に "unknown"）を書き込み、利用可能な name を取りこぼしていた。そのため daily comment-report は comment の counterparty を一度も表示できなかった。notifier の name を持つ reply は表示できていた — その結果、comment と reply が同一の意味スロットに対して異なる field を render する、非対称で「場当たり的」な report スキーマが生じていた。
- author 単位の repeat-topic gate と 24 h author 単位の rate limit は `author_id`（空文字列）を key にしていた。`count_recent_comments_by_author` と `get_prior_comment_targets` は常に 0 / [] を返していた — どちらの guard も dead no-op であり、同一 author による再投稿（ある author がほぼ同一の essay を再循環させること）は一度も throttle されなかった。
- ある weekly self-analysis が「6 日間にわたる同一投稿への re-reply」を重複バグとしてフラグした。episode log と照合して検証したところ、ある人気投稿に対して 6 人の異なる対話相手が reply していた — re-engagement ではなく健全な multi-party thread だった。この誤診断が成立しえたのは、daily report が counterparty identity を取りこぼし、下流の grouping に `post_id` だけを残したからにほかならない。

## Decision

interaction pipeline 全体で author name を canonical な counterparty key として採用する:

1. counterparty name（`target_agent`）を comment と reply の activity record に一貫して書き込む。前方互換のため `target_agent_id` は存在するときは保持する; 不在のときにのみ "unknown" として書き込み、決して primary key にはしない。
2. `count_recent_comments_by_author` と `get_prior_comment_targets` を name に re-key する。"unknown" / 空の値を guard し、attribution のない record が単一の bucket に collapse して gate を誤って発火させないようにする。
3. daily activity-report を、comment・reply・post の interaction に対して同一に render される単一の per-interaction スキーマに統一する: counterparty・post id・relevance（該当しないときは "—"）を持つ header、それに続く Context（stimulus）、[ADR-0045](0045-pre-action-internal-note.ja.md) の `internal_note`（従来 report で取りこぼされていた）、そして output。該当しない dimension は、interaction type 間で構造を変えるのではなく "—" として render する。
4. weekly-analysis prompt と weekly-report-diagnosis の self-check を、same-post / different-counterparty を re-reply ではなく multi-party thread として扱うよう補強する。

author name に対する boundary-validation 制約（`^[A-Za-z0-9_-]{1,64}$`）はそのまま維持する; これを満たさない name は propagate せず attribution なしとして扱う。

## Alternatives Considered

### `post_id` を key とする post-level reply dedup

却下。発端となった観察は、ある投稿に対する 6 人の異なる対話相手 — 正当な multi-party conversation — だった。post level で dedup すると正当な engagement を抑制し、agent の relational な姿勢に反する。この却下は `config/prompts/principles.md` にも記録されている。

### 代替 payload key から `author.id` を復元する

却下。id は live feed payload に存在せず、それを持つ代替 key もない。name は存在し、boundary-validation されており、この pipeline がカバーする interaction scope にとって安全で安定した key である。

### report を非対称のまま、weekly-analysis prompt だけを patch する

却下。prompt が必要としていた counterparty data は source — activity record そのもの — で欠落していた。prompt を patch しても false positive は潜在したまま残り、下流の grouping が `post_id` に fallback するたびに再発する。

## Consequences

### Positive

- author 単位の repeat-topic gate と 24 h rate limit が機能するようになる; 一度も throttle されなかった同一 author による再投稿が捕捉される。
- daily report が interaction type 間で構造的に一貫する。pre-action の `internal_note`（[ADR-0045](0045-pre-action-internal-note.ja.md)）と counterparty identity が両方とも表面化し、誤診断を生んでいた非対称性が解消される。
- 「re-reply」false positive が data source で除去される。diagnosis skill と `config/prompts/principles.md` が calibration note を持つので、この誤読は再発しない。

### Negative

- repeat author に向けられた engagement volume は低下する — 意図された是正だが、deploy 後の最初の数週間は監視すべき behavioral shift である。
- この変更より前に書かれた record は comment 上に `target_agent` を持たない。reader は穏当に fallback する: gate はそれらを skip し、report は "—" を render する。migration は実行しない。

### Neutral / Follow-ups

- [ADR-0029](0029-retire-dormant-provenance-elements.ja.md) の quarantine は保たれる: post body と stimulus text は distill summary に決して入らず、report 内の外部由来の text は引き続き URL-defang される。
- 実装は 6c20032 で commit 済み。

## References

- [ADR-0045](0045-pre-action-internal-note.ja.md) — refines。本 ADR が統一 report スキーマで表面化させる `internal_note` は、そこで導入・定義された。
- [ADR-0029](0029-retire-dormant-provenance-elements.ja.md) — depends-on。summarize step での quarantine 境界がここで保たれ、依拠されている。
- [ADR-0040](0040-separate-code-level-findings.ja.md) — precedent。weekly self-reflection report から code-level findings を分離した diagnosis が、この issue を表面化させた仕事である。
- 実装: commit 6c20032
