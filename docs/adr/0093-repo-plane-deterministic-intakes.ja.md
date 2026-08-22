# ADR-0093: repo 面の決定論 intake — docs 整合性と台帳条件 watch

## Status

partially-superseded-by ADR-0095（stage 6c 台帳条件 watch は 2026-08-16 に退役。stage 6b docs 整合性 scan は有効のまま）
（stage 6b）と `scripts/ledger_condition_scan.py`（stage 6c）を追加し、
`build_decision_packet.py` に packet §9/§10 と metrics フィールド
`docs_findings` / `ledger_watch_fired` を、タスク台帳に `watch:` 注釈規約を追加する。
LLM ステージ・ランタイムエージェントの挙動・承認境界は一切変えない。

## Date

2026-08-14

## Context

Boris Cherny のスケジュール実行クラウドエージェント（routines）による保守実験の
構造化検討（[evidence](../evidence/adr-0093/cloud-routines-consideration.md)、
事実は 2026-08-14 時点）は、この concept をそのまま輸入するものは無いと結論した:
提案者/昇格者の分離は Cycle #5（ADR-0085）が既に持つ形であり、11 種の routine は
既存の決定論ゲートで充足済みか ADR-0080 の機構層 north star（止まる）に逆行し、
cloud clone から見える資産には weekly chain が実際に必要とするもの
（episode log・ローカル LLM・gitignored な台帳）が含まれない。

しかしその照合の摩擦点が、**現行**パイプラインの穴を 2 つ逆照射した。どちらも
実例があり、計器建立の signal-first 基準（ADR-0071）を満たす:

1. **docs コーパスを誰も系統的に読んでいない。** この欠陥クラスの実例は 2 件:
   ADR-0081 は反証済みの安全論証を 2026-08-08 まで `accepted` の本文として
   保持しており、台帳は既に存在しない rules 条項を出典として引いていた —
   どちらも別作業中のレビュアーが**偶発的に**発見した。docs 言語方針
   （「`.ja.md` は同 PR で更新」「ADR から gitignored なローカル notes ディレクトリを参照しない」
   CODEMAPS freshness header）は CLAUDE.md に明文化されているが、
   何も強制していない。
2. **blocked タスクの解除条件は一度書かれたきり再読されない。**
   knowledge-staleness rule は提案に失効・解除条件を付けることを求め、台帳は
   それを記録している（例: T-OLLAMA-TOKENIZE は ollama/ollama#12030 待ち）が、
   それを poll する機構が無い。条件が成立してもタスクは blocked のままで、
   人間が思い出すまで放置される。

どちらの穴も repo 面（checkout と台帳の話であってランタイムデータではない）であり、
どちらも LLM 不要の決定論 80% に分解できる。weekly chain にはこの形のための
正しいスロットが既にある: dead-code intake（stage 6、T-DEADCODE-INTAKE）—
検出を decision packet へ直結し、diagnosis→fix の LLM 段を迂回し、
行動は全て土曜の人間ゲートに予約する。

## Decision

`weekly-pipeline.sh` に決定論 intake を 2 本、dead-code stage の契約
（`$MOLTBOOK_HOME/pipeline/` 下の JSON artifact、`uv run --no-sync` 規律 =
無人でのネットワークパッケージ解決なし、理由コード付き縮退、packet 節 +
metrics フィールド、行動はゲートに予約）を
鏡写しにして追加する:

**Stage 6b — docs 整合性（`scripts/docs_consistency_scan.py`、第 6 決定論
intake）。** repo checkout の自筆 docs（docs/**、CLAUDE.md、README 群。
symlink は除外）への read-only スキャン。findings: `enja_drift`（ADR の英語正本が
`.ja.md` より後に commit）、`broken_link`（相対 Markdown リンクの断線。fenced
block と inline code span は除外）、`notes_ref`（ADR から gitignored なローカル notes ディレクトリへの引用 —
clone では全て壊れる）。readings（閾値なし、finding にしない）: CODEMAPS/CYCLES の
freshness header の経過日数と commits-behind（2 方言両対応）。fault は検査単位で
`errors` に縮退（`GIT_FAIL` / `FILE_UNREADABLE`）して `DOCSCAN_PARTIAL` として
描画され、repo root が使えない場合のみ nonzero で abstain（`DOCSCAN_FAIL`）。
**設計として stateless**: finding は修理されるまで毎週再掲される — 修理可能な
欠陥には催促こそが機能（対比: `api_drift_scan` が一度だけ flag するのは、
platform drift がこちら側から修理できないから）。

**Stage 6c — 台帳条件 watch（`scripts/ledger_condition_scan.py`、第 7 決定論
intake）。** 台帳の **blocked 行**の `watch:` backtick スパン注釈 —
`gh-pr owner/repo#N` / `http-status URL CODE` / `http-post-status URL CODE` /
`file-exists PATH` — を解釈し、各条件の現在状態を報告する。他状態の行は
定義によりスコープ外: 解決済みタスクに残った注釈は永久にアラートせず
polling を止める（2026-08-14 codex review）。`http-post-status` の対象は
loopback ホストに制限する — 無人の空ボディ POST は雑なサービスには
状態変更になり、正当な POST 先はローカル Ollama probe だけ
（2026-08-14 security review）。`fired=true` は「解除条件が成立した
可能性の側へ状態が動いた」の読み値であり、それに基づく着手は人間の判断。
セキュリティ契約: レスポンス本文は出力に到達しない。GitHub PR の state は
閉じた語彙 {open, closed, merged} に写像され、それ以外は `SCHEMA_DRIFT`
理由コードになる — platform 制御の文字列がゲートセッションの読む packet に
入る経路は無い。リクエストはタイムアウトで束縛され、ネットワーク fault は
watch 単位で縮退（`UNREACHABLE` / `PARSE_ERROR` / `HTTP_ERROR`）、
`fired=null`（状態不明）は「まだ blocked」と読ませず packet に描画される。
この intake がローカル chain で走るのは台帳がローカルかつ gitignored
**だから**である — cloud エージェント検討はまさにこの境界で弾かれた。

**Packet/metrics 契約。** §9 は findings または縮退スキャンで、§10 は fired /
判定不能 / 注釈不正で描画され、静かな週は何も足さない（signal-first、§5/§8 と
同じ）。metrics は None-vs-0 規律に従う: `None` = 今週スキャンせず、`0` =
スキャンしてクリーン。

意味層の陳腐化 — 後続の証拠に反証された**主張**、穴 1 の LLM 判断 20% — は
無人チェーンでは明示的にスコープ外とする。自動化するなら、まず人間起動の
セッションとして入り、無人配線の前に shadow-mode 検証（ADR-0076 の型）を通す。

## Alternatives Considered

**スケジュール実行クラウドエージェント（発端のアイデア）。** 保守役としては
不採用: 11 の routine 原型のうち輸入 0（3 つは対象なし、4 つは既存カバレッジ —
決定論ゲート・stocktake コマンド・weekly fix chain — と重複、4 つは既存の
規律 — ADR-0080 の「done = 止まる」・chaos-TDD の決定論 fault カタログ・
mutation testing 文化 — に逆行する）。
**観測**役として生き残る 2 候補（ADR 整合性の one-shot、off-host ミラー
heartbeat — signal-first で保留、建てる場合の最安形は cloud routine でなく
data repo 側の GitHub Actions）を含む全分析は
[evidence](../evidence/adr-0093/cloud-routines-consideration.md) に保存。

**無人チェーン内の LLM ベース docs 陳腐化スキャン。** 不採用: 一方通行面
（packet）への未検証の確率的判断は shadow-first 規律（ADR-0076）に反し、
決定論サブセットが観測済み 2 実例の検出可能な半分を既にカバーする。

**外部リンクチェッカー（lychee / markdown-link-check）。** Phase 0
search-first 照合（2026-08-14 時点）: カバーするのは 4 検査中 `broken_link`
のみで、無人ネットワークパッケージ解決を意図的に排したチェーン（dead-code
stage の `uv run --no-sync` 規律）に非 stdlib のツールチェーン依存を足し、repo 固有の検査
（enja ペアリング・notes ディレクトリ禁止・freshness 方言）は表現できない。既存
scan script パターンに沿った stdlib 実装 ~40 行を選ぶ。

**docs findings の stateful flag-once 意味論。** 不採用: api-drift 計器が
一度だけ flag するのは platform スキーマがこの repo の修理対象ではないから。
docs finding は修理可能なので、修理まで見え続けることが望ましい圧であり、
stateless なら他 intake が要する状態昇格機構（emit-aside・atomic rename）も
不要になる。

**weekly chain 外の cron 駆動ローカルスキャン。** 不採用: 土曜のケイデンスは
chain が既に所有し、packet はゲートが読む唯一の場所であり、第 2 のスケジューラは
signal を足さずに運用面だけ増やす。

## Consequences

**Positive:**

- 観測済み欠陥クラスが計器化された: 初回ドッグフード run で実 findings 22 件
  （`enja_drift` 2 件 — ADR-0053 / ADR-0060 — と 6 ADR ペアにわたる
  `notes_ref` 20 件）、broken link 0 件。これらは 2026-08-16 packet の §9 行
  として人間のトリアージに届く。
- 台帳条件が週次で poll される（採択時点の実 watch 3 本: ollama#12030 の
  state、ローカル `/api/tokenize` probe、`cloud.env` の存在）。条件成立は
  人間の記憶でなく §10 に現れる。
- 両 intake は dead-code stage の実証済み契約 — 検出/行動分離・理由コード
  縮退・signal-first 描画・None-vs-0 metrics — を再利用するので、ゲートの
  読みのモデルに新しい形が増えない。

**Negative:**

- 無人チェーンに週次の有界ネットワーク egress（api.github.com、localhost
  probe）が生じる。閉じた語彙への写像と本文非出力で緩和されるが、無から有の
  新規 egress ではある。stage 無効化（`MOLTBOOK_PIPELINE_STAGES` から
  `ledgerwatch` を外す）で旧状態に戻せる。
- `notes_ref` は evidence リンク（rule が狙う違反）と台帳規約**について**の
  記述文を区別できない。初回 20 件の一部はゲートで「容認される言及」と
  判断されうるし、stateless 意味論では容認済み finding が毎週催促される。
  それがノイズ化したら allowlist は独自の設計パスを要する（signal に
  先行して作らない — 意図的な未実装）。
- docs スキャンは git を外部実行する（enja タイムスタンプは `git log
  --name-only` 走査 1 回 + freshness header ごとの `rev-list --count` —
  現行コーパスで実測 ~0.5 秒。初期実装の per-file 形は ~190 サブプロセス /
  ~6 秒で、レビューで畳んだ — 数値は同レビュー中の実測で、畳む前の形は
  履歴に残っていない）。それでも意図として週次の仕事 —
  `verify.sh` には意図的に入れていない。
- `watch:` 注釈は強制点がスキャンの MALFORMED_WATCH エラーただ一つの規約。
  typo した注釈は「黙って監視されない」でなく malformed として報告されるが、
  それもスキャンが走った時だけ。
  *2026-08-15 に限定:* 報告され**なかった** typo が一群あった。`_WATCH_RE` は
  閉じ backtick と引数 1 文字以上の両方を要求し、どちらを欠いてもマッチしない —
  それは「注釈の無い行」と同じ出力なので、blocked である限りそのタスクは
  `fired 0` のままだった。3 種（`unterminated` / `no-argument` / `swallowed`）に
  名前を付け、render（`tasks.py::render_row`）で拒否し、スキャンでも報告する。
  規約の強制点は 2 つになり、うち 1 つは週次より上流にある。
- **2026-08-15 に supersede: stage 6c の入力は file でなく store。** 採択時この
  intake は gitignored の台帳ファイル `TASKS.md` を parse していたが、ADR-0094 以降それは
  gitignored の `tasks/` store の **projection** であり、**どの stage もそれを再生成しない**
  （render は session が手で走らせる）。`tasks.py render` が落ちた週は
  `_atomic_write` に到達しないので前回の表がそのまま残り、しかもそれは正しく
  parse される — stage は、もはや写していない store に対して
  `result=ok watches=N fired=0` を記録し、新しい blocked 行は 1 行も入っていない。
  「render が壊れている」がゲートには「何も発火していない」として届く。この ADR
  自身が禁じている形が 1 層上に移っただけになる。staleness 自体は指摘より前から
  あった（store のどこかに `MalformedTask` があれば `load_store` が同じように
  落ちる）が、上記の render 拒否が入ったことで、到達経路が「store が壊れている」
  から「blocked 行 1 本の `watch:` の typo」へ降りた。
  修正は検証でなく再導出にした: `render_from_store` が `tasks.py render` を
  subprocess で走らせ（別プロセスなので、in-process なら生じる import 循環に
  ならない）、その stdout を parse する。live store で実測: exit 0、186,038 bytes、
  file と byte 一致、0.12 秒、書き込みなし（`--output` 無しの `render` は print
  するだけ）。render できない store は `LEDGER_UNRENDERABLE` で abstain し、
  detail には render 自身のメッセージを載せる — そこには既に該当タスクとセルの
  名前が入っている。
  timestamp 比較は先に作ったうえで 2 つの理由で退けた。第一に、それが検証するのは
  **age であって renderability ではない**: render 側の検査が厳しくなると、store が
  1 バイトも変わらないまま render が落ち始める — `c16642c` と `8265e3c` がまさに
  それで、mtime による検査はその週を fresh と読み、しかも「検証済み」と刻印する。
  第二に、false-stale 側が常態になる: 手動 render の合間、store が projection より
  先行しているのが通常状態で（`claims.py` が両方を union しているのはそのため）、
  stage はほぼ毎週落ち、やがて警告が何も意味しなくなる — 元の失敗が alarm fatigue
  の扉から戻ってくる。再導出は問いに答えるのでなく問いを消す: cache が無いので
  mtime も時計も read/replace 窓も、正直に保つべき limit の一覧も無い。
  disk 上の file の drift は引き続き報告する（`PROJECTION_DRIFT`、`tasks.py render
  --output` 1 回で解消）が fatal にはしない — 読み値はもう file に依存しておらず、
  かつ file は人間が開くものだから。drift は専用の JSON キーと専用の packet コード
  `LEDGERWATCH_DRIFT` で運ぶ: packet は `errors[]` の各要素を「解釈不能な watch
  注釈」として数えて「注釈構文を確認」と印字するので、そこに drift を載せると
  真の signal が偽の名前で届く — 上の欠陥と同じ型が、フィールド 1 つ隣で起きる。

**Neutral:**

- packet の節番号 9 と 10 が予約になった（§5/§8 と同じ予約方式）。§6 の
  metrics 行は不変。
- 台帳ヘッダが注釈文法を文書化する。文法は意図的に `T-…` 行 ID を要求する
  ので、台帳内の散文例はリテラル `watch:` スパンを避ける必要がある
  （採択時に観測: ヘッダの例 4 つが malformed watch として parse され、
  書き直した）。
  *2026-08-15 に精密化:* 制約は この bullet が書くより狭く、しかも上記 3 種の
  うち 1 種にしか掛からない。`` `watch:` `` 単独 — この文と `_HEADER` が注釈を
  指すのに使っているまさにその形、`no-argument` 種 — だけが blocked 行で拒否
  される。「名指すこと」と「発動すること」を分ける構文が無く、live な `ready`
  行が 1 つそれを名指しているため。未閉スパンと swallowed は全ての行で拒否する
  — 状態によらず壊れた markup であり、種を分けて測り直したところ live の実例は
  どちらも 0 件だった。台帳内の散文は `` `watch:` `` を書いてよいが、span を
  開いたまま放置してはならない。
- 同じ検討で特定された off-host ミラー heartbeat は**建てない**（実例なし）。
  建立トリガー条件付きの deferred 台帳タスクとして記録した。
