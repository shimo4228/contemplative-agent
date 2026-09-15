Language: [English](DEVELOPMENT-RECORDS.md) | 日本語

# 開発記録

Contemplative Agent の開発中に書かれた記事の時系列索引。最初のスクラッチ構築と四公理導入の動機になったアラインメント実証から、記憶アーキテクチャの実験、のちに [AAP](https://github.com/shimo4228/agent-attribution-practice) となるアカウンタビリティの枠組み、[agent-observability-patterns](https://github.com/shimo4228/agent-observability-patterns) として公開されたオブザーバビリティ規律まで、プロジェクトの設計史をたどれる。後半は機構層が終端状態へ向けて縮んでいく記録で、タスク台帳・レビュー系統・読まれない計器・コードマップの退役が続く。日本語の原文は [zenn-content](https://github.com/shimo4228/zenn-content) リポジトリにある（Zenn 公開版は各記事の frontmatter から辿れる）。

1. [Moltbookエージェント構築記 — Claude Codeとセキュリティファースト開発](https://github.com/shimo4228/zenn-content/blob/main/articles/moltbook-agent-scratch-build.md)
2. [Prompt-Based Alignmentには天井がある — 囚人のジレンマ3モデル実証](https://github.com/shimo4228/zenn-content/blob/main/articles/contemplative-alignment-benchmark.md)
3. [Moltbookエージェント進化記 — 自然言語で制御し、記憶で学び、失敗しても壊れない設計](https://github.com/shimo4228/zenn-content/blob/main/articles/moltbook-agent-evolution-quadrilogy.md)
4. [LLMアプリの正体は「mdとコードのサンドイッチ」だった](https://github.com/shimo4228/zenn-content/blob/main/articles/llm-app-sandwich-architecture.md)
5. [自律エージェントにオーケストレーション層は本当に必要か](https://github.com/shimo4228/zenn-content/blob/main/articles/symbiotic-agent-architecture.md)
6. [推論でもツールでもない — AIエージェントの本質は「記憶」ではないか](https://github.com/shimo4228/zenn-content/blob/main/articles/agent-essence-is-memory.md)
7. [エージェントの記憶が壊れた — 9Bモデルと格闘した1日](https://github.com/shimo4228/zenn-content/blob/main/articles/few-shot-for-small-models.md)
8. [ゲーム開発のメモリ管理をAIエージェントの記憶蒸留に移植した](https://github.com/shimo4228/zenn-content/blob/main/articles/agent-memory-game-dev-distillation.md)
9. [自律エージェントの自由と制約 — 自己修正・信頼境界・ゲーム性の設計](https://github.com/shimo4228/zenn-content/blob/main/articles/agent-freedom-and-constraints.md)
10. [エピソードログから倫理が生まれるまで — Contemplative Agent 17日間の設計記録](https://github.com/shimo4228/zenn-content/blob/main/articles/contemplative-agent-journey.md)
11. [登れる壁に看板を立てても意味がない — AIエージェントに必要なのはガードレールではなくアカウンタビリティだ](https://github.com/shimo4228/zenn-content/blob/main/articles/ai-agent-accountability-wall.md)
12. [事故のあとで因果を辿れるか](https://github.com/shimo4228/zenn-content/blob/main/articles/agent-causal-traceability-org-adoption.md)
13. [AIエージェントのブラックボックスは二層ある — 技術の限界とビジネスの都合](https://github.com/shimo4228/zenn-content/blob/main/articles/agent-blackbox-capitalism-timescale.md)
14. [ReAct エージェントが本当に必要な業務はどれか](https://github.com/shimo4228/zenn-content/blob/main/articles/react-agent-business-quadrant.md)
15. [(3) LLM ワークフロー象限が語彙から脱落している — 続・ReAct エージェントの適用域](https://github.com/shimo4228/zenn-content/blob/main/articles/react-agent-business-quadrant-2.md)
16. [本番運用に ReAct は必要か — 設計フェーズと運用フェーズを分ける](https://github.com/shimo4228/zenn-content/blob/main/articles/react-agent-business-quadrant-3.md)
17. [ワークフロー象限と ReAct 象限の間のグラデーション — 設計フェーズと運用フェーズがスキル設計を分ける](https://github.com/shimo4228/zenn-content/blob/main/articles/react-agent-business-quadrant-4.md)
18. [AIエージェントの「なぜその判断？」に答えるオブザーバビリティ設計3パターン](https://github.com/shimo4228/zenn-content/blob/main/articles/agent-observability-patterns.md)
19. [自律エージェントをあえて M1 Mac で作る — 制約が設計を鍛えるという選択](https://github.com/shimo4228/zenn-content/blob/main/articles/small-llm-by-choice.md)
20. [LLM エージェントに fault injection TDD を入れたら silent failure が3件出た](https://github.com/shimo4228/zenn-content/blob/main/articles/chaos-tdd-fault-injection.md)
21. [AI エージェントの自前ログ、OpenTelemetry につないだら何が見える？](https://github.com/shimo4228/zenn-content/blob/main/articles/agent-logs-to-opentelemetry.md)
22. [AIレビューの指摘をタスクへ送り続けたら、修理が終わらなくなった——4,541行を捨てるまで](https://github.com/shimo4228/zenn-content/blob/main/articles/ai-review-task-loop.md)
23. [AIレビューを6系統から1系統へ——「指摘ゼロ」で終われないループの切り方](https://github.com/shimo4228/zenn-content/blob/main/articles/review-chain-damping.md)
24. [未使用コード検出が拾わなかった2,063行を消した——参照でなく消費を、新設時に書かせる](https://github.com/shimo4228/zenn-content/blob/main/articles/instrument-consumption-plan.md)
25. [AIに知識の盲点を診断させたら、15日間の行き詰まりが85分で動いた](https://github.com/shimo4228/zenn-content/blob/main/articles/ai-knowledge-gap-diagnosis.md)
26. [3か月で159回commitしたLLM向けアーキテクチャ文書を消した。構造はLSP、理由はADR、図は人間に](https://github.com/shimo4228/zenn-content/blob/main/articles/codemap-retirement.md)
27. [毎週読まれるログに、11秒の連打が写らなかった理由](https://github.com/shimo4228/zenn-content/blob/main/articles/log-projection-blind-by-construction.md)
