# ADR-0063: NoveltyGate の比較対象を verified（可視）投稿のみにスコープする

## Status

accepted

## Date

2026-06-26

## Context

[ADR-0062](./0062-create-time-verification-handshake.md) は作成時の検証ハンドシェイクを修正し、新しい投稿・コメントが公開可視になれるようにした。だがそのデプロイ直後の60分ライブ自律セッションで、投稿生成に到達したのはちょうど1回で、NoveltyGate（[ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md)）がドラフトを `reason=reject:low_novelty`（`novelty=0.25`、過去投稿 "Can Optimization Cages Still Reach Meaning Without Arrival?" に対し `nearest=0.79`）で棄却した。セッション全体で新規の可視投稿はゼロだった。

根本原因は NoveltyGate が比較対象を選ぶ仕組みにある。ゲートは `memory.get_recent_posts(limit=50)` 経由でエージェントの直近投稿記録に対しドラフトを重複排除する。エージェントの保存済み 349 投稿はすべて `verification_status=pending` である: ADR-0062 がハンドシェイクを修正する前に作成され、5分のチャレンジ窓が `/verify` 成功なしに失効しており、プラットフォーム上で恒久的に不可視・回復不能。セッションログでの実測: `posts_count=349`、直近40件すべて pending。ゲートは**誰も見ていない投稿**に対してドラフトを照合し、新しいものを何も生成しないまま沈黙していた。

二次的な欠陥が沈黙を悪化させた。[ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md) の rate-deficit Lagrangian 項は、エージェントが本当に沈黙しているとき admit 閾値を緩めるよう設計されている: `actual_rate` が低いと `mu · (target_rate − actual_rate)` が正に育つ。だが `actual_rate` は `get_post_rate_7d()` が計算し、これは検証状態に関わらず7日窓内の全投稿記録を数えていた。349 件の pending 投稿がまだ窓内にあったため、エージェントは「活動中」に見え、deficit 項はほぼゼロの寄与しか生まず、閾値は変わらなかった。

コメントと返信は終始影響を受けなかった: これらは NoveltyGate を通らないため、pending のみの履歴は投稿生成だけをブロックしていた。

## Decision

1. **NoveltyGate の比較対象を verified（可視）投稿のみにスコープする。** `PostRecord`（frozen dataclass）に `verified: bool`（`default=False`）を追加。`record_post(..., verified: bool = True)` がフラグを `True` に設定する — 投稿パイプラインは ADR-0062 以降、検証ハンドシェイク成功後にのみ記録するため、新規記録される投稿はすべて書き込み時に verified とマークされる。`get_recent_posts(limit, verified_only=False)` に `verified_only` キーワード引数を追加し、`post_pipeline._run_dynamic_post` が `verified_only=True` で呼ぶ。フィルタ済みリストは NoveltyGate の cosine 類似度比較と body-hash 重複排除チェックの両方に渡るので、両ゲートとも実際に公開された投稿のみとドラフトを照合する。

2. **後方互換なデシリアライズに依拠し、append-only のエピソードログを改変しない。** 修正前の "post" エピソードは `verified` キーなしでシリアライズされている。ロード経路はエピソード JSON から `PostRecord(**data)` を再構築し、`verified` が無ければ dataclass はフィールド default（`False`）にフォールバックする。よって 349 件の pending 投稿は unverified としてデシリアライズされ、比較対象から自動的に除外される — エピソードログの編集・backfill・マイグレーションなしで、no-delete-episodes 不変条件に完全準拠する。

3. **rate-deficit 項は verified 限定にしない。** `get_post_rate_7d()` は全投稿記録を数え続ける。比較対象が verified 投稿（当初は空）に限定されたことで、整形済みドラフトの `novelty=1.0` となり、admit 閾値を即座にクリアするのに十分。rate 項も verified 限定にすると、verified 投稿数がほぼゼロの再構築期に `deficit ≈ target_rate` となり、`mu · deficit` がスコアを支配して**近似重複の verified 投稿を30分ごとに admit** してしまう — ゲートが防ぐために作られた 2026年5月の echo chamber（40件の近似同一投稿）の再来。rate を全投稿のままにすれば再構築期も `deficit ≈ 0` に保たれる（pending 投稿はまだ7日窓内にあり徐々に窓外へ抜ける）。verified 投稿が蓄積すれば、novelty 比較が近似重複を正しくブロックする。コードレビューにより、rate を変えないことでエージェントが再沈黙する regime は存在しないと確認済み: verified 集合が空なら deficit 項に関わらず `novelty=1.0` だから。

## Alternatives Considered

### rate-deficit 項も verified 限定にする

比較対象と rate シグナルを一致させるため、`get_post_rate_7d()` でも verified 投稿のみ数える。却下: 修正時点で verified 数は 0 なので `deficit = target_rate − 0 = target_rate`。`mu · deficit` 項が総スコアを支配し、近似重複から守る novelty 比較を迂回して deficit だけで投稿を admit してしまう。比較対象のスコープ化だけでこのリスクなしに投稿を解放でき、rate-deficit の目的（長期の本当の沈黙を破る）は現状の条件ではない。

### 349 件の pending 投稿記録とその埋め込みを purge / 書き換える

pending 記録をエピソードログから削除、あるいは上書きして `get_recent_posts` に現れないようにする。却下: 投稿記録はロード毎にエピソードから導出される。エピソードの削除・パッチは no-delete-episodes / append-only エピソードログ不変条件に違反する。インメモリ索引だけの purge は再起動で消える。後方互換デシリアライズの手法は、エピソードログに触れずに同じ除外を達成する。

### NoveltyGate の admit 閾値（theta）をグローバルに下げる

過去投稿との類似度に関わらず多くのドラフトがゲートを通るよう `theta` を下げる。却下: グローバルに低い閾値は genuinely visible な投稿への重複排除も弱め、可視投稿コーパスが育つにつれ echo chamber を再導入するリスクがある。根本欠陥（見られていないコンテンツに対する照合）に対処せず、2 度目の pending 投稿が溜まれば同じ問題に陥る。

### 何もせず、pending が窓外へ抜けて rate-deficit が緩むのを待つ

349 件の pending が7日地平を越えて抜けるにつれ7日窓が枯れ、`actual_rate` が下がり deficit が広がって閾値が緩むのを待つ。主要修正としては却下: 枯渇は遅く結果が不確実。閾値が広がっても `novelty=0.25`・`nearest=0.79` のドラフトは依然ブロックされうる（比較対象に不可視投稿が残るため）。待機は約7日に及び、その間エージェントは沈黙する。窓外抜けは rate カウントを変えないこと（Decision 3）の有用な副次的性質であって、単独の対処ではない。

## Consequences

### Positive

- エージェントが再び可視投稿を生成できる。verified 比較対象が当初空なので、整形済みドラフトは `novelty=1.0`。次に admit されたドラフトは ADR-0062 経由で検証され、最初の可視投稿になる。以降のドラフトは育っていく可視投稿集合に対して重複排除される。
- 重複排除の意味が意図と一致する: 「誰も見ていないものを繰り返さない」ではなく「読者が見たものを繰り返さない」。pending としてのみ存在したテーマはもはや反復扱いされず、再浮上が正しい挙動になる。
- エピソードログの改変・マイグレーション不要。変更は `PostRecord` への後方互換なフィールド追加であり、append-only 不変条件は完全に保たれる。

### Negative

- エージェントが 349 件の不可視 pending 投稿とテーマ的に類似した投稿を公開しうる。これは意図した結果（それらは見られていない）だが、初期の可視投稿が古い pending ドラフトを反響しうる。読者は初めてそのコンテンツに出会い、エージェントは出会わない。
- 2 つの分母が今や異なる: NoveltyGate の比較対象は verified 限定、rate-deficit 項は全投稿カウント。この非対称は意図的（Decision 3）だが、再構築期のゲート挙動を推論する際に将来の読者が保持すべき機微である。

### Neutral / Follow-ups

- 本変更で導入したものではない既存事項: `_load_episodes_into_memory` はロード時に `MAX_POST_HISTORY` を強制しないが `record_post` は強制する。高頻度書き込み窓の後、インメモリ投稿履歴と rate-deficit 窓がわずかに異なる分母で計算されうる。将来のクリーンアップ対象。
- 再構築フェーズで近似重複の verified 投稿が漏れる場合、（上記の override を避けるため）非ゼロの下限を持つ verified 対応 rate 項が妥当か再検討する。下限値は、通常運用で novelty を上書きさせずに deficit 項の「本当の沈黙を破る」目的を保てる程度に高く設定する必要がある。

## References

- [ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md) — NoveltyGate: 連続 novelty スコアと rate-deficit Lagrangian 項。本 ADR はそのゲートへの比較入力をスコープする。
- [ADR-0062](./0062-create-time-verification-handshake.md) — 作成時検証ハンドシェイク。`verification_status` と、本 ADR が依拠する検証後の記録順を確立する。`PostRecord` の `verified` フィールドが書き込み時に設定されるのは、ADR-0062 が記録を検証成功でゲートしているため。
- 実装: `memory.py`（`PostRecord`, `record_post`, `get_recent_posts`）、`post_pipeline.py`（`_run_dynamic_post`）。ADR-0062 後続修正と同一の変更セット。
- 関連: `CLAUDE.md` に記載の no-delete-episodes / append-only エピソードログ不変条件。後方互換デシリアライズはこの性質が再起動を越えて安定であることに依拠する。
