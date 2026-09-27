# submolt スコープ計器 (Phase 1: 観測のみ)

## Context

現在、エージェントが活動する submolt の範囲は `config/domain.json` の
`submolts.subscribed`（8 件）を人間が決めている。「ここもエージェントに選ばせては」
という問いに答えるための前提が 3 つ欠けている。

コードを読むと `subscribed` は**構造的に別物の 2 役を兼務**している:

| 役 | 場所 | 性質 |
|---|---|---|
| 読む範囲（feed 取得元） | `feed_manager.py:63-82` | read-only・可逆 |
| 反応してよい範囲（trust boundary） | `feed_manager.py:282-290` | 外部副作用・ADR-0007 |

後者は ADR-0044 で「search rotation を活かすために緩める」案を明示的に却下した境界
("that filter is an intentional scope boundary, not a bug")。同じフィールドなので、
片方に自律性を渡すともう片方も黙って渡る。

さらに、いま自律選定を入れても**判断材料がゼロ**である。本番の relevance スコアは
通過分に偏った分布しか持たず（feedback: relevance-distribution）、未購読 submolt の
当たり率は誰も測っていない。`client.py:841` の通り `unsubscribe_submolt` は
security by absence で削除済みなので、自律 subscribe は撤退経路のない片方向ラチェットになる。

**この変更の目的**: trust boundary を一切動かさずに、「未購読 submolt に取りこぼしが
あるか」「エージェントの選定は人間の 8 件選定より良くなりうるか」をデータで答えられる
状態にする。ADR-0071 の instrument-first、ADR-0076 の shadow 型をそのまま踏襲する。

## Scope

**やること（Phase 1）**: 読み取り専用の計器。discovery 用の GET 能力 1 個、
週次スキャン、監査ログ、集計読み値。

**やらないこと（明示）**:
- `subscribed` の自動変更・自動 subscribe / unsubscribe
- `_passes_content_gates` の submolt フィルタ緩和（trust boundary は不動）
- エージェント自身に範囲を提案させる shadow 選定（Phase 2。この計器の読みを見てから）
- 読む範囲 / 反応する範囲のフィールド分割（Phase 3）

計器はゲート・ランキング・retrieval に一切配線しない（ADR-0071 の不変条件）。

## Step 0: 前提の実測（実装前・ブロッキング）

未購読 submolt の feed が購読なしで読めるかを実測する。API doc
(`https://www.moltbook.com/skill.md`) は `GET /api/v1/submolts`（一覧）と
`GET /api/v1/submolts/{name}/feed` を公開しているが、購読要否を明記していない。

1. 既存 `client.get()` で未購読 submolt の feed を 1 本叩く
2. 403/401 なら `GET /posts?submolt={name}` にフォールバック（doc 上こちらは公開読みの記述）
3. どちらも不可なら**停止して報告** — 観測に subscribe が要るなら trust boundary を
   越えることになり、この Phase の前提が崩れるので設計から議論をやり直す

## 実装

### 1. discovery 能力 — `adapters/moltbook/client.py`

`list_submolts()` を追加（`GET /submolts`）。既存の `get()` / envelope 正規化
(`client.py:48` 周辺) と、`subscribe_submolt()` が使っている submolt 名バリデータを
そのまま再利用する。返り値は検証済み名の `tuple[str, ...]`。write 能力は追加しない。

### 2. 理由コード付き relevance — `adapters/moltbook/llm_functions.py`

現行 `score_relevance()` は **3 つの異なる理由で 0.0 を返す**（空入力 /
LLM 不達 / パース不能 / レンジ外）。計器がこれを区別できないと分布が汚れる。

- `score_relevance_detailed(post_text) -> RelevanceScore(score: float, reason: str)`
  を新設（frozen dataclass）。reason は `scored` / `empty_input` /
  `llm_unavailable` / `unparseable` / `out_of_range`
- 既存 `score_relevance()` は `.score` を返す薄いラッパにする — **本番挙動は不変**
- プロンプト解決・`wrap_untrusted_content(max_input=1000)`・`generate()` 呼び出しは
  既存実装をそのまま移送（重複実装しない）

### 3. 計器本体 — `adapters/moltbook/submolt_scope.py`（新規）

`core/skill_selection.py` を構造テンプレートとして踏襲する:

- `configure_submolt_scope(audit_dir: Path | None)` — module-global。
  `audit_dir=None` で計器そのものが no-op（**kill switch が設定に内蔵**）
- `reset_submolt_scope()` — テスト隔離用
- `scan_submolt_scope(client, domain, *, sample_size=20)`:
  - `client.list_submolts()` で候補集合を取得
  - **購読中 8 件も未購読候補も同じサンプリング・同じスコアラで測る**（baseline がないと
    「未購読 X の当たり率 0.3」に意味が持てない）
  - 各 submolt の feed 先頭 `sample_size`(=20) 件を `score_relevance_detailed()` にかける
  - LLM 呼び出しは `circuit_shield()` で囲む — 観測専用の失敗が本番セッションの
    ブレーカを開けてはならない（skill_selection.py:199 と同じ理由）
  - `client.has_read_budget()` を毎 GET 前に確認。レートリミット連発を検知したら
    **backoff で踏み抜かず中断して理由付きで記録**（rules/debugging.md: rate limit は警報）
  - 全体を try/except で包み degrade-never-abort
- 監査ログ `logs/submolt-scope-{YYYY-MM-DD}.jsonl`（`_io.append_jsonl_restricted`）:
  - run 要約 1 行: `ts` / `scan_id` / `verdict` / `discovered_count` / `sampled_submolts` /
    `subscribed_names` / `sample_size` / 中断理由
  - スコア 1 件 1 行: `ts` / `scan_id` / `submolt` / `subscribed`(bool) / `post_id` /
    `score` / `reason` / `_io.b64_audit_fields` による投稿原文（untrusted は base64+sha256）
- `read_submolt_scope_log(log_dir, *, days) -> SubmoltScopeReading` / `format_submolt_scope_report()`
  — submolt 別に件数・スコア p50/p90・`domain.relevance_threshold` 超過率・reason 内訳、
  購読中 / 未購読を並べて出す

計器はメモリ・パターンストア・identity には一切書かない（観測対象の隔離）。

### 4. CLI — `adapters/moltbook/agent.py` + `cli/agent_cmds.py` + `cli/session_cmds.py`

- `Agent.do_submolt_scan(sample_size)` を公開メソッドとして追加（`do_status` と同型。
  `_ensure_client()` を所有）
- `agent_cmds.py` の `COMMANDS` に `submolt-scan`（`Tier.AGENT`、`--sample-size` /
  `--dry-run`）を登録。GET 予算をセッションと二重消費しないよう
  `acquire_run_lock(config.RUN_LOCK_PATH, blocking=False)` を取る（`_handle_run` と同型）
- `report --submolt-scope` フラグを追加（`session_cmds.py:158-176` の
  `--skill-selection` ブロックと同型 — 失敗は WARNING に落として report 本体を壊さない）
- `cli/runtime.py` に `configure_submolt_scope(audit_dir=config.EPISODE_LOG_DIR)` を配線
  （`runtime.py:103` の隣）

### 5. スケジュール — `config/launchd/` + `cli/schedule.py`

- `config/launchd/com.moltbook.submolt-scan.plist` を新規（既存 plist をテンプレに）
- `LAUNCHD_SUBMOLT_SCAN_LABEL = "com.moltbook.submolt-scan"` + install 関数 +
  `install-schedule --weekly-submolt-scan` / `--uninstall` 対応
- 実行時刻は **JST 03:00 / 週 1 回**。セッション窓（JST 0/6/12/18、
  launchd はローカル解釈 — memory: launchd-schedule-jst）と weekly-pipeline の
  どちらとも重ならない位置。16GB 機で Ollama を取り合わせない

### 6. Chaos-TDD の fault column（CLAUDE.md 開発原則・ADR-0077）

LLM 呼び出し + 外部 I/O + untrusted 応答の parse を含むので必須。
`tests/chaos.py` の ChaosBackend / responses ヘルパーに注入する:

| fault | 期待するガード挙動 |
|---|---|
| `list_submolts` が dict / 非配列 / 巨大配列を返す | 空 tuple + `verdict` に理由コード、例外を投げない |
| submolt 名に `../` / 大文字 / 制御文字 | 既存バリデータで落とし、記録に残す |
| feed が 403 / 404 / 429 | その submolt を skip して reason 記録、スキャンは継続。429 連発は中断 |
| LLM が truncate / 非数値 / `8/10` / `1.5` | `unparseable` / `out_of_range` として記録（0.0 の判断値と混ざらない） |
| LLM 全滅 | 全件 `llm_unavailable`、read 値は「判断ゼロ件」と読めること |
| audit_dir 未設定 | 完全 no-op（kill switch） |

加えて通常テスト: `list_submolts` の envelope 正規化、`score_relevance()` の後方互換
（既存 `tests/test_llm.py` の期待値が不変であること）、reading の集計、
購読中 / 未購読のラベル付け、run lock の競合。

### 7. ドキュメント（同 PR）

- **ADR-0086**（en + ja）— 「submolt スコープの自律化は観測から始める」。
  Context に上記の 2 役兼務・ADR-0044 の却下・ラチェット問題を書く。
  Alternatives: 即時自律 subscribe / 反応ゲートの緩和 / 本番セッション内での観測 /
  何もしない、を却下理由付きで
- `docs/CODEMAPS/architecture.md` の Data Flow（鮮度規約 — 新しい観測段の追加）
- `docs/CODEMAPS/adapters-moltbook.md`（新モジュール + 新 CLI）
- `graph.jsonld`（CLAUDE.md: 新 ADR は CODEMAPS と graph の両面で更新）
- `CLAUDE.md` の CLI 頻出リストに `submolt-scan`、`docs/CONFIGURATION*.md`
- `CHANGELOG.md`

## Verification

```bash
# 機械ゲート（全体）
.claude/verify.sh

# 個別
uv run pytest tests/test_submolt_scope.py tests/test_client.py tests/test_llm.py -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
uv run lint-imports          # adapters → core の一方向依存

# Step 0 の実測（実装前）
#   未購読 submolt feed が読めるかを 1 本だけ叩いて確認

# E2E（本番アカウントで read-only、セッション窓を外して手動 1 回）
contemplative-agent submolt-scan --sample-size 5 --dry-run
contemplative-agent submolt-scan --sample-size 20
cat ~/.config/moltbook/logs/submolt-scope-$(date -u +%F).jsonl | head -3
contemplative-agent report --days 7 --submolt-scope

# kill switch: configure_submolt_scope 未呼び出しで完全 no-op になること（テスト）
# launchd
contemplative-agent install-schedule --weekly-submolt-scan
launchctl list | grep submolt-scan
```

**確認する不変条件**:
- スキャン中・後に `knowledge.json` / episode log / identity が変化していないこと
- 本番セッションの relevance 分布が変わっていないこと（`score_relevance` 後方互換）
- 監査ログに untrusted 原文の平文が入っていないこと（base64 + sha256）

## この後（今回はやらない）

数週間読んでから判断する。読み値が示すのは「購読中 8 件の当たり率」と
「未購読候補の当たり率」の比較。ここで初めて Phase 2（エージェントに範囲を
提案させる shadow）と Phase 3（読む範囲 / 反応する範囲のフィールド分割）の
要否が data-driven に決まる。unsubscribe 能力の復活は Phase 3 以降の論点。
