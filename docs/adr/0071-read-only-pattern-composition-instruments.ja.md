# ADR-0071: 読み取り専用のパターン組成計器（view supply / 多様性 / grounding）

## Status

accepted

## Date

2026-07-03

## Context

メモリー蒸留パイプラインは分野全体で同じ「3 層 + 蒸留」構造に収束しつつある — arXiv 2512.13564 "Memory in the Age of AI Agents" が分野を統一的にサーベイし、arXiv 2603.07670 がエージェントメモリを write–manage–read ループとして定式化した。この収束に対する本リポジトリの差別化要素は views 層（[ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md)）だが、監査の結果、その差別化要素はほとんど使われていないと判明した: 出荷済み 7 view のうち実際にクエリされるのは 2 つだけ — `self_reflection`（`distill-identity`、`distill.py`）と `constitutional`（`amend-constitution`、`constitution.py`）。残る 5 つ — `noise`、`communication`、`reasoning`、`social`、`technical`（旧 insight バッチ軸と旧 ingest ノイズゲート）— は何にも消費されない孤児定義である。

監査はさらに、存在しない機構を主張するドキュメントを発見した: `distill.py` のコメントと `docs/CODEMAPS/`（`architecture.md`、`core-modules.md`）が、クエリ時の noise-view フィルタと、コードに存在しないパターン単位の view テレメトリフィールド（`last_view_matches`、`last_classified_at`）を記述していた。これは実在する機構の古い記述ではなく、虚構の機構を「生きている」と記述するドキュメントである。

データ不足のまま開いていた観察が 3 つあった。第一に、distill 段で形成される echo chamber / register collapse（handoff 2026-06-22）— [ADR-0057](./0057-identity-from-self-reflection-corpus-alone.ja.md)、[ADR-0058](./0058-value-injection-at-action-time.ja.md)、[ADR-0060](./0060-per-episode-grounded-distill.ja.md) が軌道修正したが、効果自体は一度も定量化されていない。第二に、レビュー 2026-06-27 所見 M3: `insight` は singleton パターンを無言で廃棄しており、救済 lane の床値は当て推量でなく実分布から選ぶ必要がある。第三に、同レビュー所見 M2: `epistemic_counts.observed` は ADR-0060 以降構造的にゼロであり、「外部接地なし」と誤読される。

本番生成モデルは 5 日前に `gemma4:e4b` へ移行したばかりで（[ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.ja.md)）、baseline なしに今挙動を変えれば、その変化がモデル移行由来か介入由来か判別できない。オペレーターの応答は作業の順序化だった: まず計器、次に介入 — 現状を定量化し、介入は直感でなく読みから選ぶ。

## Decision

1. **`core/view_metrics.py` を追加する。** 読み取り専用のパターン組成計器モジュール。パイプラインの他の挙動は一切変えない。
2. **view supply は消費されている 2 view のみ測る。** seed への cosine 分布（閾値通過率、p50/p90/max）を `CONSUMED_VIEWS = (self_reflection, constitutional)` に限定して計算する。未消費の 5 view は測らない: 孤児 seed 上の分布は corpus の構造ではなく seed の古さを測るものであり、その読みは下流のどの行動も変えない（signal-first）。
3. **echo chamber 検出器として seed 非依存の多様性を測る。** pairwise cosine の均質度（mean/p50/p90）に加え、`insight` が見るのと同じクラスタ構造を、`insight` と同じ threshold/min/max **かつ同じ `gated` 行の除外**（codex review P2）で計算する。クラスタ統計は `CLUSTER_STATS_MAX_N=500` 超で省略（`insight.FULL_RECLUSTER_WARN_N` のミラー。import 循環を避けるためリテラル保持、テストが両値の一致を検証）。均質度の上昇 + supply の集中 + grounding の内向きの三点セットが register collapse の読みとなる — 手書きの軸を一切使わずに。
4. **grounding 組成を測る。** provenance の `source_type` 集計、ADR-0050 の epistemic 集計（`observed == 0` は ADR-0060 以降構造的である旨の明示注記つき、レビュー 2026-06-27 M2）、legacy gated 数。
5. **計器は 3 つの呼び出し点に配線し、挙動には配線しない。** `distill --dry-run` は would-be-added 集合 — dedup 後、つまり SKIP される重複は数えない（codex review P3）— の計器をログ出力する。新しい公開パラメータ名は `instrument_views`（意図的に `view_registry` と命名しない。gate 時代の threading を distill のシグネチャから排除した ADR-0060 の回帰テストを尊重するため）。`report --patterns`（新設 opt-in フラグ）は live pool 全体に同じ計器を描画する。`insight` は廃棄 singleton に最近接の消費 view を `nearest_view` で添えてログする（`extract_insight` に `instrument_views` を追加）。
6. **すべての計器を observability only に保つ。** 分布と組成はオペレーターのためのものであり、gate・ランキング・retrieval・promotion には一切供給しない — AKC ADR-0015 Decision 2（介入なき可視化）と同型で、本リポジトリの [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) / [ADR-0051](./0051-retire-trust-weighting.ja.md) によるメトリクス書き戻し却下とも整合する。計器出力は固定の両義性注記（空/薄い supply = パターン不在 or seed の古さ、計器自身には判別不能）を必ず含む — 「系統的に偏った計器は無計器より悪い」という AKC ADR-0016 の教訓による。計器はまた、raise せずに degrade する — 壊れた・次元違いの embedding 行は WARNING つきで skip し、ホストコマンドを決して中断させない（python-reviewer CRITICAL、2026-07-03）— そして自身のメモリも抑制する（pairwise 統計は `PAIRWISE_STATS_MAX_N=3000` 超で決定論的 stride サンプルに切替）。
7. **同じ変更で虚偽ドキュメントを訂正する。** `distill.py` のコメント、`insight.py` のモジュール docstring、`architecture.md` の Data Flow 節、`core-modules.md` のスキーマ例。

> **注記（2026-08-29、ADR-0101）**: 溶解義務 — 新しい計器はすべて消費計画を記載する —
> を本 ADR の釣り合いルールとして追加した。ADR-0101 は、そのルールの最終的な行き先として
> 本 ADR を名指している。

## Alternatives Considered

### 7 view すべてを計器の軸として測る

計画中にオペレーターが棄却: 孤児 5 seed には消費者がなく、その coverage 分布はどの行動にも答えない — 主に seed テキストの古さを測ってしまう（signal-first 違反）。処遇（prune / seed 再生 / 消費者を持つ新 view へのクラスタ昇格）は読みが揃った介入フェーズに委ねる。

### 計器なしで介入を直接実装する

棄却: rare-singleton 救済 lane・seed 書き直し・view prune の床値と設計を盲目で選ぶことになり（数値キャップ anti-pattern）、gemma4:e4b 移行 5 日後では挙動変化が介入由来かモデル由来か帰属不能になる。

### embedding drift 監視スタック（evidently、whylogs）の採用

棄却: pandas/scikit-learn の依存フットプリントが requests+numpy のみの方針と衝突し、reference-vs-current 型の drift プリミティブは「固定 seed embedding への view 別所属」という問いの形と異なる。必要な集計は保存済みベクトル上の ~100 行 — search-first verdict: Build。

### 孤児 topic view を insight バッチングに再配線する

棄却: 事前定義の view 軸から bottom-up embedding クラスタリングへ移行した確定済みの決定を蒸し返す。topical view を戻すなら、観測されたクラスタ構造から育て、先に消費者を与えるべき — 介入フェーズの候補（AKC サイクルの Promote と同型）。

### 本番実行時の計器（スケジュール distill 毎にログ）

保留（棄却ではない）: フェーズ 1 は計器を `distill --dry-run` と opt-in の `report` フラグに限定する。全スケジュール実行への縦断的配線は、読みの有用性が実証されたら安価に追加できる。

## Consequences

### Positive

- 最初の corpus baseline が即座に actionable — live pool n=1463: `self_reflection` supply 1108/1463（76%）、`constitutional` 986/1463（67%）が閾値 0.55 を通過し、分布はほぼ同一（両者 p50=0.58、p90=0.64）。一方 corpus の pairwise cosine mean/p50=0.554 — つまり view 閾値は corpus の均質性フロアに埋まっており、実際の選別は `top_k` が全て担っている。
- 同日の対照実験（無関係テキスト 3 本: vs corpus 0.33–0.46、vs seed 0.42–0.52）により、均質性は埋め込みモデルのフロアより genuine に ~0.1–0.2 高い（nomic-embed の anisotropy ではなく実在の echo シグネチャ）こと、0.55 が真に無関係なテキストは弾くことが判明。
- grounding 組成が live パターン中の `external_reply=0` と legacy gated 195 行を可視化。
- これらの読みが介入フェーズに校正済みの証拠を与える（フロア / corpus 平均 / view 上位 ≈ 0.68–0.77）。
- singleton 可視化（importance 分布 + 最近接消費 view）が M3 救済 lane の設計をデータ駆動の選択に変える。
- ドキュメントが虚構の機構を主張しなくなった。

### Negative

- 維持すべき新規 ~330 行 + テスト。
- `CLUSTER_STATS_MAX_N` ミラー定数は `insight.FULL_RECLUSTER_WARN_N` から drift しうる — import ではなくテストで防護。
- 計器自体は何も改善しない: 読みが無視されれば、届けられた価値は正直な docs だけ。
- これらの数字を gate に配線したくなる誘惑への防護は、モジュール docstring・本 ADR・出力の両義性注記のみ。

### Neutral / Follow-ups

- `report --patterns` は opt-in で、Ollama への seed embedding 2 回分のコスト。
- スケジュールされた本番実行の挙動はバイト単位で不変 — 計器は dry-run と opt-in 経路でのみ発火。
- ADR-0060 の回帰テストは今も gate 時代のシグネチャを distill から排除し続けている。

## References

- arXiv 2512.13564 — "Memory in the Age of AI Agents"
- arXiv 2603.07670 — "Memory for Autonomous LLM Agents": エージェントメモリを write–manage–read ループとして定式化
- AKC ADR-0015 — Decision 2、介入なき可視化（github.com/shimo4228/agent-knowledge-cycle）
- AKC ADR-0016 — 系統的に偏った計器は無計器より悪い（github.com/shimo4228/agent-knowledge-cycle）
- [ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md) — 本リポジトリが差別化する views 層
- [ADR-0031](./0031-classification-as-query.ja.md)
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) — grounding 組成計器が消費する epistemic 集計
- [ADR-0051](./0051-retire-trust-weighting.ja.md) — メトリクス書き戻しの先行却下
- [ADR-0056](./0056-retire-importance-llm-scoring.ja.md)
- [ADR-0060](./0060-per-episode-grounded-distill.ja.md) — gate 時代の `distill` シグネチャ; `epistemic_counts.observed == 0` の由来
- [ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.ja.md) — 計器なしの介入を帰属不能にしたモデル移行
- レビュー 2026-06-27 — M2（`epistemic_counts.observed`）、M3（singleton 廃棄）
