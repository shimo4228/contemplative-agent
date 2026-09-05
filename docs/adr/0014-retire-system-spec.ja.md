# ADR-0014: system-spec.md の廃止

## ステータス

accepted

## 日付

2026-04-01

## コンテキスト

`docs/spec/system-spec.md` は外部研究者と AI エージェント向けの正式仕様書として作成された（2026-03-26、325行）。アーキテクチャ、メモリシステム、エージェント動作、セキュリティモデル、設定、先行研究、AKC マッピングの7セクションで構成。

実際には7セクション中6セクションが既存ドキュメントと重複していた:

| Spec セクション | 重複先 |
|---|---|
| §1 Architecture | README Architecture + CODEMAPS/architecture.md |
| §2 Memory System | CODEMAPS/architecture.md + core-modules.md |
| §3 Agent Behavior | CODEMAPS/moltbook-agent.md |
| §4 Security Model | README Security Model + CLAUDE.md |
| §5 Configuration | README Configuration |
| §7 AKC Mapping | CODEMAPS/architecture.md |

§6（Prior Art Mapping — メモリシステム比較表、認知アーキテクチャ対応、論文リファレンス）のみが固有の価値を持っていた。

すでに乖離も発生: README はテスト数 801、spec は 794 のまま。`context-sync` スキルも同期コストに見合わないとして spec 更新をスコープから外していた。

### なぜ仕様書が必要に見えたか

外部研究者向けに包括的な単一ドキュメントを提供したかった。README は浅すぎ、CODEMAPS はコード寄りすぎ、ADR は断片的すぎた。

### なぜ負債になったか

1. **重複メンテナンス**: アーキテクチャやセキュリティの変更ごとに3文書以上の更新が必要
2. **AI はコードを直接読める**: spec の主要読者（Claude Code）は CODEMAPS・CLAUDE.md・ソースコードを直接読む。散文での再記述は情報量ゼロ
3. **研究者は README → CODEMAPS と辿る**: 2段階で十分。3層目はナビゲーションの混乱を招く
4. **同期の失敗は静かに蓄積する**: 古い仕様書は仕様書がないよりも有害 — 人を誤導する

## 決定

> **注記（2026-09-05、[ADR-0102](./0102-retire-codemaps.ja.md)）**: 下で移動先とした CODEMAPS 自体が退役した。file-level 構造はコードから導出する（LSP / `grimp`）。三役の表（README / CODEMAPS / ADR）は README / code+LSP / ADR と読む。本 ADR が `architecture.md` に移した §6 Prior Art の内容は codemap の最終版（`ced10e2`）には残っておらず、先行研究の記録として残るのは README の Related Work と `docs/BIBLIOGRAPHY.md`。

`docs/spec/system-spec.md` および `docs/spec/` ディレクトリを削除する。

固有コンテンツ（§6 Prior Art）は `docs/CODEMAPS/architecture.md` の新セクションに移動。メモリアーキテクチャセクションの隣に配置。

ドキュメント構造は3つの役割に整理:

| ドキュメント | 役割 |
|---|---|
| **README** | What/Why（外部向け） |
| **CODEMAPS** | How/Where（コード参照 + 先行研究） |
| **ADR** | Why this way（設計判断） |

## 検討した代替案

1. **spec を残し、他のドキュメントから参照させて重複を解消** — 却下。自然な読み順（README → CODEMAPS）を逆転させ、spec が単一障害点になる
2. **spec を軽量な「システム概要」に縮小** — 却下。README がすでにその役割を果たしている。軽量な spec は冗長な README でしかない
3. **Zenodo/arxiv の補足資料として spec を維持** — 却下。必要なら README + CODEMAPS をバンドルすればよい。稀なエクスポートのために生きたドキュメントを維持する理由はない

## 結果

- アーキテクチャ・セキュリティ・メモリ変更時の同期対象が1つ減る
- 先行研究比較が CODEMAPS から発見可能になる（spec ディレクトリに埋もれない）
- 将来「仕様書を書こう」という提案があれば、この ADR を参照すること
