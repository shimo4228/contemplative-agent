# ADR-0110: 週次のログ読みを系列にする — セッション台帳、週内外れ値、畳んだ窓

## Status

accepted — partially-supersedes ADR-0107 (退役させたもの: D2 の投影サンプル・D3 の denylist・D5 の Phase 0 入力 1)

## Date

2026-09-12

## Context

[ADR-0107](./0107-instrument-census-and-episode-log-folder.ja.md) は 2026-09-12 の朝に、
自己書き込みログすべてへ週次の読み手を付けた。その投影はログごとの件数表と、決定論的に
抜いた 30 行だった。同じ日の午後、RFC-0036 — セッション終端の 11 秒間、やることが無くなった
ループの中で `GET /home` と `GET /feed` を交互に 12 回叩き続ける — が**手集計で**見つかった。
あの投影では見つけられなかったし、調整の問題でもない:

- 故障の形そのものが時間である。件数表の上では、11 秒に 12 行も 1 時間に 12 行も区別できない。
- その週の api-audit 4,035 行から 30 行を抜く標本が、その 12 行を引く期待値は **0.09 行**。
  どの seed でも見えない。

同じ窓での実測（2026-09-05 – 09-11、28 セッション、生ログのみ。`logs/episodes/` は開いていない）:

| 事実 | 値 |
|---|---|
| ADR-0107 の census 出力（同じ週） | **130 KB / 443 行**（ADR の「約 200 行」は誤り） |
| うち投影サンプル | 126 KB — **97%**。問いを持たない行に払っていた |
| 本 ADR の投影（同じ窓） | **24,463 B / 311 行**。2 回走らせて byte-identical |
| 新投影での RFC-0036 | `api-audit:GET /feed gap s` が 0 秒（中央値 148、z −19.6）で 5 件中 3 位。Hunting window に `15:59:09 api-audit:GET /home ×13 in 11s` と `15:59:10 api-audit:GET /feed ×12 in 10s` |
| 新投影での RFC-0032 | 見えない。回避せずそのまま下に明記する |
| JSONL の保持 | `rotate-log.sh` が回すのは `*.log` だけ。llm-calls は 06-09 から、api-audit は 06-25 から全部残るので、過去 4 週の語彙は 1 パス増やすだけで取れる |

ADR-0107 の 1 つ目の `Review-when`（「投影が見せられたはずの故障を Phase 0 が 2 回の週次読みで
拾えなければ」）は**発火していない** — Phase 0 の実行は 0 回。supersede の根拠はその条件でなく、
初回の読みより前に、計器が担うはずの仕事を人がやって見つけた設計欠陥である。ADR-0107 には
日付つきの注記を入れた。

一般化は意図的である。既知の 2 件は**火災報知器に当てる煙であって目的ではない** — `/home` や
`score_relevance` の名を持つ列・閾値・特別扱いを投影が持てば、既に知っている 2 件だけを捕る
計器になる。代わりに覆うのは 4 つの故障形（反復・欠落・順序・値）× 全ログの全 category ×
全セッションで、列はデータから導出する。

### 古典からの転用（2026-09-12 照合、出典つき）

| 転用 | 出典 | この投影での形 |
|---|---|---|
| 4 Golden Signals / RED を**列**に | SRE Book ch.6 (2016); Wilkie RED (2015) | category ごとに時間軸 3 列（per-session 回数 / 1 分最大 / 最小間隔）。閾値と paging は転用しない — ここの故障は全部 HTTP 200 で返り、ch.6 自身が「滅多に発火しない rule は消せ」と書いている |
| USE を予算資源に | Gregg USE (2012) | `rate_remaining` の最小値と 1 分最大を、platform の 60 GET / 30 POST 契約に対して読む |
| canonical log line | Stripe / Leach (2019); Majors et al. (2022) | セッション台帳（1 セッション 1 行） |
| BubbleUp | Honeycomb (2022) | 1 セッション対他 27 を列ごとに |
| Shewhart rule 1 を median / MAD で | Shewhart 1931; Western Electric 1956; Iglewicz–Hoaglin 1993 | 週内外れ値。比較の単位は週でなく**セッション** — 週 4 点では限界を推定できない (Quesenberry 1993) |
| `last message repeated N times` | BSD syslogd | 同一 category の連続イベント（間隔 ≤ 2 s、3 件以上）を 1 行に畳む |
| count invariant は書く（mining しない） | Lou et al. 2010; He et al. 2016 | 既存の Redundancy 節。何であるかを名指ししただけ |
| 圧縮率を反復の tripwire に | LZ76; Cilibrasi–Vitányi 2005 | 台帳の zlib 1 列 |

転用しない: 閾値 paging、burn-rate、S-H-ESD（分解する季節が無い）、Skyline 式の合議（flag の洪水）、
Nelson rules 2–8（連続 8–15 点が要る）、Kleinberg の burst automaton（1 セッション約 23 event に過剰）、
Kayenta の 2 標本検定（週跨ぎ比較を建てない）、process mining の variant 表（28 trace は全部ユニーク）、
Drain / Loghub（これらのログは既に enum）。

同日の skill / MCP 探索（Anthropic 公式 skills、claude-plugins-official、awesome-claude-code / ECC、
MCP registry）では、ローカル JSONL を session × 分で束ね、間隔と median/MAD を出し、常駐を持たない
ものは**見つからなかった**。近かったのは duckdb-skills（汎用 SQL engine で問いは同梱されない）、
json-logs-mcp-server（hour 単位 group-by、11 commit）、log-analyzer-mcp と jsonl-tools-mcp
（grep / filter のみ）、log-mcp（集計なし）、Anthropic の SRE incident-responder cookbook
（`jq` を LLM に叩かせる prompt）、SaaS 連携（Honeycomb / Grafana / Logfire / Opik、いずれも常駐
backend 前提）。読み方の定石は文献として在るが、この形の実装は無い。

### 依存の方針

`pandas`・`tabulate`（`DataFrame.to_markdown` が要る）・`pandas-stubs` は
`[project] dependencies` でなく `[dependency-groups] dev` に入れる。
`scripts/` は wheel の外なので、依存の重さはそこでの却下理由にならない
（`ADR-0109` — 同日起票の「依存のフロアは wheel の中だけ」。この branch にはまだ無い）。wheel は `requests` + `numpy` のまま。
`scipy` は**入れない** — 欲しいのは MAD 1 つで、既にある numpy の 3 行で足り、週跨ぎ検定も建てない。
`weekly-analysis.sh` の census 起動は bare `python3` から `uv run --project … --no-sync -q python` へ
変える（同じ script の skill-selection intake と同じ形）。

## Decision

1. **投影サンプルを削除し、6 節で置き換える。** census 表・Distributions・Redundancy（種類としては
   不変）の後に、**セッション台帳**（1 セッション 1 行、列は log:category ごとの回数に加え 1 分最大 /
   最小間隔 / エラー数 / 予算最小 / zlib 比、末尾に `median` 行。**描く**のは category ごとの
   件数軸だけ — 単位が揃うのはそこだけで、ミリ秒の合計は大きさだけで枠を占めてしまう）、**セッション trace**（全ログの
   イベントを ts 順に、category 1 つ 1 文字で run-length 化。`A B A B` と `A A B B` が区別される）、
   **セッション帯**（最初の 60 分を 60 文字。目盛はその週の最大値で固定し帯どうしを比較できる）、
   **id 欄の反復**（`*_id` / `*_sha256` を名前から自動発見し、同一セッション内の同一値を数える）、
   **週内外れ値**、**Hunting windows**（上位外れ値の周辺の分を syslog 式に畳む）。

2. **列は宣言でなく導出。** REGISTRY 行の `category` 欄に現れた値すべてが、同じ 3 つの時間軸の列に
   なる。列の語彙は今週の category と**過去 4 週の和**、行の集合は全ログの `session_id` の和。
   だから消えた category は全 0 の列、あるログに 1 行も書かなかった session は 0 の行として、
   どちらも走査の普通のセルになる。来週生えた caller や endpoint は、生えた週に登録なしで測られる。

3. **REGISTRY 行は散文の `note` でなく標準軸を持つ。** `Entry` に `category` / `error`
   （健全な行が満たす `(欄, 演算子, 値)` の組。欄が無い・null の行は判定しない）/ `saturation` を足し、
   `note` は削除。census 表の Question 列は欄名から生成する。行は**データ**のまま（callable を持たない）
   なので、土曜ゲートはコードを読まずに編集できる。

4. **投影は load 境界の allowlist になる。** parse した行から取り出すのは `ts`・`session_id`・
   REGISTRY 行が名指す欄・スカラーの `*_id` / `*_sha256` だけ。本文欄は出力から落とすのでなく、
   そもそも値にならない。これは ADR-0107 の D3 denylist を supersede する。`strip_body` と
   `test_projection_strips_bodies_by_name_and_by_shape` は削除し、spy テスト（episode / `.log` を
   決して開かない。ただし spy は下記のとおり修理した）と end-to-end の「出力に本文が無い」テストは
   残す。Markdown の無害化は funnel 1 つに寄せる: `_short` が全てのログ由来文字列に
   `md_safe(printable(…))` を掛ける — その文字列は表のセルにも列名にも凡例にも fence の中の行にも
   なり、4 つの sink に散らした sanitiser は必ずどれかで抜ける（security review 時点で 3 つ抜けていた）。

5. **外れ値は modified z で並べ、較正を 3 つ明示する。** 列ごとにセッション母集団の median / MAD、
   `|z| ≥ 3.5`（Iglewicz–Hoaglin）、上限 5 件で**列ごと 1 行・セッションごと 1 行**。
   - 最小間隔は 3 区間以上を要する（`_MIN_GAP_EVENTS = 4`）。1 区間の最小値は標本であって速度ではない。
   - 間隔と合計は `log1p` で採点する。比尺度なので、逸脱は差でなく倍率である。
   - MAD = 0 のときの尺度の床は Iglewicz–Hoaglin の平均絶対偏差でなく**列の 1 単位**とする。
     彼らの代替は有限だが飽和する — n 件中 1 件だけ外れるとき、逸脱の大きさに関わらず同じ値を返すので、
     定数列が全部 22.3 で並び、順序がアルファベット順に落ちる。

   どの較正も実データに対して選び、どれも単純形が先に失敗した実測である: 間隔の下限が無いと 1 ログの
   疎なセッションが全枠を占め、`log1p` が無いと 1 endpoint の間隔列が 4 桁の z で全枠を占め、
   2 つの重複排除が無いと 1 セッションが同じ事実の 4 つの見え方で 5 枠中 4 つを占めた。zlib 比は台帳で
   読むが順位には入れない — trace の要約であって軸ではなく、件数と同じ尺度に無い。逸脱があれば表の下に
   1 行で出す。

6. **週跨ぎ比較は建てない。** 台帳の末尾は `median` 行で、読み手が materials に既に入っている過去
   レポートと並べる。代替案は下記。

### Consumption plan

- **(a) 誰がいつ読むか。** 無人の `/weekly-report` セッションが毎週、Phase 0 で（サンプルでなく 6 節を）。
  土曜の `/weekly-gate` Step 6f は従来どおり census 表の太字行だけを読む（この段は不変）。
- **(b) 何回の読みで何を決めるか。** 2 回（2026-09-18 と 09-25）で、下記 2 つの較正を通して投影を
  このまま続けるかを決める。以後は Distributions と同じく F1 診断の入力。どの読み値にも数値閾値を
  付けず、外れ値ゼロは正常出力として明示的に許す。1 つ目の Review-when は失敗の 2 通りを両方
  覆うが、直し方は別である: Phase 0 が走らなかった（チェーンの故障 — 直すのはチェーンで、投影は
  未検証のまま）か、走ったのに台帳を引用しなかった（投影の故障 — median 行が 1 行の価値を持たない
  ので替えるか落とす）。どちらかは weekly-pipeline の audit log が言う。
- **(c) いつ撤去するか。** 週次チェーンと一緒に（北極星の機構層停止）。外れ値の**順位付け**だけは
  先に退役しうる: 2 週連続で列挙した全件が `Discarded / no-counterfactual` なら順位付けを落とし、
  台帳を残す。

(b) が回す 2 つの較正。判定可能にするため値をここで凍結する:

1. **RFC-0036（急性）** — 未修理の週で確認済み（上表）。
2. **RFC-0032（慢性）** — 2026-09-05 – 09-11 の台帳 median 行は
   `llm-calls:moltbook.score_relevance` **44.5**、`moltbook.internal_note` **24**、
   `skill-selection:selection` **21**、`llm-calls:moltbook.comment` **11**、
   `verification-audit:comment` **11**、`api-audit:GET /submolts/{name}/feed` **28**。
   修理はこの窓の後に入った。2026-09-18 の観察文書が Exceptions に「score_relevance median
   44.5 → X」と書けば、台帳は意図どおり読まれている。書かなければ下の 1 つ目の Review-when が発火。

## Review-when

- 2026-09-18 か 09-25 の観察文書に台帳 median の行が無い → 台帳が読まれていない。median 行を
  書き手が動かざるを得ないものに替えるか、落とす
- 2 週連続で列挙した外れ値が全部 `Discarded no-counterfactual` → 順位付けが雑音を出している。
  順位付けを外し台帳を残す（消費計画 (c)）
- この投影が見せられたはずの故障が 2 週間のどこかで手集計で見つかる → 節は在るのに読まれていない。
  ADR-0107 とは別の欠陥なので別の直し方（節を減らす、自由文を出さないコード側検査にする）
- 外れ値が 4 週連続で 0 件 → 機構層が変わらなくなった（北極星の成功条件。ならそう書く）か、
  28 点の母集団に対し `_Z_THRESHOLD` が高すぎる
- 外れ値表が 2 週連続で台帳の表示列の外にある列を名指しする（2026-09-05 – 09-11 の窓で
  導出 135 列・表示 10 なので初週から起こりうる） → 「median の大きい順」という表示規則が
  発見を運ぶ側の半分を隠している。逸脱の大きさで並べる
- 帯と trace が 1 ヶ月どの観察文書にも引用されない → 装飾である。削って台帳を残す

## Alternatives Considered

### 過去 4 週との自動比較

系列をちゃんと建てる（各週の台帳を持ち越して今週を検定する）。**建てない**（著者 2026-09-12、
agent `architect` も独立に *Don't build*）。読み手は materials に入っている過去 3 週のレポートから
既に手で系列を作っている（観察 O-009 の 20.2 → 17.8 → 23.4 → 26.6% はそうやって組まれた）。
人が 1 行でやる比較のために、状態ファイルと schema と migration を足すことになる。`median` 行が
機構の全部である。

### ADR-0107 自身の「2 回の週次読み」を待つ

現状維持であり、計器が出荷された当日にこの ADR が先回りした選択肢。ADR-0107 は自分の review gate を
「2 回の週次読み」に置いたが、Phase 0 の実行は 0 回である。待たない理由は遅いからではなく
**情報が得られない**から: 読みが投影についての証拠になるのは、その投影がそもそもその故障を
見せられる場合だけで、標本の期待値 0.09 行は seed や週でなく算術の性質である。2 週待てば、
RFC-0036 を見つけられなかった読みが 2 回増え、なぜ見つからなかったかも出ない。捨てるものは
実在する — 置き換えた側も未読なので、その較正（消費計画 (b)）が同じゲートの正直な版であり、
今度は失効条件と照合できる凍結値を持つ。

### 投影サンプルを新しい 6 節と併存させる

Context の算術で却下: 問いに答えない行に出力の 97% を払い、動機になった故障の検出期待値は 0.09 行。
標本が**本来果たす役割**（文書の選択関数が偏らせられない無加工の窓）は、週次の Random Sample 節
（ADR-0099）が既に担っている — しかも telemetry でなくやり取りから引いている。

### 日次コメントレポート 7 日分の全文読みを退役させて予算を作る

検討して**却下**（著者 2026-09-12、確認の上）。直近 3 週の機構側の発見 7 件のうち 3 件はレポート
からしか出ない（O-008 nonce が出典ラベルとして公開、O-013 skill 見出しの本文流出、O-014 同じ
prompt が 3 回来て毎回新規に返答）。どれもログには出ない。変えるのは文言だけで、「全文読む」→
「grep してから 8・9 節が指したエントリを読む」— セッションが実際にやっていることに合わせる。

### robust 統計のための `scipy`

却下: 欲しい関数は MAD 1 つで numpy 3 行、週跨ぎ検定も建てない。1 関数のために依存を足すのは、
wheel の外であっても依存方針が名指しする行き過ぎである。

### pandas でなく SQL engine（sqlite3 / DuckDB）

13 行の sqlite3 試作でセッション表・1 分最大（連打セッションで 13）・間隔は再現できた。pandas が
許された時点で却下: 同じ集計が `groupby` / `pivot_table` 各 1 行で、trace と帯はどのみち Python が要り、
ファイルの中に 2 つ目の問い合わせ言語が増えるのは読む物が 1 つ増えることである。

### 変化点 / 異常検知パッケージ

`ruptures` / `changefinder` / `adtk` / `river` / `pyod` / `tsod` / `statsmodels` / `prophet`。
重さでなく適合で却下: 1 つの窓の中で比べる 28 点には trend も季節も drift も無く、この規模で
median / MAD 以上を出すものが無い。

### OpenTelemetry のパイプライン

却下: 転送規格 + 常駐 backend が要り、その上で答えるのは誰かが事前に決めた問いだけ — 直そうと
している欠陥と同じ層である。

## Consequences

- **「他のセッションと違う」は慢性故障に構造的に盲目。** RFC-0032 は初日から全セッションに在った
  ので何からも逸脱せず、どの外れ値行にも出ない — 見落としでなく構成上そうなる。この形を覆うのは
  2 つで、どちらも残す: Redundancy 節（書かれた count invariant、ADR-0107 D4）と、台帳の絶対値と
  比を読む読み手。census の冒頭文にこれを書いたので、読み手が推測する必要は無い。
- **D4 は層を足すのでなく減らす。** allowlist は今在る欄に対しては厳密に強い（本文は読まれない）が、
  置き換えた形ベースの網（200 文字超の文字列・文字列の list 全部）は**まだ誰も名指していない欄**も
  覆っていた。REGISTRY 行は土曜ゲートで人が編集するデータ（Decision 3）なので、自由文の欄を名指す行が
  入れば `_VALUE_MAX_CHARS` = 60 文字までが Distributions に載る。残したテストが検査するのは現在の
  REGISTRY であって編集面ではない。制御は `REGISTRY` を編集する段（weekly-gate 6f）で、それは人の手で
  ある。もし自由文の欄を名指す編集が実際に起きたら、安い修理は `strip_body` の復活でなく enum 値への
  形の assertion である。
- **ADR-0107 が拠り所にしていた境界テストは何も検査していなかった。この diff で修理した。**
  spy は `builtins.open` を差し替えていたが、census は `Path.read_text` で読む。これは module
  属性経由で `io.open` を呼ぶので `builtins` を通らない。spy の記録は 0 件で、assert は空リストを
  量化して**どんな挙動でも通った** — `census()` に `logs/episodes/` の読みを入れても PASS した。
  今は `Path.read_text` も張り、そもそも記録があることを assert し、突き合わせは `logs/` の**下**の
  path で行い（pytest の tmpdir がテスト名を含むので、絶対 path には必ず "episodes" と ".log" が
  出る）、その変異を実際に入れて FAIL することを確認した。境界自体は破られていない。無かったのは
  証明の方である。
- 定数列で列挙されるには `3.5 × 1.4826 ≈ 5.2` 単位の逸脱が要る（Decision 5）。全セッションが 3 回
  呼ぶ category を 1 セッションだけ 0 回、は外れ値表に**出ない** — 台帳の 0 として見える。
  列をまたいで z を比較可能にする床の代償である。
- 初回の実行が、誰も問うていなかった事実を 2 つ読んだ: 1 セッションが 2 秒で
  `comment-outcomes:reply` を 1,919 行書いた（中央セッションは 0 行）。過去 4 週に在った
  `llm-calls` の caller 16 個が今週は不在（月次・パイプライン専用の caller で、読みとしては正しく
  退屈 — 異常が無いときの 0 列はこう見える、という見本）。
- 出力は 130 KB に対し 25 KB だが、そこに収める表示予算（135 列中 10 列、trace 10 run、hunting 18 行）
  は今週の形に合わせた値である。ファイル冒頭の定数であり、表示規則そのものが誤りである条件は
  上の Review-when が名指ししている。
- 帯は block 文字でなく ASCII ランプを使う。block の方が読みやすいが 1 文字 3 バイトで、
  28 セッション × 2 帯 × 60 分で 7 KB — 読み全体の 1/4 を字形に払うことになる。
- **読み手は 1 ファイルでなく 3 モジュール。** 単一ファイルは予算 500 行に対し 1,063 行に達した。
  予算は引き算を誤った算術だった: サンプル退役で 250 行浮く前提だったが、実際に消せたのは
  `strip_body` 37 + `_render_sample` 20 + 累算器 `_Acc` 44 ≈ 101 行で、同時に REGISTRY が育った
  （`note=` 1 行が 3 つの宣言軸になった）。ADR-0107 が立てたものだけを持つファイル — header・
  `Entry`・`REGISTRY`・読み込み・census 表・Distributions・Redundancy・`main`、および ruff format が
  def 間に強制する空行 — の実測が既に **約 535 行**で、この計器のどの版も 1 ファイル 500 行には
  収まらない。分割は行数でなく責務で切った:
  `_census_registry.py`（**333**）が登録表の schema・status 語彙・読み込み（2 つの境界を含む）、
  `_census_series.py`（**315**）が集計と統計（ファイルに触れない）、`instrument_census.py`（**431**）が
  9 節の描画と、週次チェーンが呼ぶエントリポイント。import は下向きだけなので読む向きは 1 つ。
  **合計 1,079 行 — 分割そのものは 1,063 → 1,048 で、その後 code review の修理 5 件が +31**。
  3 つの header 分は圧縮で払った: module docstring が本 ADR の
  再掲をやめ（−29）、`REGISTRY` を `# fmt: off` の下で 1 行 1 レコード × 2 行に手で折り
  （82 → 33。ゲートはこの表を行単位で編集するのに formatter の 1 引数 1 行が 15 行を 82 行にしていた）、
  単一利用の helper 3 つを inline した（−11）。読み手に見えるものは 1 つも削っていない — 出力は
  分割前と byte-identical。
- 週次 materials の生成に `pandas` が要るようになった。dev group を sync していない機械では、
  shell が元から持つ stub 行（`No instrument census available`）が出るだけで、チェーンは壊れない。
- 語彙のために各ログを 1 週でなく約 5 週読むようになった。現在の corpus（api-audit 13.9 MB）で
  全体 1.8 秒なので、差分読みは作らない。

## References

- [ADR-0107](./0107-instrument-census-and-episode-log-folder.ja.md) — 部分 supersede の対象
  （D2 投影 / D3 denylist / D5 Phase 0 の入力 1）。D1（episodes フォルダ）・D4（content identity）・
  D6（配線）はそのまま
- [ADR-0101](./0101-instrument-dissolution-mandate.ja.md) — 上の消費計画が存在する理由
- `ADR-0109`（依存のフロアは wheel の中だけ） — pandas を `scripts/` で許す根拠。同じ branch に
  乗ったらリンクにする
- [ADR-0099](./0099-weekly-report-instrument-redesign.ja.md) — 無加工の窓の役を既に担う Random Sample 節
- [RFC-0036](../../rfcs/0036-session-end-cycle-spin.md) — 煙として使った急性の故障
- [RFC-0032](../../rfcs/0032-feed-score-cache-per-cycle.md) — この投影に見えない慢性の故障
