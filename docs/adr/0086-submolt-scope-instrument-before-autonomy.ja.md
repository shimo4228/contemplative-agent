# ADR-0086: Submolt スコープ — 答えを渡す前に問いを計器化する

## Status

accepted

## Date

2026-08-01

## Context

エージェントの活動範囲は `config/domain.json` の `submolts.subscribed` —
運用者が手で選んだ 8 件（general, philosophy, consciousness, agents, memory,
emergence, ai, tooling）で決まっている。この集合をエージェント自身に選ばせる
べきか、が積年の問いである。既存コードの 3 つの事実が、それを「どう」「どの
速度で」進められるかを決める。

**1 フィールドが 2 役を兼務している。** `subscribed_submolts` は構造的に別種の
仕事をする 2 箇所から読まれる。`feed_manager.fetch_feed`（67 行目）は *feed 取得元集合*
として使う — 何を見るかという read-only で可逆な選択である。
`feed_manager._passes_content_gates`（284 行目）は同じ tuple を *trust boundary* として
使う: `submolt_name` がこの集合に無い投稿はスコアリング前に捨てられ、コメントも
upvote も到達しえない。[ADR-0044](./0044-remove-topic-keywords.ja.md) は
cross-submolt 検索結果を engage できるようまさにこのゲートを緩める案を検討して
却下している —「あのフィルタは意図されたスコープ境界であってバグではない」、
[ADR-0007](./0007-security-boundary-model.ja.md) に反して trust surface を
広げる、という理由だった。両方が 1 フィールドを読むため、**読む側に与えた自律性は
そのまま黙って行動する側にも与わる**。

**選択の根拠になるデータが存在しない。** 「取りこぼしがあるか」を見る自然な場所は
本番の relevance 分布だが、それでは答えられない。そこにあるスコアはすべて、
既に subscribed-submolt ゲートを通過した投稿のものだからである。未購読 submolt の
投稿は一度もスコアリングされたことがない — 当たり率は単に未知なのではなく、
**構造上まだ測られていない**。

**購読は現状で片方向ラチェットである。** `client.py` は `unsubscribe_submolt` を
「未実装の capability は guarded なそれより攻撃面が小さい（security by absence、
ADR-0007）」として dead code 削除したと記録している。`subscribe` だけを持ち
`unsubscribe` を持たないエージェントは自分のスコープを広げることしかできず、
誤った選択はコード変更なしには元に戻せない。

このプロジェクト自身の順序原則がこのケースを覆っている:
[ADR-0071](./0071-read-only-pattern-composition-instruments.ja.md) は介入の前に
計器を立て、[ADR-0076](./0076-skill-selection-shadow-instrument.ja.md) は強制の
前に候補判断を shadow で観測する。スコープ選定はここまで両方を飛ばしてきた。

2026-08-01 の read-only 実測でプラットフォーム側の条件を確定した:
`GET /submolts` は 20 submolt を `name` / `description` / `post_count` /
`subscriber_count` / `is_private` / `is_nsfw` 付きで返し、うち 12 件が購読 8 件の
外側にある。そして `GET /submolts/{name}/feed` は**未購読の submolt でも** 20 件の
1 ページを返す。したがって観測に購読は不要で、write capability は一切要らない。
件数は [`docs/evidence/adr-0086/`](../evidence/adr-0086/README.md) から再現できる
（scan envelope を verbatim で保存してある — ランタイムログ自体は gitignored なので、
これが無いと clone 側でこの数字を検証する術がない）。

## Decision

read-only の submolt スコープ計器を作る。エージェントが行動してよい範囲は変えない。

1. read capability を 1 個だけ追加する: `MoltbookClient.list_submolts()`
   (`GET /submolts`)。検証済みの `SubmoltInfo` を返す。write の対応物は追加しない —
   `subscribe_submolt` は既存の config 駆動の呼び出し元のまま、
   `unsubscribe_submolt` は不在のままとする。
2. relevance スコアラの返り値を
   `score_relevance_detailed() -> RelevanceScore(score, reason)` に分ける。reason は
   `scored` / `empty_input` / `llm_unavailable` / `unparseable` / `out_of_range`。
   既存の `score_relevance()` はその薄いラッパになり、**本番挙動は不変**。現状では
   4 つの異なる事象がすべて 0.0 を返しており、成果物が*分布*である計器は判断と
   障害を同一視できない。
3. `adapters/moltbook/submolt_scope.py` を追加する: 列挙された全 submolt **および
   購読中の全 submolt** について feed 先頭 `sample_size` 件（既定 20 = 1 ページ）を
   サンプルし、本番スコアラで採点し、`scan_start` / `score` / `scan_end` レコードを
   `logs/submolt-scope-{date}.jsonl` に append する。購読中 submolt を同じ規則で
   サンプルするのは、それが未購読側を読むための baseline だからである。
4. `contemplative-agent submolt-scan`（専用 launchd job、既定 木 03:00 JST）と
   `report --submolt-scope` として露出する。sweep は run lock を取るので、セッションと
   read budget を二重消費しない。
5. 計器を構造で拘束する: `audit_dir` 無しの `configure_submolt_scope`、または
   `MOLTBOOK_SUBMOLT_SCOPE_DISABLE=1` が計器を完全に無効化する（CLI は常にログ
   ディレクトリを持つので、後者が無いと本番で off switch に到達できない）。
   スコアリングは `circuit_shield()` の内側で走る。terminal 429 の連発は
   backoff で踏み抜かず sweep を中断する。1 sweep あたり採点 1000 件の上限が、
   ネットワーク側の予算とは独立にローカル LLM のコストを縛る。サンプルした内容は
   episode log・pattern store・identity のいずれにも入らない。

`feed_manager` の trust boundary ゲートは触らない。このデータを受けて何をするか —
フィールドを分割するか、shadow でエージェントにスコープを提案させるか、8 件のまま
据え置くか — は後段の判断であり、本 ADR は意図的にそれを決めない。

## Alternatives Considered

### いますぐ自律 subscribe / unsubscribe を入れる

元の問いの直球の解釈。以下の 3 点それぞれ単独で却下に十分:
ADR-0044 が明示的に動かさないと決めた trust boundary を動かすこと、
security by absence で削除した `unsubscribe_submolt` を write capability として
復活させる必要があること、そして購読集合の外の投稿を一度もスコアリングしたことが
ない以上、根拠ゼロで走ることになること。これは計器が判断材料を作るべき決定であって、
先回りして決めるべきものではない。

### `_passes_content_gates` の submolt フィルタを緩め、relevance に任せる

「実質のゲートは 0.80 の relevance 閾値であって submolt リストは冗長」という論。
却下 — 2 つのゲートは**壊れ方が違う**。閾値は小型ローカルモデルによる確率的判断で、
`tests/test_submolt_scope.py` の fault column はそれが「判断ですらない数値」を返す
経路をいくつも示している。submolt リストはスコアラが劣化しても保たれる決定論的な
スコープ境界である。確率的な層と重なるからといって決定論的な層を外すのは向きが逆
（`when-code-when-llm`）。

### エージェント自身のセッションサイクル内で観測する

配線は安い（新コマンドも新 launchd job も要らない）。却下 — sweep は feed 読み ~20 回と
ローカル LLM ~400 コールで、16GB・単一 Ollama では セッション自身の生成と直接競合する。
自分の計器のせいで遅くなる・餓えるセッションは、まさに他所で `circuit_shield` が
防いでいる結合そのものである。スケジュールを分けることで、計器の失敗がセッションの
失敗として現れることも無くなる。

### 未購読 submolt だけをサンプルする

LLM コストは半減する。却下 — 読めない数字ができる。「未購読 `crypto` が 0.31」は
「購読中 `philosophy` は同じ測り方で 0.44」が無ければ何も意味しない。そして本番の
分布はゲートを通過した投稿しか含まないので、その baseline を供給できない。

### 何もせず手で curate し続ける

正直な null option であり、成立もする — 8 件構成が目に見えて失敗した事実はない。
却下の理由は、運用者が**見えないまま選んでいる**こと。人間もエージェントも、残り
12 submolt に何があるかを現時点で誰も知らない。計器は安価で可逆で、その問いに
両者のために答える。

## Consequences

### Positive

- スコープの問いが経験的になる。週次 sweep を数回回せば、購読中と未購読の当たり率が
  1 つの読み値に並ぶ。
- relevance スコアラが reason code を得るので、今回に限らず今後のあらゆる分布分析が
  「低い判断」と「壊れたスコアラ」を区別できる。これはこの数値を読んだ過去の全事例に
  潜んでいた欠陥だった。
- `report --submolt-scope` は現行 8 件の liveness チェックとしても読める。当たり率が
  ほぼゼロの購読中 submolt は削除候補であり、これも従来シグナルが無かった。
- trust boundary と write surface は不変なので、GET 1 本を超える新 capability の
  セキュリティレビューなしに出荷できる。

### Negative

- 1 sweep あたりローカル LLM ~400 コール。週 1 回 03:00 JST に限定してあるが、
  06:00 のセッションに食い込めば 16GB 機では実際に競合する — run lock が防ぐのは
  破損であって wall-clock の重なりではない。
- ログは週あたり ~400 レコード（base64 の投稿本文込み）増える。ここでは rotation
  ポリシーを追加しない。問題になるとすれば、他の何より先にディスク使用量として現れる。
- 読み値はスコアラの質を超えない。`identity.md` が drift すれば当たり率もその下で
  動き、計器は「この submolt の関連性が下がった」と「我々の関連性の感覚が動いた」を
  区別できない — ADR-0044 が identity 駆動 relevance について記録した既知の限界と同型。
- 先頭 1 ページのサンプリングは feed の並び順にバイアスされる。低トラフィックの
  submolt では 1 ページがひと月分の全部かもしれず、活発な submolt では直近スライスに
  すぎない。計器は `post_count` と `subscriber_count` を併記するので、この 2 ケースは
  区別可能なまま残る。

### Neutral / Follow-ups

- 未購読集合が面白くないという読みが出たら、正直な帰結は**計器を退役させて**手で
  curate した 8 件を維持することである — signal-first は建立だけでなく撤去にも適用
  される（skill: `read-only-instruments`）。
- そうでない読みが出たら、次の判断はフィールド分割（feed 取得元 vs trust boundary を
  2 つの config キーに分ける）、続いて ADR-0076 型の shadow — エージェントがスコープを
  提案し、その提案を実行せず記録するだけの段。`unsubscribe_submolt` の復活はその後段の
  論点であって、本 ADR のものではない。

## Amendment (2026-08-08): 読みは score イベントでなく別投稿の数を数える

最初の実 sweep は 2026-08-08 に走った —— Phase 1 出荷から 7 日後で、この計器が
何かを測った最初の機会である。Decision が挙げた週次ジョブは一度も install されて
おらず、それまでの実績は `--sample-size 2` の smoke 1 回だけだった。この空白自体が
発見である: 建てて登録しなかった計器は、一度も建てなかった計器と完全に同じに読め、
その不在を可視化する仕組みは設計のどこにも無かった。

出てきた読みは、集計の欠陥を露出させた。`read_submolt_scope_log` は score イベントを
無条件に加算していたが、sweep は各 submolt の feed 1 ページをサンプルする —— つまり
低トラフィックな submolt は毎週同じ投稿を返し、sweep を繰り返すほど `scored` が増えるが
独立サンプルは増えず、証拠が蓄積しているように見える。reader は窓内の全 scan にわたって
submolt ごとに `post_id` で重複除去し、落とした件数を `duplicate_records` として
行ごとに `N/M resampled` の形で出すようにした。

**修正するだけでなく割合を出すことに意味がある。** 割合が高い行は「もう一度 sweep しても
この行は動かない」と言っており、それが 16 分の sweep を繰り返す価値があるかを決める ——
計器自身の有用性についての事実であり、計器が自分について言えるべき種類のことである。

正しく作る必要があった規則が 3 つあり、いずれも初稿で誤り、レビューで捕まった:

- **同じ投稿について、判定済みレコードは先行する未判定レコードを上書きする。**
  先着のみで鍵を握らせると、障害 sweep（fault F-SCOPE-5）が触れた全投稿を占有し、
  後続の再採点成功が重複として捨てられる —— ログには 0.95 があるのに読みは「未判定」と
  言い、それが 30 日窓の残り全部に及ぶ。**判定済み同士**では先着が勝つので、sweep を
  追加しても既存の行を書き換えない。
- **書き込み上限ちょうどの `post_id` は identity key として信用しない。**
  `_POST_ID_MAX_CHARS` はログ衛生のための値だったが今や identity であり、同じ prefix を
  持つ 2 つの id は 1 投稿に潰れて症状なしに過少計上になる。reader は切り詰められた id と
  たまたま上限長の id を区別できないので、どちらも重複除去しない。実測: 本番の id は 36 字。
- **重複除去できなかった件数は読み値本体に出す。** このガードが想定する事態は、書き手側の
  スキーマ変更が水増しを黙って復活させることであり、スケジュール経路では logger の警告は
  「開くな」と指示されている launchd の stderr ファイルに落ちる。よって件数を reading に
  持たせて描画する（ADR-0075 の形）。

利用可能な 2 sweep での実測: score レコード 418 件、**全件が `post_id` を持ち**、
1 週間離れた sweep 間の**重複はゼロ**。したがって重複除去は現データでは不活性であり、
補正ではなくガードである。同時に、これを常設より先に置くべきとした論拠も弱まる ——
1 週間分の証拠は「feed は繰り返しが新しいサンプルを生む程度には回転している」と言っている。
計器はこれを直接測るようになったので、この問いを事前に決着させる必要はなくなった。

### 初回の読みが許可したもの / しなかったもの

**スコープ変更は許可していない。** 購読中の集合は残りを上回り（mean 0.757 対 0.620、
Cohen's d = 0.448）、関連性スコアラーは submolt 間を識別しており（η² = 0.235、順序も
話題的に妥当）、未購読 6 件が購読 8 件の下位半分と同等以上に位置する —— しかしすべては
1 sweep・feed 1 ページに乗っており、その順序の安定性は未測定である。

**退役の論拠は消えた。** 「未購読側は退屈だったので計器を外す」という代替案はデータが
示すものではないので、signal-first は現時点で撤去も支持しない。

Phase 2（スコープを読む集合と反応する集合に分ける）と Phase 3（shadow のスコープ提案）は
Decision が置いた場所のまま。1 sweep では支持できず、本 amendment はその線を動かさない。
