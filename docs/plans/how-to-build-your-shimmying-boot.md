# Contemplative Agent 研究プログラムの駆動サイクル — 正確な現状地図 (docs 作成計画)

## Context

Raft 記事（named specialists + author≠reviewer + heartbeat + shared room + 自己改善ループ）を
きっかけに、「このプロジェクトを前に進める仕組み」を組み直せないかという検討。
対話で以下が確定した:

- 対象は **Claude Code による駆動レイヤー**（エージェント本体 runtime の機能ではない）。
- **共有ワークスペース = このリポジトリ群本体**（領分別 docs + それを指す rules/CLAUDE.md）。
  herdr は pane を走らせる runtime にすぎず、Raft の channel に相当する「共有文脈」は repo が担う。
- **このセッションの成果物 = 正確な現状地図を docs として作成する**。介入設計は後段（別セッション/別 plan）。
- graph.jsonld を情報源に使うと効率がよい（concept 層の federation + AKC phase を encode 済み）。

2 回の並行調査 + graph.jsonld 精査で、当初地図の誤りを 2 点訂正した:
- ❌ 旧「dev サイクルに heartbeat が無い」→ ✅ **heartbeat は複数存在し自動化済み**。人間ゲートは
  「昇格(promotion)辺」に集中している（notes/report/findings までは自動、ADR/コード/台帳への昇格が人間）。
- ❌ 旧「weekly-report = 製品の自己内省」→ ✅ **weekly-report はバグ修正・機能改善を駆動する dev ループ**
  （ADR 0039-0043 / 0052 / 0055 / 0060 / 0061 / 0074 を実際に triggered）。

---

## 正確な現状地図（docs の中身になる本体）

研究プログラムは **単一 repo でなく、複数 repo + 外部チャネルにまたがる 9 サイクルの螺旋**。
背骨: 運用 → 内省 + 代謝 → 開発 → 結晶化 → 拡散。intake が頂点に供給する。

### マスター表

| # | サイクル | カデンス / トリガー | 自動化される脚 | 人間ゲート（昇格辺） | 主な生成物 | 住処 |
|---|---|---|---|---|---|---|
| 1 | Research intake | **毎日 05:00** `com.shimomoto.daily-research` | source 探索 → Vault ノート + graph | wiki `/ingest`、harvest 候補 → ADR/graph/コード昇格 | `daily-research/` notes, `wiki/concept/` | 別 repo `daily-research/` |
| 2 | Wiki refresh | **月 09:00** `com.shimo.wiki-refresh` | wiki 保守 | — | Obsidian Vault `wiki/` | Vault |
| 3 | Product 運用 | **6h 0/6/12/18 JST** `com.moltbook.agent` | セッション → episode log / comment-report | — | logs, reports/comment-reports | CA runtime |
| 4 | Product 代謝 (AKC) | distill 日次 / insight 週次 staged | Extract(distill) / Curate(insight) | adopt-staged（承認ゲート ADR-0012） | knowledge.json, identity/skills/rules | CA (+ data repo) |
| 5 | 週次内省 → dev | **土 09:00** `com.moltbook.weekly-analysis` | report A–E（観察のみ） | diagnosis(手動)→ F1/F2/F3 → ADR/`.notes/TASKS.md`/コード | `reports/analysis/weekly-*.md`, `-findings.md` | CA |
| 6 | 開発チェーン | 変更ごと・オンデマンド | planner→TDD→並列 reviewer(codex-review)→doc-sync→verify | commit 前 diff 承認 | code, tests, ADR, CODEMAPS | CA |
| 7 | 結晶化 → 論文 | オンデマンド | essays → position paper 起草 | deposit（人間） | **論文3本**: AKC×1 / AAP×2（全 DOI） | AKC / AAP repo |
| 8 | 拡散（発信） | オンデマンド | collect-context→article-writing→ja-to-en→substack | publish（人間） | Zenn(ja ~58) / Dev.to(en ~66) / Substack(4) | `zenn-content/` |
| 9 | 機械参照圏最適化 | 定期・オンデマンド | gap-review / citation-sync / release-doi / hf-sync | deposit / DOI 採番承認 | DOI, SWHID, HF mirror, graph 引用辺 | 全 repo |

### 共有基盤（= 記事の "shared room" の実体）

- **graph.jsonld**（concept 層）— Research Program Hub が research line を federate。AKC Phase 1–6 →
  Contemplative Agent 実装への mapping、4 公理 / 3 メモリ層 / 79 ADR / 13 Concept / 22 ExternalReference を encode。
- **CODEMAPS**（file 層）+ **docs/adr**（決定層）+ **CLAUDE.md / rules**（routing 層）。
- これらが「各エージェントが自分の領分の正しい文脈を掴む」共有面。herdr pane はこの上で走るだけ。

### 論文の内訳（確認済み）
- AKC: *Harness Alignment and Harness Drift* (Zenodo `10.5281/zenodo.20578272` + SSRN)
- AAP: *The Two-Layer Black Box* (`10.5281/zenodo.20355907`) / *Distributing Accountability, Not Capability* (`10.5281/zenodo.20353789`)

### 今回浮かんだ具体的非対称（※記録のみ。修正は今セッションでしない）
- **weekly ループ（#5）は完全配線**（自動 report → 手動 diagnosis → 人間昇格、ADR に痕跡多数）。
- **daily-research→repo ループ（#1）の昇格辺は CA では未形式化** — CA の `CLAUDE.md` に
  「Research Wiki Consultation」節が無く、wiki-harvest が owned concept を解決できず backfill 信号を返す。
  2 本の intake→dev ループが非対称になっている。

---

## 成果物: docs ファイルの仕様

- **ファイル**: `docs/CYCLES.md`（新規・単一責務。docs/ = 外部可視 durable reference）。
  既存 `DEVELOPMENT-RECORDS.md`（記録）や CODEMAPS（コード構造）とは責務が異なるため別ファイル。
- **言語**: 既定は **英語**（docs/CODEMAPS・docs/adr の agent-facing 規約に合わせる）。
  日本語がよければその旨指示で切替。
- **構成**: 上の「マスター表」+「共有基盤」+「サイクル間の螺旋（背骨）」の図（Mermaid flowchart で
  #1→#3→#5/#4→#6→#7→#8/#9 と intake 供給を表現）+「人間ゲート＝昇格辺」一覧 + 論文内訳。
- **情報源の明記**: graph.jsonld（concept/AKC phase）、各 launchd plist、weekly/daily の driver script、
  姉妹 repo の DOI。地図の各行は実資産に対応（fabrication 無し）。
- **鮮度ヘッダ**: CODEMAPS 同様、生成日と情報源コミットを stamp（後の drift 検知用）。
- **CLAUDE.md ポインター**: 作成後、`CLAUDE.md` に `docs/CYCLES.md` への 1 行ポインターを置く
  （routing は CLAUDE.md が担う原則。既存の CODEMAPS/graph 参照ブロックの近傍に配置）。
  これで `docs/CYCLES.md` と CLAUDE.md 追記が**同一 diff**に入り、Doc Sync 規約を満たす。

## 明示的に今セッションでやらないこと
- 介入（heartbeat 追加 / 責務分割 / reviewer≠author 拡張 / wiki-consultation 節の backfill）は**設計しない**。
  地図が正確に揃ったのを確認してから、別途 plan で 1 件ずつ選ぶ。

## Verification（docs 作成後）
1. マスター表の各行 ↔ 実資産の照合（`ls ~/Library/LaunchAgents/com.*`, `config/launchd/`,
   `.claude/skills/`, 姉妹 repo の CITATION.cff/.zenodo.json）。
2. Mermaid 図が artifact/README lint 相当でレンダリングされること（構文チェック）。
3. リンク整合（doc-integrity: 参照した ADR 番号・ファイルパスが実在）。
4. 人間 gate: 生成 diff をあなたが承認してから commit。
