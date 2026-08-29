---
state: blocked
state_since: 2026-08-16
---

## タスク

**機構層の embedding 依存は「LLM の貧弱さの補償」= 失効条件付き足場**（2026-08-05 の議論）。設計則: 関連性の判断はその時点で払える最強の判定者に — embedding が正当なのは LLM に読ませるコストが払えない間だけ。現世代（gemma4:e4b、prefill 実測 6.3〜7.1 ms/tok）では ADR-0019 の分業（仕組み=embedding、価値判断+生成=LLM）が正しく、**逆転させると壊れる（現状は動かさない）**。ローカル生成モデルの世代交代で文脈処理が強く安くなったら、3 層メモリの機構層（embedding 検索・候補絞り）のどこを LLM 読解に置換できるかを再評価する。先例: stocktake grouping の embedding union-find → LLM 単一コール化（memory `stocktake-grouping`、「LLM が読める規模なら読ませる方が勝つ」の実地例）。評価軸はコスト（prefill 速度 × ストア規模）と精度の両方

## 着手条件

再開条件: ローカル生成モデルの世代交代（モデル交代 ADR を書くとき同時に評価）
照合先:   `config/` の生成モデル設定と、その交代を記録する ADR
成立時:   accepted（評価軸はコスト（prefill 速度 × ストア規模）と精度の両方。備考なき限り単独で再提起しない）

## 詳細

memory `project_rag_retrieval_demotion.md`、[ADR-0019](../docs/adr/0019-discrete-categories-to-embedding-views.md)、[2026-08-05 A/B](../docs/evidence/adr-0081/skillsel-cache-ab-2026-08-05.md)

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。2026-08-17 以降 `docs/adr` / `config/` に生成モデル交代の commit なし（`git log --since=2026-08-17 -- docs/adr config/` は T-INSIGHT-WORTH の 1 件のみ）。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。2026-08-19 以降の `docs/adr` / `config/` 変更は `a9552b1`（ADR-0093 注記の文言修正）のみで、生成モデル交代 ADR なし。

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。2026-08-22 以降 `docs/adr` / `config/` に commit なし — 生成モデル交代 ADR なし。

旧 ID: T-EMBED-EXPIRY（.notes/tasks から 2026-08-25 移送）。

## 2026-08-26 triage 照合（無人 cycle）

未成立 → `blocked` 維持。08-24 以降の `docs/adr` commit は ADR-0069 の Review-when 追補のみ（モデル交代のトリガーを書いた文書であって交代そのものではない）。`config/` の生成モデル設定に変更なし。

## Status

blocked — 現世代では ADR-0019 の分業（仕組み = embedding、価値判断 + 生成 = LLM）が
正しく、逆転させると壊れるので動かさない（2026-08-25）。直近の照合 2026-08-24 も未成立
（`docs/adr` / `config/` に生成モデル交代の commit なし）。

## Next action

- 再開条件: ローカル生成モデルの世代交代（モデル交代 ADR を書くとき同時に評価）
- 照合先: `config/` の生成モデル設定と、その交代を記録する ADR
- 成立時: accepted（評価軸はコスト（prefill 速度 × ストア規模）と精度の両方。備考なき限り単独で
  再提起しない）
