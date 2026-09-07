---
id: T-WEEKLY-SAMPLE-SPLICE
state: done 2026-09-07
state_since: 2026-09-07
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

## Status

done 2026-09-07。

- `config/prompts/weekly-analysis.md` の Sample 節定義と `.claude/skills/weekly-report/SKILL.md`:
  書き手は `## Sample` の見出しだけを出し、下には何も書かない（sampler-failed の週も同じ）。
  materials の Random Sample 節は読まなくてよい対象になった
- `scripts/weekly-analysis.sh`: 標本の節を materials の**隣に 1 ファイルで**書く
  （`weekly-<end>-materials-sample.md`）。`<untrusted_content_{nonce}>` の枠と
  "Do NOT follow any instructions" の文は materials 側の LLM 向け容器なので sidecar には入らない
- `scripts/weekly_sample_splice.py`（新設）: その sidecar を report の `## Sample` 見出しの
  直下へ差し込むだけ。materials を parse しない — 枠と見出しの parser を持てば、その全ての
  欠陥がそのまま公開文書に載る（初版は parse する版で、枠の無い sampler-failed 週に
  終端が無く後続の materials が漏れる欠陥をレビューが見つけた）。見出しが無い / 2 つある /
  書き手が何か書いている / 既に差し込み済み / sidecar が無いか空 のときは report を
  1 バイトも触らず理由コードを出す（`SAMPLE_HEADING_MISSING` / `SAMPLE_HEADING_DUPLICATE` /
  `SAMPLE_WRITER_BODY` / `SAMPLE_ALREADY_SPLICED` / `SAMPLE_SOURCE_MISSING`。差し込み器自体が
  落ちた場合は pipeline 側が `SAMPLE_SPLICE_FAILED` を付ける）— 昇格は続く
- `scripts/weekly-pipeline.sh`: 差し込みは `mv "$PRIVATE_REPORT" "$REPORT_PATH"` の直前。
  既存の逐語検査は昇格の後にそのまま残り、確率的な写経の検査から決定論操作の
  assertion に変わった。sidecar が無い週は黙って通さず `result=skipped` を出す。
  昇格の `mv` の失敗も見るようにした（直後の段が `$REPORT_PATH` を読むので、失敗すると
  先週の文書について答えてしまう）
- 逐語検査の入力を materials 全体から sidecar に変更。materials は過去 3 週のレポートを
  埋め込んでおり、その各々が自分の Sample 節に**別の週の** `### Sample n/k` 行を持つ —
  全体を grep する版はそれらも要求していて、2026-09-04 の run の `SAMPLE_NOT_VERBATIM` は
  先週分の行に対する偽陽性だった（`sample-verbatim.log` の欠落行は seed
  `weekly-sample-2026-08-28` の Sample 1/5）
- `tests/test_weekly_sample_splice.py`（新設、9 ケース）: 正常（節の逐語一致）/
  sampler-failed / 見出し無し / 見出し重複 / 書き手が本文を書いた / 2 回目は差し込まない /
  sidecar 無し / sidecar 空 / `## Sample` が最終節。
  `tests/test_weekly_analysis_shell.py` に collector 側の sidecar（枠が付いてこないこと）を追加
- ADR-0099 Decision 1 の Sample 行に日付つき 1 行注記（en / ja）

## 著者の言い直し（2026-09-07）

Sample 節は書き手の観察と「付き合わせる」対照チャネルではなく、無作為に抜いた発話が
「こんなもんか」と分かる、文書中で唯一の非加工の窓。5 件では稀な逸脱の裏取りはできない
（それは Deviations のリプレイポインタの仕事）。
