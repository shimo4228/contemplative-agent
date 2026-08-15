# ADR-0026: 離散カテゴリの廃止（ADR-0019 の Phase-3 完了）

## Status

partially-superseded-by [ADR-0060](./0060-per-episode-grounded-distill.ja.md) — ADR-0060 は 2026-06-23 に ingest 時の noise gate を全廃し、Phase 2 の `core/distill.py` 側（`_classify_episodes`、`_ClassifiedRecords`、`NOISE_THRESHOLD`）を退役させた（ADR-0060 の散文はこれを "Step 0" と呼ぶが、その名称は本 ADR には存在しない）。Phase 1、Phase 3、および Phase 2 の `core/constitution.py` 側 — `amend_constitution` の view ベース検索 — は引き続き有効。なお Migration 節の `migrate-categories` CLI は別途 [ADR-0035](./0035-sunset-migration-surface-and-consolidate-artifact-extraction.ja.md) が退役させている。

## Date

2026-04-16

## Context

ADR-0019 は LLM による classify / subcategorize 呼び出しを、構造的に異なる 2 つの機構 — pattern ごとの `embedding`（意味座標）と、Markdown シードファイルで分析軸をクエリ時に展開する `views/` — に置き換えた。旧スキーマからの残骸が 2 つ生き残っている:

1. **`category: "constitutional" | "uncategorized" | "noise"`** — pattern に書き込まれる離散ラベル。LLM 呼び出しではなく embedding centroid 分類で生成されるようになったが、依然として pattern 行の state field。
2. **`_INSIGHT_EXCLUDED_VIEWS = {"self_reflection", "noise", "constitutional"}`** — `core/insight.py` 内にハードコードされた除外セット。`constitutional` view からの skill 抽出を阻害している。

この組み合わせが 3 つの問題を複合的に引き起こしている:

1. **`constitutional` view が insight パスから到達不能。** `extract_insight` は `view_registry.find_by_view(...)` を呼ぶ前に `raw_patterns` を `category == "uncategorized"` で絞り込み、さらに build-batches で `constitutional` view を除外する。分類器が `constitutional` とタグ付けした pattern は、構造上、skill 抽出から到達不能。しかし `constitutional` view は存在し、`amend_constitution` はこれを使っている。
2. **同じ意思決定が 2 つの軸でエンコードされる。** 「この pattern は憲法改正に参加するか?」が `category == "constitutional"` (distill 時に一度だけ設定される行フィールド) と `view_registry.find_by_view("constitutional", ...)` (クエリ時の cosine マッチ) の両方で問われている。両者が食い違う場合 — 新しい view seed、centroid のドリフト — 行フィールドが勝つ（アクセスをゲートしているから）。
3. **ADR-0019 が提起した「スキーマ vs 空性（Emptiness）」の摩擦が部分的に未解決。** ADR-0019 の中心的主張は「分類はクエリであって state ではない — 座標を保存し、切断はクエリ時に具現化せよ」だった。`category` フィールドはまさにその主張が排除すべき「凍結された分析軸」である。`subcategory` は削除したが、同じ問題の狭い版が残っている。

現状は安定している（agent は動く）が、パイプラインは ADR-0019 がした建築的主張から静かに乖離している。本 ADR はこの移行を完了する。

別だが補完的な問い — `noise` 判定そのものを gating 決定として残すべきか、noise episode を後日の再分類のための「種子」として保持すべきか — は意図的に本 ADR のスコープ外。それは ADR-0027 ("Noise as Seed" 提案) の領域。

## Decision

pattern-level の `category` フィールドを 3 段階の Phase で段階的に廃止する。各 Phase は独立にテスト可能、独立に revert 可能、かつ動作状態を保つ。

### Phase 1 — insight 読み出しパスから `category` gating を除去

`core/insight.py`:

- `_INSIGHT_EXCLUDED_VIEWS` から `"constitutional"` を削除。`"self_reflection"` (distill_identity にルート) と `"noise"` (gate 決定) はそのまま。
- `knowledge_store.get_live_patterns(category="uncategorized")` と `get_live_patterns_since(..., category="uncategorized")` (L213 / L217 / L220 の 3 箇所) の `category` 引数を削除。insight パスは全 live pattern を読み、ルーティングは views に委ねる。

予想される効果: `constitutional` タグ付き pattern は `extract_insight` から到達可能になり、その embedding が実際に近い centroid の view にマッチする。noise/const embedding 類似度で constitutional になった pattern は、`_build_view_batches` で constitutional view にマッチする — view はもはや到達不能ではない。

スキーマ変更なし。`category` と `views` の両方を書き続ける / 読み続ける — ハード除外のみが消える。

### Phase 2 — 3 値分類を binary `gated` フラグに置換

`core/distill.py`:

- 3-tuple の `_ClassifiedRecords(constitutional, noise, uncategorized)` を 2-tuple の `_ClassifiedRecords(kept, gated)` に置換。noise episode は `gated` に、constitutional と uncategorized は `kept` に統合。
- `_classify_episodes` を書き換え、`noise_sim` のみを計算し `gated = noise_sim >= NOISE_THRESHOLD` を設定。`CONSTITUTIONAL_THRESHOLD` 定数はコードベースに残る (Phase 3 で削除) がここでは読まれなくなる。
- `distill` 内の `for category, cat_records in [("uncategorized", ...), ("constitutional", ...)]` ループを削除。`_distill_category` を `kept` で 1 回だけ呼び出す（スキーマ互換のため category 引数は一時的に `"uncategorized"` プレースホルダー — Phase 3 で引数を削除）。
- `_distill_category` の dedup scope は依然 `existing_same_cat` を `category == "uncategorized"` でフィルタする — 移行後は no-op (全行が同じ値を持つ) になり、Phase 3 でフィルタを削除する。

`core/constitution.py`:

- `knowledge.get_learned_patterns(category="constitutional")` と `knowledge.get_context_string(category="constitutional")` を view ベースの取得に置換。具体的には: agent の `ViewRegistry` をロードし、`view_registry.find_by_view("constitutional", knowledge.get_live_patterns())` を呼び、マッチした pattern 本体を prompt に整形する。`amend_constitution` に `view_registry` 引数を追加 (`distill_identity` と同形)。CLI の `_handle_amend_constitution` から渡す。

予想される効果: 新規 pattern は依然 `category = "uncategorized"` で `knowledge.json` に入る (スキーマ保持)、noise gate は動作、`amend_constitution` は行フィールドではなく views 経由で読む。`category` フィールドは新規行ごとに退化した定数となる。

テスト影響: `tests/test_distill.py` の `_ClassifiedRecords` アサーション (4 件)、`tests/test_constitution.py` (2 件)。

### Phase 3 — `category` フィールドを削除し migration を出荷

`core/knowledge_store.py`:

- `add_learned_pattern` から `category` パラメータを削除。`_parse_json` / `save` でフィールドを書き込まない。
- `_filtered_pool` の `category` 分岐を削除。`get_raw_patterns(category=...)`, `get_learned_patterns(category=...)`, `get_context_string(category=...)`, `get_live_patterns(category=...)`, `get_live_patterns_since(since, category=...)`, `get_raw_patterns_since(since, category=...)` から `category` パラメータを削除。呼び出し側は Phase 2 までに全て移行済み — これは片付け。

`core/distill.py`:

- `_distill_category` と `add_learned_pattern(..., category=...)` から `category` 引数を削除。
- dedup scope は「全 live pattern」になる (per-category 分割なし)。クロス軸の重複はすでに views で dedup 可能だった; 行レベルの分割は人工的だった。
- `_distill_category` の `MEMORY_EVOLUTION_PROMPT` 分岐から `live_same_cat` の `category == category` 述語を削除。

`core/migration.py`:

- `drop_category_field(knowledge: KnowledgeStore, *, dry_run: bool = False) -> MigrationStats` を追加。`backfill_pattern_embeddings` と同形: in-place 変更（dry-run では count のみ）、呼び出し側が save する。legacy `category == "noise"` は `gated = True` として保存 (退化された 3 値ラベルとは別の binary flag)。
- CLI: `_handle_migrate_categories` を `_handle_migrate_patterns` の隣に追加。同じ ergonomics — `--dry-run`、summary 出力、`_log_approval("migrate-categories", ...)` エントリ。

テスト影響: `tests/test_migration.py` に `drop_category_field` 用の 2–3 ケース追加、`tests/test_knowledge_store.py` から `category` フィルタのアサート削除、`tests/test_memory_evolution.py` から `category` preserve チェック削除。

## Alternatives Considered

1. **単一 commit での big-bang 削除。** 検討して却下: クロスファイル表面は 8 モジュール (`insight.py`, `distill.py`, `constitution.py`, `knowledge_store.py`, `memory_evolution.py`, `migration.py`, `views.py`、および tests)。単一 commit 削除はテストを通るが post-merge 挙動がドリフトすると bisect が困難。3 Phase 化で各ステップを net ~60 LOC 以下に抑える。
2. **`constitutional` を個別の行レベル namespace として保持し、insight のハード除外のみ削除。** 変更は小さいが、スキーマ/クエリ重複が未解決のまま。`constitutional` view は insight から到達可能になるが、`distill` と `amend_constitution` の `category == "constitutional"` 分岐が同じ決定を二重にエンコードし続ける。これは ADR-0019 の著者が明示的に反対した "worst-of-both-worlds" 状態 ("partial migrations rot")。
3. **`gated` をクエリ時に導出し、永続化しない。** ADR-0019 が同じ理由で検討・却下した: noise 分類はパイプラインステップを gate しているので、導出化すると distill 実行ごとに全 episode を再 embed することになる。gate 決定は永続化、意味軸はクエリ化。
4. **noise gating も廃止する ("radical" オプション)。** ADR-0027 に先送り。その変更の動機は別軸（noise 判定そのものが適切か?）であり、実装リスクも別（LLM prompt 量、`num_ctx` truncation、forgetting 依存の cleanup）。スコープを分離してロールバック面を小さく保つ。
5. **`category` → `namespace` にリネーム、削除しない。** state-vs-query 摩擦を解決しない。却下。

## Consequences

**Positive**:

- `amend_constitution` と `extract_insight` が同じ機構 (`ViewRegistry`) で読むようになり、同じ概念的問い（「どの pattern が constitutional か?」）が 2 つの答えで食い違う乖離が閉じる。
- 新しい分析軸（例: `aesthetic` view）の追加が、既存 pattern に分類器を再実行する必要なく、seed Markdown ファイルを書くだけでクエリ時に具現化される。ADR-0019 の中心的主張の完全な payoff。
- 移行は one-shot で可逆: 変更前に `knowledge.json.bak.{timestamp}` が自動保存され、rollback は `cp` + post-migration ファイルの削除。
- テストスイート縮小（Phase 3 着地後、推定 net ~80 LOC 削減）。

**Negative / risks**:

- Phase 2 が `amend_constitution` のシグネチャを変更する (必須の `view_registry` 引数を追加)。単一 CLI 呼び出し元はロックステップで更新; リスクはその site に限定。
- `NOISE_THRESHOLD = 0.55` が蒸留に入るものを制御する唯一のツマミになる。本 ADR 着地後のミス tuning は以前より blast radius が広い（以前は "constitutional" として生き残る余地があった）。緩和: Phase 2 の threshold 変更出荷前に 14 日 window で dry-run。閾値変更は本 ADR では着地しない。
- pre-0019 LLM 分類器で `category: "noise"` とタグ付けされた legacy `knowledge.json` ファイル（このコードベースには存在しない可能性が高いが、clone された研究データにはあり得る）は、migration で signal を静かに落とさずに `gated: True` として保存する必要がある。migration はこれを明示的に処理する。
- `category` indexed の dedup scope (`distill._distill_category`) は Phase 3 後にクロス namespace になる。以前は衝突しなかった constitutional-ish pattern が uncategorized-ish pattern と dedup される可能性がある。許容: 空性公理は、結局は同じ意味座標に対する別 namespace を保持することに反対する。

**Explicitly not addressed** (next ADR territory):

- `noise` gate 自体を残すべきか (ADR-0027 候補)。
- per-view threshold の再形成（per-view tuning は既に `views/*.md` frontmatter にある）。
- view centroid が動いた時の過去 pattern のランタイム再評価 (ADR-0027 領域)。

## Rollback Plan

各 Phase は独立に revert 可能:

- **Phase 1**: insight.py の 3 行を復元。スキーマ変更なしのためデータ作業不要。
- **Phase 2**: 3-tuple の `_ClassifiedRecords`、`distill()` の 2-category ループ、`constitution.py` の `category="constitutional"` read を復元。Phase 2 下で書かれた新規 pattern は既に `category = "uncategorized"` を持っているので revert で変更されず生き残る。
- **Phase 3**: migration は in-place だが、pre-migration バックアップ `.bak.{timestamp}` が authoritative rollback artifact。復元して distill を再実行; migration 後に追加された pattern は `embedding` から `category` フィールドを設定する必要がある（分類を再実行）。緩和: Phase 3 をデータ量操作と同日に着地させない。

## Migration

`drop_category_field` は冪等。legacy ファイルで 2 回実行しても同じ結果。`category` フィールドなしの Phase-3 ファイルで実行すると no-op。CLI はその場合「already migrated」を報告する。

```bash
contemplative-agent migrate-categories --dry-run   # 件数のみ
contemplative-agent migrate-categories             # 実際に移行
```

migration は:

1. `knowledge.json` をロード（`KnowledgeStore` 経由）。
2. 各 pattern について: `category == "noise"` なら `gated = True` を設定（稀 — 主として legacy 研究データへの防御）。常に `category` キーを削除。
3. `KnowledgeStore.save()` で結果を書き込む。

`audit.jsonl` エントリは CLI が書く（`migrate-patterns` (ADR-0021) と `migrate-identity` (ADR-0025) と同パターン）。

## References

- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — 方向性を宣言; 本 ADR は `category` 半分を完遂。
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — `migrate-patterns` CLI の形; `migrate-categories` はこれをミラー。
- [ADR-0025](0025-identity-history-and-migrate-cli.md) — 先送りされていた wiring を着地させる規律を再利用。
- 内部 issue tracker (local-only) の N4 エントリ — 本 ADR を動機づけた。
