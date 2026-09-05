# Runbooks

運用 know-how の durable 置き場。「どう動かすか」「事故ったらどう復旧するか」。

## コンテンツ

| Path | 種別 | 対象 |
|---|---|---|
| `rca/` | Post-mortem | 事故 / 想定外挙動の根本原因分析 |
| `silent-llm-calls.md` | 診断ガイド | pytest 遅延の silent Ollama 呼び出し検出と `tests/conftest.py` による予防 |
| `sibling-backend-conformance.md` | リリースゲート | リリース前に sibling backend の `LLMBackend` 適合を確認する（ADR-0088） |

> Past migration guides (e.g. `adr-0019-migration.md`) were retired together
> with their CLI subcommands once active deployments finished migrating.
> See ADR-0035 for the sunset rationale.

## 配置ルール

- **Migration guide**: ADR と対応する運用手順。`<adr-slug>-migration.md` 形式
- **RCA**: `rca/YYYY-MM-DD-<slug>.md` 形式。再発予防が目的、ただの愚痴や状況記録ではない
- **リリースゲート**: リリース手順の特定の一点で人間が判断する検査。`<slug>-conformance.md`
  等の内容ベース命名。**手順の実体をここに置き、`~/.claude/skills/release-doi/` からは
  リンクだけ張る** — skill は git 管理外なので、そちらに手順を書くと clone 先に伝わらず
  ADR からも参照できない。判断基準（何が出たらリリースを止めるか）を必ず含める
- **Docker / セットアップ guide**: 既存の `docs/CONFIGURATION.md` または README の該当節を優先

## 書くべきでないもの

- 決定そのもの → `docs/adr/`
- アーキテクチャ俯瞰 → `docs/adr/README.md`（構造は LSP / `grimp` でコードから、ADR-0102）
- 測定・実験 → `docs/evidence/`
- 途中経過メモ → `.notes/` (gitignored)
