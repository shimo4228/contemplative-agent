# Chaos × TDD パイロット — fault-injection テスト基盤

## Context

LLM ワークフロー型のこのエージェントでさえ、運用中に予想外のバグが繰り返し起きている（num_ctx silent truncation、done_reason=length 途中切れ、dedup 無発火、API レート制限、CAPTCHA gate drift）。これらは「LLM / 外部 I/O が想定外の応答を返したとき、パイプラインが黙って壊れる」という同族の障害で、fault injection で事前に露出できた種類。

パイロットの実体は「**運用障害カタログ → fault-injection テストを先に書く（TDD）→ ガード実装**」のループ。Netflix 流の本番ランダム chaos ではなく、seed 固定の決定論的 fault-injection を pytest に組み込む。既存の ai-regression-testing 規律（確定バグ → 機械的ガード）の前倒し版と位置づける。

成否判定: 「思想の実証」ではなく (a) 既知バグ族の再発を何件テストで固定できたか、(b) 新規 silent failure を何件事前に露出できたか。

種別: `feat`。

## External Research Findings

**Verdict: Compose — hypothesis + responses + 既存 `FakeBackend` seam の薄い custom 拡張**

- **hypothesis**（MIT、依存ゼロ、6.156.6 = 2026-07-10 リリースで活発、Py3.10+）: seed 固定 / `derandomize` で CI 決定論、`RuleBasedStateMachine` が fault シーケンス生成 + 最小失敗列への shrinking に適合。dev group に新規追加
- **responses**（Apache-2.0、Sentry がメンテ、活発）: requests 層の 429/500/timeout/ConnectionError 注入。**pyproject dev group に宣言済みだが import ゼロの未使用 dep** — 採用は新規依存ゼロ
- **却下**: chaostoolkit / toxiproxy（インフラ・別プロセス daemon 前提で単一ローカルプロセスには高度違い）、pytest-chaos 系プラグイン（実用可能なものが存在しない — pytest-disrupt は TODO のみの scaffold）、requests-mock（responses と重複）
- **agent-chaos**（25 stars、Anthropic SDK / DeepEval 結合、pytest 統合なし）: 採用不可だが fault taxonomy（llm_rate_limit / llm_server_error / llm_timeout / stream faults / prompt injection / tool faults）は本パイロットのカタログが正しい形である prior-art 検証として有用

## 調査結果（コードベース）

### 注入 seam と既存ガード（src 側）

- **Protocol**: `core/llm.py:125` `LLMBackend`（`model` / `context_window` / `generate(...) -> Optional[BackendResult]`。契約: 失敗時 None、sanitize は caller 側）。`BackendResult`（frozen, `:79`）に `finish_reason`（`"length"` が drop gate を駆動）
- **注入点**: `configure(backend=...)`（`llm.py:208`）→ `_generate_impl` が `:1077` で分岐（`_generate_via_backend` / `_post_ollama`）。テスト撤去は `reset_llm_config()`（`:265`、circuit breaker もリセット）
- **Ollama 経路**: `_post_ollama`（`:1175`）。`requests.post(..., timeout=(30,1200))`、リトライなし・単発。失敗は `_circuit.record_failure()` + None。circuit breaker は閾値 5 / cooldown 120s（`:53-54`）、open 時 `outcome="circuit_open"`
- **truncation gate**: `_drop_for_output_truncation`（`:1239`）— `drop_truncated=True` で drop（circuit 成功扱い）、else warn+keep（`outcome="truncated_kept"`）
- **distill の失敗処理**: `_distill_one`（`distill.py:514`）→ LLM None は per-episode drop（リトライなし）、shape violation は **silent bullet fallback**（`:500`）。**abstain 理由コードの enum はない** — ADR-0075 の観点で改善余地
- **観測チャネル（ready-made）**: LLM 呼び出しごとに `llm-calls-{date}.jsonl` telemetry（`_emit_telemetry` `llm.py:804`、`outcome` = ok/empty/circuit_open/budget_exceeded/truncated_dropped/truncated_kept、prompt は sha256 のみ）。**全 fault がここに現れる = chaos run の steady-state 判定にそのまま使える**
- **Moltbook client ガード**: `has_read_budget`/`has_write_budget`（`client.py:287,293`）、429 リトライ（`MAX_RETRY_ON_429`、Retry-After cap 5min、terminal のみ `recent_429_count`）
- **untrusted 境界**: `wrap_untrusted_content`（`llm.py:1423`、`_INJECTION_TOKENS` 除去 + frame + 完全性マーカー）、`_sanitize_output`（`:700`、`_finalize_ok` `:1296` で両経路に一律適用）

### テストパターン（再利用する既存資産）

- **LLM フェイクの正本**: `tests/test_llm_backend.py::FakeBackend`（dataclass、`LLMBackend` Protocol 準拠を isinstance で assert 済み）。応答キュー（str / `BackendResult` / `None`=hard failure）+ `raise_exc=` + 呼び出し記録。`configure(backend=...)` / `reset_llm_config()` で注入・撤去 — **chaos 注入の自然な seam はここ**
- **sandbox**: `tests/conftest.py` が `MOLTBOOK_HOME` を tempdir に、`OLLAMA_BASE_URL` を到達不能ポートに設定。autouse fixture が circuit breaker を毎テストリセット
- **HTTP 層モック**: `@patch("contemplative_agent.core.llm.requests.post")` 慣行（`test_llm.py::TestDoneReasonTruncation._mock_resp`）。dev deps に `responses>=0.23.0` が**宣言済みだが未使用**（採用可能な公認ツール）
- **embedding フェイク**: `test_snapshot.py::_fake_embed`（SHA256-seeded 決定論 8-dim）、`test_rules_distill.py::_mock_embed_texts`

### 失敗系カバレッジの現状

既にテスト済み: done_reason=length（warn+keep / drop_truncated）、Moltbook API 429+backoff、JSON decode error / 空応答、circuit breaker（開閉・回復）、embed down（None 経由の間接）、malformed 永続 state（JSONL 破損行スキップ等）

**未テスト = パイロットの標的**:
1. 遅延・read-timeout（途中で止まる LLM）— ConnectionError しかない
2. embedding HTTP 経路の直接障害（429/timeout/次元不一致の注入）
3. **parse は通るが schema/型が壊れた LLM JSON**（structured output の意味的破損 — 系統的 fuzz なし）
4. Ollama 側の 429（429 テストは Moltbook client のみ）
5. flapping backend（成功/失敗が交互のシーケンス）

### 慣行

- hypothesis 未使用（導入するなら greenfield）。決定論は構造的に達成（SHA256 seed フェイク、固定キュー）
- regression は専用ディレクトリでなく **topic ファイル内に日付/incident 名付き**で置く慣行
- replay corpora は `tests/fixtures/*.jsonl`（real_sample.jsonl 等、ADR-0075 系）
- 新テストの置き場: LLM chaos → `tests/test_llm_chaos.py`（flat 慣行）または `test_llm_backend.py` 拡張。HTTP chaos → `responses` 採用

## Fault カタログ（fault → 注入機構 → assert する挙動）

| ID | Fault（未テストギャップ） | 注入機構 | Assert する挙動（RED で書く仕様） |
|----|----|----|----|
| F1 | 生成中 read-timeout | `responses` で `/api/generate` に `ReadTimeout` 注入（+ ChaosBackend の EXC_TIMEOUT） | `generate()` → None、circuit failure +1、telemetry `outcome="error"` + **`error_kind="timeout"`（新設）**。distill 経由は `reason=llm_none` で abstain |
| F2 | embedding HTTP 直接障害 | `responses` で `/api/embed` に 429 / ReadTimeout / 次元不一致 / 行数不足 | `embed_texts` → None（pin）。行数不足は embedding なし格納 + `reason=embed_failed` トークン付き WARNING。クラッシュなし |
| F3 | **parse は通るが shape 違反の JSON**（structured output） | hypothesis 戦略 `non_patterns_json()` を ChaosBackend 応答に注入 + `@example` で既知形を pin | **新挙動**: valid-JSON-wrong-shape は bullet fallback せず `reason=shape_violation` で abstain。いかなる入力でも例外なし（property） |
| F4 | Ollama 自身の 429 | `responses` で `/api/generate` に 429 + Retry-After | retry も sleep もせず即 None（fail-fast 方針を pin）+ `error_kind="http_429"` + circuit failure |
| F5 | flapping backend（成功/失敗交互・連続列） | `ChaosBackend(schedule=[...])` 明示列 + hypothesis `fault_schedules()`（seeded） | distill サマリの per-reason 集計 = schedule の集計と一致。circuit は連続 5 失敗でのみ open（交互列では open しない） |

F1/F4 は HTTP 経路（`_post_ollama`）、F3/F5 は `configure(backend=ChaosBackend(...))` 経路 — dispatch 分岐（llm.py:1077）の両側をカバー。

## 本番コード変更（in scope は 2 点のみ）

**変更 A — distill.py: abstain 理由コード（~40-60 行）** — ADR-0075「silent fallback 禁止」への distill 失敗経路の準拠:
- `_parse_patterns`（:482）: 戻り値を `(patterns, parse_mode)` に変更。**valid-JSON-wrong-shape は bullet スキャンせず `shape_violation`**。非 JSON body の bullet fallback は維持（H2 テスト test_distill.py:413 が pin 済みの正当な degradation）だが `parse=bullet_fallback` トークンで可観測化
- `_distill_one`（:514）: 失敗を reason 付きで返す（`llm_none` / `empty_render` / `shape_violation`）。machine-greppable な WARNING 形式 `reason=%s`
- `_distill_episodes`（:566）: `failed` カウンタを reason 別 `Counter` に、サマリ行を per-reason 集計に
- docstring の「malformed-JSON … cannot occur」を実態に訂正（検証済み: 実際は occur し得る）
- 既存テスト影響: test_distill.py:442-459（トップレベル配列/scalar → `[]` 期待）を abstain 期待に反転 — これ自体が F3 の RED の一部

**変更 B — llm.py: `error_kind` テレメトリ（~10-15 行）** — 現状 429/timeout/connection/bad JSON が全部 `outcome="error"` に潰れて判別不能。`_post_ollama` の except 節で `tel["error_kind"]` を設定（`timeout` / `http_429` / `connection` / `bad_json`）、`_generate_via_backend`（:1143）に `backend_exception`。**`outcome` の値集合は不変**（additive、後方互換）

**Deferred（ADR に明記）**: Ollama 429 への backoff、per-episode retry、distill 専用 audit JSONL（follow-up 第一候補）、他パイプライン拡張、sandbox chaos-mode meditate、skill の公開版汎用化 fork

## 実装ステップ（TDD 順序）

- **Step 0 足場**: pyproject dev group に `hypothesis>=6.100` + `uv sync` / `tests/chaos.py` 新規（`ChaosBackend`: Protocol 準拠 dataclass、fault 語彙 OK/NONE/EMPTY/EXC_TIMEOUT/EXC_CONNECTION/TRUNCATED/SHAPE_VIOLATION、`from_seed(seed,n,weights)` で schedule 確定・inspectable、responses ヘルパー、hypothesis 戦略）/ conftest.py に `settings.register_profile("ci", derandomize=True, max_examples=50, deadline=None, database=None)`（`.hypothesis/` 生成防止）
- **Step 1 F3**（変更 A を駆動）: RED = `tests/test_distill_chaos.py` の property + `@example` pin（`'["p1"]'` / `'{"patterns":"str"}'` / `'{"patterns":[123]}'` — :492 の str 昇格確認必須）+ test_distill.py 期待値反転 → GREEN = 変更 A
- **Step 2 F1+F4**（変更 B を駆動）: RED = `tests/test_llm_chaos.py`（responses ベース、telemetry 読み出しは test_llm_telemetry.py の `_read_records` 流用、429 は `time.sleep` monkeypatch で「呼ばれない」を assert）→ GREEN = 変更 B
- **Step 3 F5**: 明示 schedule → per-reason 集計 assert + `@given(fault_schedules())` property + circuit 系列テスト（cooldown 待ちなし、open 観測まで）
- **Step 4 F2**: `test_embeddings.py` 追記（pin）+ 行数不足 → `reason=embed_failed`（変更 A の 1 行で GREEN）
- **Step 5 Doc Sync（同一 diff）**: ADR-0077 `chaos-tdd-fault-injection`（en + ja、index 更新、adr-writer skill 使用）/ `docs/CODEMAPS/architecture.md` distill セクションの H2 注記・abstain 記述・`error_kind` を同期（鮮度規約）
- **Step 5b Skill 化**: `.claude/skills/chaos-tdd-fault-injection/SKILL.md` 新規（CA project skill、`origin: shimo4228`、replayable-audit-logs / shadow-mode-validation と同型の設計ノウハウ skill）。**実装完了後に書く** — 実際に踏んだ知見（RED で何が仕様化しにくかったか、fuzz が実際に拾った例）を含めるため。内容: ①fault カタログの起こし方（運用障害履歴 → 同族分類 → 未テストギャップ）②注入 seam の選び方（Protocol seam / HTTP 層の 2 段、production hook を新設しない）③決定論規律（seed 固定 schedule・derandomize・実 sleep 禁止 = timeout 例外注入）④steady-state assertion チャネル（telemetry outcome/error_kind + reason トークン、実装内部への assert 禁止）⑤TDD 契約（fault テストが望ましいガード挙動を先に主張 → 最小ガードを同 PR で）⑥いつ使う/使わない（NOT for: 単発バグの回帰テスト = ai-regression-testing、イベントログ設計 = replayable-audit-logs）。CLAUDE.md の project skills 表に 1 行追加（同一 diff、Doc Sync 規律）。公開版への汎用化 fork は follow-up（portability 規約に従い CA 文脈例のまま repo 同梱が正本）
- **Step 6 Review**: 下記 Parallel Group 2 → Verify

```
Parallel Group 1: （Phase 0 / 探索は完了済み）
Parallel Group 2: [python-reviewer, security-reviewer, codex-review]   # 同じ diff に並列
Sequential: TDD (Step 0-4) → Doc Sync (Step 5) → Review (Step 6) → Verify
```

security-reviewer を含める理由: F3 の fuzz 入力は untrusted LLM 出力の parse 境界そのもの。abstain ログに untrusted 原文を書いていないか（ADR-0075 規約）の確認が要る。

## Verification

```bash
# 1) chaos テスト群を 2 回連続実行 — 出力が同一（決定論の確認）
uv run pytest tests/test_llm_chaos.py tests/test_distill_chaos.py -q  # ×2
# 2) 変更影響トピックの回帰
uv run pytest tests/test_distill.py tests/test_llm.py tests/test_llm_backend.py tests/test_llm_telemetry.py tests/test_embeddings.py -q
# 3) フルスイート
uv run pytest -q
# 4) 静的検査
uv run ruff check . && uv run pyright
# 5) 汚染チェック
test ! -d .hypothesis && git status --porcelain
```

PASS = (1) 2 回同一で全 green、(3) full green（意図的反転は test_distill.py 該当クラスのみ）、(4)(5) クリーン。加えて手動 1 点: chaos テスト 1 本を流し telemetry JSONL に `error_kind` が実書き込みされることを目視。

## パイロット成功基準

- **(a) 既知バグ族の再発 pin**: ≥4（truncation 系 / shape violation / per-episode silent drop / circuit flapping）
- **(b) 新規露出 silent failure**: ≥2 確定済み — ①valid-JSON-wrong-shape → `[]` が正当な空抽出と区別不能、②telemetry の fault 種別無区別。③`{"patterns":[123]}` の str 昇格が fuzz で拾えればボーナス
- **(c) Skill 化（in scope、Step 5b）**: 実装知見を含む `chaos-tdd-fault-injection` skill が repo に同梱されること
- Follow-up（スコープ外）: skill の公開版汎用化 fork、insight/reply 拡張、sandbox chaos-mode meditate

## Critical Files

- `src/contemplative_agent/core/distill.py`（変更 A: `_parse_patterns` :482 / `_distill_one` :514 / `_distill_episodes` :566）
- `src/contemplative_agent/core/llm.py`（変更 B: `_post_ollama` :1175 except 節 / `_generate_via_backend` :1143）
- `tests/chaos.py`（新規）/ `tests/test_llm_chaos.py`（新規）/ `tests/test_distill_chaos.py`（新規）
- `tests/test_llm_backend.py::FakeBackend`（設計テンプレート、移動しない）/ `tests/conftest.py`（プロファイル追記）
- `docs/adr/0077-*`（新規 en+ja）/ `docs/CODEMAPS/architecture.md`（distill 節同期）
- `.claude/skills/chaos-tdd-fault-injection/SKILL.md`（新規、Step 5b）+ `CLAUDE.md` project skills 表 1 行追加
