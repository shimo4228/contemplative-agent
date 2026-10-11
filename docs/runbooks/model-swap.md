# Runbook: Model Swap Checklist

> **対象**: 生成モデル（`OLLAMA_MODEL`）か判断モデル（`DECISION_MODEL`）を入れ替える、または両者を別モデルにするとき。

## チェックリスト

- [ ] `DECISION_MODEL` を served の生成モデルと**別**のモデルにするなら、[ADR-0112](../adr/0112-decision-backend-seam-and-shadow-skill-decision.ja.md) の phase separation（cycle の全候補を判定 → 1 回降ろす → 全部生成）を再訪する — 別モデルだとバッチごとにモデル交代（再ロード 2 回）が起きる。同じモデル（`DECISION_MODEL` 未設定）なら交代は無く、この項目は不要（ADR-0113 追補 3 で閉じた理由）
