---
id: T-INSIGHT-DESCRIPTION-CALL-FULL-SYSTEM-PROMPT
state: done 2026-10-17
state_since: 2026-10-17
origin: gate
---

## タスク

insight の description / name コール（RFC-0042 item 3 / ADR-0111 のコール分割）が `system=` を渡さずに
`llm.generate_full` を呼ぶため（producer: `src/contemplative_agent/core/insight.py:331`）、既定の
`_build_system_prompt()`（identity + axioms + skill 全文 + rules、`src/contemplative_agent/core/llm/__init__.py:768`）
が入り、context-budget の事前検査で skip される。2026-10-16 の weekly insight run では、4 週ぶりの `new` 判定
（cluster-54）が本文コールまで進んだあと、description コールが `system_chars 102,193` / 推定入力 34,898 token で
`budget_exceeded` になり、`description_invalid`（fault 扱い）で終わった。llm-calls の全履歴で
`insight.description` はこの 1 行だけ、`insight.name` は 0 行で、コール分割は本番で一度も完了していない。
本文コールは `get_distill_system_prompt()` を明示している（`insight.py:278`）。

## 詳細

- 診断: `reports/analysis/weekly-2026-10-16-findings.md` の F1.1
- 観察: `reports/analysis/weekly-2026-10-16.md` の Exceptions 1
- Source quote（`logs/llm-calls-2026-10-16.jsonl:578`）: `"caller": "insight.description"`,
  `"system_chars": 102193`, `"input_tokens": 34898`, `"num_predict": 300`, `"outcome": "budget_exceeded"`
- 同じ run の naming コールは `system_chars 138`（`:574, 576, 580`）
- `description_invalid` は `FAULT_ABSTAIN_REASONS`（`insight.py:134-143`）にあり、incremental window を
  消費しないので、同じクラスタは次の run でも同じ skip に当たる
- 関連: ADR-0058（蒸留時に値層を注入しない）、ADR-0087（budget guard）、ADR-0111

## 2026-10-17 triage 照合（無人 cycle）

前提を確認した。`core/insight.py:331` の `_ask_json_field` は `llm.generate_full(...)` に `system=` を渡さない（description と name の両方がここを通る）。本文コールは `insight.py:276-278` で `system=llm.get_distill_system_prompt()` を明示している。採否はオーナー（digest）。

## 2026-10-17 オーナー回答（triage digest）

`draft` → `accepted`。案 A を採用: description / name のコールにも本文コールと同じ `get_distill_system_prompt()` を渡す（資格情報の漏えい防止の 1 行だけで、値層も axioms も入らない — `core/llm/prompting.py:97-115`）。ADR-0058（蒸留時に値層を注入しない）とそろう。build は S44（cloud）。

Packet: [S44](../docs/plans/rfc-0052-s44-insight-format-calls-system.md)。

## 2026-10-17 S44 merge（判断役の検収）

`c751f05` を ff-only で main へ取り込んだ（cloud session、effort medium → medium、bounce は rebase 1 回 = gate・rebase）。

- 修正は `core/insight.py` の `_ask_json_field` 1 か所で、description と name の両方が `system=llm.get_distill_system_prompt()` を受け取る。回帰テストは `tests/test_insight.py::TestExtractSkill::test_format_calls_use_distill_system_prompt`（2 パラメタ）と `::test_format_calls_never_receive_default_system_prompt`（既定の system prompt を約 44 万文字に差し替え、本番と同じ `description_invalid` を修正前に再現）
- CI は tip で success。diff は packet が許した 4 ファイルだけ
- build が名指した逸脱: packet と本 RFC が書いた「axioms だけ」は誤りで、`get_distill_system_prompt()` に axioms は入らない。ADR-0111 の注記と docstring は正しい記述で書かれた（判断役は逸脱を受け入れ、本 RFC の 10-17 オーナー回答節の記述を直した）
- build の Proposed tasks 1 件（`generate_full` が `system=` 省略時に黙って全文 prompt に落ちる、`core/llm/__init__.py:768`）は、再現手順が失敗を示す形でなく（長さを印字するだけ）`MOLTBOOK_HOME` を読むので走らせず、捨てた。commit 本文に残る
- 次の読み: 2026-10-23 の weekly insight run で、cluster-54 か次の `new` が description / name を通って staging に届くか（`logs/llm-calls-*.jsonl` の `insight.description` / `insight.name` 行と `insight-staged.jsonl`）
