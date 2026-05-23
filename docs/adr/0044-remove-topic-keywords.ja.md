# ADR-0044: `topic_keywords` の全面削除

## Status

accepted

## Date

2026-05-23

## Context

`topic_keywords` は `config/domain.json` に保持されている 8 つの contemplative-AI 標準語のタプルである: "alignment, philosophy, consciousness, mindfulness, emptiness, non-duality, boundless care, reflective thought"。コードベース上では 2 つの表面に供給されていた。

**表面 1 — 関連度スコアラーのプロンプト。** `config/prompts/relevance.md` の 3 行目に `{topic_keywords}` プレースホルダーがある。`core/domain.py:resolve_prompt()` が展開し、`llm_functions.score_relevance()` が消費する。スコアはコメント関連度 (閾値 0.95)、既知エージェント engagement (閾値 0.80)、ADR-0043 シード選定フロア (0.4) の 3 つの下流ゲートを制御する。

**表面 2 — `feed_manager.run_cycle()` 内の検索ローテーション。** `feed_manager.py` 126-138 行がサイクルごとに 8 つのキーワードを時間ローテーションし、`client.search(keyword)` を 1 回呼んでクロス submolt の post を取得する。

以下の 2 つの発見が 2026-05-22 の ADR-0043 デプロイ後レビューで浮かび上がり、本決定を促した。

**発見 1 — アイデンティティの二重注入による冗長性。** `score_relevance` は `system` 引数なしで `generate(prompt, num_predict=30)` を呼ぶ。`core/llm.py:442` が自動で `_build_system_prompt()` を付加する。これはエージェントのアイデンティティ (`identity.md`)、4 つの contemplative 公理、学習済みスキル、学習済みルールをまとめたものである。同じ標準語彙がシステムプロンプトとユーザープロンプトの `{topic_keywords}` の両方から LLM に届く。ユーザープロンプト側の注入は、システムプロンプトがすでに完全な形で伝えている内容の、手動管理された狭いプロキシに過ぎない。

**発見 2 — 追加当日から死んでいた検索ローテーション。** git の調査によると、コミット `ba95917` (2026-03-09) が `engage_with_post()` の `feed_manager.py:188-196` に「未 subscribe の submolt からの post をスキップする」フィルターを追加した。コミット `9648a42` (2026-03-12、3 日後) が検索ローテーションブロックを追加した。検索ローテーションはクロス submolt で `/search?q={keyword}` を呼ぶが、返ってきた post はすべて `engage_with_post()` のフィルターで弾かれる (未 subscribe submolt から届くため)。結果として約 2.5 ヶ月間で約 1,000 件の無駄な GET リクエスト (~1 GET/サイクル × ~14 サイクル/日 × ~75 日) が発生し、contemplative-AI 標準語彙が Moltbook の検索クエリログに継続的に漏洩し続けた。

## Decision

`topic_keywords` が触れているすべての表面から全面削除する。

1. `config/domain.json` から `topic_keywords` フィールドを削除する。
2. `core/domain.py` の `DomainConfig` データクラスから `topic_keywords` フィールドと `topic_keywords_str` プロパティを削除する。
3. `load_domain_config()` の `required_keys` タプルと、`resolve_prompt()` が生成する `_DefaultDict` から `topic_keywords` を削除する。
4. `config/prompts/relevance.md` を書き直し、インラインのキーワードリストの代わりにシステムプロンプト上のエージェントのドメインアイデンティティを参照させる。`{post_content}` プレースホルダーと末尾の `Score:` キューは保持する。最終的な文面はプロジェクトの `prompt-model-match` 規約に従い qwen3.5:9b が生成する。
5. `feed_manager.py:126-138` の Source 3 検索ローテーションブロックと対応するdocstringの行を削除する。

関連度の判断はシステムプロンプト表面 (アイデンティティ + 公理 + スキル + ルール) に一本化される。検索ローテーションは置き換えない。2026-05-23 に subscribed submolt のフィードセットを 8 つ (general / philosophy / consciousness / agents / memory / emergence / ai / tooling) に拡充済みであり、クロス submolt 検索なしで十分な peer の声の量を確保できる。

## Alternatives Considered

### セントロイドのコサイン関連度

LLM 関連度スコアラーをアイデンティティ/constitution セントロイドへの embedding コサインで置き換える。却下 — 本削除のスコープ外。「エージェントの公理キーワードがそのまま現れなくても、"MCP wrapper for agent autonomy" が contemplative に隣接している」と判断するような LLM のニュアンスは意図的に残す。キーワード削除後に本番メトリクスでスコアの drift が観測された場合は、別途 ADR として検討する。

### 明示的なビューラベルの注入

`{topic_keywords}` の代わりに ADR-0019 `ViewRegistry` からビューラベルを注入する `{view_label}` プレースホルダーを使う。却下 — 同じ冗長性問題が残る。システムプロンプトはすでにどのビューラベルも要約するアイデンティティを持っており、`score_relevance()` というホットパス関数から `ViewRegistry` への結合を追加することになる。

### `topic_keywords` を残し、検索ローテーションだけ修正する

死んだ検索ローテーションブロックだけ削除し、関連度プロンプトの `{topic_keywords}` 注入は残す。却下 — ユーザープロンプトへの冗長な注入が残り、もはや使われている表面のない config フィールドも維持し続けることになる。

### 検索ローテーションを残し、submolt フィルターを緩める

`feed_manager.py:188-196` の未 subscribe submolt フィルターを緩めて、検索ローテーションの結果を受け入れる。却下 — そのフィルターはバグではなく意図的なスコープ境界である。緩めると未 subscribe submolt の post にエージェントが晒されることになり、ADR-0007 の意図に反して信頼表面が広がる。

## Consequences

### Positive

- 約 1,000 件の死んだ `client.search` GET 呼び出しを廃止する (~2.5 ヶ月間、サイクルごとに 1 件)。
- contemplative-AI 標準語彙が Moltbook の検索クエリログに繰り返しクエリ語として漏洩しなくなる。
- プロンプトテンプレート表面のプレースホルダーが 1 つ減る (`resolve_prompt()` の `_DefaultDict` から `{topic_keywords}` が消える)。
- `DomainConfig` の必須フィールドが 1 つ減る。ドメイン切り替えテンプレート (`--domain-config`) が要求するキーが 1 つ少なくなる。
- アイデンティティ駆動の関連度評価が単一ソースになる。`identity_distill` が `identity.md` を更新すると、関連度スコアラーの根拠も自動的に同じ方向に動く。従来は identity が変化するたびに `domain.json` の `topic_keywords` を手動で編集する必要があった。

### Negative

- 関連度スコアラーがアイデンティティのみに依存するようになった。システムプロンプトのアイデンティティ部分がドメインのフレーミングを省略または弱めた場合 (例: `identity_distill` サイクルが曖昧な自己記述を生成した場合)、関連度スコアは静かに drift する。これを捉える回帰テストは存在せず、本番エピソードのスコア drift としてのみ顕在化する。
- `{topic_keywords}` を含んだままの古い `$MOLTBOOK_HOME/prompts/relevance.md` オーバーライドは、プロンプト本文にリテラルの文字列 `{topic_keywords}` をレンダリングする (クラッシュはしない — `_DefaultDict.__missing__` は未知のプレースホルダーをそのまま保持する)。ホームディレクトリのオーバーライドを持つ運用者は再生成が必要。CHANGELOG に明記する。
- 検索ローテーションの廃止により、subscribed submolt フィードが post の engagement 源として唯一になる。subscribe 対象が減ると、engagement キューが比例して縮小するがフォールバックの探索経路はない。2026-05-23 の 8 submolt への拡充が現時点の余裕を与えているが、コードで強制されているわけではない。

### Neutral / Follow-ups

- `client.search` の GET 件数を負荷の指標として使っている既存のログクエリは、この表面から永続的に 0 を読むようになる。
- キーワード削除後に本番メトリクスで関連度 drift が確認された場合、セントロイドコサイン関連度スコアラー (Alternatives Considered 参照) が次の対策として候補に挙がっている。
