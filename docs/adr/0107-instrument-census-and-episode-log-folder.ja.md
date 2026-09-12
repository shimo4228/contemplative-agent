# ADR-0107: 自己書き込みログにはすべて読み手を付ける — 計器センサス、Phase 0 通読、エピソードログのフォルダ分離

## Status

accepted

## Date

2026-09-12

## Context

RFC-0032（同じ投稿を 1 セッションで約 10 回 LLM 採点し、全文 GET と internal note の生成も
毎回やり直す）は、挙動が始まって 6 ヶ月後の 2026-09-12 にコードレビューで見つかった。証拠は
初日から disk にあった: `core/llm/__init__.py:emit_llm_telemetry` が LLM 呼び出し 1 回ごとに
`logs/llm-calls-{date}.jsonl` へ `caller`・prompt digest・（`_io.append_jsonl_restricted` 経由で）
`session_id` を書く。(session, caller, digest) ごとに行を数えれば 1 週目に出ていた。週次チェーンの
どの段もこのファイルを読んでいなかった。

2026-09-12 の `$MOLTBOOK_HOME/logs/` 棚卸し（コードから writer → reader を辿る）で、これが 1 本の
問題でなく一般形だと分かった:

| 読み手 | ファイル |
|---|---|
| 自動読み手ゼロ | `llm-calls-*`, `constitution-shadow`, `injection-detect-*`, `verification-audit`, `weekly-pipeline-audit`, `pipeline-metrics` |
| 手動 script のみ（チェーン外） | `insight-novelty`, `insight-staged`, `submolt-scope-*` |
| writer 退役、ファイルだけ残存 | `insight-worth.jsonl`（ADR-0097）, `noise-*.jsonl`（ADR-0060） |
| 毎週読まれている | `audit.jsonl`, `api-audit.jsonl`, `skill-selection-*`, `comment-outcomes`, `*.log`, エピソードログ（hash 投影のみ、ADR-0083） |

構造的原因は 2 つで、計器 1 本の欠落ではない:

1. **週次の読みはすべて事前に決めた問いに答える。** 7 つの intake（anomaly sweep / API drift /
   state invariant / cross-day duplicate / skill selection / never-selected / confusion pair）は
   それぞれ誰かが既に想像した故障クラスを符号化している。観察文書（RFC-0010）が受け付けるのは
   宣言済み baseline からの偏差と決定論計器の信号だけ。反復された**正常な**呼び出しは警告を
   出さず、不変条件を壊さず、誰も宣言した baseline でない — 既知の問いしか立てない系には
   見えない。問いを付けずに LLM が生データに近いものを読む段が無かった。
2. **エピソードログ禁止の射程が間違っていた。** エピソードログ（`YYYY-MM-DD.jsonl`、他エージェント
   が書いた生テキスト）は `logs/` 直下に自己書き込みの 14 ファイルと同居していた。
   `~/.claude/hooks/_episode-log-common.sh` の Bash guard はそのため `logs/` 配下の glob を全部
   止めていた — このバグを調べる操作者自身の `llm-calls-*.jsonl` 集計も含めて。混在 dir への
   ファイル名 regex で引いた境界は「他人のテキストを読むな」でなく「logs/ を見るな」を教える。

読み手を作る途中で 3 つ目の事実が出た: `prompt_sha256` は**生の** prompt の digest で、wrap された
呼び出しは毎回新しい nonce（`secrets.token_hex`、`guard.py`）を持つので、同じ本文への 2 回の呼び出し
が digest を共有しない。RFC-0032 修理前の週にセンサスをかけると **反復 0** と読めた。テレメトリは
呼び出しがあったことは記録したが、以前にもあったとは言えなかった（ADR-0089 §968 が eval replay の
文脈で同じ drift を記していた）。

## Decision

1. **エピソードログを `logs/episodes/` へ移す。** `adapters/moltbook/config.py` に
   `EPISODES_DIR = EPISODE_LOG_DIR / "episodes"`。`EpisodeLog` とレポート生成はこれで構築する
   （呼び出し 6 箇所）。`EPISODE_LOG_DIR` は名前を保ち、自己書き込みテレメトリの dir のまま。
   週次セッションの deny はフォルダ `Read(/$MOLTBOOK_HOME/logs/episodes/**)`、duplicate scan の
   `--log-dir` も追従、harness guard の predicate は「`episodes` という名の dir 直下の日付名
   `.jsonl*`」、Bash の glob 規則は `/logs/…*` から `/episodes/…*` へ狭める。既存 225 ファイル
   （日次 190 / `.bak` 9 / `.pre-cleanup.bak` 26）は 2026-09-12 に一度だけ移送し、件数を照合、
   削除なし。守る対象はフォルダ 1 つになり、1 段上は全部読める。
2. **登録表駆動のセンサスが最後の読み手**（`scripts/instrument_census.py`、read-only、stdlib）。
   `REGISTRY` は自己書き込みログ 1 本につき 1 行: glob、所有 ADR、`live` / `writer_retired`、
   分布を出す enum / numeric 欄、任意の session 内 `redundancy_key`、任意の heartbeat
   `expect_events`。行がそのファイルへの毎週の問いそのもの。出力は順に: 閉じた語彙の status を
   持つセンサス表 — `OK` / `NO_ROWS`（live で窓内 0 行）/ `MISSING_EVENT` / `ORPHAN`（退役 writer、
   ファイル残存）/ `UNKNOWN`（ファイルあり、行なし）/ `ABSENT`; 分布; redundancy（同一 `session_id`
   内の同一 key。session 跨ぎの反復は正当）; 各ログの決定論・本文剥ぎ取り済み投影サンプルと、
   最長 session の `caller` run-length 列。センサスは `logs/episodes/` と `*.log` を決して開かない。
   追加・削除の stale 検知はこの週次読み値だけ — 行なしで書き始めた writer は `UNKNOWN`、退役した
   writer は `NO_ROWS`、残存ファイルは `ORPHAN`。書き込み時契約も import 検査も持たない（下で却下）。
3. **投影は名前と形の denylist で、信用しない。** `_b64` 終わり、本文トークン（`content` `prompt`
   `output` `body` `message` `text` `reason` `note`）を含む名前（`_sha256` 終わりを除く）、200 文字超の
   文字列、文字列のリスト全部（モデル生成の名前 — skill-selection renderer の ADR-0083 境界）を落とす。
   数値・真偽・timestamp・enum・id・digest は残る。`tests/test_instrument_census.py` が境界を pin
   （`open` を spy して「episode / `.log` を開かない」を含む）。
4. **テレメトリに内容の同一性を持たせる。** `guard.nonce_stable_digest` が `untrusted_content_<hex>`
   nonce を正規化した prompt をハッシュし、`emit_llm_telemetry` が生 digest の隣に
   `prompt_norm_sha256` を書く（ADR-0065 の metadata-only 契約は保つ — 一方向 digest）。センサスの
   llm-calls redundancy は `(caller, prompt_norm_sha256)` をキーにする。2026-09-12 以前の行は
   この欄を持たず数えない。
5. **週次セッションに Phase 0 — 通読を足す**（`weekly-report` skill）。観察文書を合成する前に、
   センサス（**判断**の投影: 採点・選択・呼び出し列）と 7 日分の comment-report **全文** —
   `Context`（相手の投稿）を含む。返答は相手の投稿なしに読めないし、report は既に加工済みの
   正規経路 — を、開いた問い 1 つ（*反復・欠落・順序・値に予期しないものはないか*）で読む。
   気づきは既存 6 見出しの中へ — センサス由来は Exceptions、行動由来は Deviations の (b) 構造的
   新規性、Counterfactual が書けなければ Discarded `no-counterfactual`。**機構側の観察のみ**:
   skills / rules / identity / constitution を直せば解ける類は書かない — 値層は観察対象であって
   修理対象ではなく、その種の提案が続いたことが文書を RFC-0010 の形へ縮めた理由。処方も書かない。
   F1/F2/F3 診断は不変。
6. **配線。** `weekly-analysis.sh` が state-invariant check の後にセンサスを走らせ materials の
   同位置に `## Instrument Census` を置く。`config/prompts/weekly-analysis.md` は (5b) として列挙し、
   census status と redundancy を Exceptions の信号に加える。`weekly-gate` Step 6f はセンサスの
   太字 status 行だけ読んで `REGISTRY` を直す。孤児 2 ファイルはここでは**削除しない** — `ORPHAN`
   として出し、人間がゲートで決める。

### Consumption plan

- **(a) 誰がいつ読むか。** 無人 `/weekly-report` セッションが毎週 Phase 0 で（分布・redundancy・
  投影）。土曜 `/weekly-gate` Step 6f がセンサス表の非 OK 行だけ。
- **(b) 何回の読みで何を決めるか。** 非 OK status 1 つにつき 1 読みで登録表の編集 1 つ
  （登録 / 退役 / 削除 / 理由 1 行つきで放置）。redundancy と分布の偏りは F1 診断の入力で、
  それ自体は決定でない。どの読み値にも数値閾値を付けない。
- **(c) 撤去条件。** `logs/` への書き込みが書き込み時に登録行を要求するようになったとき
  （`append_jsonl_restricted` の契約）— 週次の `UNKNOWN` 検査は冗長になりセンサスは分布と投影だけに
  縮む。または週次チェーン自体が退役したとき（北極星: 機構層は止まる）。

## Review-when

- センサスの投影に**写り得た**のに Phase 0 が存在後 2 回の週次読みで拾わなかった第 2 の故障クラスが
  出た → 通読が仕事をしていない。LLM 段に別の投影（例: session ごとの時系列）を渡すか、落とすかを
  再検討する。
- `prompt_norm_sha256` の反復が設計上の retry を持つ正当な caller に 4 週連続で支配される → 読み飛ばす
  のでなく `REGISTRY` にその caller の除外を書く。
- 登録表の編集が 1 ヶ月に 2 回以上要る月が出た → (c) の書き込み時契約の方が週次の人手より安い。作る。
- 禁止にもかかわらず Phase 0 が値層への提案を出し始めた → 禁止文が効いていない。通読を自由記述の無い
  コード側投影へ移す。
- hook の `episodes` 親 dir 規則が他 repo の正当な `episodes/` を止めた → フォルダ名が二役をしている。
  writer と guard の双方で名前空間を付ける（例: `moltbook-episodes`）。

## Alternatives Considered

- **Bash guard の glob 規則をリテラル接頭辞判定で直す**（「`*` の前の接頭辞が日付か
  `agent-launchd.log` の先頭になりうる時だけ止める」）。著者が却下: 境界が混在 dir への regex の
  まま残る。守る対象を専用フォルダへ移す方が単純で、見た通りに読める。
- **エピソードログでなくテレメトリを移す**（`logs/instruments/`）。却下: writer 14 本、launchd
  plist、rotation / backup script、全 reader が動く。エピソードログは writer 1 種・reader 経路 1 つ。
- **センサスに加えて `append_jsonl_restricted` の書き込み時登録契約と import 解決の writer テスト。**
  却下（著者、2026-09-12）: 週次で検知できる条件に網を重ねる冗長。センサスの status が追加・削除を
  既に検知する。登録表の編集が頻発したときの撤去条件 (c) として残す。
- **未読ログごとに専用 reader。** 却下: 固定の問いを持つ script 6 本は故障形を再生産する — 次の
  未読ログは誰かがその故障を想像するまで読み手を持たない。登録行は script より安く、`UNKNOWN`
  が次のファイルを覆う。
- **Phase 0 に生のエピソードログを読ませる。** 却下: comment-report が同じ本文を正規経路で既に
  運び、判断側はセンサスが覆う。ADR-0083 の境界は立ったまま。
- **Phase 0 を自筆部分（`Internal note` / `Output`）に限る。** 著者が却下: 返答は答えた投稿なしに
  判断できない。report は加工済み出力で、以前の週次形式は全文を読んでいた。

## Consequences

- 未読だった 6 本のログが毎週宣言済みの問いに答える。孤児 2 本は人間が決めるまで見える。
  初回の実走（2026-09-05 – 09-11）は `constitution-shadow` と `insight-novelty` に `NO_ROWS` を
  出した — 月次 shadow とその週 staging しなかった pipeline なら想定内だが、沈黙でなく明記になった。
- 週次 materials は 1 節（`--sample 30` で約 200 行）増える。`/weekly-report` セッションが Phase 0 で
  読む。読み方の規律は skill の文面にあり code で強制しない — 失敗は Review-when が覆う。
- `logs/episodes/` は `MOLTBOOK_HOME` の新しい path。backup（`logs/` を丸ごと除外）、
  `sync-research-data.sh`（同）、anomaly sweep（`*.log` glob）は無影響。`logs/YYYY-MM-DD.jsonl` を
  綴っていた外部ツールは追従が要る。repo 内は定数 1 つが唯一の綴り。
- harness guard（global、`~/.claude`）とこの repo は同時に変わった。公開 harness copy は別途同期
  （`harness-sync`）。
- `llm-calls` 行に 12 hex の欄が 1 つ増える。redundancy の読みは 2026-09-12 から。RFC-0032 の週自体は
  この方法では読めない — 生 digest は nonce 込み。
- センサス自体も計器で、上の消費計画が無ければゲートで拒否される（ADR-0101）。その撤去条件が
  「作ること」なのは意図した逆転 — 安い方をコストが測れるまで残す。
