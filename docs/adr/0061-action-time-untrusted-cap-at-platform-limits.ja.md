# ADR-0061: action 時 untrusted 入力 cap を platform field 上限に統一; 内省ノートは全文を読む

## Status

accepted

## Date

2026-06-23

## Context

weekly 診断の finding F1.1（2026-06-15 に初出、06-18・06-21 に再発）は、agent の内省ノートに機械的な
mid-word の字切れ — 「…isn't na」のように文の途中で終わる断片 — が含まれ、contemplative register が
それを clipping のアーティファクトではなく作者の意図的な「間」や誘いとして読み直していると報告した。
この所見は 3 週連続の weekly レポートで安定していた。

当初の F1.1 診断は原因を次のコード経路に置いていた:
`_io.truncate()` → `content_summary` → `reply_handler.history_summaries` →
`_build_context_section`。2026-06-23 に 10-agent の ultracode トレース + 敵対的検証で再診断したところ、
この経路は dead だった: `history_summaries` と `_build_context_section` は
[ADR-0059](./0059-remove-dead-reply-history.md) で撤去され、`content_summary` の唯一の reader は
[ADR-0060](./0060-per-episode-grounded-distill.md) の `_is_rich_episode`（activity-only フィルタ）以降
到達不能になっている。字切れの症状は、当初診断が辿り着かなかった生きたコード経路に移っていた。

再診断は action 時経路の実在する欠陥を 2 つ確認した。

1 つ目は内省ノートに関わる。`feed_manager` はノート（`generate_internal_note`）を
`_fetch_full_if_truncated` を呼ぶ前に、つまり「on the preview by design」（コスト最適化）で生成していた。
submolt-feed サーバは各投稿に対し `FEED_CONTENT_PREVIEW_LEN=500` 文字のプレビューを返す。500 はノートの
`max_input=1000` 未満なので、`wrap_untrusted_content`（[ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md)
で確立）はサーバが既に mid-word で切った本文に対し、偽の「complete (500 chars)」マーカーを付けた。wrapper は
500 文字を見て、それが 1000 文字 cap に収まると判断し complete と報告した — 実際にはサーバが配信前に
切っていたのに。

2 つ目は action 生成側の呼び出し全般に関わる。`wrap_untrusted_content` 自身が切る場合
（comment / reply で `max_input=8000` の `post_text[:max_input]`）、マーカーは正直に「truncated」と言うが、
切られた残テキストは依然 mid-word で終わる。contemplative register はマーカーが正直でも、その mid-word の
切れ端を意図的な「間」として読み直した。action 時生成の呼び出しが小さな `max_input` を渡していた理由は
`num_ctx` overflow の安全弁だけである: `core/llm.py` の `generate()` は推定
`system + prompt + num_predict > NUM_CTX (32768)` のときコールを skip し、前置きされた値層を守る。この安全弁は
8000 文字 cap を必要としない: 実際の Moltbook 投稿は p90 ≈ 4700 文字、max ≈ 7400 文字で、platform の実 field
上限でも `NUM_CTX` に十分収まる。

[ADR-0060](./0060-per-episode-grounded-distill.md) は distill の抜粋 cap を Moltbook の platform field 上限に
合わせるパターン（`EXCERPT_CAPS = {original_post: MAX_POST_LENGTH, their_comment: MAX_COMMENT_LENGTH, ...}`、
「現実的なコンテンツは決して切られない」ように）を確立し、`truncate_boundary` を out-of-spec データ用の構造
ガードとしてのみ残していた。action 時経路はこの方針をまだ採用していなかった。

## Decision

action 時の untrusted 入力 cap を Moltbook の platform field 上限に引き上げ、内省ノートの前に全文を fetch する。

1. **`generate_comment` の投稿本文 cap** を 8000 → `MAX_POST_LENGTH`（40000、`core/config.py` 由来）に引き上げる。

2. **`generate_reply` の cap** を `original_post`（8000 → `MAX_POST_LENGTH`）と
   `their_comment`（8000 → `MAX_COMMENT_LENGTH`、10000）の両方で引き上げる。

3. **`generate_internal_note` の content cap** を 1000 → `MAX_POST_LENGTH + MAX_COMMENT_LENGTH`（50000）に
   引き上げる。ノートの content は feed 経路では投稿本文、reply 経路では投稿 + コメントの本文であり、両者の
   platform 上限の和が正しい上界である。

   実コンテンツは platform field 上限を超えられないので、これらの cap では `wrap_untrusted_content` の
   truncation 分岐は実コンテンツで決して発火しない。マーカーは常に正直に「complete」となり、mid-word の
   切れ端は発生しない。cap は `num_ctx` 安全弁として残る。本番の値層に対する実測（2026-06-23）: フル
   システムプロンプトは `_estimate_tokens` で ≈14.5K tok（skills 6 本が ≈11.8K で支配的）、comment/reply の
   出力予算は `num_predict` ≈6.7K tok で、`NUM_CTX=32768` のもと入力に使える余裕は ≈11.6K tok。よって
   `generate()` の予算ガードは ASCII ポストなら ≈34.8K 字超、CJK ポストなら ≈11.6K 字超で skip する — どちらも
   本番実測 max（≈7.4K 字）を大きく上回るので、現実的なコンテンツは常に余裕をもって収まる。規格外の巨大ポストは
   mid-word で黙って切られるのではなく **skip** される（ログに残り、値層は保護）。境界スライスで部分的に engage
   する案は本 ADR の全文方針と整合させるため却下した（Alternatives 参照）。

4. **ゲート / 分類の cap は変更しない。** `score_relevance=1000`、`select_submolt=1000`、
   `summarize_post_topic=2000` は小さいまま。これらは全 feed 投稿に対して走る安価なゲートで散文を生成しないため、
   そこでの mid-word の切れ端は無害であり、生成物や保存物に伝播しない。

5. **内省ノートの前に投稿本文を全文 fetch する**（`feed_manager` の feed-engagement 経路、
   `score >= min(upvote_only_threshold, threshold)` でゲート）。`create_comment` の前にあった別個の全文 fetch
   コールは削除し、より早い 1 回の fetch をノートとコメントの両方の全文ソースとする。
   `_fetch_full_if_truncated` は冪等で read-budget を尊重したまま: read budget が枯渇したときはプレビューに
   フォールバックする。

6. **`wrap_untrusted_content` と `truncate_boundary`（`core/llm.py`）は変更しない。** 修正は呼び出し側の
   cap 値と fetch 順序だけであり、[ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md)
   が確立した wrapper の契約は不変である。

## Alternatives Considered

### 死んだ F1.1 経路に `content_full_len` を追加

当初の F1.1 提案は、`content_summary` 経路に `content_full_len` フィールドで元の長さを保持し、cap に収まって
見えても truncated マーカーを出すことだった。却下: その経路（`history_summaries` /
`_build_context_section`）は [ADR-0059](./0059-remove-dead-reply-history.md) で撤去され、
[ADR-0060](./0060-per-episode-grounded-distill.md) 以降到達不能。死んだ経路にパッチを当てても何も直らない。

### `wrap_untrusted_content` を単語 / 文境界で切る

wrapper 内で `truncate_boundary` を再利用し、残テキストが必ず綺麗な境界で終わるようにし、正直な残長を報告する。
主たる修正としては却下。呼び出し側 cap が platform field 上限に等しくなれば、wrapper は実コンテンツを決して
切らないので、境界対応スライスは platform が起こり得ないと保証する out-of-spec 入力でしか発火しない。
二重マーカーのロジックと文字数報告を wrapper に足すのは、構造的に排除済みのケースのために複雑さを持ち込む。
`truncate_boundary` は [ADR-0060](./0060-per-episode-grounded-distill.md) に従い distill の out-of-spec 構造
ガードとして残し、wrapper には移さない。

### 全文 fetch を前に移さず cap だけ引き上げる

ノートを 500 文字のサーバプレビューに対して生成したまま、`generate_internal_note` の cap を
`MAX_POST_LENGTH` に引き上げる。却下: cap を上げても、サーバが既に 500 文字プレビューとして配信した本文は
un-clip できない。`wrap_untrusted_content` は依然 500 文字を見て「complete」と報告し、ノートは依然 mid-word で
切られた本文を読む。false-complete マーカーの欠陥は全文を先に fetch することでのみ直る。

### ノート生成をコメント判断の後に移す

コメント閾値を超えた投稿だけ内省ノートを生成し、全文 fetch のコストをその投稿だけに限定する。却下: 内省ノートは
upvote-only エピソード（`score >= upvote_only_threshold` だがコメント閾値未満の投稿）でも生成される。ノートは
両経路に供するためコメント判断の前に生成しなければならない。

## Consequences

### Positive

- 内省ノートと生成される comment・reply はすべて投稿本文を全文読む。サーバが切った 500 文字プレビューに対する
  false-complete マーカーは解消される。contemplative register が意図的な「間」と誤読していた mid-word の
  切れ端は実コンテンツで発生しなくなる。
- action 時の cap 方針が [ADR-0060](./0060-per-episode-grounded-distill.md) で確立した distill の `EXCERPT_CAPS`
  パターンと揃う: cap は platform field 上限に置かれ、`wrap_untrusted_content` の truncation 分岐は実コンテンツ
  経路から構造的に排除される。
- `create_comment` の前にあった別個の全文 fetch コールは削除され、ノートとコメント生成の両方に供する 1 回の
  より早い fetch に統合される。

### Negative

- 全文は、コメントに進む投稿だけでなく、engagement bar を超えた全投稿
  （`score >= min(upvote_only_threshold, threshold)`）で fetch されるようになる。GET リクエスト数が増える。
  増分は `_fetch_full_if_truncated` の read-budget ガード（budget が低いときプレビューにフォールバック）と、
  engagement bar に到達する投稿を制限する per-author の pacing / ゲートロジックで上限が抑えられる。

### Neutral / Follow-ups

- 2026-06-15・06-18・06-21 の具体的な断片の字切れの正確な出所はコードだけからは確定できない; 内省ノートの
  episode ログを直接読むことはプロンプトインジェクション経路として禁止されている（CLAUDE.md）。500 文字
  プレビューの欠陥がコードレベルで最有力の候補で、修正済みである。ソース著者のテキスト由来、またはモデル自身の
  生成由来の可能性は排除できない。本修正のデプロイ後、再発を観察する。
- reply 経路のノートは notification の `post_content` を読むが、これには 500 文字プレビュークランプの記述が
  ない（そのクランプは submolt-feed 固有）。notification ペイロードが全文でなくプレビューを配信するなら、
  全文 fetch の原則を reply 経路のノートにも広げる必要がある。現時点で未検証。
- `tests/test_llm.py` の `generate_comment` / `generate_reply` / `generate_internal_note` の truncation
  アサーションを更新する必要がある: platform 上限未満の現実的長さのコンテンツは「complete」とマークされ、
  out-of-spec コンテンツは platform field 上限で truncated される。`tests/test_agent.py` には、内省ノートが
  500 文字プレビューではなく全文を読むことを検証する回帰を追加する。
- [ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md)（truncation 契約）と
  [ADR-0060](./0060-per-episode-grounded-distill.md)（platform 上限 cap パターン）を action 時経路に拡張する。
  [ADR-0059](./0059-remove-dead-reply-history.md)（F1.1 が当初指した死んだ経路を撤去した）、
  [ADR-0045](./0045-pre-action-internal-note.md)（事前内省ノート）、
  [ADR-0007](./0007-security-boundary-model.md)（untrusted 境界）に関連する。supersede するものはない。

## References

- [ADR-0007](./0007-security-boundary-model.md) — untrusted 境界モデル; `wrap_untrusted_content` は本 ADR が
  action 時経路に拡張する enforcement 機構。
- [ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md) — untrusted wrapper の明示的な
  truncation 契約; 本 ADR はこの契約を action 時の呼び出しに拡張する。
- [ADR-0045](./0045-pre-action-internal-note.md) — 本 ADR が全文を読ませる事前内省ノートを導入した。
- [ADR-0059](./0059-remove-dead-reply-history.md) — `history_summaries` と `_build_context_section` を撤去し、
  当初の F1.1 診断経路を死なせた。
- [ADR-0060](./0060-per-episode-grounded-distill.md) — distill で platform field 上限 cap パターン
  （`EXCERPT_CAPS`）を確立した; 本 ADR は同じパターンを action 時生成に適用する。
