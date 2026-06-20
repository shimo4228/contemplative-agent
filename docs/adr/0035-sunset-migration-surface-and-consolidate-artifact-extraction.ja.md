# ADR-0035: ADR-0019 移行 CLI のサンセットと artifact 抽出の統合

## Status
accepted

## Date
2026-05-05

## Context

ADR-0019 が landed し 2026-04-15 以降の安定化期間に入って以降、コードベースに 2 系統の摩擦が蓄積した。

### 1. 移行コマンドが、移行完了後も CLI 表面を残し続けた

ADR-0019 で `knowledge.json` は category-tagged から embedding + view 形に移った。ADR-0021 で provenance / bitemporal / trust schema が加わり、ADR-0026 で `category` フィールドを廃止した。それぞれ `core/migration.py` の下に one-shot CLI コマンドを伴って出荷された:

- `embed-backfill` (ADR-0019) — 既存 pattern + episode log の埋め込み計算
- `migrate-patterns` (ADR-0021) — provenance / bitemporal default の埋め込み、ADR-0028/0029 廃止フィールドの除去
- `migrate-categories` (ADR-0026) — `category` / `subcategory` 削除、legacy `noise` を `gated=True` に変換

唯一の active deployment は 2026-04-15 に移行完了済み。disk 上の `knowledge.json` schema は一貫していて、key 集合は `{distilled, embedding, gated, importance, pattern, provenance, source, trust_score, trust_updated_at, valid_from, valid_until}`。それ以降、新たな caller がこれらの移行コマンドを呼んでいない。それでも `core/migration.py` に約 700 LOC、tests に約 390 LOC、CLI subparser 3 つ、移行関連の段落が 3 つの doc ファイル (`CHANGELOG.md`, `docs/CONFIGURATION.md`, `docs/CONFIGURATION.ja.md`) と 1 つの runbook (`docs/runbooks/adr-0019-migration.md`) に残っていた。

承認ゲート 4 コマンド (`insight`, `rules-distill`, `distill-identity`, `amend-constitution`) の `--dry-run` フラグは ADR-0012 で interactive approval gate が導入された時点で deprecated になった (承認プロンプトで reject すれば dry-run preview と同等)。それ以来 deprecation 警告付きで出荷していた。フラグ本体と handler 側の `if _is_dry_run(args): ...` 分岐 4 箇所は、自身の deprecation 警告以外には誰も exercise しないコード経路として残っていた。

`core/knowledge_store.py` の `_parse_legacy_markdown` reader は v1.x format (knowledge.json が JSON になる前) からの生き残り。production data は v2.0 以降 JSON 一本。reachable な caller は legacy Markdown を合成して parser を exercise する 2 つの test case のみ。

### 2. Artifact 抽出ロジックが 3 つのコマンドで重複している

`insight` (ADR-0023)、`rules-distill`、`skill-reflect` (ADR-0023) はそれぞれ:

1. 候補集合をイテレート
2. LLM を呼んで artifact を生成
3. identity-content sanitizer で出力を validate
4. title を抽出
5. filename を slugify
6. path-escape を guard
7. 結果を command 固有の `*Result` dataclass に wrap

実装は各 30–60 LOC。3 つは loop scaffold (3, 5, 6) でほぼ同一、prompt (2)、marker handling (7)、result shape (7) で分岐する。

CLI handler 側も同様: `_handle_insight`、`_handle_skill_reflect`、`_handle_rules_distill`、`_handle_amend_constitution` が approval-gate boilerplate (snapshot, iterate, print, `_approve_write`, `_log_approval`, write-on-approve, summary print) をほぼ重複して持つ。各 30 LOC。summary print と result shape は違うが、gate mechanism は同じ。

弱い形の重複: 8 つの retrieval / quality threshold — `CLUSTER_THRESHOLD` (insight 0.70)、`CLUSTER_THRESHOLD_RULES` (0.65)、`NOISE_THRESHOLD` (distill 0.55)、`SIM_DUPLICATE` (stocktake 0.90)、`SIM_UPDATE` (stocktake 0.80)、`SIM_CLUSTER_THRESHOLD` (stocktake 0.80)、skill-router default (0.45)、rules-stocktake reflect threshold — がモジュールローカルに、ad-hoc な ADR-reference コメント付きで定義されている。`core/snapshot.py` は既に late-import で集めて pivot snapshot に dump しているので、事実上の registry pattern を逆さに持っているだけ。

### 3. 直近の撤回サイクルからの制約

ADR-0024/0025 は identity block parsing を導入し、ADR-0030 でまとめて withdrawn された。ADR-0030 は `single-responsibility-per-artifact` heuristic を残した: artifact の責務は exactly one layer に住む。別のレイヤーに居場所があるなら、既存 artifact の sub-structure に新しい concern を押し込むな。本 ADR の plan はこれを尊重する必要がある — どんな consolidation も、command 固有のドメインロジック (prompt、marker handling、result field) を共通 base class に引き上げてはならない。

## Decision

本 ADR は 3 つの連動する変更を記録する。1 つ目 (Sunset) は同 PR で land、2 つ目と 3 つ目 (Helper extraction、Loop consolidation) は follow-up PR で land する。ADR が follow-up PR の継承する contract になる。

### 1. ADR-0019 移行表面のサンセット

以下を削除:

- `src/contemplative_agent/core/migration.py` (~700 LOC)。`_ensure_adr0021_defaults` も同モジュール内のみで使われるので一緒に死ぬ
- `tests/test_migration.py` (~390 LOC)
- `tests/test_knowledge_store.py` の `TestMigrationADR0021` クラス (~110 LOC)
- `tests/test_memory.py` の legacy-Markdown 系 2 test (`test_legacy_markdown_migration`、`test_legacy_markdown_gets_default_importance`)
- `cli.py` の `_handle_migrate_patterns`、`_handle_migrate_categories`、`_handle_embed_backfill` と 3 subparser、no-LLM / LLM dispatch table の entry
- `cli.py` の `EPISODE_EMBEDDINGS_PATH` import (唯一の consumer は `_handle_embed_backfill` だった)
- `cli.py` の `_warn_dry_run_deprecated` と `_APPROVAL_GATE_COMMANDS` frozenset。4 handler 内の `_warn_dry_run_deprecated(args)` 呼び出しと `if _is_dry_run(args): ...` 分岐も同時に削除
- `insight`、`rules-distill`、`distill-identity`、`amend-constitution` の `--dry-run` argparse 宣言
- `core/knowledge_store.py` の `_parse_legacy_markdown` と caller。non-JSON `knowledge.json` は warning を log して空 store として load する
- `docs/runbooks/adr-0019-migration.md` および `docs/runbooks/README.md` の対応エントリ
- `docs/CONFIGURATION.md` / `docs/CONFIGURATION.ja.md` の "One-Time Migrations" セクション

更新:

- `CHANGELOG.md` — "Run these migrations once" ブロックを sunset 注記に置換 (晩到 v1 → v2 移行は v2.0.x release tag を使う旨)
- `core/distill.py` — `enrich` の docstring と `distill_identity` の docstring から `embed-backfill first to migrate` 行を削除
- `core/constitution.py` — constitutional view lookup 上のコメントから `embed-backfill first to migrate` 句を削除

ディスク上の `knowledge.json` および `.bak.*` ファイルは触らない。本 PR 後に v1.x の `knowledge.json` を持って到着した者は、v2.0.x release tag を checkout して migration を走らせ、その後 main を pull することを期待する。

### 2. Threshold registry と text utilities (PR2)

`src/contemplative_agent/core/thresholds.py` を追加。8 つの threshold 定数を移動。各定数に ADR / calibration date / unit の docstring を必須付与。`core/snapshot.collect_thresholds` は late-import せず本モジュールから読む。

`src/contemplative_agent/core/text_utils.py` を追加 (`extract_title`、`slugify`、`strip_frontmatter`)。`_extract_title` と `_slugify` を `core/insight.py` から、`_strip_frontmatter` を `core/rules_distill.py` から移動。caller (`cli.py`、`rules_distill.py`、`stocktake.py`) を更新。`stocktake → rules_distill` の import 依存が解消される。

`stocktake.format_report` を `format_stocktake_report` に rename して `metrics.format_report` との同名衝突を解消。fmt 対象 (SessionReport vs StocktakeResult) が違うので、rename は hygienic。

以下のモジュール抽出は **拒否** する (検討済み、いずれも棄却):

- `core/sanitizer.py` — `_sanitize_output` と `wrap_untrusted_content` は同じ理由で `core/llm.py` 内に co-located されている: `_INJECTION_TOKENS` を共有し、同じ trust boundary で動く。2 関数モジュールへの分離は overengineering
- `core/approval_gate.py` — `_log_approval`、`_approve_write`、`_stage_results`、`StageItem`、`AUDIT_LOG_PATH` は CLI-bound (`STAGED_DIR`、`MOLTBOOK_DATA_DIR`、`AUDIT_LOG_PATH` を参照)。`core/` に移すと ADR-0001 の `cli.py → core/` import direction に逆転する
- 新 `core/io.py` — `core/_io.py` は既存。PR3 で重複 I/O helper が出てきたら `_io.py` に寄せる

### 3. Artifact-extraction loop の統合 (PR3a/PR3b)

`src/contemplative_agent/core/artifact_extraction.py` を追加し、以下を export:

```python
@dataclass(frozen=True)
class ArtifactSpec:
    name: str                                      # "insight" | "rules" | "skill-reflect"
    target_dir: Path
    filename_template: str                         # 例: "{slug}.md"
    validator: Callable[[str], bool]               # 例: validate_identity_content
    no_change_marker: Optional[str] = None         # 例: _NO_CHANGE
    no_rules_marker: Optional[str] = None          # 例: _NO_RULES_MARKER

def extract_artifacts(spec: ArtifactSpec, items: Iterable[X]) -> ArtifactBatch: ...
```

`insight.py` / `rules_distill.py` / `skill_reflect.py` の各 caller は自分の `ArtifactSpec` を組み立て、`extract_artifacts` を呼び、結果を自分の `*Result` 型に wrap する。**Base class での framing は ADR-0030 ルールにより拒否**: command ごとの差分 (prompt content、marker semantics、result field) は call site に住む、共通親に持ち上げない。

CLI handler 4 つには `cli.py` 内に `_run_approval_loop(items, *, command, snapshot_path)` を追加。各 handler は依然として自分の summary print を持つ (dropped/skipped/no-change/revised の文言が command で違う)。loop body — print、approve、log、write-on-approve — は helper に集約。

`cli.py` を `cli/` package に分割するのは PR3 のスコープ外として **拒否**。PR1 後で ~1700 LOC、すべてのセクションは CLI handler、cohesion は高い。PR3b 完了後に再評価。

## Consequences

**Positive**:

- Sunset 単体で runtime + tests から ~1100–1300 LOC 削減
- 4 つの approval-gate handler が orphan deprecation path を抱えなくなる。将来 handler を読む者が「`--dry-run` が 5 ヶ月前に deprecated だった」を発見する必要がない
- `knowledge_store._parse_json` が唯一の reader path、契約が一意になる
- PR2 後、threshold provenance (どの ADR が、いつ、どの calibration で値を決めたか) が co-located になる。`snapshot.collect_thresholds` が 6-import collector から 3 行 read に縮む
- PR3 後、`insight.py` / `rules_distill.py` / `skill_reflect.py` は各 250 LOC 未満、CLI handler 4 つは各 30 LOC 未満を目標。重複 cluster 監査で見つかった 10 cluster のうち、最重量 2 つ (Cluster 1 / Cluster 2) が ADR-0024/0025 over-extraction を再演しない形で解消する

**Negative**:

- まだ移行していない v1.x deployment は本 PR 以降で main を pull しても upgrade できない。先に v2.0.x release tag を checkout し migration を走らせ、main を pull する必要がある。README の "v1 → v2.0 migration" link は current main ではなく tagged release に向け直す
- non-JSON `knowledge.json` は row を一切報告しない (warning を log し、store は空)。以前の auto-fallback は v1 → v2 transition 期の safety net だった、その net がなくなる
- `insight` / `rules-distill` / `distill-identity` / `amend-constitution` に `--dry-run` を渡す script は `unrecognized arguments` で fail する。CHANGELOG にはっきり記載、failure mode は silent ではなく loud

**Neutral**:

- `~/.config/moltbook/knowledge.json.bak.*` は touch しない。v1 → v2 移行 recovery path として残す
- ADR-0019 (embedding + views) と ADR-0021 (pattern schema) は accepted のまま、それを delivered した移行表面が retire するだけ
- ADR-0026 (retire categories) は accepted のまま、それを完了した `migrate-categories` コマンドが retire する
- `core/distill.py` の `_CategoryResult` dataclass は **削除しない**。`_distill_category` の戻り型 (モジュール内 4 箇所で使用)。ADR-0026 の category retirement にもかかわらず、これは意味のある internal type であって leftover ではない

## 先行 ADR から継承する教訓

ADR-0030 が `single-responsibility-per-artifact` を残し、ADR-0034 が "validate a mechanism against actual LLM output before generalizing it" を加えた。本 ADR は 3 つ目を追加する (`feedback_substrate-migration-sweep` がすでに部分的に捉えていた): **one-shot CLI subcommand には sunset 条件がある。導入した ADR にそれを記録し、docs と一緒に 1 PR で retire する**。移行コマンドを残したままのコストはゼロではない — test、runbook entry、`--dry-run` flag が累積し、システムの残りはそれらと歩調を合わせ続けないといけない。retirement それ自体が、次の refactor がそれらを継承しないように守る `chore` である。

## References

- [ADR-0001](0001-core-adapter-separation.md) — `cli.py → core/` import direction、`_log_approval` / `_stage_results` を `core/` に出さなかった制約
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — embedding + view shape と embed-backfill 元来の motivation、retire しない
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — pattern schema landing、retire しない
- [ADR-0026](0026-retire-discrete-categories.md) — category retirement、本 ADR で retire するのは delivered した `migrate-categories` コマンドの方
- [ADR-0028](0028-retire-pattern-level-forgetting.md) / [ADR-0029](0029-retire-sanitized-flag.md) — `migration.py` と一緒に strip-on-load logic が死ぬ retired field
- [ADR-0030](0030-withdraw-identity-blocks.md) — first withdrawal ADR、PR3 design を制約する `single-responsibility-per-artifact` heuristic
- [ADR-0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.md) — 直近の withdrawal precedent、retire-with-docs-in-one-PR pattern を踏襲
