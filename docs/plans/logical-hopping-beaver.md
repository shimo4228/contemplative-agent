# 複雑性・可読性リファクタリング（Codex レビュー指摘 8 件）

## Context

Codex CLI（gpt-5.6-sol）によるクロスモデルレビューで、`src/contemplative_agent`（69 ファイル / 20,532 行 / 595 関数）に保守性ホットスポットが 8 件検出された。バグ・セキュリティ指摘はゼロで、すべて「1 関数・1 クラスが多段の責務を抱えていて、変更のたびに全体を読む必要がある」型の負債。

実測で裏取り済み: 487 行の `main()`、148 行の `_distill_episodes`、1132 行の `verification_parse.py`、3 箇所に重複した監査エンコード。

目的は**振る舞いを一切変えずに**、変更コストの高い箇所を分解すること。特に外部書き込みパスの三重実装は、可視性・記録の意味論を直したときに 3 箇所でドリフトする実害があり、実際に `_publish_post` だけ 429 → `set_rate_limited()` が抜けている非対称が既に発生している。

種別は `refactor`。Chain: Plan → Refactor Clean → (python-reviewer ∥ codex-review) → Verify。TDD は新規挙動が無いため既存テストの緑維持で代替する。

### 方針

- `verification_parse.py` は**段分けリライトを行う**。challenge 文法はサーバ側が握っており、ADR-0062 は既に 9 回改正されている。改正の到来が止まる根拠は無いので、「`_resolve` と `_resolve_implicit` を人手で協調させる」構造が続く限り**片方だけガード漏れが再発する**（既に 2 回発生済み）。継続する外科手術こそが再構成の理由。
- 検証は **differential replay**（旧実装 vs 新実装の全件一致）で行う。振る舞い保存のリファクタに ground truth は不要で、必要なのは旧実装との一致。したがって manual label の有無に関係なく corpus 1272 件**全件（100%）**が検証対象になる。ラベル付き 82.5% しか検証できないのはバグ修正の場合の話であって、本件には当てはまらない。
- 4 コミットに分割。低リスク → 高リスクの順。各コミットで `pytest` 全通過を確認し、途中で止めても壊れない。

---

## C1 — 監査フィールドエンコードの共有化（P3 / 低リスク）

**問題**: replay-safe な `sha256 + base64 + bytes + truncated` の生成が 3 箇所に独立実装されている。

| 箇所 | 形 | byte cap |
|---|---|---|
| `core/insight_novelty.py:301-313` | ネスト関数 `_b64_fields` | 131072 |
| `core/skill_selection.py:250-263` | モジュール関数 `_b64_fields`（本文はバイト単位で同一） | 65536 |
| `adapters/moltbook/verification.py:370-378` | record dict にインライン展開 | 8192 |

**やること**: `core/_io.py` に `b64_audit_fields(name, text, *, max_bytes) -> dict[str, Any]` を追加し、3 箇所を差し替える。

- 置き場所の根拠: `_io.py` は既に `append_jsonl_restricted` / `now_iso` / `strip_to_printable` / `truncate_boundary` を持ち、`verification.py:40` から実際に import されている。`pyproject.toml:74-81` の layers contract は `cli → adapters → core` なので新しい辺は増えない。
- 各呼び出し側は cap 値だけを渡す（現行値を維持し、統一しない — cap は監査ログごとのサイズ設計であり、揃える理由が無い）。
- `verification.py` は `challenge_sha256` を上流の `_sha256_text` から受け取っているため、helper に `sha256_override` を渡すか、helper 側の算出値と一致することをテストで固定する（`encode("utf-8", "replace")` 同士なので等価）。

**併せて直す（Explore が発見した実害）**: 3 実装とも `raw[:cap]` でバイト境界を無視して切るため、日本語を含む truncated payload を `b64decode(...).decode("utf-8")` すると `UnicodeDecodeError` になる。`_io.truncate_boundary` の考え方を使い、helper 内でコードポイント境界に丸める。JA 主体のプロジェクトで実際に踏みうる。

**主な変更ファイル**: `core/_io.py`, `core/insight_novelty.py`, `core/skill_selection.py`, `adapters/moltbook/verification.py`
**テスト**: `tests/test_io.py`（新規ケース: 境界丸め / None / cap 超過）, 既存 `tests/test_skill_selection.py:190,195,267`, `tests/test_verification.py`, `tests/test_insight.py`

---

## C2 — CLI registry 化 + stocktake の run state 化（P2 / 中リスク）

### C2-a `cli/__init__.py` の main() 分解（102-589 行）

**問題**: 23 コマンドの parser 構築（~350 行）と 4 段の dispatch が 1 関数に同居。コマンド追加時に parser 節と正しい tier テーブルの両方を編集する必要があり、乖離しやすい。

**やること**: `cli/registry.py`（新規）に

```python
@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str
    add_arguments: Callable[[argparse.ArgumentParser], None]
    handler: Callable[..., None]
    tier: Tier          # NO_LLM | LLM_RUNTIME_ONLY | LLM_FULL | AGENT
    hidden: bool = False
```

を定義し、各ハンドラモジュールが `COMMANDS: tuple[CommandSpec, ...]` を公開する。`main()` は registry を回して subparser を作り、tier で dispatch する 1 経路になる。

- ハンドラのシグネチャは 18 コマンドすべて `(args, parser) -> None` で既に統一済み（Explore 確認）。移行は機械的。
- **モジュール単位ではなくコマンド単位で tier を持つ**: `dialogue` は NO_LLM、`dialogue-peer` は LLM_FULL で同一モジュール。`memory_cmds` は 6 コマンド、`session_cmds` は 7 コマンドを抱えるため、シングルトンではなくタプルで公開する。
- `register` / `status` / `run` / `solve` は `_handle_agent_command`（`cli/__init__.py:56-101`）内の分岐で、`domain_config` を追加引数に取る。これらは `AGENT` tier として登録し、ラッパで `(args, parser)` 形に揃える。`run` の引数レンジ検証・session-id ライフサイクル・`acquire_run_lock` は `AGENT` tier の共通前処理ではなく `run` の `handler` 内に閉じる。
- 現状 tier 3 は**フォールスルー**なので未知コマンドが `Agent()` 構築まで到達する。registry 化で未知コマンドは `parser.error` に落ちる（挙動改善だが、テストがフォールスルーに依存していないか確認）。
- `dialogue-peer` は internal-only なので `hidden=True`。`enrich` は ADR-0019 以降 no-op のまま登録を維持する（退役判断は別件）。

**主な変更ファイル**: `cli/registry.py`（新規）, `cli/__init__.py`, `cli/{adopt,memory_cmds,schedule,session_cmds,stocktake_cmd}.py`

### C2-b `_handle_stocktake_result` の run state 化（`cli/stocktake_cmd.py:468-600`）

**問題**: 10 引数 + 5 系統のローカルコレクション（`items_dict` / `staged_batch` / `consumed_names` / `actually_dropped` / 3 組の traces+labels）を全フェーズが手で受け渡している。

**やること**: `StocktakeRun`（frozen な設定 + 可変な累積を分離）と `PhaseResult` を導入し、merge / drop / clean / description-audit の各フェーズが名前付きの状態を返す形にする。

- **flagged drop と actual drop の区別は絶対に保持する**（意味論の中心）:
  - clean フェーズの skip は `consumed_names | dropped_names`（**flagged**）— drop 提案中のファイルを整形しても無駄
  - description フェーズの skip は `consumed_names | actually_dropped`（**actual**）— 運用者が残した flagged ファイルは selector カタログに残るので description 監査が要る（2026-07-24 codex review 由来、`:562-565` のコメント）
  - この 2 つを `PhaseResult` の別フィールドとして型で分ける。混同を構造的に不可能にするのがこの分解の主目的。
- `staging._stage_results` は呼ぶたび STAGED_DIR を wipe するため、**単一バッチを 1 回だけ flush する**制約（`:492-497` のコメント）を `StocktakeRun` の docstring と assert に移す。
- description フェーズの `desc_prompt` 空文字ガード（`:558-561`、空テンプレートが findings を捏造する）を維持。

**テスト**: `tests/test_cli_stocktake.py`, `tests/test_cli_stocktake_drop.py`（`_stocktake_merge_phase` を直接 import しているのでシグネチャ変更に追従が要る）, `tests/test_stocktake.py`

---

## C3 — LLM / distill / memory の段分け（P2 / 中リスク）

### C3-a `core/llm/__init__.py` の GenerationRequest 化

**問題**: `generate` → `_generate_full` → `_generate_impl` → `_generate_via_backend` / `_post_ollama` が 9 引数を全部位置引数で 5 段積み替えており、`_generate_impl` では `num_predict` が `effective_num_predict` に化け `caller` が消える（`tel` の中だけに残る）。

**やること**:
- `core/llm/request.py`（新規）に frozen `GenerationRequest`（prompt / system / max_length / num_predict / format / temperature / drop_truncated / caller / think）を定義。
- `_generate_full` 以降を `GenerationRequest` 1 引数 + telemetry で回す。budget clamping は `request.with_num_predict(...)` の派生を返す（frozen 維持、`effective_` の別名を消す）。
- **公開 API は一切変えない**。`generate` / `generate_full` / `generate_for_api` のシグネチャは現状維持。ADR-0079 により `core.llm` は sibling repo（`contemplative-agent-cloud` / `-mlx`）の恒久 facade であり、`LLMBackend` Protocol（`core/llm/backend.py:132`）も変更しない。内部 5 段のみの整理。
- 影響範囲: 呼び出し側 19 箇所は無変更（facade 経由のため）。

**テスト**: `tests/test_llm.py`, `test_llm_backend.py`, `test_llm_chaos.py`, `test_llm_telemetry.py`（telemetry のキー集合が不変であることを既存テストで固定）

### C3-b `core/distill.py::_distill_episodes` の段分け（`:484`, 148 行）

**やること**: 現在の 8 段を 4 つの型付きステージ関数に割る。

```
_extract(records)                 -> ExtractResult(provenance, abstain_counter, results)
_embed(provenance)                -> EmbedResult(embeddings, degraded: bool)
_deduplicate(knowledge, ..., mutate_existing)
                                  -> DedupResult(add_patterns, add_embeddings, add_indices, skipped, updated)
_persist_or_instrument(...)       -> _CategoryResult
```

- `dry_run` 分岐は `_persist_or_instrument` の中だけに閉じる（現在は dedup の `mutate_existing` にも波及しているので、そこは引数として明示的に渡す）。
- `_CategoryResult` を `DistillOutcome` に改名（ADR-0019 以降 category という語が実態と乖離。Codex 指摘）。`distill()` 内の唯一の消費点だけ追従。
- ADR-0077 の abstain 集計ログ（`:523-546`）と ADR-0071 の dry-run instrument 出力（`:600-623`）は**文言・reason コードを一切変えない**（監査ログの互換性）。

**テスト**: `tests/test_distill.py`, `tests/test_distill_chaos.py`, `tests/test_dedup.py`, `tests/test_knowledge_store.py`

### C3-c `core/memory.py::MemoryStore` の facade 分割（`:91`）

**問題**: 1 クラスが 4 つのストレージ面（episode JSONL / `knowledge.json` / `agents.json` / `commented_cache.json`）と 5 責務を単独所有。

**やること**: 公開 facade（メソッド名・シグネチャ）は完全維持したまま、内部を 4 リポジトリへ委譲する。

| リポジトリ | 所有 | 移す既存メソッド |
|---|---|---|
| `InteractionIndex` | `_interactions`, `_interacted_ids` | `record_interaction` `has_interacted_with` `unique_agent_count` `interaction_count` `get_top_interacted_agents` |
| `FollowState` | `agents.json` | `record_follow` `record_unfollow` `get_followed_agents` `_load/_save_agents_json` |
| `PostHistory` | `_post_history` | `record_post` `get_recent_posts` `get_post_rate_7d` |
| `CommentLedger` | `commented_cache.json` | `has_commented_on` `record_commented` `count_recent_comments_by_author` `get_prior_comment_targets` + cache 3 メソッド |

- `_count_within`（`:389`）は PostHistory と CommentLedger の両方が使うので `core/memory/_windows.py` 等に共有ヘルパーとして残す。
- `FORBIDDEN_SUBSTRING_PATTERNS` による `agents.json` 検証（`_load_agents_json:151`）は `FollowState` に持っていく。**これは LLM メモリ信頼境界のガード**なので、検証失敗時のデフォルトフォールバック挙動を変えない。
- 既存の seam を活用: CLI サブコマンドは既に `MemoryStore` を経由せず `EpisodeLog` / `KnowledgeStore` を直接構築している（`cli/memory_cmds.py:53-54` ほか）。分割後のリポジトリも同じ粒度で単体構築可能にする。
- 呼び出し側（`adapters/moltbook/` の 6 ファイル）は無変更。

**テスト**: `tests/test_memory.py`, `test_agent.py`, `test_novelty_gate.py`, `test_session_context.py`, `test_dedup.py`

---

## C4 — publish 三重実装の集約 + parser 重複ルールの共有化（P1 / 高リスク）

### C4-a 外部書き込みトランザクションの集約

**問題**: 3 経路が独立に「write → scheduler 計上 → verification → dedup → action history → episode log → memory 記録」を並べている。

| | reply_handler.py:294-373 | feed_manager.py:449-526 | post_pipeline.py:369-483 |
|---|---|---|---|
| write | `post_comment(parent_id)` | `post_comment` | `client.post("/posts")` |
| scheduler | `record_comment()` | `record_comment()` | `record_post()` |
| verification | 同一 | 同一 | 同一 |
| 429 → `set_rate_limited()` | あり | あり | **なし（漏れ）** |

**やること**: `adapters/moltbook/publish.py`（新規）に、3 経路が共有する**不変部分だけ**を切り出す。

```python
def publish_and_record(
    *, write: Callable[[], CreatedObject],   # 経路ごとの API 呼び出し
    on_scheduler: Callable[[], None],
    handle_verification: Callable[[dict], bool],
    ctx: SessionContext,
    record: RecordSpec,                      # dedup key / action label / episode payload
) -> PublishOutcome                          # verified / unverified / client_error
```

- 共有する不変部分（3 経路で完全一致、Explore 確認済み）: verification ハンドシェイク + 「未検証なら何も記録しない」不変条件、`ctx.actions_taken.append` → INFO preview + DEBUG 全文（コメントブロックが 3 箇所に逐語コピーされている）、`episodes.append("activity", ...)`、`try/except MoltbookClientError`。
- 経路固有として**残す**もの（差分には理由がある）:
  - dedup キー粒度（reply は `reply:{post_id}:{comment_id}`、comment は `post_id`、post は無し）
  - `content.mark_posted`（reply は意図的に無し — 相手宛の返信を本文ハッシュで dedup するのは誤り）
  - `record_interaction`（reply は received+sent の 2 回、comment は sent のみ、post は無し）
  - `record_post` + novelty gate sidecar（post のみ、ADR-0018）
  - `parse_created_post_response` によるエンベロープ検証（post のみ。comment 系は client 側で検証済み）
  - pacing sleep（feed のみ）、courtesy upvote（reply のみ）
- **429 → `set_rate_limited()` の欠落を共通経路に取り込むことで post 側にも適用される**。これは唯一の挙動変更なので、コミットメッセージと ADR 追記で明示し、専用の回帰テストを 1 本足す。

**テスト**: すべて `tests/test_agent.py` に集中（`TestHandleVerification:618` / `TestEngageWithPost:770` / `TestRunPostCycle:1287` / `TestOwnPostIdTracking:1870` / `TestRunReplyCycle:2124` / `TestCheckOwnPostComments:2344`）。特に `test_comment_verification_failure_not_recorded:919` と `test_failed_verification_not_recorded:1429` が「未検証なら記録しない」不変条件のアンカー。
**chaos**: CLAUDE.md の chaos-TDD 原則に従い、`tests/chaos.py` を使って「verification 応答が想定外形状」「write は成功したが envelope が壊れている」の fault 列を追加する。

### C4-b `verification_parse.py` の段分け（差分テストで担保）

**問題**: `_resolve`（`:847`）と `_resolve_implicit`（`:962`）に同じルールが二重実装され、**実際に 2 回「片方の経路にしかガードが無い」バグが出ている**（コメントに codex-review / python-reviewer の指摘として記録済み）。文法改正はサーバ都合で今後も来るので、この二重協調が続く限り 3 回目が出る。

**先に検証床を作る（コード変更の前）**: `docs/evidence/adr-0062-parser-rewrite/differential_replay.py`（新規）

- 旧実装を `verification_parse_legacy.py` として**そのままコピー**して一時的に併存させる（このコミット内でのみ存在。C4-b の最後に削除）。
- ローカル corpus（`~/.config/moltbook/logs/verification-audit.jsonl`、1272 unique challenge）の**全件**を両実装に流し、`(戻り値, abstain したか)` の完全一致を要求する。
- **ground truth 不要**。ラベル付き 82.5% ではなく **1272/1272 = 100%** が検証対象になる。1 件でも不一致なら fail。
- 併せて `tests/test_verification.py` のフィクスチャ（2026-06-28 / 07-06 / 07-07〜09 / 07-10〜14 の実障害由来、base64 で commit 済み）を差分ハーネスの固定入力としても流す。こちらは corpus と違って repo に入っているので、他マシン・CI でも回る最低限の床になる。

**段構成**: 現在のパイプラインは既に段になっており（`_scan` → `_dedup_numbers` → `_compose_operands` → `_apply_points` → `_dedup_operands` → `_resolve`）、崩れているのは最終段だけ。そこを 3 つに割る。

```
operands, events, atoms
  → _extract_signals(...)  -> Signals    # 位置分類・cue・tail・隣接性を 1 箇所で判定（frozen）
  → _resolve_operation(Signals) -> Operation | _Abstain   # 演算子決定の唯一の場所
  → _compute_chain(operands, Operation) -> str            # 既存を流用
```

- `_resolve` / `_resolve_implicit` の分岐は `_resolve_operation` 内の**明示的な explicit / implicit 分岐**になり、両者は同じ `Signals` を見る。二重実装が構造的に不可能になるのが本改修の目的。
- 二重化している 3 ルールは自動的に `_extract_signals` に一本化される: (1) 非隣接 trailing marker のノイズ扱い（`_POSTFIX_ADJACENCY`、`_resolve` の tail_marks 処理 と `:1001`）、(2) subtract vs "combined" の矛盾 abstain（`:948-952` と `:1008-1010`）、(3) `_normalize_op` / `_ADD_CHANGE` を含む tail-op 分類。
- **fail-closed セマンティクスを変えない**: 迷ったら `_Abstain`。差分テストで abstain 件数まで一致を要求するので、「沈黙していたケースが誤答になる」逆転は構造的に検出される。
- 段分け後、`verification_parse_legacy.py` と差分ハーネスの legacy 参照を削除。`differential_replay.py` 自体は次回改正時にも使えるよう docs/evidence に残す（次の改正はこれで「旧挙動からの意図的な差分だけ」をレビューできる）。

**検証（このコミットの合否条件）**:
```bash
python3 docs/evidence/adr-0062-parser-rewrite/differential_replay.py   # 1272/1272 一致が hard gate
python3 docs/evidence/adr-0062-parser-rewrite/replay_parser.py         # 誤答ゼロ（既存 gate）
uv run pytest tests/test_verification.py -v                            # 67 tests
```
差分ハーネスが 1 件でも不一致なら、その challenge を最小再現に落として原因を特定するまで進めない（差分を「改善」と解釈して通さない — 振る舞い保存が本コミットの契約）。

**ADR**: ADR-0062 に 10 番目の改正として「resolve 段の構造分離（振る舞い不変、differential replay で担保）」を追記。差分ハーネスの存在と使い方も同時に記録する。

---

## Verify（各コミット共通）

```bash
source .venv/bin/activate
uv run pytest tests/ -v                                   # 1546+ tests
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing   # >= 80%
uv run lint-imports                                       # ADR-0001 layers contract
uv run ruff check src/ tests/
uv run pyright                                            # 型エラー 0 維持
git status --short                                        # 意図しないファイルの混入確認
```

C4 のみ追加:
```bash
python3 docs/evidence/adr-0062-parser-rewrite/differential_replay.py   # 1272/1272 旧新一致
python3 docs/evidence/adr-0062-parser-rewrite/replay_parser.py         # wrong=0（既存 gate）
```
どちらもローカル corpus（`~/.config/moltbook/logs/verification-audit.jsonl`）に依存するため、**この Mac 上でのみ完全実行可能**。CI では repo 同梱のフィクスチャ分だけが回る。

**Review**: 各コミット前に `python-reviewer` と `codex-review --uncommitted` を並列起動。C4 は `security-reviewer` も追加（外部書き込み・信頼境界に触れるため）。いずれかが CRITICAL を返したら停止して報告。

**Doc Sync**: C4-a は publish 経路の段構成が変わるため `docs/CODEMAPS/architecture.md` の Data Flow を同じ diff で更新（CLAUDE.md 鮮度規約）。C4-a の 429 挙動変更は ADR-0063 系への追記か新規 ADR で記録。C3-c の MemoryStore 分割は `docs/CODEMAPS/` のモジュール記述を更新。C1〜C2 は内部整理のみで doc 追従不要。

**コミット規律**: 個人研究 repo なので `main` 直コミット → push（branch / PR を作らない）。
