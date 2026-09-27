# Plan: 自己書き込みログの週次読みを「件数分布 + 30 行サンプル」から「セッション 1 行の表 + 週内外れ値 + 畳んだ窓」へ（ADR-0107 D2 / D3 / D5 の部分 supersede → ADR-0110）

## スコープ（著者 2026-09-12）: 既知バグの対症療法ではなく、今後の未知の異常を拾う仕組み

仕組みの被覆 = **4 つの故障形（反復 / 欠落 / 順序 / 値）× 全ログの全 category × 全セッション**。対象をバグ名で
名指しする列・閾値・特別扱いは持たない。具体的に守る不変条件:

- **列は宣言しない、導出する。** ログに現れた category（caller / endpoint / kind / event …）すべてについて同じ
  4 軸（回数 / エラー / 所要時間 / 予算）と時間軸 3 列（per-session 回数 / 1 分最大 / 最小間隔）をセッションごとに
  計算し、外れ値の走査は**その行列全体**にかける。表示だけ量の多い列に絞る。新しい caller や endpoint が
  生えた瞬間に同じ軸が当たる（登録変更なし）
- **欠落も同じ行列で見る。** 行列の**列の語彙**は今週のログに現れた category と**過去 4 週の生ログに現れた
  category の和**（集合の和だけ。統計比較ではない — B は建てない）。**行の集合**は全ログの `session_id` の和。
  だから「今週から完全に消えた category」は全セッション 0 の列として、「あるログに 1 行も書かなかった session」は
  0 の行として、どちらも外れ値走査に乗る（Codex 反証 3 を採用、2026-09-12）
- **反復は id 欄を自動発見して数える。** 名前が `*_id` / `*_sha256` の欄を登録なしで拾い、同一セッション内の
  同一値の反復回数を (log, 欄) ごとに median / max で出す（declared な `redundancy_key` はその特例に縮む）
- **順序は run-length の trace で見せる。** session の全イベント（全ログ、ts 順）を category ごとに動的に文字割当
  （凡例つき）し、既存 `_compress_sequence` の run-length で 1 行にする（`H A B A B` と `H A A B B` を区別する。
  cycle 別の件数に潰さない — Codex 反証 1 / 代替 4 を採用）。`GET /home` は cycle の標識として**主張しない**
  （初期化 `agent.py:771` でも取得し、cycle の取得は `:822` — 1:1 でない。Codex 反証 2 を採用）。連打を畳むのは
  表示だけで、件数は畳まない
- **新しい書き手は UNKNOWN で登録を迫られ、登録した瞬間に同じ軸が当たる**（ADR-0107 の census 表はそのまま）
- **既知の 2 件（RFC-0032 / RFC-0036）は目的でなく動作確認**（火災報知器に煙を当てる fault injection）。
  合成 fixture のテストと、修理前の実データでの目視に使うだけで、投影にその名を持つ列は無い

## 平たい全体像（何を捨てて何を足すか）

1. **今朝の census が見せているもの**: ログごとに「件数の表」と「30 行のランダム抜き出し」。ランダム抜き出しでは
   11 秒間の `GET /home` 連打 12 行は 4,035 行の中から平均 0.09 行しか当たらない — 空叩きは**原理的に**見えない。
   出力 130 KB のうち 97% がこの抜き出しで、当たらないものに 35k トークン払っている
2. **代わりに足すもの**: 監視の定石（SRE の 4 シグナル / Stripe の 1 リクエスト 1 行ログ / Honeycomb の「異常な 1 つを
   他全部と比べる」/ 工程管理の Shewhart rule 1 / syslog の `repeated N times`）でログを**セッション 1 行の表**に変える。
   列は cycle 数・LLM 回数（caller 別）・API 回数（endpoint 別）・エラー・予算残り・**1 分間の最大回数**・**最小間隔**。
   28 セッションを並べ、1 つだけ他と違う行を数字で挙げ（`/home` の 1 分最大が他は全部 2、1 つだけ 13）、その時間帯を
   `GET /home ×12 in 11s` と畳んで見せる。**試作を実データで走らせたら空叩きは #2 に浮いた。出力 14 KB**。
   集計は **pandas**、統計は numpy の MAD 3 行（著者決定 2026-09-12: 基礎ライブラリを避けて再発明しない、
   ただし過剰なら入れない → scipy は 1 関数のためなので不採用。sqlite3 案は失効）
3. **見えないもの（正直に）**: 同じ投稿の再採点（RFC-0032）はこの表では見えない。「他と違う」でも「変化」でもなく最初から
   ずっとそうだった慢性だから。慢性は「同じ入力が同じセッションに 2 回来た回数」を数える Redundancy（今朝の D4）でしか
   見えない — そこは残す
4. **コメントレポート 7 日分の全文読み**: **残す**（著者 2026-09-12「冗長であれば削除して良い」→ 冗長でなかった）。直近 3 週の
   機構側の発見 7 件のうち 3 件（O-008 nonce が出典ラベルとして公開 / O-013 skill 見出しが本文に流出 / O-014 同じ prompt が
   3 回来て毎回新規に返答）はレポートからしか出ない（`weekly-2026-08-28.md:70`、`weekly-2026-09-11.md:146,181` で確認）。
   文言だけ「全文」→「grep してから該当エントリを読む」に直す（`weekly-2026-09-11.md:51-60` のとおり実際にそうしている）
5. **「今週 vs 過去 4 週」の自動比較（B）は建てない**（著者決定 2026-09-12、architect と一致）: 表の末尾に今週の代表値
   （median 行）を 1 行出すだけにし、過去レポートと並べるのは読む側

## Context

ADR-0107（2026-09-12 朝）は census + Phase 0 を入れた。同日、RFC-0036 を手集計で見つけたことで、census の api-audit
投影（endpoint 別週合計 + 30 行無作為抽出）が時間の形をした故障に**構造的に**盲目だと分かった。ADR-0107 の Review-when
1 つ目（「2 回の週次読みで拾えなければ」）は**厳密には発火していない**（読みは 0 回。architect の指摘）。supersede の根拠は
発火でなく、初回の読みの前に見つかった設計欠陥。ADR-0107 にはその旨を日付つきで注記する。

実測（9/5〜9/11、28 セッション、生ログのみ。`logs/episodes/` は開いていない）:

| 事実 | 値 |
|---|---|
| 現行 census 出力（同じ週） | **130 KB / 443 行 ≈ 35k トークン**（ADR-0107 の「約 200 行」は誤り） |
| うち Projection sample | 126 KB（97%）。verification-audit 20 KB、llm-calls 18 KB、comment-outcomes 16 KB … |
| daily comment reports | 2.46 MB / 週（materials 2.59 MB の 95%）。ただしセッションは grep で当たりを付けて読んでおり全文は読んでいない |
| 試作投影（scratchpad `proto.py`、同じ週） | **14 KB / 225 行 ≈ 4k トークン** |
| 試作での RFC-0036 | 週内外れ値 #2（`home_max_1m` 13 vs 他 27 セッション全部 2、MAD 0）。畳んだ窓に連打が出る。**新事実**: `GET /feed` も交互に空転（RFC-0036 本文に無い） |
| 試作での RFC-0032 | 慢性なので週内外れ値にも週跨ぎにも出ない。ledger では score_relevance 44/セッション vs comment 11 の比としてだけ見える。「feed GET = 0 なのに採点 > 0」の cycle も 0/220（submolt 別 feed は毎 cycle 取りに行く） |
| 週別 median（参考） | `score_relevance`/セッション: 08-14 週 136 → 62 → 58 → 36 → 44（8/14→8/21 の一段は原因未特定。ADR-0110 に記録） |
| JSONL の保持 | `rotate-log.sh` は `*.log` のみ。llm-calls は 6/9〜、api-audit は 6/25〜が全部残る |
| `session_id` | `core/_io.py:178` `append_jsonl_restricted` が run session 中の全行に刻印。cycle 数の記録は無く `GET /home` 行が唯一の cycle 標識（`adapters/moltbook/agent.py:822`） |
| 9/12 の 2 セッション | score 34 / 21（修理版がいつから走ったか未確認。校正には使えない） |

### 古典からの転用（2026-09-12 照合、一次ソース付き — 研究 agent 報告を判断）

| 転用する | 出典 | この投影での形 |
|---|---|---|
| 4 Golden Signals / RED を**列**として当てる | SRE Book ch.6 (2016)、Wilkie RED (2015) | session を持つログの Distributions に時間軸 3 列（per-session max / 1 分最大 / 最小間隔）。閾値・paging は転用しない（故障は全部 200。ch.6 自身が「滅多に発火しない rule は消せ」） |
| USE を**予算資源**に | Gregg USE (2012) | `rate_remaining` min と GET/POST の 1 分最大（60 GET / 30 POST の platform 契約に対する利用率） |
| canonical log line | Stripe / Leach (2019)、Majors et al. (2022) | **session ledger**（1 セッション 1 行）と **session trace**（cycle 別 wide event を 1 行に） |
| BubbleUp | Honeycomb (2022) | 週内: 1 セッション vs 他 27、列ごとに modified z、該当だけ列挙 |
| Shewhart rule 1 を median/MAD で | Shewhart 1931 / WE 1956 / Iglewicz–Hoaglin 1993 | 週内外れ値。**単位は週でなくセッション**（週 4 点では限界を推定できない。Quesenberry 1993） |
| syslog `last message repeated N times` | BSD syslogd | 同一 category の連続行（間隔 ≤ 2 s、3 行以上）を `GET /home ×12 in 11s @15:59:09` に畳む |
| count invariant を**書く**（mining しない） | Lou et al. 2010 / He et al. 2016 | 「同一 (caller, prompt_norm_sha256) ≤ 1 回/セッション」= 既存 Redundancy。RFC-0032 型はこれでしか見えない |
| 圧縮率を反復の tripwire に | LZ76 / Cilibrasi–Vitányi 2005 | ledger に 1 列（zlib）。説明不能なので見出しにしない |

### skill / MCP 層の search-first（2026-09-12、scout 報告）

Anthropic 公式 skills、claude-plugins-official、awesome-claude-code / ECC、MCP registry の 4 系統に「session × 分の
集計 + 間隔 + median/MAD をローカル JSONL に常駐なしで当てる」skill / agent / MCP は無い。近かったもの:
duckdb/duckdb-skills（engine の汎用 SQL skill、問いは同梱されない）、mfreeman451/json-logs-mcp-server（hour 単位
group-by まで、11 commit）、Fato07/log-analyzer-mcp と antonlvovych/jsonl-tools-mcp（grep / filter のみ）、
ascii766164696D/log-mcp（Rust + BERT で集計なし）、Anthropic の SRE incident-responder cookbook（「LLM に jq / grep
させる」prompt）、Honeycomb plugin / Grafana / Logfire / Opik MCP（SaaS か常駐 backend）。ローカルにキャッシュ
された ando-marketplace の incident-response / error-diagnostics / observability-monitoring / debugging-toolkit は
ELK / Prometheus / Datadog 前提の一般論。→ 読み方の定石は文書として在るが Claude 用の実装は無い（Build）。

転用しない: 閾値 paging、burn-rate（検出時間は週で固定）、S-H-ESD（分解する季節が無い）、Skyline 合議（flag 洪水）、
Nelson rules 2–8（連続 8–15 点が要る）、Kleinberg burst automaton（23 event/セッションに過剰）、Kayenta の 2 標本検定
（著者決定で B を建てない）、pm4py / trace variant 表（28 trace は item 数で全部ユニーク）、Drain/Loghub（既に enum）。

### 依存の方針（著者 2026-09-12: 「scipy も pandas も入れてよい。基礎ライブラリを避けて再発明しない」）

同日の追記「過剰なら入れなくていい」で判定: **pandas は入れる、scipy は入れない。**
- pandas: 行列 / 分バケット / 間隔 diff / cycle cumsum / id 反復 / `to_markdown` — 手書き ~150 行が各 1 行。本業
- scipy: 使うのは MAD 1 関数で numpy（既存依存）3 行。1 関数のために足すのは過剰。週跨ぎ検定は建てないので他に出番なし

この決定で、上の「stdlib のみ」「sqlite3 で集計」は**失効**。pandas と `tabulate`（`to_markdown` の依存）を
`[dependency-groups] dev` に置く（`uv run` が既定で sync する。wheel の `dependencies` は requests + numpy のまま —
`scripts/` は wheel に入らない）。census の起動は bare `python3` から `uv run --no-sync python` に変える
（先例: skill-selection 段 `weekly-analysis.sh:502`）。方針は memory（feedback）に保存する（実装着手時）。

再発明しないもの → ライブラリの対応:

| 手書き予定だったもの | 置き換え |
|---|---|
| JSONL 読み込み・窓フィルタ | `pd.read_json(path, lines=True)` を concat、`ts` を `to_datetime(utc=True)` |
| session × category の回数行列（0 埋め） | `pivot_table(index="session_id", columns="cat", values=…, aggfunc="size", fill_value=0)` |
| 分バケット最大 | `groupby(["session_id","cat", ts.dt.floor("min")]).size().groupby(level=[0,1]).max()` |
| 連打間隔（最小・中央値） | `groupby(["session_id","cat"])["ts"].diff().dt.total_seconds()` |
| trace（run-length） | 全ログ concat → `sort_values("ts")` → `groupby(session_id)["cat"]` → 既存 `_compress_sequence` |
| category の語彙（欠落用） | 過去 4 週分も `read_json` して `cat.unique()` の和（統計は取らない） |
| id 欄の反復 | `groupby(["session_id", field, value]).size()` |
| median / MAD / modified z | numpy 3 行: `np.median`、`1.4826 * np.median(np.abs(x - med))`（scipy は不採用） |
| 分位点・p95 | `Series.quantile(0.95)` |
| markdown 表 | `DataFrame.to_markdown()`（`tabulate` を dev group に足す）— 手書き render を消す |
| syslog 式の畳み込み、凡例つき trace 文字列 | 手書き（各 ~15 行。ライブラリに無い） |

### search-first（2026-09-12 照合 — scout 報告。依存方針の更新前の verdict は上で上書き）

実データ試験の記録: sqlite3 の SQL 13 行でセッション表・1 分最大（a6eac8ae = 13）・連打間隔が再現できた
（scratchpad `proto_sqlite.py`）— pandas なら同じ集計が groupby / pivot 各 1 行。OpenTelemetry はこの repo にも
harness にも無く、仮にあっても転送規格 + 別途の backend（常駐）と「何を測るか」の定義が要る層で、既知の問いにしか
答えない — 今回の欠陥と同じ層。
robust z は Iglewicz–Hoaglin (1993) modified z（公表定数 3.5）、MAD = 0 は「定数 c からの逸脱」枠（値と定数を並べる
だけ）。変化点/異常検知パッケージ（ruptures / changefinder / adtk / river / pyod / tsod / statsmodels / prophet）は
N≈28 点の週内比較に過剰で、median/MAD 以上の機構を持ち込む理由が無い → 不採用（依存の重さは理由にしない）。
DuckDB / lnav / agrind / mlr は pandas が入るなら役割が無い → 不採用。Datadog / Honeycomb /
OTel collector: ローカル静止ファイルの週次バッチに送出・常駐・課金を足すだけで統計は自前 → 対象外。

## Build-or-not（4 問。judge-tier の自答 + agent: architect の独立判定、2026-09-12）

| 候補 | ①存在 | ②大きさ | ③消費者 | ④失効 | architect | 採用 |
|---|---|---|---|---|---|---|
| **A** ledger + trace + 週内外れ値 + 畳んだ窓 | 削除で解けない（30 行サンプルを消すだけでは RFC-0036 を拾えない）。既存流用: 集計は pandas、統計は numpy、表は `to_markdown` | `instrument_census.py` 1 ファイル **≤ 500 行**（現行 616。sample / strip_body / run-length / 手書き render −250、pandas 集計 + trace + 畳み込み + 節組立 +130）。出力 **≤ 250 行 / ≈ 5k トークン**。新規ファイル・状態・常駐 0。依存は dev group に pandas / tabulate | `/weekly-report` Phase 0（毎週）。`/weekly-gate` 6f は不変 | 週次チェーン退役。外れ値順位: **2 週連続で全件が Discarded `no-counterfactual`** なら順位付けを落として ledger だけ残す | **Build smaller**: 独立の RED 表は Distributions と重複、15 行中 rate/error/duration を持つのは 4 行で残りは filler → 落とす。外れ値は top 5 上限 + 生値併記 | A' = 下記 |
| **B** 今週 vs 過去 4 週の自動比較 | 読む側が previous reports（3 週）から手で系列を作っている実績（O-009: 20.2→17.8→23.4→26.6%）。慢性に盲目 | — | — | — | **Don't build** | **建てない**（著者決定）。ledger 末尾に median 行を 1 行 |
| **C** comment-report 全文読みの退役 | 機構側 Deviation 7 件中 3 件がレポート由来（O-008/013/014）で log からは出ない。materials を切ると Phase 1（Ledger / Deviations）が痩せる | — | — | — | **Don't retire**。skill の 1 行を grep-first に | **残す**。文言のみ変更 |

架空の「4 つ目の未読計器」化を防ぐ具体策（architect 指摘）: 順位付き top-N は健康な週にも #1 を必ず出す → **|z| ≥ 3.5 か
定数逸脱に該当する行だけ**（上限 5、無ければ「該当なし」が正常出力）、z の横に生値と母集団の median / MAD を併記。

## 投影の形（`## Instrument Census` の中。census 表 → Distributions → Redundancy → 以下 4 節）

全節が**本文欄を読まない**: 印字するのは ts / enum / 数値 / id の **allowlist** だけ（生行を印字しなくなるので denylist
`strip_body` は不要 → 削除。allowlist は denylist より強い境界）。

1. **Distributions（現行 + 時間軸 3 列）** — enum 分布と数値 min/median/max は現行どおり。`session_id` を持つログの
   `category` 欄には per-session max / **1 分最大** / **最小間隔 s** を足す。session を持たないログ（audit / pipeline-metrics /
   insight-* / constitution-shadow / weekly-pipeline-audit）は現行のまま
2. **Session ledger（1 セッション 1 行）** — 行 = 全ログの `session_id` の和、start 順。**列は導出**: 各ログの各
   category（語彙 = 今週 ∪ 過去 4 週）について per-session 回数、加えてログ単位で error 数 / duration 合計 /
   saturation min / 圧縮率。`GET /home` は他の category と同じ 1 列（生件数。cycle 数とは呼ばない）。**表示**は
   セッション合計が多い順に上位 ≈ 16 列（残りは節 4 の走査対象にはなるが表には出ない）。**末尾に median 行**
   （B の代替。週次文書が Exceptions の Clean-this-window 行に写し、previous reports 経由で読み手が系列を見る）
3. **Session trace（1 セッション 1 行、run-length）** — 全ログのイベントを ts 順に並べ、category を文字に動的割当
   （凡例を先頭に）、`_compress_sequence` で `H f×15 s×14 n×10 c×3 H f s×8 …` のように run で書く。順序が残る
   （`A B A B` ≠ `A×2 B×2`）。「問いの無い生データ」の代替。28 行、≈ 6 KB
3a. **Session strips（文字のグラフ。著者決定 2026-09-12）** — セッションごとに 60 分 = 60 文字の帯を 2 本
   （API 行数 / 分、LLM 行数 / 分）。`▁▂▃▄▅▆▇█` の 8 段、0 は `·`。目盛はログごとに**その週の全セッション共通の最大値**
   で固定し（帯どうしを比べられる）、凡例に `█ = N/min` を書く。例: `a6eac8ae API ·▁▁·▁▁·▁▁·▁▁·▁·▁▁·▁▁·▁▁·▁▁·▁▁·▁▁·▁▁·▁▁·▁█`
   → 末尾 1 分の `█` が連打。28 × 2 行 ≈ 4 KB。連打・空白・末尾集中の形が見え、数値は節 2 と節 4 から引用する
3b. **id 欄の反復（自動発見）** — 各ログの `*_id` / `*_sha256` 欄について、同一セッション内の同一値の反復回数を
   (log, 欄) 1 行で: sessions / median 反復 / max 反復（session 短縮 id つき）。declared な `redundancy_key`
   （D4 の `caller + prompt_norm_sha256`）は既存 Redundancy 節に残す
4. **週内外れ値（BubbleUp）** — **行列全体**（語彙 = 今週 ∪ 過去 4 週の全 category × 時間軸 3 列 + ログ単位列、
   行 = 全ログの session の和、0 埋め）で列ごとに
   median / MAD（28 セッション母集団）。|modified z| ≥ 3.5 の行、または MAD = 0 で母集団の定数から離れた行を、
   z 降順で**上限 5**。列: z / 列名 / session / 値 / median / MAD。該当なしは「no session departed from the others」
   の 1 行。欠落（普段ある category が 0）も同じ走査で出る
5. **Hunting windows** — 節 4 の上位 3 件について、そのセッションのピーク分 ±2 分を **syslog 式に畳んで** ≤ 25 行
   （`HH:MM:SS category ×N in Ks` / 単発は `HH:MM:SS category status`）。category は何でもよい

残す: census 表（status 語彙、太字行）、**Redundancy 節**（D4 の `prompt_norm_sha256` 鍵 = count invariant）、
`_compress_sequence`（trace の実体。最長 session だけだった適用を全 session・全ログに広げる）。
消す: Projection sample、`random` import。

### Codex plan-stage 反証の fold（2026-09-12、1 回・1 系統。折衷なし）

| # | finding | 判定 |
|---|---|---|
| 1 | cycle 別件数の trace は cycle 内順序を失う | 採用 → trace は run-length |
| 2 | `GET /home` は cycle と 1:1 でない（初期化 `agent.py:771` / cycle `:822`）。<5 s を畳むと高速反復の不具合を消す | 採用 → cycle 数を主張しない、件数は畳まない |
| 3 | 週初から消えた category は列が生えず、0 行の session は行にならない | 採用 → 語彙 = 今週 ∪ 過去 4 週、行 = session の和 |
| 4 | 代替: `_compress_sequence` を全 session に広げる | 採用（1 と同じ処置） |

**トークン**: 現行 ≈ 35k → **新 ≈ 6k**（試作 14 KB + trace / strips / id 反復 / median 行の増分 ≈ 7 KB）。
materials（2.59 MB）は変えない。

## REGISTRY の行（`note` を標準軸に置き換える。callable は持たない — 行は data）

```python
Entry(glob, owner_adr, status=LIVE,
      enum_fields=(...), numeric_fields=(...),          # 現行（Distributions）
      category="caller",                                # 時間軸 3 列と ledger / trace の単位。無いログは None
      error=("outcome", ("ok",)),                       # (欄, OK 値の集合)。集合外なら error。None なら数えない
      saturation="rate_remaining",                      # 予算軸（min）。None 可
      redundancy_key=(...), expect_events=(...))        # 現行
```

census 表の Question 列は `note` でなく欄名から生成（例: `caller · error if outcome∉{ok} · duration_ms`）。
13 live 行の写像（試作で確認）: llm-calls = caller / outcome∈{ok}、api-audit = endpoint / status<400 / rate_remaining、
comment-outcomes = kind、skill-selection = kind / publish_status∈{published}、verification-audit = action /
solve_success∧verify_success、submolt-scope = event、injection-detect = event、audit = command / decision∈{approved…}、
weekly-pipeline-audit = stage / result≠fail、pipeline-metrics = phase、insight-novelty = verdict、insight-staged = None、
constitution-shadow = verdict。試作の副産物: skill-selection に `kind` 無し 379 行（書き手 3 つのうち 1 つ）→ category
`None` 行として Exceptions に出る。ADR-0110 Consequences に記す（修理は起票）。

## ベースライン（B を建てないので消費計画は投影自身に）

- **(a)** `/weekly-report` Phase 0、毎週。`/weekly-gate` 6f は不変（太字行のみ）
- **(b)** 最初の 2 読み（9/18、9/25）で校正 2 件（下記）が読み手に落ちなければ投影を変える。以後は F1 診断の入力
- **(c)** 週次チェーンの退役。外れ値順位だけ: 2 週連続で全件 Discarded `no-counterfactual` なら順位付けを落とす
- 保存ファイル無し。ledger median 行の「過去」は previous reports（materials 第 10 節、3 週）が担う

## 動作確認（既知の故障 2 件を煙として当てる。目的ではない）

| 故障 | データ | 新投影での見え方 | 判定 |
|---|---|---|---|
| RFC-0036（連打） | 修理前 9/5〜9/11 の api-audit | 節 4: `home_max_1m` 13 vs 定数 2（**試作で #2 確認済み**）。節 5 に `GET /home ×12 in 11s` | 合成 fixture で pin。commit 前に実データで再確認 |
| RFC-0032（再採点） | 修理前 9/5〜9/11 の llm-calls | 週内にも週跨ぎにも浮かない（慢性）。修理後は ledger median 行の `score` が下がる | **ADR-0110 に 9/5〜9/11 の median 行を凍結**（score 44.5 / note 24 / sel 21 / reply 7.5 / comment 11 / cycles 7 / home_max_1m 2）。9/18 の週次文書が Exceptions に「score median 44.5 → X」を書けば校正成立。書かなければ Review-when 発火 |

ADR に明記: 「自分の過去との差」は慢性故障に構造的に盲目。慢性は (i) count invariant（Redundancy）と (ii) ledger の
絶対値・比を読む LLM が受け持つ。

## ADR-0107 の supersede（新 ADR-0110、0107 には日付つき注記）

| 0107 | 扱い |
|---|---|
| D1 episodes フォルダ | 残す |
| D2 census | **部分 supersede**: REGISTRY 駆動・status 語彙・Distributions・Redundancy は残す。Projection sample / caller run-length → ledger / trace / 外れ値 / 畳んだ窓。REGISTRY 行は `note` → 標準軸 |
| D3 denylist | **supersede**: 投影は allowlist だけを印字。`strip_body` と `test_projection_strips_bodies_by_name_and_by_shape` は削除。「episodes / .log を開かない」spy と「出力に本文が無い」end-to-end は残す |
| D4 content identity | 残す（count invariant として位置づけ直す） |
| D5 Phase 0 | **部分 supersede**: 入力 1 を census 表 + 4 節に。入力 2（comment reports）は残し「全文」→「grep-first、節 4–5 が指した session の日時のエントリは全文」 |
| D6 wiring | 5b の文言と weekly-report 本文を更新。6f は「分布・redundancy・投影は Phase 0 が読み済み」を「4 節」に |
| Review-when 1 つ目 | 「発火はしていない（読み 0 回）。2026-09-12 に投影の構造欠陥（時間軸無し）を手集計で発見 → ADR-0110」と注記 |
| 消費計画 (c) 書き込み時契約 | 引き続き不採用 |

## 週次チェーンの配線

- `scripts/weekly-analysis.sh` `# --- Instrument census` 段（450–467 行）: `python3` → `uv run --no-sync python`
  （pandas / scipy は venv にしか無い。先例 502 行）。冒頭コメントを「セッション 1 行の ledger + 週内外れ値 +
  畳んだ窓。状態なし」に書き換え（鮮度規約）。stub 文字列は不変（`tests/test_weekly_analysis_shell.py:277` が pin）。
  shell テストの fixture が bare `python3` で census を呼ぶ前提なら合わせて直す
- `.claude/verify.sh` は `uv run` 経由なので変更なし。`uv lock` の差分を同 PR に含める
- `config/prompts/weekly-analysis.md` (5b、92 行) と Exceptions の信号列挙（58 行）: 「distributions / projection sample」→
  「distributions / session ledger / trace / within-week outliers / hunting windows」、Exceptions に「週内外れ値・定数逸脱」を
  足し、Clean-this-window 行に「ledger median 行を写す」を足す
- `.claude/skills/weekly-report/SKILL.md` Phase 0（32–61 行）: 入力 1 を 4 節に、入力 2 の「全文読む」を grep-first +
  hunting に。問い（反復・欠落・順序・値）と禁則（機構側のみ・処方なし）は不変
- `.claude/skills/weekly-gate/SKILL.md` 6f（305–319 行）: 1 文だけ
- `docs/diagrams/pipeline-05-weekly-gates.workflow.json` + HTML 再生成（skill archify）: census 段は ADR-0107 で図に
  入っていない → 本 PR で 1 ノード足す（鮮度規約の追いつき）
- `graph.jsonld`: ADR-0110 ノード + 0107 との supersedes 辺
- `CLAUDE.md` 「Claude Code エピソードログ直読み禁止」節の `instrument_census.py` 説明を 4 節の語に

## 実装順序（feat。RED → GREEN、verify.sh）

0. **memory に feedback を保存**（`feedback_basic_libs_allowed.md`）: 「pandas / scipy 等の基礎ライブラリは依存に
   入れてよい。避けて再発明しない。ただし 1 関数のためなら入れない（著者 2026-09-12）。scripts/ の依存は dev group」。skill 層の search-first の結果
   （該当 skill / MCP なし、2026-09-12）はこのプランと ADR-0110 の Alternatives に記録する
1. **RED** — `tests/test_instrument_census.py`（合成 fixture、実ログは読まない）:
   - `test_burst_in_any_category_is_a_within_week_outlier`: 28 セッション分の合成行（1 つだけ**任意の** category
     `X` を 12 行 11 秒に）→ 節 4 の先頭が `X` の 1 分最大でそのセッション、節 5 に `X ×12 in 11s`。
     category 名は fixture 側の定数で、実装が特定の endpoint 名を知らないことを pin
   - `test_new_category_gets_axes_without_registry_change`: REGISTRY を触らず未知の caller を混ぜた fixture で、
     その caller の列が ledger 行列に生える
   - `test_absent_category_in_one_session_is_an_outlier`: 27 セッションに毎回ある category が 1 セッションで 0 →
     節 4 に値 0 で出る
   - `test_category_seen_last_weeks_but_absent_this_week_is_a_zero_column`: 過去週の合成行にだけある category →
     今週の行列に全 0 の列として現れ、節 4 の「定数からの逸脱」でなく「全セッション 0」として 1 行出る
   - `test_session_with_no_rows_in_one_log_gets_a_zero_row`: api-audit にだけ現れる session が llm-calls の列で 0
   - `test_trace_keeps_within_cycle_order`: `H A B A B` と `H A A B B` の trace 文字列が異なる
   - `test_id_field_repeats_are_auto_discovered`: `foo_id` を持つ合成行が同一セッションで 3 回 → 節 3b に
     (log, foo_id) max 3
   - `test_strip_is_60_chars_and_peaks_at_the_burst_minute`: 60 分セッションの帯が 60 文字、連打の分だけ `█`、
     0 の分は `·`、目盛が週の最大値で固定（別セッションの同じ回数が同じ文字になる）
   - `test_collapse_runs_same_category_within_two_seconds`: 純関数（≥ 3 行・間隔 ≤ 2 s だけ畳む、混在は畳まない）
   - `test_mad_zero_departure_is_listed_without_infinity`
   - `test_healthy_week_lists_no_outliers`: 28 セッションが同型 → 節 4 は「no session departed」1 行
   - `test_ledger_has_one_row_per_session_and_a_median_row`
   - `test_trace_is_run_length_over_all_logs`: 2 ログ混在の合成行が ts 順に 1 本の run-length になる
   - `test_registry_category_and_error_are_data`（tuple / str のみ、callable 無し）
   - `test_aggregation_matches_hand_count`（合成 5 行: 行列 / 分最大 / 連打間隔を手計算と照合）
   - `test_body_fields_never_enter_the_frame`（`prompt_b64` / `content` を持つ行を load しても DataFrame の columns に
     無い）
   - 残す: `test_registry_globs_cover_the_known_writers`、`test_rendered_output_carries_no_bodies`（`prompt_b64` /
     `content` を入れた行が出力に現れない）、`test_episodes_and_dot_log_files_are_never_opened`（spy）、TestStatus 全部、
     TestRedundancy の 2 本、`test_non_ok_rows_are_summarized_up_front`、`test_main_never_fails_the_caller`
   - 残す: `test_caller_sequence_keeps_order_as_runs`（`_compress_sequence` は trace の実体として残る）
   - 削除: `test_projection_strips_bodies_by_name_and_by_shape`、`test_sample_is_deterministic_for_a_seed`
2. **GREEN** — `scripts/instrument_census.py`: `Entry` に `category` / `error` / `saturation`、`note` 削除。
   読み込みは `pd.read_json(lines=True)` の後、REGISTRY が名指す欄（ts / session_id / category / error 欄 /
   numeric / saturation）と `*_id` / `*_sha256` 欄**だけ**を `df[keep]` で残す — 本文欄は DataFrame に入らない
   （allowlist は load 境界で成立）。集計は pivot_table / groupby / diff / cumsum（上の対応表）、統計は numpy の
   MAD 3 行、表は `to_markdown()`。手書きは `collapse_runs` と trace の文字列化と節の組立だけ。`random` と
   `strip_body` を削除。**ファイル ≤ 500 行**。
   `pyproject.toml`: `[dependency-groups] dev` に `pandas`、`tabulate`（`to_markdown` の依存）、`pandas-stubs`
   （pyright 用）を追加し `uv lock`。`[tool.pyright] include` に `scripts` は無いので型ゲートは ruff のみ
   （`evals` と同じ扱い。足すかは実装時に判断）
3. **Doc sync（同 PR）**: ADR-0110 新設（skill adr-writer → agent adr-reviewer。消費計画 (a)(b)(c)、校正表、凍結した
   median 行を Review-when に）、ADR-0107 注記、weekly-analysis.sh 冒頭コメント、weekly-analysis.md、weekly-report /
   weekly-gate SKILL.md、diagram 05 JSON + HTML、graph.jsonld、CLAUDE.md
4. `bash .claude/verify.sh`（ruff format / ruff / pyright / lint-imports / bandit / shellcheck / markdownlint / pip-audit /
   pytest）→ `/code-review medium`（実装者と別 process）
5. **校正の実行（commit 前）**: 9/5〜9/11 で走らせ、節 4 の上位 2 件に `home_max_1m a6eac8ae`、節 5 に `GET /home ×12` が
   出ることを目視。ledger median 行の値を ADR-0110 の凍結値と照合。出力 bytes が 25 KB を超えていれば列を削る

## Verification

- `uv run pytest tests/test_instrument_census.py tests/test_weekly_analysis_shell.py -q`、`bash .claude/verify.sh` exit 0
- 実データ: `python3 scripts/instrument_census.py --home ~/.config/moltbook --start 2026-09-05 --end 2026-09-11 | wc -c`
  ≈ 15–25 KB。同じ引数で 2 回走らせて byte-identical（乱数を消した決定論）
- `bash scripts/weekly-analysis.sh --end-date 2026-09-11 --out /tmp/x.md` → `## Instrument Census` が 1 回、stub 無し
- 9/18 の週次文書の Exceptions に「score median 44.5 → X」が出るか（校正 2、ADR-0110 Review-when）
