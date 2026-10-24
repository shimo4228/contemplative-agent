# ADR-0106: 環境が返した答えを記録する — コメントの outcome を選択に結ぶ

## Status

accepted (amended 2026-09-12, 2026-09-19, 2026-10-03)

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

**D3 追補（2026-09-19、RFC-0038）— 返信経路が行動を変えるのは `parent_rejected` だけ。**
返信の書き込みはこの理由のときだけ dedup キー（`reply:{post}:{comment}`）を処理済みとして
記録し、対象を返信キューから出す。他の 3 つは「その時の状態」なので対象は再試行可能なまま
残り、`unverified` 出口も同じ。これは失敗列の読みであって反応列の読みではないので、
D7（反応を下流へ流さない）は不変。記録先は dedup 台帳で、そこには公開の意味が無い —
返信が出たと言うのは `published` の行と activity エピソードであり、この経路はどちらも
書かない。「キューから出る」の永続性は台帳の永続性そのもので、それ以上ではない —
commented cache の cold rebuild はエピソードから post id だけを拾い reply キーを拾わないので、
cache ファイルを失うと終端済みの対象が戻る（公開済みの reply キーが元から持っていた穴）。

**D3 追補（2026-10-03、RFC-0049）— 返信の行は返信先を名指す。** record に
`reply_key_sha256`（dedup キー `reply:{post}:{comment}` の sha256 hex）と
`parent_comment_id`（返信先 comment の id）が入った。RFC-0038 以後の `parent_rejected` 行は
返信先ごとに数えられず、残る 2 つの説明 — 本文が byte 単位で同一の別 comment id が来続けている、
終端済みのキーが後のセッションまで残らない — を区別できなかった。理由列と違い、2 列は返信経路の
すべての状態（published / unverified / failed / declined）に載る。読みは 1 つの返信先の行を
状態に関わらず数えるため。他の経路では明示的な null で書き、キーの無い行はこの追補より前に
書かれた行。何を記録するかは書き手（`record_publish_outcome`）が決める: キーは digest だけ
（両半分は platform 由来の id で、join に要るのは digest — commented cache の要素を hash
すれば同じ値になる）、親 id は `comment_id` と同じ `is_valid_id` を通ったときだけで、通らなければ
切り詰めずに null。通知経路には親が無い（top-level に投稿する）ので、その行は digest と null の
親を持つ。挙動は変えない: 2 つの説明のどちらが成り立つか、したがって終端印をどう永続させるかは、
この列を読んでから決める。

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
skill 別の `injected_comments` / `comments_with_reply` / `replied_fraction`（2026-10-24 まで `reply_rate`。skill ごとの 返信のあったコメント / 注入されたコメントで、
`core/metrics.py` のアカウント単位の `reply_rate` とは別物）/
`mean_thread_depth` を出し、固定の `observation_note` を付ける — どの skill が注入されたかは
selector の判断で、その判断は状況と交絡する。`min_age_days`（2）より新しいコメントは
除外して数える（返信は数時間〜数日遅れて届く）。

**D7 — 下流へは流さない。** 反応は選択・抽出・退役へ、自動でも手動でも流さない。帰属設計
（randomized masking、ASSAY の形）は RFC-0028 Future possibilities に置いたまま: そもそも
反応が skill 間で分かれるかを知る前に本番経路へ介入するのは順序が逆で、Goodhart 圧
（返信を引く方向へ店が寄る）が入るのもそこだから。

**D8 — 軸 × 適用位置の表と、出口候補の隣の reply_rate（追補 2026-10-24、P2-06.3）。**
[ADR-0080](./0080-north-star-layered-end-state.ja.md) 2026-08-26 追補 §B の代謝の質の要件は、摂取を
複数軸で見分け、単一スカラーにしないこと、軸の列挙は開いたままにすることを求める。
どの軸がどこに当てはまるかを 1 枚に置く場所は本 ADR で、読み手が存在しえない読み値を
探し回らずに済むようにする。

| 軸 | 入口（insight 候補 → staging） | 出口（store の skill → archive 候補） |
|---|---|---|
| 新規性 | 読む: novelty gate・名乗り（naming kind）・重複判定（ADR-0096 / ADR-0111）と surprise の読み | 定義されない — 店にある skill は自分自身に対する新規性を持たない。最も近い読みは混同対の類似度（ADR-0105）で、別の量 |
| 重要度 | 計器なし（ADR-0056 の ablation は立ったまま。ここで軸に名前を挙げるのは計器の再建ではない） | 計器なし（同上） |
| 環境の反応 | 構造上定義されない — 候補はまだどのコメントにも注入されていない | 読む: skill ごとの `reply_rate` / `injected_comments`（D6）を候補の隣に出す |
| 選択頻度（上の 3 軸ではない。出口の規則が使うので載せる） | 定義されない — 候補を選ぶものがない | ADR-0105 の strict 規則と混同対。**決めるのはこちら** |

列挙は開いたまま（ADR-0080 §B）。どのセルもスコアではなく、行を足し合わせることもしない。

stage 7d の末尾（`scripts/archive_candidate_context.py`）が、候補ファイルの隣に
`weekly-{end}-archive-candidates.context.txt` を書く: 候補 1 件 1 行で `reply_rate`・
`injected_comments`・窓の `observed_publishes`。**候補ファイルの列ではなく兄弟ファイル**
なのは、`adopt-staged --archive-names` が読めない行で abort するため。これは D6 の分布を
ゲートが候補に出会う場所に出す表示であって、archive 判定の入力ではない。決めるのは
ADR-0105 の strict 規則のままで、ゲートは書面の理由があればどの行も削ってよい / 残してよい。
一方向の流れは `tests/test_archive_candidate_context.py` で固定してある: 候補の生成側と
`adopt-staged` / `remove-skill` のコードはこの読みを名指さず、context スクリプトは候補ファイルを
書かない。読みが候補の絞り込みや順位付けに使われるなら、それは D7 の場合で自前の ADR を要する。

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

> **注記（2026-10-24、P1-04.5）**: 「≥ 500 judged records」は `joined_publishes`（選択の読みが数える
> のと同じ母集団）で数え、返信率は `observed_publishes`（D5 の観測分母、joined の約 3 分の 1）を分母に
> 読む。したがって率は観測されなかった残り 3 分の 2 については何も言わない。skill が分かれるかは、
> 3 週窓 2 つ（2026-09-12..10-02 と 10-03..10-23）を `scripts/comment_outcome_separation.py` で 1 回
> だけ読み、事前に固定した線で判定する: 合算 10 件以上の観測を持つ skill の組で、率の差が 0.2 以上かつ
> Wilson 区間（k(k-1)/2 組の比較に対して Bonferroni で広げたもの）が重ならないものがあるか。
> **2026-10-24、最初の読みの前に改訂**: 当初は素の 95% 区間で約 800 組を比べ、帰無シミュレーションの 77% で
> 「分かれる」と出た。この補正は事前登録の修理であり事後変更ではない。読みは分布であり adopt / archive には流さない（D6、
> ADR-0051）。判定（stage 7d を撤去するか、帰属 RFC を起票するか）は土曜ゲートの D-P1-04-2。
> 手順と出力は [`docs/evidence/adr-0106/`](../evidence/adr-0106/README.md)。

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
