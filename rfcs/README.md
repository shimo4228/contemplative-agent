# RFCs

この repo の提案と作業項目の公開台帳 — 1 エントリ 1 ファイル `NNNN-slug.md`、ID は
`RFC-NNNN`。フル RFC の提案から小さな作業項目まで同居する。**state は各ファイルの
frontmatter が唯一の正本**。

起票の手順と規約（足切り・採番・様式・公開規約）の正本は
[skill: rfc-writer](https://github.com/shimo4228/claude-harness/blob/main/skills/rfc-writer/SKILL.md)、状態語彙は
[skill: task-stocktake](https://github.com/shimo4228/claude-harness/blob/main/skills/task-stocktake/SKILL.md)、判断は
[claude-harness ADR-0049](https://github.com/shimo4228/claude-harness/blob/main/docs/adr/0049-unify-task-ledger-into-public-rfcs.md)。規約本文をこの README には書かない
（複製は drift する）。

| # | Title |
|---|---|
| [0001](0001-apple-foundation-models-backend.md) | Apple Foundation Models を生成 backend として挿すか |
| [0002](0002-axiom-removal-ab-experiment.md) | 公理除去 A/B 実験（distill 面の足場待ち） |
| [0003](0003-count-tokens-time-bound.md) | `count_tokens` に時間上限が無い |
| [0004](0004-distill-fragment-pattern-rate.md) | distill の断片パターン率 |
| [0005](0005-embedding-scaffold-expiry.md) | 機構層 embedding 依存の失効条件 |
| [0006](0006-heartbeat-end-state-criteria.md) | heartbeat 終了条件の具体化 |
| [0007](0007-finish-reason-truncation-gate.md) | `finish_reason` 非報告 backend で truncation ゲートが no-op になる |
| [0008](0008-instrument-read-at-event-boundaries.md) | 計器の読みを「比較が壊れる境界」で記録する |
| [0009](0009-ollama-real-token-counting.md) | Ollama に実トークン計数を挿す（上流待ち） |
| [0010](0010-weekly-report-content-redesign.md) | 週次レポート A–E の中身の再設計 |
| [0011](0011-submolt-scope-sweep-reading.md) | submolt スコープ sweep の読みと撤去判断 |
| [0012](0012-shadow-constitution-reading-consumption.md) | shadow 憲法計器の読み値を次回改正ゲートで消費する |
| [0013](0013-skill-family-promotion-to-rules.md) | skill family の共通姿勢を rule へ昇格する |
| [0014](0014-skill-selection-instrument-reading.md) | skill 選択計器の定期読み |
| [0015](0015-skill-name-hallucination-vs-catalog-size.md) | skill 名の幻覚率と catalog サイズの相関 |
| [0016](0016-restore-surprise-instrument.md) | surprise 計器の復元（ADR-0097 D1 の部分 supersede 候補） |
| [0017](0017-insight-extraction-redesign.md) | insight 抽出の再設計 — 頻度キー抽出に飽和と新規性の器官を与える |
| [0018](0018-self-post-seed-voice-label.md) | 自己投稿 seed ブロックに公開してよい voice ラベルを付ける |
| [0019](0019-weekly-session-value-layer-read.md) | 週次無人セッションの Read 許可に値層 4 パスを足す |
| [0020](0020-eval-baseline-staleness-standing.md) | eval baseline の STALE 警告が常設化している |
| [0021](0021-skill-stocktake-family-saturation.md) | skill-stocktake の再設計 — family 飽和の統合と weekly 定期化、天井は selector 幻覚率 |
| [0022](0022-wikiskill-fidelity-check.md) | WikiSkill 論文との整合性チェック（fresh context）+ replay paper アームの是正（≤ 8 件・15k 字 cap・Proposer turn 上限） |
| [0023](0023-novelty-gate-retrieval-and-rare-lane.md) | insight の novelty gate を候補検索（BM25 + nomic）に置き換え、希少レーンを持つ |
| [0024](0024-skill-extraction-free-body-split-calls.md) | skill 抽出の型を解く — 本文自由記述、frontmatter は別コール、長さは保存時拒否 |
| [0025](0025-retire-wiki-mechanism.md) | wiki 機構の退役（RFC-0017 D4〜D10 / RFC-0022 の閉鎖。gemma で平坦化、opus では機能） |
| [0026](0026-weekly-sample-splice.md) | 週次観察文書の `## Sample` 節を LLM の写経でなく pipeline の決定論的な差し込みにする |
