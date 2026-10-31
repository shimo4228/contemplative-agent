# T-CAND7（2026-08-16 dropped）— 写し

<!-- 2026-10-31 に非公開ノート（archive/tasks/T-CAND7.md）から昇格した写し（P3-02.5）。本文は 2026-08-16 時点のまま、file:line も当時のもの。親は RFC-0008 の parent 行。 -->

```yaml
id: T-CAND7
state: dropped 2026-08-16
seq: 60
state_since: 2026-08-16
```

## タスク

計器の本番配線（毎スケジュール実行の instrument ログ）

## 旧・着手条件

旧条件「`T-P3` の手動観察で読みの有用性が実証されたら」は、**「有用性の実証」自体が
解釈を要する判断**であり、実証された後に「本番配線するか」を改めて決める工程が残る。
条件成立だけで ready へ移せないので `blocked` ではない（ADR-0071 が保留した毎スケジュール
実行時ログ）。

## 決着（2026-08-16、`dropped`）— 毎回配線という形を捨て、イベント駆動へ置き換える

T-P3 が 6 週間の縦断を **2 点の手読みだけ**で結論まで運んだ（pairwise 0.55 → 0.58、
「介入は多様性を増やさず新レジスタが均質度を押し上げている」）。**per-run の分解能を要求する、
名前の付いた決定が現時点で 1 つも無い** — skill `read-only-instruments` の signal-first
（常時配線は読みの有用性が実証されるまで保留）に照らして落とす。

**この判断を最初に支えていた論拠は誤りだったので、記録として残す。** 「ストアが bitemporal
（`knowledge_store.py:49-52` の `is_live` = `valid_until is None`）だから任意の過去日の corpus を
**厳密に**再構成でき、毎回のログは情報ゼロ」と主張したが、cross-model review（Codex、
2026-08-16）が 3 点で反証し、いずれも裏が取れた:

1. **埋め込みの in-place backfill** — `scripts/restore-embed-knowledge.py:62-66` が
   `rows[i]["embedding"] = vec` を timestamp 無しで書く。distill は埋め込み失敗時に
   ベクトル無しで保存する設計（`distill.py:705-713`）なので実在経路。過去の pairwise が動く
2. **view supply は原理的に再構成不能** — `view_metrics.py:160-185` が
   `registry.get_centroid()`（実行時に seed 文を埋め込んだもの）と `view.threshold`（現行値）に
   依存。どちらも版管理されていない。view が使えなかった回の「その軸が欠けた」事実も復元不可
3. **backup/restore で元ベクトルは失われる** — export が埋め込みを落とし、restore が再導出する。
   埋め込みモデルが変われば過去の読みは再現しない

つまり contemporaneous な観測には**実在の固有価値がある**。冗長だから捨てるのではなく、
**消費者がいないから捨てる**。この違いは再提起の条件を変えるので重要。

置き換え先は T-INSTRUMENT-EVENT-READ（イベント駆動の読み）。上の 3 つの再構成破れは
**全部そのタイミングで起きる**ので、境界にだけ印を残す方が毎回のログより安く正確。

## 詳細

handoff T3 は非公開ノートのまま（未昇格）。T-P3 の読みは [docs/evidence/regimes/t-p3-reading.md](../regimes/t-p3-reading.md) に再計算して昇格済み。
