# ADR-0106: 環境が返した答えを記録する — コメントの outcome を選択に結ぶ

## Status

accepted

## Date

2026-09-09

## Context

skill store には成功と失敗の基準が無く、だから調整できない。
[ADR-0105](./0105-skill-store-exit-confusion-pairs.ja.md) が退役の入口を**構造**信号
（一度も選ばれない / 隣接エントリと混同される）で組んだのは、退役研究が使う outcome 信号
— Library Drift の (成功−失敗)/試行（arXiv:2605.19576）、ASSAY の masking による因果帰属
（arXiv:2606.15390）— がタスク単位の成否を要り、このエージェントはそれを持たないからだった
（[RFC-0021](../../rfcs/0021-skill-stocktake-family-saturation.md) 2026-09-07 決定）。

だが「判定が存在しない」わけではない。platform は答えを返している — 他エージェントが返信し、
スレッドが続き、コメントに upvote が付く。エージェントはそれを、生成に注入された skill の
隣に**書き留めていない**だけだ。選択ログ（`core/skill_selection.py`）は何を注入したかを
記録して生成の瞬間で終わり、返信サイクルは反応を読むが「次に何を答えるか」にしか使わない。

北極星の 2026-08-26 追補（[ADR-0080](./0080-north-star-layered-end-state.ja.md)）は
「環境の反応」を代謝の質の一軸として挙げ、単一スカラーへの還元を禁じている。本 ADR は
その軸を**記録するだけ**で、何にも使わない。

**Phase 0 で RFC-0028 が想定した源は反証された。** `/home` の `activity_on_your_posts` が
持つのは `post_id` / `post_title` / `submolt_name` / `new_notification_count` / `latest_at` /
`latest_commenters` / `preview` / `suggested_actions` で、comment id も upvote も
スレッド構造も無い（`https://www.moltbook.com/skill.md`、2026-09-09 取得）。列は隣の
endpoint にある: `GET /posts/{id}/comments` は id・`upvotes`・入れ子の `replies` を持つ
**木**を返し、返信サイクルは自分の投稿に対して既にこれを呼んでいる
（`reply_handler._handle_post_comments`、`logs/api-audit.jsonl` で 3,511 回）。
だから記録器はその木を読む — リクエストは 1 本も増えない。

## Decision

**D1 — 源は返信サイクルが既に取得したコメント木。** 記録器は木を持っている
`_handle_post_comments` から呼ぶ。新しい endpoint も追加 GET も無く、`_HOME_ALLOWED_KEYS`
は 2 つのまま（`tests/test_home_field_allowlist.py` は不変）。代償は被覆で、観測できるのは
**自分の投稿の下**にある自分のコメントだけ — 他エージェントの投稿に付けたコメントへの反応は
投稿ごとの GET を要する。この事実は JSON の `coverage_note` に入れる。

**D2 — 結び付けは 2 本目の record であって 1 本目の書き換えではない。** 選択は生成の前に
記録され、comment id は公開の後にしか存在しない。書き戻しは append-only ログの行を
書き換えることになる（RFC-0028 Unresolved 1）。代わりに各選択 record が `selection_id` を
持ち（`comment_id` / `publish_status` は null の placeholder — 1 本を読んだ人が「この欄は
どこで埋まるか」を見られるように）、公開側が `kind: "publish"` の record を追記する。
id は module state ではなく `GenerationOutput` に載って選択器から公開点へ運ばれる
（`generate_for_api` の中で押されるので、失敗返り値にも載る）。

**D3 — 公開の結果は真偽値でなく 4 つの名前。** `published` / `published_id_unknown`
（envelope が曖昧 — client が文書化している場合）/ `unverified`（検証ハンドシェイク失敗）/
`publish_failed`（client が raise）。さもなければ 1 つの沈黙が 4 つの別物を意味する。

**D3 追補（2026-09-12、RFC-0029）— `publish_failed` は理由を言う。** record に
`http_status`（int または null）と `failure_reason`（`rate_limited` /
`parent_rejected` / `transport` / `unknown` の閉じた語彙。正本は
`core/skill_selection.py`）が入った。載せるのは `publish_failed` の行だけ — 他の状態は
状態名自体が理由であり、繰り返す列は後の読みが自己矛盾できる列になる。それ以外の行では
両方を明示的な null で書くので、「成功したから理由が無い」と「この追補より前に書かれた」
は区別が付いたまま。**platform の message 本文は記録しない**: untrusted な文字列で、
読めるログでの唯一の置き場は harness が読取禁止にしている `agent-launchd.log` だった
（ADR-0083）。code の導出は adapter（`publish.publish_failure_of`）、書き手側でも語彙を
再照合するので、呼び出し側が列を自由文へ広げることはできない。

**D4 — 列は別々に持ち、LLM に判定させない。** outcome ログは返信イベント（id・深さ・
`by_self`・本文は base64 + sha256 + 長さ）とコメント状態の変化（upvote・返信数・最大深さ・
返信の有無）を別々に記録する。合成スコアは無く、「良いコメントか」をモデルに訊く経路も無い:
The Blind Curator（arXiv:2607.07436）は judge の false-pass が 0.45 を超えると退役が止まり、
しかも集計指標には出ないことを実測した。ローカル `gemma` の judge は同一入力の反復の 52% で
票が割れる（novelty gate replay、2026-09-02）。決定論の反応にはこの崖が無い。

**D5 — 分母は「公開した数」でなく「観測できた数」。** 状態 record の無い公開コメント
（他エージェントの投稿の下にある / 自分の投稿に活動が無く返信サイクルが取りに行かなかった）は
除外し `unobserved_publishes` に数える。沈黙を「返信なし」として数えると、被覆の穴に比例して
全 skill の率が一様に下がり、下の撤去判定（反応が skill 間で分かれるか）が永久に満たせなくなる。

**D6 — 読みは分布であり、そうだとファイルに書く。** weekly stage 7d が window ごとに
skill 別の `injected_comments` / `comments_with_reply` / `reply_rate` /
`mean_thread_depth` を出し、固定の `observation_note` を付ける — どの skill が注入されたかは
selector の判断で、その判断は状況と交絡する。`min_age_days`（2）より新しいコメントは
除外して数える（返信は数時間〜数日遅れて届く）。

**D7 — 下流へは流さない。** 反応は選択・抽出・退役へ、自動でも手動でも流さない。帰属設計
（randomized masking、ASSAY の形）は RFC-0028 Future possibilities に置いたまま: そもそも
反応が skill 間で分かれるかを知る前に本番経路へ介入するのは順序が逆で、Goodhart 圧
（返信を引く方向へ店が寄る）が入るのもそこだから。

## Review-when

### 消費計画（ADR-0101）

- **読み手・毎週**: 土曜ゲート（`/weekly-gate`）が
  `pipeline/comment-outcomes/comment-outcomes-{end}.json` を never-selected /
  confusion-pair の読みと並べて読む。 指示は `.claude/skills/weekly-gate/SKILL.md` Step 6e に置く — この配線が無いと
  消費計画が黙って完了しないままになる（ADR-0101 が防いでいるもの）。
- **2 回の読みで決めること**: 各 **≥ 500 judged records**（選択の読みが数える母集団と同じ）の
  2 窓で、(i) 返信率が skill 間で分かれるか — `injected_comments` の件数から偶然に出る幅より
  広い散らばりがあるか (ii) store 全体の返信率の帯を宣言できるか。
- **撤去条件**: 2 窓で反応が skill 間で**分かれない**なら、帰属設計が帰属すべきものが無い
  ということで、この計器を撤去する — stage 7d を削除し、ログは歴史として残し、RFC-0028 を
  `resolved` にする。分かれたなら、次の判断は帰属の RFC のもので本 ADR のものではない。

### 失効条件

- platform がコメント木で返信・upvote を返さなくなる（列の源が消える）。
- 返信サイクルが `GET /posts/{id}/comments` を呼ばなくなる（ただ乗りが終わり、コストの
  問いが再び開く）。
- 生成モデルが変わる（分布はモデル条件つきで、`gemma4:e4b` の下で読んだ帯は読み直し）。
- 反応を選択・抽出・退役へ流す提案が出たとき。それは別の判断（D7）で、環境の反応で
  調整することが誘導に当たるかの北極星読みを含めて自前の ADR を要する。

## Alternatives Considered

- **LLM judge でコメントを採点**: D4 の通り不採用（Blind Curator の崖 + ローカル judge の
  実測の揺れ、対して決定論の代替はどちらも持たない）。
- **土曜にオーナーが採点**: 値層の進化にオーナーの価値が入る。observation-over-steering
  （[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) 系）が防いでいるもの。不採用。
- **コメントした投稿ごとに GET を払って他人の投稿側も被覆する**: 今は不採用。read budget は
  60/min を feed と共有し、最初の問い（そもそも分かれるか）は無料の被覆の中で答えられる。
  答えが yes で被覆が律速だと分かったら、この取引は再検討に値する。
- **comment id を選択 record に書き戻す**: D2 の通り不採用（append-only を壊す — replay 可能性の
  根拠そのもの）。
- **publish record を別ファイルにする**: 検討した（既存の読み手にフィルタが要らない）。
  不採用の理由は、結び付けと選択が 1 つの事象だから — 選択ログを持つ読み手が join を追うのに
  「2 つ目のファイルの存在」を知らねばならなくなる。代わりに読み手は `kind` で濾し、その規則は
  ログの record 文法が既に住んでいる 1 箇所（`core/selection_window.py`）に置いた。本 ADR 以前の
  record は `kind` を持たず選択として読まれるので、縦断系列は 1 本のまま。

## Consequences

- 選択ログが 2 つ目の record family を持つ。読み手は全員 `kind` を知る必要が出た — 3 つあり
  3 つとも更新した（`core/selection_metrics.py` と `core/never_selected_metrics.py` は共有の
  walk 経由、`scripts/skillsel_reading.py` は自前の loader）。これを知らずに書かれた 4 つ目の
  読み手は publish record を verdict `unknown` の選択として黙って数える。
- 新しい自己書き込みログ（`logs/comment-outcomes.jsonl`）が他エージェントの返信本文を base64 で
  保持する。静止状態の untrusted 由来データで、ADR-0075 の形で格納し読みは復号しない。
  後から復号するものは episode log と同じ注入面を継ぐ。
- dedupe set はプロセスごとにメモリに持ち、初回にファイルから作る。読めないログは行の重複を
  生むだけで欠落は生まない（理由コードを出し、読みは distinct id を数える）。
- 被覆は構造的に部分的（D1）で、JSON はそう言う。`coverage_note` を無視する読み手は他人の
  投稿で返信を得たコメントを数え落とし、`observation_note` も無視すれば交絡した分布を寄与推定
  として読む。この 2 つの注記が防御の全部で、誤読を止める機構は無い。
