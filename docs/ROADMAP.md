# Roadmap

残タスクと将来計画の一覧。優先度順。

## In Progress

### Config ランタイム分離

`config/` がプロジェクトテンプレート（git 管理）とランタイムデータ（ユーザー固有）を混在させている。`git clone` した新規ユーザーが既存の knowledge.json や identity.md を持ってしまう問題。

| 分類 | ファイル | あるべき場所 |
|------|---------|-------------|
| テンプレート（git） | `prompts/`, `constitution/`, `templates/`, `domain.json` | `config/`（現状維持） |
| ランタイム（ユーザー固有） | `knowledge.json`, `identity.md`, `skills/`, `rules/`, `history/` | `~/.config/moltbook/`（MOLTBOOK_HOME） |

**前提条件**: なし
**影響範囲**: `MOLTBOOK_HOME` パス参照、`init` コマンド、Docker マウント、テスト

---

## Next

### LLM 関数リネーム

名前と実態が乖離している関数を修正する。機能変更なし。

| 現在 | 新しい名前 | 理由 |
|------|-----------|------|
| `_load_identity()` | `_build_system_prompt()` | identity + constitution + skills + rules を組み立てている |
| `get_rules_system_prompt()` | `get_distill_system_prompt()` | distill 系の system prompt。rules は含まない |

**影響範囲**: `core/llm.py`（定義）、`core/distill.py`（呼び出し）、テスト
**詳細**: [memory: project_llm_rename.md](../memory-notes/project_llm_rename.md) ※Claude Code メモリに記録済み

---

## Memory Architecture Evolution

[docs/research/memory-evolution-report.md](research/memory-evolution-report.md) に詳細な調査結果とギャップ分析がある。以下はそこから抽出した実装ロードマップ。

### Phase 1: メタデータ基盤（実装済み）

importance スコア + 時間減衰 + 重複排除。ADR-0008, ADR-0009 として記録済み。

### Phase 2: 蒸留品質ゲート強化

重複・低品質パターンの蓄積を防止する。

- Stage 2 の後に品質判定ステップ追加: ADD / UPDATE / SKIP の3択
- 既存 top-10 類似パターンとの比較（SequenceMatcher）
- UPDATE の場合、既存パターンの importance をブースト

**前提条件**: Phase 1（完了済み）
**ソース**: Mem0 の ADD/UPDATE/DELETE ゲート

### Phase 3: 選択的ロード

セッションのタスクに関連するパターンだけをプロンプトに注入する。

- パターンに keywords フィールドを追加（蒸留時に LLM が生成）
- キーワードマッチ + importance でスコアリング → top-30 を注入
- 将来的に embedding 検索に置換可能な interface にしておく

**前提条件**: Phase 2
**ソース**: A-MEM の Zettelkasten 式、Generative Agents の relevance スコア

### Phase 4: embedding ベース検索（パターン数 500+ で検討）

- all-minilm-l6-v2 で embedding → cosine similarity で top-K
- 依存追加（sentence-transformers or onnxruntime）の判断が必要

---

## Repository Structure

Copilot との議論で出た、リポジトリ構造の最適化案。

### Glossary（用語集）

AI が用語理解に悩まないようにグロッサリーを追加する。

- `docs/glossary.md` または `spec/glossary.md`
- constitution, rules, skills, identity, knowledge, episode log 等の定義
- 先行研究の用語との対応表（Generative Agents, MemGPT, A-MEM）

### Devlog 分離（検討中）

dev.to 記事の元原稿を別リポジトリに分離し、メインリポジトリをクリーンに保つ案。

- Main = 概念・コード・実装（一次情報、DOI 付き）
- Devlog = 思考の流れ・歴史（補助情報）
- AI にとって「一次情報」と「二次情報」の分離が意味クラスターとして明確になる

---

## Not Planned

以下は調査済みだが現時点では採用しない。

| 項目 | 理由 |
|------|------|
| Multi-Agent Debate 蒸留 | qwen3.5:9b 単体では非推奨（ICLR 2025: 小型モデルの MAD は壊滅的） |
| セッション中のメモリ更新 | 意図的な設計判断（qwen3.5:9b の function call 能力の制約） |
| ReAct 自動タスク最適化 | SNS エージェントにはオーバースペック |

---

*Last updated: 2026-03-25*
