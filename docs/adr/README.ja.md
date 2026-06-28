# Architecture Decision Records

このプロジェクトの主要な設計判断を記録する。

## 一覧

| ADR | タイトル | Status | Date |
|-----|---------|--------|------|
| [0001](0001-core-adapter-separation.md) | Core/Adapter 分離 | accepted | 2026-03-10 |
| [0002](0002-paper-faithful-ccai.md) | 論文準拠 CCAI 適用 | accepted | 2026-03-12 |
| [0003](0003-config-directory-design.md) | Config ディレクトリ設計 | accepted | 2026-03-12 |
| [0004](0004-three-layer-memory.md) | 3層メモリアーキテクチャ `[AKC: Extract/Curate/Promote]` | accepted | 2026-03-17 |
| [0005](0005-session-context-refactoring.md) | SessionContext リファクタリング | accepted | 2026-03-14 |
| [0006](0006-docker-network-isolation.md) | Docker ネットワーク分離 | superseded-by 0070 | 2026-03-14 |
| [0007](0007-security-boundary-model.md) | セキュリティ境界モデル | accepted | 2026-03-12 |
| [0008](0008-two-stage-distill-pipeline.md) | 2段階蒸留パイプライン `[AKC: Extract]` | accepted | 2026-03-22 |
| [0009](0009-importance-score.md) | KnowledgeStore Importance Score `[AKC: Extract/Quality Gate]` | accepted | 2026-03-24 |
| [0010](0010-research-data-sync.md) | 研究データ同期 | accepted | 2026-03-25 |
| [0011](0011-knowledge-injection-to-skills.md) | Knowledge 直接注入の廃止 → Skills 経由 `[AKC: Curate]` | accepted | 2026-03-26 |
| [0012](0012-human-approval-gate.md) | 行動変更コマンドの人間承認ゲート `[AKC: Curate/Promote]` | accepted | 2026-03-26 |
| [0013](0013-shelve-coding-agent-skills.ja.md) | コーディングエージェントスキルのお蔵入り `[AKC: Curate/Promote]` | accepted | 2026-03-28 |
| [0014](0014-retire-system-spec.ja.md) | system-spec.md の廃止 `[AKC: Maintain]` | accepted | 2026-04-01 |
| [0015](0015-one-external-adapter-per-agent.ja.md) | 1エージェント1外部アダプタ原則 | accepted | 2026-04-08 |
| [0016](0016-insight-narrow-stocktake-broad.ja.md) | insight = narrow generator / skill-stocktake = broad consolidator `[AKC: Extract/Curate]` | accepted | 2026-04-11 |
| [0017](0017-yogacara-eight-consciousness-frame.ja.md) | 唯識八識モデルを設計の枠組みとする | accepted | 2026-04-11 |
| [0018](0018-per-caller-num-predict-embedding-stocktake.ja.md) | caller 別 num_predict + embedding-only stocktake | accepted | 2026-04-15 |
| [0019](0019-discrete-categories-to-embedding-views.ja.md) | 離散カテゴリ廃止 → Embedding + Views `[AKC: Promote]` | accepted | 2026-04-15 |
| [0020](0020-pivot-snapshots-for-replayability.ja.md) | Pivot スナップショットで再現可能性確保 `[AKC: Curate]` | accepted | 2026-04-16 |
| [0021](0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md) | Pattern スキーマ拡張 — Provenance / Bitemporal / Forgetting / Feedback | partially-superseded-by 0028, 0029, 0051 | 2026-04-16 |
| [0022](0022-memory-evolution-and-hybrid-retrieval.ja.md) | Memory Evolution + Hybrid Retrieval (BM25) | withdrawn-by 0034 | 2026-04-16 |
| [0023](0023-skill-as-memory-loop.ja.md) | Skill-as-Memory ループ — Router / Usage Log / Reflective Write | superseded-by 0036 | 2026-04-16 |
| [0024](0024-identity-block-separation.ja.md) | Identity Block Separation — Frontmatter で addressing する persona ブロック | proposed | 2026-04-16 |
| [0025](0025-identity-history-and-migrate-cli.ja.md) | Identity History ログ配線 + migrate-identity CLI | proposed | 2026-04-16 |
| [0028](0028-retire-pattern-level-forgetting-feedback.ja.md) | pattern 層の forgetting と feedback を撤回 — 記憶動的層は skill 層にある | proposed | 2026-04-18 |
| [0029](0029-retire-dormant-provenance-elements.ja.md) | dormant な provenance 要素を撤回 — `user_input` / `external_post` / `sanitized` | accepted | 2026-04-18 |
| [0030](0030-withdraw-identity-blocks.ja.md) | Identity Block 分離と History 配線の撤回 — Single Responsibility | accepted — ADR-0024 と ADR-0025 を supersede | 2026-04-18 |
| [0031](0031-classification-as-query.ja.md) | Classification as Query — 自己改善メモリの substrate 原則 | accepted | 2026-04-27 |
| [0032](0032-runtime-agent-stance.ja.md) | Stance — Contemplative Agent はランタイムエージェントである | withdrawn — contemplative axioms (ADR-0002) との tension | 2026-04-27 |
| [0033](0033-aap-quadrant-lens-usage-note.ja.md) | Note — AAP の 4 象限レンズを usage description として借用 | accepted (note) | 2026-05-01 |
| [0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.ja.md) | Memory Evolution と BM25 Hybrid Retrieval の撤回 — コストに対し効果が見えない | accepted — ADR-0022 を supersede | 2026-05-05 |
| [0035](0035-sunset-migration-surface-and-consolidate-artifact-extraction.ja.md) | ADR-0019 Migration Surface の sunset と artifact extraction の統合 | accepted | 2026-05-05 |
| [0036](0036-sunset-skill-as-memory-loop.ja.md) | Skill-as-Memory ループの sunset — Router / Usage Log / Reflect の撤回 | accepted — ADR-0023 を supersede | 2026-05-05 |
| [0037](0037-memory-subsystem-yogacara-convergence.ja.md) | メモリ subsystem は唯識フレームに収束した — 論文借用機構の退役 | accepted | 2026-05-05 |
| [0038](0038-moment-of-recognition-distill.ja.md) | Distill の観察対象に moments of recognition を再導入する `[AKC: Extract]` | accepted | 2026-05-13 |
| [0039](0039-novelty-score-lagrangian-self-post-gate.ja.md) | self-post gate を連続値 novelty スコア + rate-deficit Lagrangian に置換 | proposed | 2026-05-19 |
| [0040](0040-separate-code-level-findings.ja.md) | 週次自己内省レポートからのコード診断 findings の分離 | accepted | 2026-05-19 |
| [0041](0041-engagement-gradient-asymmetry-in-self-post-prompt.ja.md) | self-post prompt の engagement gradient 非対称を修復する | proposed | 2026-05-19 |
| [0042](0042-explicit-truncation-contract-for-untrusted-wrapper.ja.md) | `wrap_untrusted_content` の truncation を明示的契約に変える | accepted | 2026-05-20 |
| [0043](0043-per-post-seeding-for-self-post-generation.ja.md) | self-post 生成への peer post 直接シーディング | proposed | 2026-05-21 |
| [0044](0044-remove-topic-keywords.ja.md) | `topic_keywords` の全面削除 | accepted | 2026-05-23 |
| [0045](0045-pre-action-internal-note.ja.md) | エピソード層での pre-action `internal_note` 記録（ADR-0038 の Gap 2 を閉じる） | accepted | 2026-05-25 |
| [0046](0046-stocktake-llm-grouping-over-embedding-clustering.ja.md) | Stocktake の重複検出 — embedding クラスタリングではなく LLM グルーピング | accepted | 2026-05-30 |
| [0047](0047-comment-sampling-temperature.ja.md) | 外向きコメント生成のサンプリング温度引き上げ | accepted | 2026-05-30 |
| [0048](0048-trigger-altitude-skill-lifecycle.ja.md) | スキルライフサイクル全体のトリガー高度化 | accepted | 2026-06-02 |
| [0049](0049-meditation-active-inference-fidelity-and-deferral.ja.md) | 瞑想アダプタ — Beautiful Loop 忠実性監査と忠実な再実装の保留 | accepted | 2026-06-03 |
| [0050](0050-epistemic-taxonomy-and-approval-lineage.ja.md) | Epistemic taxonomy と承認系譜 — steering なしの可観測性 | partially-superseded-by 0051 | 2026-06-05 |
| [0051](0051-retire-trust-weighting.ja.md) | trust 重みの全廃 — 純 cosine 検索と bitemporal のみの生死判定 | accepted | 2026-06-05 |
| [0052](0052-retire-session-insight.ja.md) | セッション洞察生成の退役 — identity が承認済み継続性チャネルである | accepted | 2026-06-05 |
| [0053](0053-importance-encoding-time-significance.ja.md) | 観測時の手応えとしての importance — 三つの判断時点と再観察による昇格 | accepted (amended 2026-06-06) | 2026-06-06 |
| [0054](0054-externalize-llm-instruction-text-to-prompts.ja.md) | LLM 指示テキストを `config/prompts/` へ外出しし、injection 境界にはハードコードの fallback を持たせる | accepted | 2026-06-09 |
| [0055](0055-counterparty-identity-by-author-name.ja.md) | author name による counterparty 識別と activity/report スキーマの統一 | accepted | 2026-06-15 |
| [0056](0056-retire-importance-llm-scoring.ja.md) | distill 時の importance LLM 採点を撤去 — 抽出重みは純粋な time decay に | accepted | 2026-06-17 |
| [0057](0057-identity-from-self-reflection-corpus-alone.ja.md) | アイデンティティを self-reflection コーパスのみから蒸留する — 前アイデンティティの種と冗長な公理注入を外す `[AKC: Promote]` | accepted | 2026-06-20 |
| [0058](0058-value-injection-at-action-time.ja.md) | value 層の注入は「行動時」に属し、「蒸留時」には属さない `[AKC: Extract/Curate/Promote]` | accepted | 2026-06-20 |
| [0059](0059-remove-dead-reply-history.ja.md) | 死んでいた reply 履歴機構の撤去 | accepted | 2026-06-22 |
| [0060](0060-per-episode-grounded-distill.ja.md) | エピソード単位の grounded distill — バッチ抽出 + noise gate を「engagement エピソード 1 件 = grounded な LLM 1 コール」に置換 | accepted | 2026-06-23 |
| [0061](0061-action-time-untrusted-cap-at-platform-limits.ja.md) | action 時 untrusted 入力 cap を platform field 上限に統一; 内省ノートは全文を読む | accepted | 2026-06-23 |
| [0062](0062-create-time-verification-handshake.ja.md) | 作成時コンテンツ検証ハンドシェイク（LLM/コード併用ソルバ）と、可視化を条件とする記録ゲート | accepted | 2026-06-26 |
| [0063](0063-novelty-gate-verified-only-comparison.ja.md) | NoveltyGate の比較対象を verified（可視）投稿のみにスコープする | accepted | 2026-06-26 |
| [0064](0064-mlx-generation-backend.ja.md) | Apple Silicon で生成を host-local の mlx_lm.server 経由にする | superseded-by 0070 | 2026-06-27 |
| [0065](0065-mlx-ondemand-launchd-and-telemetry-model-contract.ja.md) | mlx_lm.server を launchd のオンデマンドジョブとして配線し、LLM テレメトリに served-model-id 契約を課す | partially-superseded-by 0067/0070 | 2026-06-27 |
| [0066](0066-backend-aware-context-budget-guard.ja.md) | `LLMBackend.context_window` 契約による backend-aware なコンテキスト予算ガード | accepted | 2026-06-27 |
| [0067](0067-keep-ollama-for-unattended-production.ja.md) | 本番生成バックエンドを Ollama に固定する — 16GB Apple Silicon の無人連続運用では mlx_lm.server は不適 | accepted — partially-supersedes 0065 | 2026-06-28 |
| [0068](0068-per-call-think-flag-and-thinking-trace-capture.md) | per-call の think フラグと推論トレースのエピソードログ保存 | accepted | 2026-06-28 |
| [0069](0069-gemma-production-model-and-think-on-value-layer-pipelines.md) | gemma4:e4b を本番生成モデルに採用し、値層パイプラインを think-ON で実行 | accepted | 2026-06-28 |
| [0070](0070-retire-mlx-to-sibling-repo-and-remove-docker.md) | MLX backend を sibling repo へ退役し Docker を main から削除 | accepted | 2026-06-28 |

## ADR の種別

このプロジェクトの ADR は 2 種類に分かれ、編集ルールが異なる:

**問題解決 ADR (emergent)**
具体的な課題に触発された反応的な設計判断を記録する。この index に載っている ADR の大半はこの種別。同じ問題に対するより良い解が見つかれば、後続の ADR で上書き (supersede) できる。

例: ADR-0005 (SessionContext リファクタリング)、ADR-0008 (2 段階蒸留パイプライン)、ADR-0009 (importance score)、ADR-0016 (insight narrow / stocktake broad)。

**世界観 ADR (axiomatic)**
プロジェクトが最初から作動している mental model や哲学的フレームを記録する。これらは反応的ではない — **問題解決 ADR がそもそも定式化できる前提** として機能する。世界観 ADR を変えることはバグ修正とは違う、プロジェクトのアイデンティティを変更する行為であり、別レベルの判断を要する。

例: ADR-0002 (論文準拠 CCAI 適用)、ADR-0007 (セキュリティ境界モデル)、ADR-0017 (唯識八識モデル)。

**判定のヒント**: その ADR が「同じ問題を抱えた別プロジェクトでも違う形で書かれうる」なら問題解決 ADR。その ADR が「プロジェクトの問題がそもそも読み取れるようになるための枠組み」を記述するなら世界観 ADR。世界観 ADR は下流を持たない (何かの結果ではない)、問題解決 ADR は (たとえ名指されていなくても) 世界観の下流にある。

## テンプレート

新しい ADR を追加する際は以下のフォーマットに従う:

```markdown
# ADR-NNNN: タイトル

## Status
accepted / superseded by ADR-XXXX / deprecated

## Date
YYYY-MM-DD

## Context
何が問題だったか

## Decision
何を決めたか

## Alternatives Considered
却下した案とその理由

## Consequences
この判断の結果どうなったか
```

## 運用ルール

- 番号は連番（0001〜）、時系列順
- 既存 ADR の変更は新 ADR で supersede する（上書きしない）
- 小さな判断は記録不要。アーキテクチャ・データモデル・セキュリティに影響する判断のみ
- `/sync-context` で ADR index とファイルの整合性をチェックできる
