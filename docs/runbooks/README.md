# Runbooks

運用 know-how の durable 置き場。「どう動かすか」「事故ったらどう復旧するか」。

## コンテンツ

<!-- `docs/runbooks/*.md`（README を除く）と下表の `*.md` 行は tests/test_doc_links.py が突き合わせる -->

| Path | 種別 | 対象 |
|---|---|---|
| `rca/` | Post-mortem | 事故 / 想定外挙動の根本原因分析（様式は [`incident-response.md`](incident-response.md) の RCA テンプレ、AAP ADR-0006 の 5 問と 1:1） |
| `silent-llm-calls.md` | 診断ガイド | pytest 遅延の silent Ollama 呼び出し検出と `tests/conftest.py` による予防 |
| `sibling-backend-conformance.md` | リリースゲート | リリース前に sibling backend の `LLMBackend` 適合を確認する（ADR-0088） |
| `release.md` | リリース手順 | タグ付きリリースを切る 10 段（検証・兄弟適合・packaging・版/DOI 整合・タグ・DOI 戻し・HF・データ版・pin）。各段に停止基準。台帳は `docs/evidence/releases.md` |
| `runtime-backup-restore.md` | 運用 / 復旧 | `$MOLTBOOK_HOME` の private mirror への backup と restore 手順 |
| `knowledge-embedding-sidecar-migration.md` | Migration guide | live store の pattern embedding を sidecar へ移す一度きりの cutover（ADR-0108） |
| `credential-rotation.md` | 運用 / 事故対応 | 鍵の全所在（7 箇所）、keychain を使わない理由、漏洩時の回転手順 |
| `constitution-amendment.md` | 手順 | 憲法改正の人間側の手順（`amend-constitution` → 単一ファイル確認 → hash 照合 → 採用。ADR-0090） |
| `model-swap.md` | チェックリスト | 生成モデル / 判断モデルを入れ替えるときに再訪する設計判断（ADR-0112 の phase separation） |
| `weekly-chain-rerun.md` | 運用 / 復旧 | 週次 chain の欠報・途中死・同一週の再実行（`--end-date`）、`.private/` の quarantine、サブスクリプション枯渇 / timeout の読み方 |
| `machine-rebuild.md` | 運用 / 復旧 | 新機・再インストール後に無人 chain を立ち上げ直す順序と各段の確認（`scripts/host_check.sh`） |
| `wind-down.md` | 終了手順 | 観察走行を終えるときの固定順序（発動条件は持たない。検討イベントは ADR-0080 追補 2026-10-24） |
| `continuity.md` | 継続性 | オーナーが動けないときに第三者がすべきこと（何もしない / GitHub archive のみ）と継承者の記録（D-P4-03-1） |
| `operator-handoff.md` | 引継ぎ | 責任者（accountable operator）交代のチェックリスト。継承者あり（B）なら archive 権限の付与と audit 1 行だけ |
| `incident-response.md` | 事故対応 | 検知 → 停止 → 版の特定 → RCA テンプレ → 公表。公開済み第三者テキストの扱い |

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
- **セットアップ guide**: 既存の `docs/CONFIGURATION.md` または README の該当節を優先

## 書くべきでないもの

- 決定そのもの → `docs/adr/`
- アーキテクチャ俯瞰 → `docs/adr/README.md`（構造は LSP / `grimp` でコードから、ADR-0102）
- 測定・実験 → `docs/evidence/`
- 途中経過メモ → `.notes/` (gitignored)
