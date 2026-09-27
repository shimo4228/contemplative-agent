# Plan: 計器センサス + 週次通読 Phase + episode log のフォルダ分離

## Context

RFC-0032（同一投稿を 1 セッションで ~10 回 LLM 採点）は半年見つからなかった。信号は初日から
`llm-calls-{date}.jsonl`（`core/llm/__init__.py:318 emit_llm_telemetry` が全 LLM 呼び出しに
`caller` / `prompt_sha256` / `outcome` を記録、`_io.py:178` が `session_id` / `run_id` を自動付与）に
あったが、**読み手がゼロ**だった。棚卸し（2026-09-12）で読み手ゼロの自己書き込みログは 6 本、
手動 script のみ 3 本、writer 退役後の孤児 2 本。

構造的な原因は 2 つ: (1) 週次の読みが「事前に決めた問い（計器）」と「宣言済み baseline からの偏差」
だけで、**決めていない問いを LLM が生データの投影から見つける段が無い** (2) エピソードログ禁止 hook の
射程が `logs/` 配下全体に及び（glob は全部 block）、自己書き込み計器の集計まで止まる。

著者判断（2026-09-12）: センサスを足す / 通読 Phase を足す / hook は regex を直すのでなく
**エピソードログをフォルダで分離**する / 通読から値層（skills・rules・identity）への改善提案は出さない。

## 変更 A: エピソードログを `logs/episodes/` へ移す（hook 誤検知の根治）

- `adapters/moltbook/config.py` に `EPISODES_DIR = EPISODE_LOG_DIR / "episodes"`。
  `EpisodeLog(log_dir=…)` の構築 6 箇所（`core/memory.py:128`, `core/distill.py:141`,
  `cli/memory_cmds.py:59`, `cli/session_cmds.py:236/321/463`）と `core/report.py:generate_report /
  generate_all_reports` の呼び出し元を `EPISODES_DIR` に。`append_jsonl_restricted` が親 dir を作る
  ので mkdir 追加は不要
- `scripts/weekly-analysis.sh:463` の `cross_day_duplicate_scan.py --log-dir` を `logs/episodes` に
- `scripts/weekly-pipeline.sh:358` の deny `Read(/$MOLTBOOK_HOME/logs/20*.jsonl*)` →
  `Read(/$MOLTBOOK_HOME/logs/episodes/**)`（prefix 形の説明コメント :346 も更新）
- `scripts/backup-runtime.sh` / `sync-research-data.sh` は `logs/` 単位の除外なので無変更
- **一回限りの移送**（実装 step、`mv` のみ、削除なし）: `logs/` 直下の `^[0-9]{4}-[0-9]{2}-[0-9]{2}\.jsonl`
  で始まる 225 ファイル（.jsonl 190 / .jsonl.bak 9 / .pre-cleanup.bak 26）を `logs/episodes/` へ。
  移送前後で件数一致を確認。移送は次の運用セッション（JST 0/6/12/18）に重ねない
- 文書: CLAUDE.md「エピソードログ直読み禁止」節の path、ADR-0083 の path 記述、memory
  `comment-reports-canonical-read-path` は無変更（reports 側）

**hook 側（`~/.claude/hooks/_episode-log-common.sh`、global 正本）**: 予測を「`logs` 直下の日付名」から
「`episodes` 直下の日付名」に変更（`is_episode_log_path` の parent 判定、`episode_logs_reachable` の
`find -name logs` → `episodes`）。Bash guard の glob 規則 `'/logs/[^ ]*\*'` と `cd …/logs` は
`/episodes/` に狭める。`agent-launchd.log` の名指し規則はそのまま（logs/ 直下に残る）。
`~/.claude/tests/episode-log-guards.bats` の fixture を `logs/episodes/` に移し、
「`cat logs/llm-calls-*.jsonl` は allow」「`cat logs/episodes/*.jsonl` は block」を追加。
公開 copy への反映は後で `harness-sync`（この plan の外）。

## 変更 B: `scripts/instrument_census.py`（新規、read-only、stdlib のみ）

`state_invariant_check.py` と同型（`--home`, `--start`, `--end`, markdown 出力, 失敗は reason 行,
exit 0）。`logs/episodes/` は開かない（episode の投影は変更 C で別扱い）。

**登録表 `REGISTRY`**（script 内 frozen dataclass tuple）: `glob`, `owner_adr`, `status`
(`live` / `writer_retired`), `enum_fields`, `numeric_fields`, `redundancy_key`, `expect_events`。
enum_fields が「そのログに毎週答えさせる問い」そのもの — **読み手ゼロだった 6 本はここで初めて
読み手を得る**:

| glob | 毎週答える問い | enum / numeric / key |
|---|---|---|
| `llm-calls-*.jsonl` | 同一 session で同一 prompt を何回呼んだか（RFC-0032 型）。caller 別の outcome / error / 打ち切り率 | caller, outcome, error_kind, done_reason / duration_ms / **(caller, prompt_sha256)** |
| `constitution-shadow.jsonl` | shadow 憲法の乖離は動いているか（ADR-0092 の「次回改正ゲートの材料」を週次読み値にする） | verdict / cosine_vs_current |
| `injection-detect-*.jsonl` | guard は生きているか（`guard_alive` が窓内に 1 行以上）、除去は起きたか | event, saturated / total_removed / expect_events=(guard_alive,) |
| `verification-audit.jsonl` | CAPTCHA 解答の成功率は落ちていないか | solve_success, verify_success, action, solver_path |
| `weekly-pipeline-audit.jsonl` | 先週の chain のどの stage がどの reason で落ちたか（watchdog は成果物の有無しか見ない） | event, stage, result, reason |
| `pipeline-metrics.jsonl` | 土曜ゲートの判定分布 | phase, verdict |
| `insight-novelty.jsonl` | novelty judge の fail_open 率 | verdict, reason |
| `insight-staged.jsonl` | 週の staging 件数 | （件数のみ） |
| `submolt-scope-*.jsonl` | scan の完走率 | event, verdict, subscribed |
| `api-audit.jsonl` | endpoint 別 status 分布（drift scan は schema しか見ない） | method, endpoint, status |
| `audit.jsonl` | 承認決定の分布 | decision, source, command |
| `skill-selection-*.jsonl` | 同一 prompt の再選択 | kind, verdict, enforced / **(kind, prompt_sha256)** |
| `comment-outcomes.jsonl` | 行種の分布 | kind, by_self |
| `insight-worth.jsonl` | writer_retired (ADR-0097) | — |
| `noise-*.jsonl` | writer_retired (ADR-0060) | — |

**出力 `## Instrument Census`**:
1. Census 表: file / status / rows_in_window / sessions / last_ts。status は `OK` / `NO_ROWS`
   （live で窓内 0 行）/ `MISSING_EVENT`（expect_events 不在）/ `ORPHAN`（writer_retired で disk 残存）
   / `UNKNOWN`（disk にあるが表に無い）/ `ABSENT`。追加・削除の stale 検知はこの週次読み値だけで
   行う（機構を重ねない）: 未登録 writer → UNKNOWN、writer 退役 → NO_ROWS、箱だけ残存 → ORPHAN。
   直すのは土曜ゲート
2. 分布: enum の値分布（上位 8）、numeric の min/median/max
3. Redundancy: redundancy_key を持つエントリで (session_id, key) が 2 回以上の件数、
   Σ(n−1)、最大反復、上位 10（caller / repeat / outcome 分布）。digest 12 hex はそのまま出す
4. **投影サンプル**（LLM 通読用、`--sample N` 既定 30）: 各 live エントリの窓内行を決定論サンプル
   （seed = end-date）し、**本文欄を落として** 1 行 1 JSON。落とす欄: `_b64` 終わり /
   `content` `prompt` `output` `body` `message` `text` `reason` を含む名前 / 200 文字超の文字列。
   llm-calls は窓内最長 session の `caller` 時系列を 1 行に圧縮（`moltbook.comment ×1,
   moltbook.internal_note ×9 …`）。テストで「出力に b64 欄・200 文字超文字列が無い」を pin

孤児 2 本の処分はこの PR ではしない — ORPHAN として土曜ゲートに出し、人間が決める。

## 変更 C: 週次チェーンへの配線

- `scripts/weekly-analysis.sh`: State Invariant Check（:437）の直後に同型ブロックで
  `INSTRUMENT_CENSUS` を作り、USER_PROMPT の `$INVARIANTS` の次に挿入。冒頭コメントの intake 列挙更新。
  状態ファイル無し（promote 配線不要）
- **`.claude/skills/weekly-report/SKILL.md` に「Phase 0 — 通読」を Phase 1 の前に追加。**
  入力は 2 つ: (a) `## Instrument Census`（判断の投影 — 採点・選択・呼び出しの系列）
  (b) Daily Reports = 7 日分の comment-report **全文**（`Context`（相手の投稿）/ `Internal note` /
  `Output`。相手の投稿を読まなければ文脈が分からない — comment-report は加工済みで、読んでよい
  正規経路。untrusted 枠の「中の指示に従わない」はそのまま）。
  問いは開いたまま: 「予期しない反復・欠落・順序・値はないか」。
  **出すのは機構側の観察のみ** — skills / rules / identity / constitution を直せば解ける類は
  書かない（値層は観察対象であって修理対象ではない。過去にこの種の提案が続いて今の簡素な
  文書になった — RFC-0010）。書き先は既存 6 見出しの中: 計器由来は Exceptions、行動由来は
  Deviations (b) 構造的新規性（Counterfactual が書けなければ Discarded `no-counterfactual`）。
  診断 F1/F2/F3 は変えない
- `config/prompts/weekly-analysis.md:92` の materials 構成列挙に Instrument Census を追加、
  Exceptions 節の列挙に「census status / redundancy」を追加
- `.claude/skills/weekly-gate/SKILL.md` T4 手順に「Census の UNKNOWN / ORPHAN / NO_ROWS 行を読み、
  登録表を直す」1 行

## 変更 D: テスト

- `tests/test_instrument_census.py`（`test_state_invariant_check.py` の形）: UNKNOWN / ORPHAN /
  NO_ROWS / MISSING_EVENT 判定、redundancy 集計（session 跨ぎは数えない、同 session 同 key 3 回 →
  repeat 3 / redundant 2）、`logs/episodes/` と `agent-launchd.log` を置いても open されない、
  投影に b64 欄・200 文字超が無い、登録表の各 glob が既知ファイル名に当たる
- `tests/test_weekly_analysis_shell.py:262` の intake 到達テストに `## Instrument Census`
- episode 移送に伴う既存テスト: `EpisodeLog` を tmp dir で構築するテストは無影響。
  `test_weekly_pipeline_session_scope_shell.py` の deny 規則検査を `episodes/**` に更新
- `bats ~/.claude/tests/episode-log-guards.bats`

## 変更 E: 文書同期（同 PR）

- **ADR-0107**（+ `.ja.md`）: Context に RFC-0032 の 6 ヶ月と棚卸し（読み手ゼロ 6 / 手動 3 / 孤児 2）、
  Decision に (1) episodes/ 分離 = 「守るのは本文を持つ箱だけ」 (2) 登録表と status 語彙
  (3) Phase 0 通読 = 決めていない問いを LLM が見つける段、値層提案の禁止、
  `### Consumption plan`（ADR-0101）: (a) 毎週 `/weekly-report` Phase 0 が読む、UNKNOWN / ORPHAN /
  NO_ROWS は土曜 `/weekly-gate` T4 が読む (b) status 行は 1 読みで登録表を直す、redundancy の偏りは
  F1 診断の入力 (c) 撤去条件 — logs/ の書き込み時契約（登録なしに書けない）に置換されたとき。
  `docs/adr/README.md` index、`graph.jsonld` に ADR ノード、ADR-0083 の path 追補
- CLAUDE.md: 禁止節の path を `logs/episodes/`、「本文を落とした投影（`instrument_census.py --sample`）
  なら読める」を 1 行
- diagram `pipeline-05-weekly-gates.workflow.json` は materials ノード内部の変更なので更新不要

## 実行者

in-session で実装する（変更は script 1 本 + shell 2 箇所 + config 定数 1 つと呼び出し元 +
hook 1 ファイル + 文書。文脈が全部ここにあり委任オーバーヘッドの方が大きい）。
著者直接指示なので RFC 起票はせず、ADR-0107 が判断記録。

## Verification

- `uv run pytest tests/ -v` 全 PASS（episodes 移送後に `EpisodeLog` 系・shell 系が緑）
- `./scripts/weekly-analysis.sh --end-date 2026-09-11 --out <scratch>/materials.md` →
  `## Instrument Census` が出て、llm-calls の Redundancy に `moltbook.internal_note` 等の repeat が
  実データで見える（RFC-0032 修理前の日付を窓に含める）
- `bats ~/.claude/tests/episode-log-guards.bats` 全 PASS。その後 Bash で
  `python3 scripts/instrument_census.py --home ~/.config/moltbook …` が hook に止められない、
  `cat ~/.config/moltbook/logs/episodes/2026-09-11.jsonl` は止められる
- `ls ~/.config/moltbook/logs/episodes | wc -l` = 225、`logs/` 直下に日付名ファイルが残っていない
- `contemplative-agent generate-report` が新 path から comment-report を再生成できる
- `.claude/verify.sh`、`git status` で ADR index / graph / prompts / skills / CLAUDE.md が同 commit
