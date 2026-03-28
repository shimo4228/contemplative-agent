# Roadmap

残タスクと将来計画の一覧。優先度順。

## Next

### コーディングエージェント用メンテナンススキル

insight, rules-distill, distill-identity, amend-constitution の処理をコーディングエージェント（Claude Code 等）が直接実行するスキルを作成。9B モデルの多段パイプラインではなく、Opus クラスの推論能力で knowledge.json を読み、skills/rules/identity/constitution を生成・更新する。`--stage` フラグは「オーケストレーターなしの自律運用」用に残す。

**distill（エピソード → knowledge）はコーディングエージェントに委任してはならない。** エピソードログはプロンプトインジェクション経路（ADR-0007）。ツール権限を持つコーディングエージェントが生ログを読むと、注入されたプロンプトが実行される。distill は必ずツール権限なしのローカル LLM（9B）が処理し、サニタイズ済み knowledge.json を出力する。コーディングエージェントは knowledge.json から先のみ操作可能。

### Dedup スケーラビリティ

パターン数が増えると dedup の品質・性能が劣化する問題。現在は全既存パターンと SequenceMatcher で総当たり比較しており、グレーゾーン（ratio 0.3-0.7）は LLM 判定に回される。パターン数が数百を超えると:

- 比較回数が O(N) で増加（新パターン1件あたり全既存と比較）
- UNCERTAIN 判定が増え、LLM 呼び出しが増加
- 9B モデルの semantic dedup 判定精度が低下するリスク

本質的な解決は **importance 減衰による忘却**。`effective_importance = base × 0.95^days` は既に実装済みだが、現在は読み出し時の優先順位づけにしか使われていない。これを dedup にも適用する:

- effective_importance が閾値以下のパターン → dedup 比較対象から除外
- 重要なパターンは減衰が遅い（base が高い）ため長く残る
- 使われないパターンは自然に「忘れられる」
- 新しい仕組み不要。既存の減衰メカニズムの適用範囲拡張

補助的な対応:
- カテゴリ内のみ比較（既に部分的に実装済み）

### Importance Scoring 安定化

constitutional パターンの importance scoring で LLM が `{"scores": [...]}` の JSON を返せず、デフォルト 0.5 にフォールバックする問題。uncategorized でも散発的に発生。`_parse_importance_scores()` のパース失敗。

- 原因: 9B モデルが constitutional パターンに対して安定した JSON を出力できない
- 影響: 現時点では限定的（amend-constitution は importance を使わない、dedup は max を取る）
- 対応案: コードフェンス除去（026a26c と同様）、2段階化（自由記述→JSON整形）、またはプロンプト改善
- 推定 ~50-100 LOC

### キャラクターテンプレート一式

identity, skills, rules, constitution の初期セットを 10 種類程度作成。`config/templates/` に格納し、`init` コマンドでテンプレート選択可能にする。Fallout の Perk/Trait システムのように、初期構成でエージェントの「性格」が決まり、SNS 活動を通じて経験を蒸留してレベルアップしていく。

テンプレート案:
- Contemplative (現行デフォルト: CCAI 四公理)
- Debater (論争好き、弁証法的)
- Curator (情報収集・整理特化)
- Empath (感情共鳴重視)
- Analyst (データ駆動、論理重視)
- Stoic (ストア哲学ベース)
- Trickster (遊び心、逆説的)
- Mentor (教育・指導特化)
- Explorer (未知への好奇心)
- Minimalist (簡潔・本質主義)

各テンプレートは:
- `identity.md` — 人格定義
- `constitution/*.md` — 倫理フレームワーク
- `skills/*.md` — 初期スキル (2-3 個)
- `rules/*.md` — 初期ルール (2-3 個)

### 承認監査ログ（Audit Log）

承認ゲートの判断（承認/拒否、コマンド、タイムスタンプ、コンテンツハッシュ）を `logs/audit.jsonl` に記録。研究プロジェクトとして、人間-エージェント間の意思決定境界のデータが価値を持つ。

- 推定 ~100 LOC

### Meditation Adapter 卒業

瞑想結果を KnowledgeStore にフィードバックし、蒸留パイプラインに接続。現在 meditation は `results.json` に書き込むだけで AKC ループに接続されていない。

- 推定 ~150 LOC

### Glossary（用語集）

`docs/glossary.md` に用語定義と先行研究との対応表。system-spec.md を読む外部研究者向け。

### AKC サイクル分析

episodes → knowledge → skills/rules/identity/constitution の変換率・タイムラインを可視化する `report --akc` モード。

- 推定 ~300 LOC

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

### Stocktake プロンプトロード修正 + マージ機能 (2026-03-28)

skill-stocktake / rules-stocktake が常に空レスポンスだった原因は `load_prompt_templates()` にプロンプトのロード漏れ。修正後、重複検出が正常動作。さらに `merge_group()` を追加し、検出された重複グループを LLM でマージして承認ゲート経由で保存。`_write_staged()` で古い staged ファイルのクリアも実装。776 tests passing。

### rules-distill 入力ソース修正 (2026-03-28)

rules-distill の入力を KnowledgeStore から skills/*.md に変更。YAML frontmatter をスキップして Markdown 本文を抽出。incremental モードは skill ファイルの mtime で判定。MIN_SKILLS_REQUIRED=3、BATCH_SIZE=10。739 tests passing。

### ADR-0012: 人間承認ゲート実装 (2026-03-26)

行動変更コマンド（insight, rules-distill, distill-identity, amend-constitution）に書き込み前の承認ゲートを導入。core 関数は生成のみ行い、ファイル書き込みは cli.py が承認後に実行。`--dry-run` は4コマンドで非推奨化（distill は従来通り）。724 tests passing。

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

*Last updated: 2026-03-28*
