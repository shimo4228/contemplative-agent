# Roadmap

## Status: 安定稼働フェーズ

蒸留パイプライン（分類・抽出・dedup・品質ゲート・承認ゲート）が完成し、コード側の開発は完了。今後はプロンプトチューニングと実運用による蒸留品質の改善が中心。

## Completed

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

### Phase 4: Logit 制約による出力安定化（完了）

Ollama の structured outputs (JSON schema) で dedup 判定・importance スコアリングの LLM 出力を制約。フォールバックチェーンに頼らず「そもそも壊れない」根本解決。

### Phase 5: embedding ベース検索（中止）

ADR-0011 で knowledge 直接注入を廃止したため、「大量パターンから関連性の高いものを選択的にプロンプト注入する」という前提が消失。knowledge の現用途（distill-identity の入力、insight/rules-distill の入力）はいずれも線形スキャンで十分であり、embedding 検索の導入動機がなくなった。

---

## Future Candidates

現時点では実装できないが、将来的に検討する候補。

### Meditation Adapter 卒業

瞑想結果を KnowledgeStore にフィードバックし、蒸留パイプラインに接続。現在 meditation は `results.json` に書き込むだけで AKC ループに接続されていない。

- 推定 ~150 LOC

### `_TEST_AGENT_NAMES` 外部化

`memory.py` の `_TEST_AGENT_NAMES` フロズンセットが本番コードにテスト用定数として埋め込まれている。コンストラクタ引数やコールバックで外から注入可能にする。動作変更を伴うため慎重に。

### Forbidden Pattern 検証の共通化

forbidden pattern の検証ループが5ファイル10箇所に重複。`config.py` に `contains_forbidden(text) -> bool` ヘルパーを追加し、全箇所から呼ぶ。影響範囲が大きいため安定稼働中は見送り。

---

## Not Planned

以下は調査済みだが現時点では採用しない。

| 項目 | 理由 |
|------|------|
| サブモルト自動選択 | 活動場所はエージェントの経験蓄積の方向を決定する重大判断。ユーザーが domain.json で選択する現設計が適切 |
| AKC サイクル分析 | 個別コマンド（insight, rules-distill 等）の出力で事足りる。複数エージェント比較実験を始めたときに再検討 |
| Multi-Agent Debate 蒸留 | qwen3.5:9b 単体では非推奨（ICLR 2025: 小型モデルの MAD は壊滅的） |
| セッション中のメモリ更新 | 意図的な設計判断（qwen3.5:9b の function call 能力の制約） |
| ReAct 自動タスク最適化 | SNS エージェントにはオーバースペック |

---

## Done

### Dedup スケーラビリティ + パース耐性 (2026-03-31)

`effective_importance` を dedup 比較対象のフィルタリングに適用（`DEDUP_IMPORTANCE_FLOOR=0.05`）。長期間使われないパターンは比較から自然に除外。`_parse_dedup_decisions()` にコードフェンス除去 + 正規表現抽出を追加し、qwen3.5:9b の出力を安定パース。

### コーディングエージェント用メンテナンススキル (2026-03-29)

`integrations/` に `-ca` サフィックス付き5スキルを追加。Opus クラスのコーディングエージェントが knowledge.json を直接読み、ホリスティック判断で skills/rules/identity/constitution を生成・更新する。9B 多段パイプラインの代替。distill（episodes → knowledge）はセキュリティ上コーディングエージェントに委任しない（ADR-0007）。Claude Code, Cursor, OpenAI Codex の3エージェント対応。各エージェント用インストールスクリプト付き。

### Glossary (2026-03-29)

`docs/glossary.md` に用語定義（14項目）と先行研究対応表（7論文）を追加。外部研究者・AI エージェント向けの単一参照点。

### Devlog 分離 (2026-03-29)

記事は外部（dev.to / Zenn）に公開済み。リポジトリ内に devlog ファイルは存在しないため、分離は既に達成済みと判断。README のリンクは現状維持。

### Tabula-Rasa テンプレート (2026-03-29)

skills/rules/identity なし、constitution のみの最小テンプレート（`tabula-rasa`）。contemplative との対照実験用。経験だけで全て獲得していく素寒貧スタート。

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

*Last updated: 2026-03-30*
