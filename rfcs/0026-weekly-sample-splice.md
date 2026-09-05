---
id: T-WEEKLY-SAMPLE-SPLICE
state: draft
state_since: 2026-09-05
origin: gate
---

## タスク

週次観察文書の `## Sample` 節を LLM の写経でなく pipeline の決定論的な差し込みにする。producer:
`scripts/weekly-pipeline.sh:417`（`SAMPLE_NOT_VERBATIM` の検査）。この節は「書き手が curate
できない唯一の対照チャネル」として設計されている（ADR-0099）のに、現在はその書き手自身が
バイト列を打ち直す経路になっており、2026-08-28 の run で実際に 1 文が落ちた
（collector 側 *"Dashboards stay green. Callers stop paging. Everyone calls it progress. Then
two agents reconcile…"* → 昇格済みレポート側は *"Everyone calls it progress."* を欠く。証拠:
`logs/weekly-pipeline/weekly-2026-08-28-090001/sample-verbatim.log`）。書き手は `## Sample`
見出しだけを出し、pipeline が `mv "$PRIVATE_REPORT" "$REPORT_PATH"`（`:407`）の**前**に
collector の節（`:423` が既に抽出している行 + `scripts/weekly-analysis.sh:544-550` の frame
marker）を見出しの下へ差し込む。既存検査は残す — 確率的な写経の検査から、決定論的操作の
assertion に変わる（`sampler-failed` の週は `scripts/weekly-analysis.sh:552` の 1 行だけを
出すので従来どおり通る）。

## 詳細

- 診断: `weekly-2026-09-04-findings.md` F1.1（`reports/analysis/`）。観察側の出所は
  weekly-2026-09-04.md の Exceptions 第 1 項
- Source quote（現行コード、`scripts/weekly-pipeline.sh:409-431`）:
  *"the Sample section exists to be the one part of the document the writer cannot curate, and a
  trimmed / reordered / annotated copy is exactly the failure it exists to detect. … A reason code,
  not an abort"*
- 検査は昇格の**後**に走る（`:407` → `:417`）ので、壊れた対照チャネルを持つレポートが
  `reports/analysis/`・公開 sync・翌週の `PREV_REPORTS` に届く。差し込みにすればこの順序は
  無害になる（順序だけを直す案は、写経の信頼性に依存したままなので不十分）
- テスト: `rg 'sample_verbatim|SAMPLE_NOT_VERBATIM' tests/` は 0 件 — この stage は未カバー。
  変更と同じ PR で最初の 1 本を入れる（`tests/test_weekly_analysis_shell.py` が同系の shell 検査を持つ）
- 関連: ADR-0099（Sample 節と対照チャネルの目的）、ADR-0098 Decision 6（chain の指摘も
  同じ triage 経路）、RFC-0010（`state: done 2026-08-29`、review-when はこの面を含まない）。
  `rfcs/` にこの面のエントリは無い
