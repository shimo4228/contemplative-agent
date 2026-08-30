---
state: withdrawn 2026-08-30
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

## 2026-08-29 triage 照合（無人 cycle）

未成立 → `blocked` 維持。08-26 以降の `docs/adr` / `config/` commit は `2b59a60`（RFC-0010 weekly 計器再設計）と `37cbea2`（ADR-0080 追補）のみで、生成モデル交代 ADR なし。

## 2026-08-30 withdrawn（著者判断 — 便乗型を ADR-0069 へ移設）

`blocked` を解いて終端化する。**内容は失われず、発火する場所へ移した。**

この行は task-stocktake が「台帳に置かない型」と名指しする**便乗型**だった —
再開条件が「次にモデル交代するとき同時に評価」で、台帳はモデル交代をする人に届かない
（store 運用は全件を読まず、`claims.py ready` は blocked を出さない）。CA の実測でも便乗 4 件中
2 件で対象ファイルが起票後に計 12 回変更され全部空振りしている。

**移設先**: [ADR-0069](../docs/adr/0069-gemma-production-model-and-think-on-value-layer-pipelines.md)
の Review-when 手順に **step 6「同じ機会に embedding 足場を再評価する」** を追加した
（2026-08-30、en / ja 両面）。あの手順はモデル交代の実行手順そのものなので、交代する人は
必ず読む。設計則「関連性の判断はその時点で払える最強の判定者に」、ADR-0019 の分業を現世代では
逆転させないこと、判定はコスト（prefill 速度 × ストア規模）と精度の両軸、先例（stocktake の
grouping が embedding union-find → LLM 単一コール）は全部そちらへ写した。

## Status

blocked — 現世代では ADR-0019 の分業（仕組み = embedding、価値判断 + 生成 = LLM）が
正しく、逆転させると壊れるので動かさない（2026-08-25）。直近の照合 2026-08-24 も未成立
（`docs/adr` / `config/` に生成モデル交代の commit なし）。

## Next action

- 再開条件: ローカル生成モデルの世代交代（モデル交代 ADR を書くとき同時に評価）
- 照合先: `config/` の生成モデル設定と、その交代を記録する ADR
- 成立時: accepted（評価軸はコスト（prefill 速度 × ストア規模）と精度の両方。備考なき限り単独で
  再提起しない）
