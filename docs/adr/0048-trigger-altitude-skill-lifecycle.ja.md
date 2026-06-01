# ADR-0048: スキルライフサイクル全体のトリガー高度化

## Status

accepted

## Date

2026-06-02

## Context

自動抽出スキルの「When to Use」トリガーは、エピソード由来の transient な表層識別子 —— 特定のユーザー名、投稿 / トピック ID、飽和した relevance スコア（例: `>0.92`）、タイムスタンプ / 継続時間ウィンドウ —— で埋め尽くされている。こうしたトリガーはそれを生んだ過去の特定エピソードにしかマッチせず、将来の類似状況では発火しない。これでは再利用可能なスキルの意味をなさない。

これは 3 段階にまたがるライフサイクル問題である。(1) **生成** —— `insight` 抽出が transient なトリガーをそのまま出力する。(2) **統合-マージ** —— `stocktake` が冗長なスキル群を検出してマージスキルを生成するが、マージプロンプトはトリガーを一般化しておらず、表層識別子が素通りしていた。(3) **統合-クリーン** —— マージの相手がいないスキルは生のエピソード由来トリガーを永久に保持し、未マージ singleton 用のパスは存在しなかった。

コミット `c20ec5f`（"require recurring structural triggers in skill extraction"）は段階 1 を遡及的に締めたが、段階 2 と 3 は未処理のままだった。すべての外向き生成（`generate_comment` / `generate_reply` / `generate_cooperation_post`）は全スキル本文をシステムプロンプトに注入するため、狭くしか発火しないスキルが肥大した corpus は誤発火とトークン肥大の双方をもたらす。

クリーン段の実装中にフロントマターの回帰が表面化した。マージプロンプト（`config/prompts/stocktake_merge.md`）は YAML フロントマターを出力していなかったため、マージスキルは `name` / `description` / `origin` を欠いていた。クリーン段（`core/stocktake.py`）はフロントマター除去済みの本文を書き換えて元ファイル名に書き戻すため、ソースファイルのフロントマター —— reflection 簿記フィールド（`last_reflected_at` / `success_count` / `failure_count`）と `origin` を含む —— を黙って失っていた。

## Decision

トリガー高度化をライフサイクルの 3 段階すべてに適用し、フロントマター処理を全体で修正する。

1. **段階 1 — Insight 生成**（`config/prompts/insight_extraction.md`）: recurring structural なトリガーを要求し、transient 識別子を一般化する。遡及的、コミット `c20ec5f` で実装済み。

2. **段階 2 — Stocktake マージ**（`config/prompts/stocktake_merge.md`）: トリガー内の transient な表層識別子を構造的高度へ一般化する。飽和した relevance スコアは数値ごと drop（「high relevance」と書く。「high relevance (>0.92)」とは書かない）し、真の recurring 閾値（例: "more than 3 times in 7 days"）は残す。一般化により構造的に同一になったトリガーは 1 つに畳む。マージプロンプトは `config/prompts/insight_extraction.md` をミラーして YAML フロントマターブロック（`name` / `description` / `origin: auto-extracted`）を出力するようになった。

3. **段階 3 — Stocktake クリーン**（`core/stocktake.py` `clean_skill_triggers` + `config/prompts/stocktake_clean.md`）: 新規パス。マージの相手がいない singleton の「When to Use」トリガーを直接、構造的高度へ書き換える。`CLEAN_NOOP` センチネルがパスを冪等にする。

4. **グルーピング**（`config/prompts/stocktake_skills.md`）: トリガーの同一性を表層識別子レベルではなく構造的高度で判定する。

5. **フロントマター処理**: クリーン段は元ファイルのフロントマターを `text_utils.split_frontmatter` で取り出し、書き換え後の本文へそのまま再付与して温存する。フロントマター出力以前の legacy スキルには `text_utils.synthesize_frontmatter` が最小ブロックを生成する。これによりクリーンのフロントマター喪失回帰が修正され、reflection 簿記が保持される。

## Alternatives Considered

### Verbatim トリガー（現状維持）

エピソード由来の具体値を無修正で保持する。却下 —— トリガーは過去の特定エピソードにしか発火せず、飽和スコアやユーザー名は一般化されないため、スキルが類似の将来状況へ転移しない。

### スキル数への数値キャップ

corpus を N スキルに制限し、残りを drop する。却下 —— LLM 出力への数値品質フィルタは anti-pattern（`no-numeric-caps` ルール）。冗長性ではなく件数でスキルを除去するため、キャップに達した時点で有効なスキルまで捨てる。

### 統合に embedding クラスタリング

near-duplicate スキルをトリガー正規化のために cosine ベースのグルーピングで再導入する。却下 —— [ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.ja.md) で既に却下済み。embedding-cosine は共有された contemplative-AI のボイラープレート語彙で over-merge する。トリガー高度化は LLM グルーピング / マージ経路の内側で動作し、embedding クラスタラの復活ではない。

### フロントマター出力を一切やめる

all-injected single-shot 生成では、フロントマター `description` は各スキル本文の一部として LLM が読む dead-weight である。却下 —— メンテナの判断で、フロントマター衛生と将来の決定論的メタデータビューの潜在入力のために出力を選択。保存はフロントマター喪失回帰も併せて修正する。

### クリーンごとに LLM でフロントマターを合成

毎回のクリーンパスで元を保存せずフロントマターをゼロから再生成する。却下 —— 再生成は reflection 簿記（`success_count` / `failure_count`）を失い、`origin` と `name` を変えうる。保存を選択し、合成はフロントマター欠如の legacy 入力に対してのみ用いる。

## Consequences

### Positive

- 生存スキルが再利用可能で構造的に一般的なトリガーを持つ。実機ランで 16 スキルを 6 に統合（3 マージが 13 ソースファイルを消費 + 3 件の clean singleton）し、スキル corpus のトークン肥大を大幅に削減した。
- マージではフロントマターが出力され、クリーンでは reflection 簿記（`success_count` / `failure_count` / `last_reflected_at`）を保持したまま温存される。
- `CLEAN_NOOP` がクリーン段を冪等にする。clean 済み corpus への再ランで churn が出ない。

### Negative

- マージ段の高度化は stochastic: `qwen3.5:9b` は時折トリガー内に飽和 relevance スコアを残す（実機ランで 1 件、`adopt` 前に手修正）。
- 積極的な統合は over-broad なマージスキルを生みうる。実機ランの 7→1 マージは 10 トリガーのスキルを生み、[ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.ja.md) が指摘する selectivity 閾値を下回った。
- マージスキルのフロントマター `name` はファイル名 slug と一致しないことがある。insight 抽出の既存挙動と同じ。

### Neutral / Follow-ups

- クリーン段は「When to Use」トリガーのみを一般化する。スキルの Solution 本文に埋め込まれた飽和スコアは verbatim 保存される。これはスコープ外。
- より深い単調増加圧 —— insight はスキルを生成し続け、[ADR-0036](./0036-sunset-skill-as-memory-loop.ja.md) は embedding usage-log の退役シグナルを撤去した —— が、stocktake を唯一の counter-pressure として残す。定期的な stocktake cadence または将来の決定論的退役シグナルは別 ADR の領域。

## Related

- [ADR-0016](./0016-insight-narrow-stocktake-broad.ja.md) — Insight as Narrow Generator, Stocktake as Broad Consolidator。本 ADR はそのパイプラインの clean / merge 段を拡張する
- [ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.ja.md) — Stocktake Duplicate Detection — LLM Grouping over Embedding Clustering。トリガー高度化はそこで確立した LLM グルーピング / マージ経路の内側で動作する
- [ADR-0036](./0036-sunset-skill-as-memory-loop.ja.md) — Sunset Skill-as-Memory Loop。stocktake をスキル corpus 増大の唯一の counter-pressure として残す embedding usage-log シグナルの退役
