# Roadmap

残タスクと将来計画の一覧。優先度順。

## Next

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

### Importance Scoring 安定化 (DONE)

コードフェンス除去、カンマ区切り整数フォールバック、パース失敗時のログ出力、プロンプトに few-shot example 追加。

### キャラクターテンプレート一式 (DONE)

identity, skills, rules, constitution の初期セットを 10 種類作成済み。`config/templates/{name}/` に格納。`init` コマンドでテンプレート選択可能にするのは次のステップ。Fallout の Perk/Trait システムのように、初期構成でエージェントの「性格」が決まり、SNS 活動を通じて経験を蒸留してレベルアップしていく。

**倫理研究系 (5種)** — 異なる倫理フレームワークの比較実験:
- Contemplative (デフォルト: CCAI 四公理, Laukkonen et al. 2025)
- Stoic (ストア哲学: 四徳 + 制御の二分法)
- Utilitarian (功利主義: 最大幸福原則)
- Deontologist (義務論: カント的定言命法)
- Care Ethicist (ケアの倫理: ギリガン)

**ゲーム系 (5種)** — RPG パーティ的なキャラクター:
- Berserker (前衛・即レス脳筋)
- Bard (語り部・比喩とアナロジー)
- Rogue (斥候・裏読み懐疑)
- Jester (道化・核心を突くボケ)
- Doomsayer (預言者・最悪シナリオ)

各テンプレートは:
- `identity.md` — 人格定義 (SNS プロフィール)
- `constitution/*.md` — 倫理フレームワーク (4カテゴリ × 2条項)
- `skills/*.md` — 初期スキル (2 個)
- `rules/*.md` — 初期ルール (2 個)

**残タスク**: なし（`init --template <name>` 実装済み）

### 承認監査ログ (DONE)

承認ゲートの判断（承認/拒否、コマンド、タイムスタンプ、コンテンツハッシュ）を `logs/audit.jsonl` に記録。4コマンド（insight, rules-distill, distill-identity, amend-constitution）に統合。

### Meditation Adapter 卒業

瞑想結果を KnowledgeStore にフィードバックし、蒸留パイプラインに接続。現在 meditation は `results.json` に書き込むだけで AKC ループに接続されていない。

- 推定 ~150 LOC

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

## Not Planned

以下は調査済みだが現時点では採用しない。

| 項目 | 理由 |
|------|------|
| Multi-Agent Debate 蒸留 | qwen3.5:9b 単体では非推奨（ICLR 2025: 小型モデルの MAD は壊滅的） |
| セッション中のメモリ更新 | 意図的な設計判断（qwen3.5:9b の function call 能力の制約） |
| ReAct 自動タスク最適化 | SNS エージェントにはオーバースペック |

---

## Done

### コーディングエージェント用メンテナンススキル (2026-03-29)

`.claude/skills/` に `-ca` サフィックス付き5スキルを追加。Opus クラスのコーディングエージェントが knowledge.json を直接読み、ホリスティック判断で skills/rules/identity/constitution を生成・更新する。9B 多段パイプラインの代替。distill（episodes → knowledge）はセキュリティ上コーディングエージェントに委任しない（ADR-0007）。

- insight-ca, skill-stocktake-ca, rules-distill-ca, amend-constitution-ca, distill-identity-ca
- README（英語・日本語）、CONFIGURATION（英語・日本語）に使い方を記載

### Glossary (2026-03-29)

`docs/glossary.md` に用語定義（14項目）と先行研究対応表（7論文）を追加。外部研究者・AI エージェント向けの単一参照点。

### Devlog 分離 (2026-03-29)

記事は外部（dev.to / Zenn）に公開済み。リポジトリ内に devlog ファイルは存在しないため、分離は既に達成済みと判断。README のリンクは現状維持。

### v1.1.0: init --template, importance scoring, audit log (2026-03-29)

`init --template <name>` でテンプレート選択（10種）、identity + constitution + skills + rules を全コピー。importance scoring にコードフェンス除去 + カンマ区切りフォールバック。承認ゲートに audit.jsonl ログ追加。789 tests passing。

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

*Last updated: 2026-03-29*
