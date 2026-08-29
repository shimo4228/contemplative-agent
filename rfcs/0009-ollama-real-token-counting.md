---
state: blocked
state_since: 2026-08-16
---

## タスク

**Ollama に実トークン計数を挿す**（上流待ち）。ADR-0087 の seam は既に受け口になっているので、**ガード本体は無改変**で `count_tokens` 経由で差し込める。現状 `/api/tokenize` `/api/detokenize` は稼働中の 0.30.11 で **404**（route 自体が無い）、上流 PR [ollama#12030](https://github.com/ollama/ollama/pull/12030) は 2025-08-22 から未マージのまま open（最終更新 2026-06-04）、要望 issue [#12031](https://github.com/ollama/ollama/issues/12031) も open。**マージされても自動採用しない** — 生成ごとに HTTP 往復が 1 回増えるので、無人スケジュール上のレイテンシを実測してから判断する（endpoint の存在は採用理由にならない）

## 着手条件

再開条件: PR ollama#12030 がマージされ、かつ稼働版に載ること
照合先:   `gh pr view ollama/ollama#12030` と `curl -X POST localhost:11434/api/tokenize`（404 を返す間は着手不能）
成立時:   accepted（ただし**マージされても自動採用しない** — 生成ごとに HTTP 往復が 1 回増えるので、無人スケジュール上のレイテンシを実測してから判断する。endpoint の存在は採用理由にならない）

照合は手動。旧記述の「週次自動照合: `watch: …`」は ADR-0095 の台帳機構退役で消費者が消えており、
放置すると「自動で見張られている」と誤読される。**手動照合 2026-08-16: 404 を返す = 未成立**。

## 詳細

[ADR-0087](../docs/adr/0087-optional-token-counting-capability-for-the-context-budget-guard.md) の Follow-ups、`core/llm/__init__.py` の `_measure_input_tokens`

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`gh pr view 12030 --repo ollama/ollama`: state OPEN / mergedAt null。`POST /api/tokenize` → HTTP 404。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`gh pr view 12030 --repo ollama/ollama`: OPEN / mergedAt null。`POST /api/tokenize` → HTTP 404。

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。`gh pr view 12030 --repo ollama/ollama`: OPEN / mergedAt null。`POST /api/tokenize` → HTTP 404。

旧 ID: T-OLLAMA-TOKENIZE（.notes/tasks から 2026-08-25 移送）。

## 2026-08-26 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`gh pr view 12030 --repo ollama/ollama`: OPEN / mergedAt null。`POST /api/tokenize` → HTTP 404。

## 2026-08-29 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`gh pr view 12030 --repo ollama/ollama`: OPEN / mergedAt null。`POST /api/tokenize` → HTTP 404。

## Status

blocked — 上流 PR ollama#12030 が未マージで `/api/tokenize` は 404、着手不能
（2026-08-25）。直近の照合 2026-08-24 も未成立（PR は OPEN / mergedAt null、`POST
/api/tokenize` → HTTP 404）。

## Next action

- 再開条件: PR ollama#12030 がマージされ、かつ稼働版に載ること
- 照合先: `gh pr view ollama/ollama#12030` と `curl -X POST localhost:11434/api/tokenize`
  （404 を返す間は着手不能）。照合は手動
- 成立時: accepted（ただし**マージされても自動採用しない** — 生成ごとに HTTP 往復が 1 回増える
  ので、無人スケジュール上のレイテンシを実測してから判断する）
