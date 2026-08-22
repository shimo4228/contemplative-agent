# Architecture Decision Records

このプロジェクトの主要な設計判断を記録する。

## 一覧

| ADR | タイトル | Status | Date |
|-----|---------|--------|------|
| [0001](0001-core-adapter-separation.ja.md) | Core/Adapter 分離 | accepted | 2026-03-10 |
| [0002](0002-paper-faithful-ccai.ja.md) | 論文準拠 CCAI 適用 | accepted | 2026-03-12 |
| [0003](0003-config-directory-design.ja.md) | Config ディレクトリ設計 | accepted | 2026-03-12 |
| [0004](0004-three-layer-memory.ja.md) | 3層メモリアーキテクチャ `[AKC: Extract/Curate/Promote]` | accepted | 2026-03-17 |
| [0005](0005-session-context-refactoring.ja.md) | SessionContext リファクタリング | accepted | 2026-03-14 |
| [0006](0006-docker-network-isolation.ja.md) | Docker ネットワーク分離 | superseded-by 0070 | 2026-03-14 |
| [0007](0007-security-boundary-model.ja.md) | セキュリティ境界モデル | accepted | 2026-03-12 |
| [0008](0008-two-stage-distill-pipeline.ja.md) | 2段階蒸留パイプライン `[AKC: Extract]` | accepted | 2026-03-22 |
| [0009](0009-importance-score.ja.md) | KnowledgeStore Importance Score `[AKC: Extract/Quality Gate]` | accepted | 2026-03-24 |
| [0010](0010-research-data-sync.ja.md) | 研究データ同期 | accepted | 2026-03-25 |
| [0011](0011-knowledge-injection-to-skills.ja.md) | Knowledge 直接注入の廃止 → Skills 経由 `[AKC: Curate]` | accepted | 2026-03-26 |
| [0012](0012-human-approval-gate.ja.md) | 行動変更コマンドの人間承認ゲート `[AKC: Curate/Promote]` | accepted | 2026-03-26 |
| [0013](0013-shelve-coding-agent-skills.ja.md) | コーディングエージェントスキルのお蔵入り `[AKC: Curate/Promote]` | accepted | 2026-03-28 |
| [0014](0014-retire-system-spec.ja.md) | system-spec.md の廃止 `[AKC: Maintain]` | accepted | 2026-04-01 |
| [0015](0015-one-external-adapter-per-agent.ja.md) | 1エージェント1外部アダプタ原則 | accepted | 2026-04-08 |
| [0016](0016-insight-narrow-stocktake-broad.ja.md) | insight = narrow generator / skill-stocktake = broad consolidator `[AKC: Extract/Curate]` | partially-superseded-by ADR-0097 | 2026-04-11 |
| [0017](0017-yogacara-eight-consciousness-frame.ja.md) | 唯識八識モデルを設計の枠組みとする | accepted | 2026-04-11 |
| [0018](0018-per-caller-num-predict-embedding-stocktake.ja.md) | caller 別 num_predict + embedding-only stocktake | accepted | 2026-04-15 |
| [0019](0019-discrete-categories-to-embedding-views.ja.md) | 離散カテゴリ廃止 → Embedding + Views `[AKC: Promote]` | accepted | 2026-04-15 |
| [0020](0020-pivot-snapshots-for-replayability.ja.md) | Pivot スナップショットで再現可能性確保 `[AKC: Curate]` | accepted | 2026-04-16 |
| [0021](0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md) | Pattern スキーマ拡張 — Provenance / Bitemporal / Forgetting / Feedback | partially-superseded-by 0028, 0029, 0051 | 2026-04-16 |
| [0022](0022-memory-evolution-and-hybrid-retrieval.ja.md) | Memory Evolution + Hybrid Retrieval (BM25) | withdrawn-by 0034 | 2026-04-16 |
| [0023](0023-skill-as-memory-loop.ja.md) | Skill-as-Memory ループ — Router / Usage Log / Reflective Write | superseded-by 0036 | 2026-04-16 |
| [0024](0024-identity-block-separation.ja.md) | Identity Block Separation — Frontmatter で addressing する persona ブロック | superseded-by 0030 | 2026-04-16 |
| [0025](0025-identity-history-and-migrate-cli.ja.md) | Identity History ログ配線 + migrate-identity CLI | superseded-by 0030 | 2026-04-16 |
| [0026](0026-retire-discrete-categories.ja.md) | 離散カテゴリの廃止（ADR-0019 の Phase-3 完了） | partially-superseded-by 0060 | 2026-04-16 |
| [0027](0027-noise-as-seed.ja.md) | Noise as Seed — binary gate から salience-based forgetting へ | superseded-by 0060 | 2026-04-16 |
| [0028](0028-retire-pattern-level-forgetting-feedback.ja.md) | pattern 層の forgetting と feedback を撤回 — 記憶動的層は skill 層にある | accepted — partially-supersedes 0021 | 2026-04-18 |
| [0029](0029-retire-dormant-provenance-elements.ja.md) | dormant な provenance 要素を撤回 — `user_input` / `external_post` / `sanitized` | accepted — partially-supersedes 0021 | 2026-04-18 |
| [0030](0030-withdraw-identity-blocks.ja.md) | Identity Block 分離と History 配線の撤回 — Single Responsibility | accepted — supersedes 0024 and 0025 | 2026-04-18 |
| [0031](0031-classification-as-query.ja.md) | Classification as Query — 自己改善メモリの substrate 原則 | accepted | 2026-04-27 |
| [0032](0032-runtime-agent-stance.ja.md) | Stance — Contemplative Agent はランタイムエージェントである | withdrawn — contemplative axioms (ADR-0002) との tension | 2026-04-27 |
| [0033](0033-aap-quadrant-lens-usage-note.ja.md) | Note — AAP の 4 象限レンズを usage description として借用 | accepted (note) | 2026-05-01 |
| [0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.ja.md) | Memory Evolution と BM25 Hybrid Retrieval の撤回 — コストに対し効果が見えない | accepted — supersedes 0022 | 2026-05-05 |
| [0035](0035-sunset-migration-surface-and-consolidate-artifact-extraction.ja.md) | ADR-0019 Migration Surface の sunset と artifact extraction の統合 | accepted | 2026-05-05 |
| [0036](0036-sunset-skill-as-memory-loop.ja.md) | Skill-as-Memory ループの sunset — Router / Usage Log / Reflect の撤回 | accepted — supersedes 0023 | 2026-05-05 |
| [0037](0037-memory-subsystem-yogacara-convergence.ja.md) | メモリ subsystem は唯識フレームに収束した — 論文借用機構の退役 | accepted | 2026-05-05 |
| [0038](0038-moment-of-recognition-distill.ja.md) | Distill の観察対象に moments of recognition を再導入する `[AKC: Extract]` | accepted | 2026-05-13 |
| [0039](0039-novelty-score-lagrangian-self-post-gate.ja.md) | self-post gate を連続値 novelty スコア + rate-deficit Lagrangian に置換 | accepted | 2026-05-19 |
| [0040](0040-separate-code-level-findings.ja.md) | 週次自己内省レポートからのコード診断 findings の分離 | accepted | 2026-05-19 |
| [0041](0041-engagement-gradient-asymmetry-in-self-post-prompt.ja.md) | self-post prompt の engagement gradient 非対称を修復する | accepted | 2026-05-19 |
| [0042](0042-explicit-truncation-contract-for-untrusted-wrapper.ja.md) | `wrap_untrusted_content` の truncation を明示的契約に変える | accepted | 2026-05-20 |
| [0043](0043-per-post-seeding-for-self-post-generation.ja.md) | self-post 生成への peer post 直接シーディング | accepted | 2026-05-21 |
| [0044](0044-remove-topic-keywords.ja.md) | `topic_keywords` の全面削除 | accepted | 2026-05-23 |
| [0045](0045-pre-action-internal-note.ja.md) | エピソード層での pre-action `internal_note` 記録（ADR-0038 の Gap 2 を閉じる） | accepted | 2026-05-25 |
| [0046](0046-stocktake-llm-grouping-over-embedding-clustering.ja.md) | Stocktake の重複検出 — embedding クラスタリングではなく LLM グルーピング | partially-superseded-by ADR-0097 | 2026-05-30 |
| [0047](0047-comment-sampling-temperature.ja.md) | 外向きコメント生成のサンプリング温度引き上げ | accepted | 2026-05-30 |
| [0048](0048-trigger-altitude-skill-lifecycle.ja.md) | スキルライフサイクル全体のトリガー高度化 | partially-superseded-by ADR-0097 | 2026-06-02 |
| [0049](0049-meditation-active-inference-fidelity-and-deferral.ja.md) | 瞑想アダプタ — Beautiful Loop 忠実性監査と忠実な再実装の保留 | accepted | 2026-06-03 |
| [0050](0050-epistemic-taxonomy-and-approval-lineage.ja.md) | Epistemic taxonomy と承認系譜 — steering なしの可観測性 | partially-superseded-by 0051, 0082 | 2026-06-05 |
| [0051](0051-retire-trust-weighting.ja.md) | trust 重みの全廃 — 純 cosine 検索と bitemporal のみの生死判定 | accepted — partially-supersedes 0021, 0050 | 2026-06-05 |
| [0052](0052-retire-session-insight.ja.md) | セッション洞察生成の退役 — identity が承認済み継続性チャネルである | accepted | 2026-06-05 |
| [0053](0053-importance-encoding-time-significance.ja.md) | 観測時の手応えとしての importance — 三つの判断時点と再観察による昇格 | partially-superseded-by 0056 | 2026-06-06 |
| [0054](0054-externalize-llm-instruction-text-to-prompts.ja.md) | LLM 指示テキストを `config/prompts/` へ外出しし、injection 境界にはハードコードの fallback を持たせる | accepted | 2026-06-09 |
| [0055](0055-counterparty-identity-by-author-name.ja.md) | author name による counterparty 識別と activity/report スキーマの統一 | accepted | 2026-06-15 |
| [0056](0056-retire-importance-llm-scoring.ja.md) | distill 時の importance LLM 採点を撤去 — 抽出重みは純粋な time decay に | accepted — partially-supersedes 0053 | 2026-06-17 |
| [0057](0057-identity-from-self-reflection-corpus-alone.ja.md) | アイデンティティを self-reflection コーパスのみから蒸留する — 前アイデンティティの種と冗長な公理注入を外す `[AKC: Promote]` | accepted | 2026-06-20 |
| [0058](0058-value-injection-at-action-time.ja.md) | value 層の注入は「行動時」に属し、「蒸留時」には属さない `[AKC: Extract/Curate/Promote]` | accepted | 2026-06-20 |
| [0059](0059-remove-dead-reply-history.ja.md) | 死んでいた reply 履歴機構の撤去 | accepted | 2026-06-22 |
| [0060](0060-per-episode-grounded-distill.ja.md) | エピソード単位の grounded distill — バッチ抽出 + noise gate を「engagement エピソード 1 件 = grounded な LLM 1 コール」に置換 | accepted — supersedes 0027; partially-supersedes 0026 | 2026-06-23 |
| [0061](0061-action-time-untrusted-cap-at-platform-limits.ja.md) | action 時 untrusted 入力 cap を platform field 上限に統一; 内省ノートは全文を読む | accepted | 2026-06-23 |
| [0062](0062-create-time-verification-handshake.ja.md) | 作成時コンテンツ検証ハンドシェイク（LLM/コード併用ソルバ）と、可視化を条件とする記録ゲート | accepted | 2026-06-26 |
| [0063](0063-novelty-gate-verified-only-comparison.ja.md) | NoveltyGate の比較対象を verified（可視）投稿のみにスコープする | accepted | 2026-06-26 |
| [0064](0064-mlx-generation-backend.ja.md) | Apple Silicon で生成を host-local の mlx_lm.server 経由にする | superseded-by 0070 | 2026-06-27 |
| [0065](0065-mlx-ondemand-launchd-and-telemetry-model-contract.ja.md) | mlx_lm.server を launchd のオンデマンドジョブとして配線し、LLM テレメトリに served-model-id 契約を課す | partially-superseded-by 0067/0070 | 2026-06-27 |
| [0066](0066-backend-aware-context-budget-guard.ja.md) | `LLMBackend.context_window` 契約による backend-aware なコンテキスト予算ガード | accepted | 2026-06-27 |
| [0067](0067-keep-ollama-for-unattended-production.ja.md) | 本番生成バックエンドを Ollama に固定する — 16GB Apple Silicon の無人連続運用では mlx_lm.server は不適 | accepted — partially-supersedes 0065 | 2026-06-28 |
| [0068](0068-per-call-think-flag-and-thinking-trace-capture.ja.md) | per-call の think フラグと推論トレースのエピソードログ保存 | accepted | 2026-06-28 |
| [0069](0069-gemma-production-model-and-think-on-value-layer-pipelines.ja.md) | gemma4:e4b を本番生成モデルに採用し、値層パイプラインを think-ON で実行 | accepted | 2026-06-28 |
| [0070](0070-retire-mlx-to-sibling-repo-and-remove-docker.ja.md) | MLX backend を sibling repo へ退役し Docker を main から削除 | accepted — supersedes 0006, 0064; partially-supersedes 0065 | 2026-06-28 |
| [0071](0071-read-only-pattern-composition-instruments.ja.md) | 読み取り専用のパターン組成計器（view supply / 多様性 / grounding） | accepted | 2026-07-03 |
| [0072](0072-echo-chamber-interventions.ja.md) | echo chamber への介入 — レジスタ指示・corpus 育ちの seed・抽出失敗ガード | accepted | 2026-07-03 |
| [0073](0073-prune-orphaned-view-seeds.ja.md) | 孤児化した 5 つの view seed を削除する | accepted | 2026-07-03 |
| [0074](0074-weekly-staged-insight.ja.md) | 週次 staged insight — テーマ検出への役割再定義、pending ガード、staging 時マーカー更新、LLM novelty ゲート、厳密高速クラスタリング | accepted | 2026-07-09 |
| [0075](0075-observability-by-default.ja.md) | Observability by Default — リプレイ可能な監査ログは機能と同じ PR で出荷する | accepted | 2026-07-09 |
| [0076](0076-skill-selection-shadow-instrument.ja.md) | Skill 選択シャドウ計器 — pass-1 LLM 適用判断を観測し、強制しない | accepted | 2026-07-10 |
| [0077](0077-chaos-tdd-fault-injection.ja.md) | Chaos-TDD Fault Injection — seed 固定 fault schedule をテストファーストの仕様にする（パイロット: distill） | accepted | 2026-07-13 |
| [0078](0078-otel-connection-via-vocabulary-and-offline-export.ja.md) | 語彙 mapping とオフライン export による OTel 接続 — runtime 導入はしない | accepted | 2026-07-16 |
| [0079](0079-module-reorganization-package-splits.ja.md) | モジュール再編 — package 分割・恒久 facade・サイズ上限の文書化された例外 | accepted | 2026-07-18 |
| [0080](0080-north-star-layered-end-state.ja.md) | North Star — 層別の最終状態定義（能力目標にしない） | accepted | 2026-07-20 |
| [0081](0081-skill-selection-two-pass-injection-enforcement.ja.md) | skill 選択の二段注入 enforcement | accepted | 2026-07-24 |
| [0082](0082-retire-observed-epistemic-key.ja.md) | `observed` エピステミックキーの退役 — 警告ではなく死んだフィールドを消す | accepted — partially-supersedes 0050 | 2026-07-25 |
| [0083](0083-episode-logs-enter-the-weekly-prompt-as-hashes-only.ja.md) | エピソードログは週次プロンプトへハッシュとしてのみ入る | accepted | 2026-07-25 |
| [0084](0084-post-distill-durability-gate.ja.md) | 蒸留後の durability ゲート — エピソードではなく、生成されたパターンを judge する | accepted | 2026-07-26 |
| [0085](0085-unattended-weekly-fix-chain-single-saturday-gate.ja.md) | 無人 weekly fix チェーンと土曜単一ゲート | accepted | 2026-07-29 |
| [0086](0086-submolt-scope-instrument-before-autonomy.ja.md) | Submolt スコープ — 答えを渡す前に問いを計器化する | accepted | 2026-08-01 |
| [0087](0087-optional-token-counting-capability-for-the-context-budget-guard.ja.md) | コンテキスト予算ガードに任意の `count_tokens` capability を足す | accepted — 0066 を拡張 | 2026-08-01 |
| [0088](0088-shipped-conformance-kit-for-the-llm-backend-contract.ja.md) | `LLMBackend` 契約の適合キットを出荷物に入れる | accepted | 2026-08-02 |
| [0089](0089-llm-behavioral-eval-layer-on-deepeval.ja.md) | DeepEval を土台にした LLM 行動 eval 層 | accepted | 2026-08-06 |
| [0090](0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md) | 憲法改正の採択前に IPD 2 アームベンチを回す | accepted | 2026-08-09 |
| [0091](0091-value-layer-cadence-in-the-weekly-chain.ja.md) | weekly チェーンにおける value 層の更新周期 | accepted | 2026-08-10 |
| [0092](0092-shadow-constitution-instrument.ja.md) | Shadow 憲法計器 — パターンのみ合成・観測専用 | accepted | 2026-08-11 |
| [0093](0093-repo-plane-deterministic-intakes.ja.md) | repo 面の決定論 intake — docs 整合性と台帳条件 watch | partially-superseded-by 0095 | 2026-08-14 |
| [0094](0094-agent-first-task-ledger.ja.md) | エージェント優先のタスク台帳 — store / journal / projection | superseded-by 0095 | 2026-08-15 |
| [0095](0095-retire-task-ledger-machinery.ja.md) | タスク台帳機構の退役 — store と claims を残し、パースするものを全部落とす | accepted — supersedes 0094; partially-supersedes 0093 | 2026-08-16 |
| [0096](0096-insight-promotion-worth-abstain.ja.md) | insight 時の promotion-worth abstain — 生成された skill を judge し、surprise は材料として列挙する | partially-superseded-by ADR-0097 | 2026-08-17 |
| [0097](0097-consolidator-dissolution-and-skill-store-exit.ja.md) | 統合器の解体と skill store の出口 — 引き算、出口、語彙の順に | accepted — partially-supersedes ADR-0016, ADR-0046, ADR-0048, ADR-0096 | 2026-08-22 |

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
accepted / proposed / withdrawn / superseded-by ADR-NNNN

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

## References
- `ADR-NNNN`（`NNNN-slug.md`）— 関係を一行で（supersedes / refines / depends-on / precedent）
- 外部ソース（論文・先行事例・エビデンス）
```

### Status 行の語彙

Status 欄は決まった言い回しに従う。index・ADR 本文・`graph.jsonld` を同期させるための語彙なので、
以下のいずれかを使う（語は英語のまま、後続の説明だけ日本語にしてよい）:

- `accepted` — 現在有効
- `accepted — supersedes ADR-NNNN` — 先行 ADR を置き換える（置き換えられた側の index 行は
  `superseded-by ADR-NNNN` になる）
- `accepted — partially-supersedes ADR-NNNN[, ADR-NNNN]` — 先行 ADR の特定の節だけを置き換える
  （旧側の index 行は `partially-superseded-by ADR-NNNN` になる。どの節かは本文に書く）
- `accepted (note)` — 観測的・限定的な ADR。長期の規則を約束しない
- `accepted (amended YYYY-MM-DD)` — 本文を改訂した。詳細は ADR 内の Amendment 節
- `partially-superseded-by ADR-NNNN[, ADR-NNNN]` — 一部の節だけ置き換えられた。残りは有効
- `superseded-by ADR-NNNN` — 全面的に置き換えられた。本文は原文のまま保存する
- `withdrawn by ADR-NNNN` — 後続 ADR がこのアプローチを誤りと判断して撤回した
- `withdrawn (YYYY-MM-DD)` — その場で撤回した（多くは同日・同一著者）。本文に撤回理由を残す

関係を表す語（`supersedes` / `superseded-by` / `withdrawn by` / `partially-supersedes` /
`partially-superseded-by`）は `graph.jsonld` の型付きエッジ（`supersedes` / `supersededBy` /
`withdrawnBy` / `partiallySupersedes` / `partiallySupersededBy`）と対応させる。LLM が散文を
解析せずに supersede / 撤回の系譜を辿れるようにするため。

この語彙は `tests/test_adr_status_consistency.py` が機械検査する（本文 en / 本文 ja /
index en / index ja / `graph.jsonld` の 5 面で先頭の語が一致すること、後方 supersede では
参照先 ADR 番号が一致すること、graph の型付きエッジがそのノード自身の Status 散文と
一致すること — 素の `accepted` なノードは supersede 系のエッジを持たない）。

対応は原則ノード単位だが、部分 supersede だけはノード横断で双方向を要求する。前向きと後ろ向きは
語彙の選択肢ではなく、同じ主張を両端から述べたものだからである。6 件が後ろ向きの半分しか
記録していなかったが 2026-08-15 に解消し（T-ADR-PARTIAL-RECIPROCITY）、片側だけを足すと
`test_partial_supersede_edges_are_reciprocal` が落ちる。撤回を supersede とも読むべきかは
判断の問題として残し、検査しない。

**どちらの半分がどちらの範囲を書くか。** 部分 supersede には「退役させた範囲」と「存続する範囲」の
2 つがあり、書く面が違う。**前向き**の半分（新しい ADR 側）は**自分が退役させた範囲だけ**を書く。
**存続する範囲**は**後ろ向き**の半分（supersede された ADR 側）が持つ — 後から別の部分 supersede が
着地しても正しくあり続けられる唯一の面だからである。ADR-0021 の今日の残余は ADR-0028・ADR-0029・
ADR-0051 の 3 つを経た後のものなので、どれか 1 本の面に複製すると、その ADR の日付時点では
真でなかった状態を主張することになる。これは 2 つの散文面の意味的な一致なので**検査できない** —
規約として書き残す（2026-08-15 のレビューが、規約が無いまま書かれた前向き半分 4 本すべてで
これを取り違えているのを検出したため）。本文中で範囲つきの supersede を述べるときは
`supersedes X in part` を使う（Status のパーサも受ける形）。範囲つきの対象に素の `superseded` を
当てると全面退役として読まれる。

## 運用ルール

- 番号は連番（0001〜）、時系列順
- 既存 ADR の変更は新 ADR で supersede する（上書きしない）
- ある ADR が他を supersede / 撤回したら、古い側の Status を新しい ADR に向けて更新する
  （一行の編集。本文は書き換えない）
- 小さな判断は記録不要。アーキテクチャ・データモデル・セキュリティに影響する判断のみ
- 新規 ADR を追加したら `graph.jsonld` にもノード（と supersede / 撤回のエッジ）を追加し、
  LLM 向けナレッジグラフを追従させる
- `/sync-context` で ADR index とファイルの整合性をチェックできる
