# Roadmap

残タスクと将来計画の一覧。優先度順。

## Next

### ADR-0012: 人間承認ゲート実装

行動変更コマンド（insight, rules-distill, distill-identity, amend-constitution）に書き込み前の承認ステップを追加。`--dry-run` は distill 以外で廃止。詳細は [ADR-0012](adr/0012-human-approval-gate.md)。

---

## Memory Architecture Evolution

[docs/research/memory-evolution-report.md](research/memory-evolution-report.md) に詳細な調査結果とギャップ分析がある。以下はそこから抽出した実装ロードマップ。

### Phase 1: メタデータ基盤（実装済み）

importance スコア + 時間減衰 + 重複排除。ADR-0008, ADR-0009 として記録済み。

### Phase 2: 蒸留品質ゲート強化（実装済み）

重複・低品質パターンの蓄積を防止する。SequenceMatcher のグレーゾーン（ratio 0.3-0.7）を LLM に判定させる2層構造。

- `_dedup_patterns()`: SequenceMatcher で SKIP/UPDATE/ADD/UNCERTAIN の4分類
- `_llm_quality_gate()`: UNCERTAIN のみバッチ LLM 判定（ADD/UPDATE/SKIP）
- LLM 失敗時は全て ADD にフォールバック（safe default）

**ソース**: Mem0 の ADD/UPDATE/DELETE ゲート

### Phase 3: エピソード分類 + Knowledge 注入廃止（実装済み）

蒸留前の分類ステップ（Step 0）と Knowledge 直接注入の廃止。

- Step 0: LLM でエピソードを3カテゴリに分類（constitutional, noise, uncategorized）
- カテゴリ別に蒸留（同カテゴリ内 dedup）
- noise は蒸留対象から除外（明示的忘却）
- KnowledgeStore に category フィールド追加
- Knowledge 直接注入を廃止 → skills 経由のみ (ADR-0011)
- insight / rules-distill は uncategorized パターンのみ対象

**設計メモ**: [docs/research/episode-classification-distill.md](research/episode-classification-distill.md)

### Phase 4: embedding ベース検索（中止）

ADR-0011 で knowledge 直接注入を廃止したため、「大量パターンから関連性の高いものを選択的にプロンプト注入する」という前提が消失。knowledge の現用途（distill-identity の入力、insight/rules-distill の入力）はいずれも線形スキャンで十分であり、embedding 検索の導入動機がなくなった。

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

## Done

### LLM 関数リネーム (2026-03-25)

`_load_identity()` → `_build_system_prompt()`、`get_rules_system_prompt()` → `get_distill_system_prompt()` にリネーム。機能変更なし。

### Memory Phase 2: LLM 品質ゲート (2026-03-26)

`_dedup_patterns()` に UNCERTAIN 分類を追加し、`_llm_quality_gate()` で意味的重複を LLM ���定。697 tests passing。

### Memory Phase 3: エピソード分類 + Knowledge 注入廃止 (2026-03-26)

Step 0 で LLM がエピソードを3カテゴリ（constitutional / noise / uncategorized）に分類。noise は蒸留から除外（明示的忘却）、constitutional は独立パスで保護。Knowledge 直接注入を廃止し、行動への影響は skills 経由のみに (ADR-0011)。insight / rules-distill は uncategorized のみ対象。720 tests passing。

### amend-constitution コマンド (2026-03-26)

蓄積された constitutional パターンから constitution の改正案を LLM に起草させるコマンド。憲法フィードバックループを閉じる。core/constitution.py に実装。730 tests passing。

### Config ランタイム分離 (2026-03-25)

`config/` をテンプレート専用（prompts, templates, domain.json）に整理。ランタイムデータ（identity, knowledge, constitution, skills, rules, history, launchd, meditation）は `MOLTBOOK_HOME` に移動。`init` コマンドで constitution デフォルトを自動コピー。

---

*Last updated: 2026-03-26*
