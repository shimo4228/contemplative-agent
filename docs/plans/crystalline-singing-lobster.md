# Lint ゲート一括導入（doc リンク / frozen / adapter 独立 / ruff 拡張 / ADR ペア / 統計 warning）

## Context

import-linter 導入（`8be938b`）の続き。「文書には書いてあるが機械強制されていない不変条件」の棚卸しで挙げた 6 候補を全て導入する（ユーザー承認済み。統計照合のみ warning 設計の指定あり）。事前監査で **リンク切れ 24 件**、**INDEX.md 統計の実測ズレ（1920 vs 1921 tests）** が既に実証されている。

- **Phase 0**: 新規依存ゼロ。link checker は Build（lychee / markdown-link-check は外部 URL 志向 + 非 Python toolchain、必要なのはオフライン決定論の相対リンク検査のみ、stdlib ~30 行）。frozen ゲートも Build（ruff に frozen 強制ルールは存在しない、AST ~40 行）。他は既存ツール（ruff / import-linter）の設定のみ
- **種別: chore + test**。ADR は書かない（各ゲートの根拠は既存 ADR-0001/0012/0015/0079 と AKC Maintain 原則）

## 事前監査の確定事実

- リンク切れ 24 件の内訳: CHANGELOG のパス誤り 5（0034/0035 の旧ファイル名、`../docs/` 起点ミス）/ ADR-0035 en+ja の 0028・0029 参照 4 / `core/llm.py`（ADR-0079 で `core/llm/` package 化）8 / `mlx_backend.py`・`run-with-mlx.sh`（ADR-0070 で sibling repo へ退役）4 / ADR-0024 en+ja の 0012 参照 2 / `docs/adr/README.md` のテンプレ placeholder `NNNN-slug.md` 1
- ruff 拡張時の違反: **T201 print 205 件**（cli/ 135 + approval TTY 8 + dialogue stderr 1 + tests/scripts 61 — 全て正当なコンソール UI、core/ はゼロ）/ **I001 66 ファイル**（自動修正可）/ **B905 13**（zip strict なし。うち verification_parse.py 5）/ **B011・B017 各 1**（tests）
- 非 frozen dataclass は `core/metrics.py` の `_Tally` 1 件のみ（docstring で mutable accumulator と明示された私的クラス = 正当な例外）
- adapters 間相互 import は現状ゼロ

## 変更内容

### Commit A — `chore: widen ruff rule set (B, I, T20) and add adapter-independence contract`

**pyproject.toml**:

```toml
[tool.ruff.lint]
extend-select = ["B", "I", "T20"]

[tool.ruff.lint.per-file-ignores]
# Console UI seams — print IS the interface here (rules/python/hooks.md の
# print 警告は library code (core/, adapters ロジック) にのみ適用する)
"src/contemplative_agent/cli/**" = ["T20"]          # CLI user output
"src/contemplative_agent/adapters/moltbook/agent.py" = ["T20"]  # ADR-0012 approval-gate TTY
"src/contemplative_agent/adapters/dialogue/peer.py" = ["T20"]   # stderr progress
"tests/**" = ["T20"]
"scripts/**" = ["T20"]
```

```toml
# ADR-0015: one external adapter per agent — adapters must stay separable.
[[tool.importlinter.contracts]]
name = "Adapter independence (ADR-0015)"
type = "independence"
modules = [
    "contemplative_agent.adapters.moltbook",
    "contemplative_agent.adapters.meditation",
    "contemplative_agent.adapters.dialogue",
]
```

既存の `[tool.ruff]` コメント（「rule set 拡張は dedicated cleanup で」）は本 commit で消化されるため書き換え。

**機械修正**:
- I001: `uv run ruff check --fix`（66 ファイル、import 並べ替えのみ）
- B905 (13): **保守的ポリシー** — 意味保存の `strict=False` を既定とし、両 iterable が構成上同長（同一ソースから対で生成）と確認できる箇所のみ `strict=True`。特に `verification_parse.py` の 5 箇所は zero-wrong-answer replay gate 対象なので挙動不変（`strict=False`）とし、既存テストで確認。ルールの狙いは「今後のコードに明示的選択を強制する」ことにある
- B011: `tests/test_metrics.py:266` の `assert False` → `pytest.fail(...)`
- B017: `tests/test_llm.py:964` の blind `Exception` → 実際に上がる例外型に絞る（実装時に対象コードで確認）

### Commit B — `test: add doc-integrity gates and fix 24 broken doc links`

**リンク修正（24 件、fail ゲート導入前に修正）**:
- CHANGELOG: 0034 → `0034-withdraw-memory-evolution-and-hybrid-retrieval.md`、0035 → `0035-sunset-migration-surface-and-consolidate-artifact-extraction.md`、`../docs/` → `docs/`
- ADR-0035 / 0024 en+ja: 0028・0029・0012 の実ファイル名に retarget（`ls docs/adr/` で確認して修正）
- `core/llm.py` 参照 8 件 → `core/llm/`（package ディレクトリ）へ retarget
- 退役物 4 件（`mlx_backend.py`、`run-with-mlx.sh`）→ リンクを外して inline code + 「(retired to contemplative-agent-mlx, ADR-0070)」注記（CHANGELOG の「swept to point at this ADR」前例に倣う）
- `docs/adr/README.md` の `NNNN-slug.md` → リンクでなく inline code に（テンプレ placeholder）

**新規テスト 3 ファイル**（concern 別分割 — test_graph_integrity.py / test_packaged_assets.py の前例に従う）:

1. `tests/test_doc_links.py`（fail ゲート）
   - 事前監査で使った走査ロジックをそのまま pytest 化: repo 内全 `.md`（`.venv` / `.notes` / `dist` 除外）の相対リンクを regex 抽出し、解決先ファイルの存在を assert。失敗時は全 broken link を列挙
   - 同ファイルに ADR en↔ja 双方向ペア整合テスト: `docs/adr/NNNN-*.md` ⇔ `NNNN-*.ja.md`（README 除外、orphan ja も検出）
2. `tests/test_frozen_dataclasses.py`（fail ゲート）
   - `src/**/*.py` を `ast` で走査し、`@dataclass` / `@dataclasses.dataclass`（bare / call 両形式）で `frozen=True` の無いクラスを検出
   - **明示 allowlist** `{"core/metrics.py::_Tally"}` — 「例外は allowlist に書かれたものだけ」という機械可読な形に規約を締める。allowlist エントリには理由コメント必須
3. `tests/test_doc_stats.py`（**warning-only** — ユーザー指定）
   - `docs/CODEMAPS/INDEX.md` の Statistics 表から機械照合可能な行をパースし、表内に記載の測定コマンドと同じ方法で実測、不一致は `warnings.warn(UserWarning)` で報告して **テスト自体は常に PASS**（検出は code、更新判断は人間 — AKC Maintain）
   - 照合対象: Total .py / Test files / tests collected（`pytest --collect-only -q` subprocess、timeout 付き）/ per-package module counts / config templates。LOC は `~` 付きなので >10% 乖離のみ warn。counting 規約が曖昧な行（Core modules の「llm/ package as one row」）は実装時に doc の規約へ厳密に合わせるか対象外とする

**Doc Sync（同一 commit）**:
- `docs/CODEMAPS/INDEX.md` Statistics 表を実測値に更新（test files 56→59、collected 数、Last Updated）— 本ゲートが強制する規律をこの PR 自身が実演する
- CHANGELOG Unreleased 節に追記（リンク修正もこの commit に含まれる）

## Chain（planning.md 準拠）

- 種別: chore + test / TDD: - / Security Review: - / codex-review: -
- **Code Review: python-reviewer**（新規テスト 3 本 + src の B905 修正が対象）
- Parallel Group: [python-reviewer] のみ。Sequential: Commit A 実装 → Commit B 実装 → review → Verify → commit → push

## Verification

1. `uv run ruff check src tests scripts` PASS（新ルールセットで）
2. `uv run lint-imports` → **Contracts: 2 kept, 0 broken**
3. `uv run pytest tests/ -q` 全 PASS。INDEX.md 更新後は stats warning が**出ない**ことも確認
4. **各 fail ゲートの発火実証**（one-run-not-evidence）: (a) 一時的に bogus リンクを md に注入 → test_doc_links 赤 → revert、(b) 一時的に非 frozen dataclass を src に追加 → test_frozen 赤 → revert、(c) 一時 `docs/adr/9999-test.md` 作成 → ペア整合赤 → 削除。warning テストは INDEX.md の値を一時改変 → warning 出力確認 → revert
5. `uv run pyright` 0 errors
6. verification_parse.py の B905 修正が挙動不変であることを既存 parser テスト群の PASS で確認
7. `git status` 意図外なし → Verify 結果報告 → main 直 commit ×2 + push（push-workflow）
