# T-TESTQ: Agent.__init__ 注入シーム + 残余 brittle クラスタ修理

## Context

2026-07-18 のテスト internals 監査（`.notes/test-internals-audit-2026-07-18.md`）で、「behavior をテストし internals をテストしない」規律への実違反 ~50 テストを特定。bug-masking 3 件と安価な置換は同日修理済み（`a3abcb8`）。残余が T-TESTQ:

- `test_agent.py`（~196 テスト）の大多数が `agent._client = MagicMock()` 等の **private 直接代入**で arrange（`_client` 66 / `_scheduler` 38 / `_content` 24 / `_verification` 12 箇所）。内部コンポジション変更で数十テストが一斉に壊れる構造
- brittle クラスタ 5 種（`_verification` mock assert 群 / `_novelty_gate` 2 段チェーン / `_process_reply` 代理 assert / H4 dispatch 全 mock / bound-method 差し替え）+ `test_insight.py` の内部 seam mock 2 件

**種別: refactor**（プロダクションは挙動不変のシーム追加のみ、本体はテスト構造変更）。作業ツリーは clean（T-INSIGHT-FIX 分は `5cfbbee` / `a3abcb8` でコミット済み）。

## 前提事実（調査確定済み）

- `Agent.__init__`（agent.py:72-131）: 注入口は `memory=` / `domain_config=` のみ。`_content` / `_verification` は無引数構築、`_client` / `_scheduler` は None → `_ensure_client()`（:237-249）で遅延ペア生成。`_novelty_gate`（:119-122）は Agent が所有し PostPipeline へ `novelty_gate=` で渡す（既に PostPipeline の public DI パラメータ）
- `_ensure_client` は `self._client is not None` なら即 return → **client を注入すると credentials ロードも scheduler 生成も走らない**（現行テストの直接代入と同一挙動）
- `VerificationTracker`（verification.py:679-701）: public surface は `should_stop` / `record_success()` / `record_failure()` のみ。失敗カウント getter なし。`max_failures` はコンストラクタ注入可能
- conftest が `OLLAMA_BASE_URL=http://127.0.0.1:1` 固定 → 実 NoveltyGate の `record` は embed 失敗で no-op（観測不能）。**クラスタ 2 に実物 gate は使えず、注入 fake が唯一の hermetic 解**
- reply_handler / feed_manager は `MoltbookClientError` しか catch しない → KeyError / AttributeError は `_run_cycle_step` まで素通し（H4 の client 境界 fault 注入が成立）
- 監査の `:3043-3095` の実体はクラス **TestSelfReplyGatesByName**。TestSelfReplySkip（:3370-）は既に境界 assert で正しく、先例として使う側
- test_insight.py の対象 2 テストは `known_themes` 空で novelty gate 不発火 → `generate_full` patch は `caller="insight.skill_extract"` の呼び出しだけ受ける。`_build_cluster_batches` は LLM 非依存の純クラスタリング（fixture は `_unit_vec` embedding 付与済み）

## 実装ステップ

### Step 1 — Agent.__init__ 注入シーム（commit 1、プロダクションのみ）

`src/contemplative_agent/adapters/moltbook/agent.py:72-131`

keyword-only optional 引数 5 つを追加（挙動不変。必要な型は全て import 済み）:

```python
def __init__(
    self,
    autonomy: AutonomyLevel = AutonomyLevel.APPROVE,
    memory: Optional[MemoryStore] = None,
    domain_config: Optional[DomainConfig] = None,
    *,
    client: Optional[MoltbookClient] = None,
    scheduler: Optional[Scheduler] = None,
    content: Optional[ContentManager] = None,
    verification: Optional[VerificationTracker] = None,
    novelty_gate: Optional[NoveltyGate] = None,
) -> None:
```

- 代入行のみ変更: `self._content = content if content is not None else ContentManager()` 等（`or` は使わない）。`self._client = client` / `self._scheduler = scheduler`
- `_ensure_client` は無変更（client 注入時は早期 return — 現行の直接代入とバイト単位で同挙動）。「client を注入するなら scheduler も注入するのはテスト側の責任」を docstring に 1 行明記
- **novelty_gate を含める根拠**: (a) クラスタ 2 の修理にこれ以外の hermetic 解がない（conftest 下で実 gate の record は no-op） (b) `novelty_gate` は既に PostPipeline.__init__ の public パラメータで、新 API 発明でなく既存 DI 契約の露出 (c) 監査の 4 コンポーネント列挙は arrange 頻度上位でありクローズドリストではない（監査自身がクラスタ 2 を修理対象に挙げている）
- cli.py:2500 は無変更（デフォルト経路が完全に旧挙動）

### Step 2 — test_agent.py 一括書き換え（commit 2、assert 不変の機械変換）

- 8 個の重複 `_make_agent`（:42, :705, :2080, :2310, :3024, :3106, :3152, :3373, :3477）を**モジュールレベル 1 関数に統合**（client/scheduler/content/verification/novelty_gate を kwargs で受け、デフォルトで client/scheduler の MagicMock + `can_comment/can_post=True` を用意）。テスト固有 arrange（`own_agent_id` seed 等）は各クラスに残す
- 変換手順: `agent._client = MagicMock()` → 構築前にローカル `client = MagicMock()` を作り `Agent(..., client=client)`、本文の `agent._client.xxx` 参照を `client.xxx` に置換。`_scheduler` / `_content` / `_verification` も同様
- **クラス単位で変換 → `uv run pytest tests/test_agent.py -k TestClassName -q` で局所確認**（一括 sed しない）
- 完了条件: `grep -n "agent\._\(client\|scheduler\|content\|verification\) = " tests/test_agent.py` が 0 件
- 据え置き（対象外）: `agent._ctx.own_agent_id = ...` 等の SessionContext フィールド seed、`_feed_manager._feed_fetched_at` / `_cycle_wait` 直接代入 — mock 差し替えでなく arrange-only の状態 seed（監査の据え置き節と同種）

### Step 3 — クラスタ 1: `_verification` mock assert 群 → 実物 tracker（commit 3）

TestHandleVerification（:575-701）+ TestHandleVerificationMalformedObject（:3600-）。test_llm.py の circuit breaker probe が先例。

- 失敗記録 ×6（:600, :643, :665, :678, :3615, :3638）: `VerificationTracker(max_failures=1)` を注入し、act 後 `assert tracker.should_stop is True`
- `record_success`（:621）: 判別 probe — `max_failures=2` で pre-seed 1 失敗 → 成功経路 → probe で `record_failure()` 1 回 → `assert not tracker.should_stop`（リセットされていなければ 2 到達で立つ）
- should_stop ガード（:576）: pre-seed で should_stop 状態にし、`solve_challenge_result` module patch の `assert_not_called` で「solve へ進まない」を境界確認
- audit assert（module-level patch）は現行維持

### Step 4 — クラスタ 2: novelty_gate 2 段チェーン → 注入 fake（commit 3 同梱）

arrange 11 箇所（:1243-1244, :1299-1300, :1380-1381 等）+ assert :1336, :1404。

- テストファイルに duck-typed `_RecordingNoveltyGate`（`evaluate` は固定 GateDecision を返し引数を記録、`record` は `(post_id, title)` を list に記録。実 NoveltyGate とシグネチャ一致の型注釈付き — MagicMock 不使用規律と整合）
- `_make_agent(..., novelty_gate=gate)` で注入し、assert は `len(gate.recorded) == 1` / `gate.recorded == []`。`_post_pipeline._novelty_gate` への 2 段到達を全廃

### Step 5 — クラスタ 3: TestSelfReplyGatesByName → 境界 assert（commit 4）

:3018-3099 の 4 テスト。`handler._process_reply = MagicMock()` を廃し、既存 idiom（`@patch("...reply_handler.generate_reply")` + 注入 client）で実 `_process_reply` を走らせる:

- self skip 系: `mock_reply.assert_not_called()` + `client.post_comment.assert_not_called()`
- 処理系: `client.post_comment.assert_called_once_with("post1", "Thanks!", parent_id=...)` — **replier_name assert は `parent_id`（誰のコメントに返信したか）へ移設**（notification 経路は parent_id=None、comment scan 経路は該当コメント id）
- 実 `_process_reply` の `generate_internal_note` は conftest の unreachable Ollama で即 None（TestRunNotificationCycle が同条件で成立済み）

### Step 6 — クラスタ 4: H4 dispatch → client 境界 fault 注入（commit 4 同梱）

TestSessionCycleStepIsolationH4（:3555-3597）。collaborator の丸ごと MagicMock 化を全廃:

- 注入 client に `get_home.return_value`（`your_account` + `activity_on_your_posts` を home 側に含める — `_fetch_home_data` が home 全体を `_home_data` に格納するため直接 seed 不要）、feed 用 `client.get` 応答、`scheduler.can_post=False`（post step は境界タッチで即終了）を用意
- reply fault: `client.get_post_comments.side_effect = KeyError` → 後続 step の生存を `client.get`（feed）+ `scheduler.can_post` called で観測
- feed fault: `client.get.side_effect = AttributeError` → `client.get_post_comments` + `scheduler.can_post` called で観測
- step 名 log テスト: caplog assert 維持、fault 注入だけ client 境界に変更

### Step 7 — クラスタ 5: bound-method 差し替え → module patch（commit 4 同梱）

:816-867 の 2 テスト。`agent._feed_manager._handle_verification = MagicMock()` を廃し、既存 idiom（`...agent.solve_challenge_result` / `...agent.submit_verification` / `...agent.record_verification_audit` の module patch、:586-608 で実証済み）で実 `_handle_verification` を走らせる。プロダクション側の bound-method 遅延解決化は**不採用**（テスト都合だけの間接層。実メソッドを走らせれば配線問題自体が消える）:

- 成功系: `submit_verification → {"success": True}`、assert は現行 behavior 側（`result is True` / `has_commented_on` / `record_comment`）維持 + `mock_submit.call_args` で verification オブジェクト到達を確認
- 失敗系: `solve_challenge_result → _solve_result(None)` で失敗経路を実走、現行 assert 維持

### Step 8 — test_insight.py: generate_full 境界化（commit 5）

- `test_gated_patterns_excluded`（:208-233）: `_extract_skill` patch → `generate_full` fake（prompt を記録し `GenerationOutput(text=GOOD_SKILL_RESPONSE)` を返す。fake 内で `caller == "insight.skill_extract"` を assert し意図しない LLM 呼び出しを検出）。assert: prompt 1 件、`clean-*` 3 つを含み `noise-*` を含まない
- `test_superseded_patterns_excluded`（:402-430）: `_build_cluster_batches` side_effect fake → `generate_full` fake。実クラスタリングを走らせ（live 3 件は同一 embedding で 1 cluster 化）、prompt に `live-*` のみ含まれることを assert。戻り値 assert は string → `InsightResult` に変わるため、テスト名/docstring を「superseded は LLM プロンプトに載らない」へ更新しコミットメッセージに明記
- 同型 2 件（:192-206 `test_extraction_failure` / `test_returns_insight_result`）も同 idiom へ置換（`generate_full → None` / `→ GenerationOutput(text=GOOD_SKILL_RESPONSE)`）
- 注意: GenerationOutput の text はタイトル行必須（無いと `_extract_skill` が None を返す）— `GOOD_SKILL_RESPONSE` で充足

### Step 9 — 台帳・監査ノート更新（commit 5 同梱 or 6）

- `.notes/test-internals-audit-2026-07-18.md` の「残（T-TESTQ）」節を修理済みへ
- `.notes/TASKS.md` の T-TESTQ を Done 節へ移動

## コミット分割

| # | メッセージ | 内容 | ゲート |
|---|---|---|---|
| 1 | `refactor(agent): add keyword-only collaborator injection seam to Agent.__init__` | Step 1 | **既存テスト無変更で全 green**（= 挙動不変の機械的証拠）+ ruff + pyright |
| 2 | `test(agent): arrange via constructor injection instead of private assignment` | Step 2 | test_agent.py green + grep 0 件 |
| 3 | `test(agent): observe VerificationTracker/NoveltyGate through public surface` | Step 3+4 | 同上 + 判別性の手元 mutation 確認 1 回 |
| 4 | `test(agent): assert at client boundary for self-reply gates, H4 isolation, verification wiring` | Step 5+6+7 | 同上 |
| 5 | `test(insight): mock at generate_full boundary instead of internal seams` | Step 8+9 | test_insight.py green |

main 直 commit → push（feedback: push-workflow。branch/PR なし）。

## Chain（refactor 種別）

- TDD: 非該当（テスト自体が成果物）。Phase 0: 非該当（バグ修正・リファクタ）
- Review（実装後、Verify 前に並列）: **python-reviewer**（.py 変更）。codex-review は C 判定 — Agent.__init__ は public API だが optional kwargs 追加のみの低リスク refactor のため起動する（diff にプロダクション変更を含むため念のため）。security-reviewer: 不要（入力処理・認証・permissions に非接触 — verification 関連はテストのみ）
- Parallel Group: [python-reviewer, codex-review]（commit 5 まで完了後の全 diff に対して）

## Verify

```bash
uv run pytest tests/ -v                        # フル（~470 テスト）
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing   # 80%+
uv run ruff check . && uv run ruff format --check .
uv run pyright
```

完了判定 grep（定義参照を除き 0 件）:

```bash
grep -n "_verification\.record_\|_novelty_gate\.\(record\|evaluate\) = \|_process_reply = MagicMock\|_handle_verification = MagicMock" tests/test_agent.py
grep -n "patch.*_extract_skill\|_build_cluster_batches.*side_effect" tests/test_insight.py
grep -n "agent\._\(client\|scheduler\|content\|verification\) = " tests/test_agent.py
```

## リスク

1. **140 箇所の機械変換の打鍵ミス** → クラス単位変換 + クラス単位 pytest で局所化。ローカル変数 `client` のシャドウ衝突をクラスごとに確認
2. **`_RecordingNoveltyGate` の契約ドリフト** → 実 NoveltyGate とシグネチャ一致の型注釈（pyright が検出）。Protocol 化はテスト専用 API 最小限の精神で見送り
3. **H4 の home データ形状**が `_fetch_home_data` の `your_account` 抽出と結合 → `name` を含めて DEGRADED warning ノイズ回避
4. **test_superseded の assert 意味変更**（string → InsightResult）→ docstring・コミットメッセージで意図を明示
