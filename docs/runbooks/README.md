# Runbooks

運用 know-how の durable 置き場。「どう動かすか」「事故ったらどう復旧するか」。

## コンテンツ

| Path | 種別 | 対象 |
|---|---|---|
| `rca/` | Post-mortem | 事故 / 想定外挙動の根本原因分析 |
| `silent-llm-calls.md` | 診断ガイド | pytest 遅延の silent Ollama 呼び出し検出と `tests/conftest.py` による予防 |

> Past migration guides (e.g. `adr-0019-migration.md`) were retired together
> with their CLI subcommands once active deployments finished migrating.
> See ADR-0035 for the sunset rationale.

## 配置ルール

- **Migration guide**: ADR と対応する運用手順。`<adr-slug>-migration.md` 形式
- **RCA**: `rca/YYYY-MM-DD-<slug>.md` 形式。再発予防が目的、ただの愚痴や状況記録ではない
- **Docker / セットアップ guide**: 既存の `docs/CONFIGURATION.md` または README の該当節を優先

## 書くべきでないもの

- 決定そのもの → `docs/adr/`
- アーキテクチャ俯瞰 → `docs/CODEMAPS/`
- 測定・実験 → `docs/evidence/`
- 途中経過メモ → `.notes/` (gitignored)
