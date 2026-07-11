# ADR-0031: Classification as Query — 自己改善メモリの substrate 原則

## Status

accepted — ADR-0019、ADR-0022、ADR-0026 に既に実現されている原則の post-hoc articulation。

`docs/adr/README.md` の定義による **worldview ADR**: 新しい問題を解決するのではなく、本プロジェクトの他のメモリ ADR が成立する前提条件を名指す。

## Date

2026-04-27

## Context

自己改善するエージェントは時間とともに自身の分類軸を改訂する。カテゴリが書き込み時に state として保存されている場合、軸の改訂のたびにデータ migration が必要になり、コストはコーパスサイズに比例して増える。再分類が高くつく時点で再分類できなくなったエージェントは、まさに「興味深いことを学べるだけの履歴を蓄積した瞬間」に学習エージェントであることをやめる。

## Decision

カテゴリは、書き込み時に **state** として保存されるのではなく、**読み出し時** に編集可能な意味的シードに対する投影として計算される。

各 view は、centroid embedding + 名前 + プロンプトを持つ小さな編集可能 artifact。任意のパターンの任意の view 下での分類は、クエリ時にパターンの embedding と view の centroid の類似度として計算される。パターン自体は category フィールドも、タグリストも、namespace も持たない — 内容と embedding だけを持つ。

これは分類を **state フィールド** ではなく **クエリ操作** として扱う。

## Implications

軸の改訂コストは O(seed-edit) であり、O(corpus-size) ではない。Curate フェーズ (`distill`、`insight`、`rules-distill`、`amend-constitution`、`skill-reflect`) が分類軸を改訂しても、history 層 (`episodes.sqlite`、不変 JSONL) と pattern 層 (`knowledge.json`) はそのまま、その上の投影だけがシフトする。

**消費実態の明確化 (2026-07-11)。** 上の Curate 列挙は「全 Curate コマンドが view を query する」という意味ではない。view を query するのは 2 つだけ — `distill-identity` (`self_reflection`) と `amend-constitution` (`constitutional`)。`insight` と `rules-distill` は意図的に教師なし embedding clustering を使う。判断規則: 意味軸が事前に既知のとき（「X に関わる patterns はどれか？」）は **view** が正しい投影であり、オペレーターがまだ命名していない構造を発見することが目的のときは **clustering** が正しい投影 — そこに seed を課すと発見が既命名の軸に偏る。どちらのメカニズムも本 ADR に等しく従う: カテゴリはいずれにせよ query 時の計算であり、違いは query 軸が事前定義（seed）か創発（cluster）かだけである。

## Reference Implementations

- [ADR-0019](0019-discrete-categories-to-embedding-views.ja.md) — 離散的 `category` フィールドから view ベース投影への initial migration
- ~~[ADR-0022](0022-memory-evolution-and-hybrid-retrieval.ja.md) — cosine + BM25 ハイブリッドスコアと memory evolution~~ (ADR-0034 で撤回)
- [ADR-0026](0026-retire-discrete-categories.ja.md) — Phase-3 完了、legacy `category` フィールド削除

## Closest Prior Art

A-MEM (Xu et al., 2025, [arXiv:2502.12110](https://arxiv.org/abs/2502.12110)) — 同じ attractor に独立に到達。複数の研究グループが同時期に同じメカニズムへ収束していること自体が、設計空間がそこに固定されつつある証拠。

## References

- [ADR-0017](0017-yogacara-eight-consciousness-frame.ja.md) — 投影 / state の区別が legible になる worldview フレーム
- ADR-0019, ADR-0022, ADR-0026 — 参考実装
