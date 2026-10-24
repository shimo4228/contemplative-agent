# RFC-0047 evidence — face 台帳の 3 列と pilot の教訓（P1-15.1、2026-10-24）

同じディレクトリの `README.md`（昇格時点の凍結）の face 台帳に足す 3 列と、pilot（relevance gate）から得た教訓。
README と同じく **standing register ではない**（[ADR-0101](../../adr/0101-instrument-dissolution-mandate.md) D4）— 2026-10-24 時点の写しで、
現在値は台帳の再導出（`config/prompts/*.md` × 呼び出し元の grep）で取り直す。本ファイルは昇格先の段落（[docs/CYCLES.md](../../CYCLES.md) の Cycle 6 sub-loop）を
複製しない。置くのは列と教訓だけ。

## 3 列

| face | temperature | 失敗時の向き（所有 ADR） | 真値 judge |
|---|---|---|---|
| relevance gate | 0（decision seam の logprobs 要求、`core/llm/decision.py`。`generate()` は通らない） | **fail-closed**（[ADR-0113](../../adr/0113-decision-faces-and-relevance-score4-shadow.md) 追補 1） | **Jev `jev-1.13.0`**（既定、版 pin）/ opus `claude-opus-5`（Jev 不可の時の代替）。D-P1-15-2 = A |
| skill selection pass-1 | 0（`_SELECTION_TEMPERATURE`、RFC-0044） | **fail-open**（全量注入に戻る、[ADR-0081](../../adr/0081-skill-selection-two-pass-injection-enforcement.md)） | 無（台帳は「retire、RFC-0044 第 1 段で修理済み」） |
| comment 生成 | 1.3（`COMMENT_TEMPERATURE`、[ADR-0047](../../adr/0047-comment-sampling-temperature.md)） | skip（`drop_truncated` — 途中で切れた本文は publish しない、audit M2） | 無（adherence 判定器 `evals/judging.py`、label-once の judge ではない） |
| insight novelty gate | 0（`_NOVELTY_TEMPERATURE`） | **fail-open**（[ADR-0111](../../adr/0111-insight-entrance-stages.md) Decision 5） | 無（`novelty_replay_ab`、RFC-0023） |
| insight 名乗り・抽出後の重複判定 | 0（`STAGE_TEMPERATURE`） | **fail-open**（同上） | 無 |
| submolt 選択 | 既定 1.0（`select_submolt`） | skip（`post_pipeline.py::_choose_submolt`、audit L5） | 無 |
| distill（抽出・postgate） | 既定 1.0 | 棄権（理由コード、ADR-0075） | 退役（ADR-0071/0072） |
| verification solve | 0（`verification.py`） | 答えを出さない（検証は通らない） | 正解が決定論 |

読み方:

- temperature 列は `generate()` の引数の既定（1.0）と、0 を渡す判断コール（verification の算術、insight の判定段、skill selector）を区別する。
  relevance gate は `generate()` を通らず、decision seam が `num_predict: 1` / temperature 0 の logprobs 要求で問う。
  `generate()` の docstring はこの列を指す（`core/llm/__init__.py`）。
- 失敗時の向きは**所有 ADR が決めたもの**で、ここは写し。向きが違えば lab 指標の読み方も違う（fail-closed の face は「取りこぼし」を、fail-open の face は「素通し」を測る）。
- 真値 judge の列は label-once の資産を持つ face だけ埋まる。relevance gate の manifest は `judge` / `judge_version` を pin し（`scripts/relevance_label_set.py sample --judge`）、
  `label` / `score` は manifest と違う judge のラベルを拒否する。judge の交代（Jev ↔ opus、版の変更）は**装置境界**で、
  P3-02 の regime 表に 1 行入れる（その表はまだ無い — P3-02 が作る時にこの行を受け取る）。

## pilot の教訓（relevance gate、RFC-0046 / 0047）

1. **事前登録の問いは post 単位で置く。** 行単位の gate 率 0.127 は、gate が落とした post が feed に残る限り採点し直され、1 post が平均 2.84 行を書いたことの産物だった。
   post 単位は 0.271（RFC-0046 S38、2026-10-04）。問いの単位の誤りであって、予測の誤りではない。
2. **paired 行は二重に数えない。** 旧 gate と score4 を同じ行に並べた期間は、同じ post の判定が 2 本ある。比較は post の単位で 1 回だけ数える。
3. **予測値にも区間を付け、差の区間で判定する。** 「±6 pt に収まるか」は点推定でなく、差の区間が帯のどこにあるかで読む（`relevance_shadow_reading.py` の `adopt_window` は
   `hold` / `reopen` / `indeterminate`、10 post 未満は件数のみ — 規則は
   [preregistration-third-reading.md](../rfc-0046/preregistration-third-reading.md)）。
4. **n=300 の導出 1/√n は p=0.5 の最悪値。** 実際の gate 率 p≈0.13 なら半幅は ±3.8 pt（計算: 1.96·√(0.13·0.87/300)）。問いを決めたのは n ではなく予測値の不確かさ。
5. **P(top) は未較正の順位づけ。** AUC が高くても確率ではない（較正の欠けた読みの実例は ADR-0112 が skill selection の per-entry 形で測った ECE 0.766）。relevance gate 自身の ECE は今まで未測定で、初回の値は次の `score` が出す。`relevance_label_set.py score` が reliability 5 帯と ECE を出し、
   comment-report は `P(top) 0.88 (uncalibrated)` と書く。

## ratchet 規約（RFC-0047 §4 の補足）

face の prompt（`config/prompts/relevance_score4.md`）・identity・seam に触る変更は、`scripts/relevance_label_set.py score --baseline …` を回してから merge する
（手順は [rfc-0046 README](../rfc-0046/README.md) の「ratchet の回し方」）。決定論の半分 — manifest の sha が現在の tree と合うか —
は `.claude/verify.sh` の full mode が advisory で回す（`relevance_label_set.py check`、label set が無い clone では静かに skip）。
task-triage の検収 checklist の 1 行は P2-03 の持ち分。
