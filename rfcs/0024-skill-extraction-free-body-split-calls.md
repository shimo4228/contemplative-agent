---
state: draft 2026-09-04
state_since: 2026-09-04
review-when: 本番の生成モデルが様式指定を守れる世代に替わる（コール分割の理由が消える）、または RFC-0023 が blocked のまま（順序の前提が崩れる — 単独で進めるか再判断）
---

## Summary

skill 抽出を「本文（自由記述）→ description → name」の 3 コールに分け、Problem / Solution / When to Use の固定様式と「複数のパターンを 1 つに溶かせ」「個人的観察を普遍的な指示に訳せ」の指示を外す。長さは prompt の目安 + 保存時の拒否（切断はしない）。

## Motivation

`config/prompts/insight_extraction.md` は 1 コールで frontmatter と 4 節の様式を gemma に守らせている。
2026-09-04 の読み:

- **機械が消費するのは frontmatter の 2 欄だけ。** skill selection の pass 1 は `name — description` の 1 行
  しか読まず（`core/skill_selection.py` の `_render_catalog`）、選ばれた skill の本文は frontmatter を剥いで
  そのまま生成プロンプトに注入される。`## When to Use` を読む code は無い。`## Problem` / `## Solution` の
  有無を見るのは stocktake の構造検査（`core/stocktake.py`、advisory）だけ
- **様式強制は gemma に効いていない。** 命名節が禁じた `fluid-` / `dynamic-` / `anchoring` が store に残っている
  （`fluid-contextual-anchoring-loop`、`fluid-dynamic-resonance-regulation-…`）
- **様式が平坦化を指示している。** knowledge.json の行は一人称で状況を持つ具体（例: 「『runtime にどんな無意味な
  儀式が要るか』という誘いを効率計算への挑戦と受け取り…」）なのに、skill は「構造的な境界を特定する」に丸まる。
  「複数を 1 つに溶かせ」「普遍的な指示に訳せ」はその丸め方の指示そのもの。同じ失敗を wiki（RFC-0025）でも
  見た: 小型モデルに複数を溶かして書き直させると一般論に落ちる

「同じような skill が大量にできる」のうち、件数は RFC-0023 の候補検索が減らすが、**同型さ**（どのクラスタからも
「structural / systemic / deconstruct / detect」に着地する）は抽出の register の問題で、検索では直らない。

## Guide-level explanation

- **本文は自由記述。** 型を指定しない。指示は「行にある具体（誰に何を聞かれて何をしたか）を残す」方向にだけ書く。
  行をそのまま 1 本引用させる（few-shot 化）かどうかは Unresolved
- **description は本文から書く**（行からではない）。選択が読むのはこの 1 行なので、本文と食い違うと選択が壊れる。
  これは stocktake の description 忠実度監査（唯一の LLM コール）を生成側で先取りする形で、
  「成果物の後に judge を置く」（skill `llm-pipeline-layering` の順序則）
- **name は description から**（機械的な切り出しで足りればコール不要）
- **長さ**: prompt に語数の目安、保存時に超過を**拒否**（理由コード、silent fallback なし）。切断しない —
  途中で終わる文が本番に入るより、その週は出さない方がよい。`num_predict` は上限の上に置く（切断の機構に
  しない）。再試行はしない（行は残るので次週また来る）
- stocktake の `## Problem` / `## Solution` 検査は撤去（旧様式の skill は残る。検査は新様式に対して意味を持たない）

## Reference-level explanation

触るもの: `config/prompts/insight_extraction.md`（本文用に書き直し）、新 prompt 2 本（description / name）、
`core/insight.py` の抽出コール（1 → 2〜3 コール、保存時の長さ拒否と理由コード `BODY_TOO_LONG`）、
`core/stocktake.py::_check_skill_quality`（節検査の撤去）、`core/artifact_extraction.py`（frontmatter 合成は
`synthesize_frontmatter` を流用）、tests。`core/text_utils.skill_theme` の契約（name / description）は変えない。

## Drawbacks

- コール数が 1 → 3 で weekly insight の所要時間が伸びる（クラスタ数 × 2 コール分。gemma 1 コール ≈ 数十秒）
- 自由記述は「言い換え」に寄る可能性が高い。それを許容する（生成時に読むのは具体例の方が挙動を変える）
  かどうかは著者判断

## Rationale and alternatives

- **様式を prompt で強める**: 禁止語の列挙が効かなかった実測があるので不採用
- **選抜（合成なし、行の引用のみ）**: 平坦化は構造的に起きないが「いつ使うか」が description に閉じる。
  Unresolved に残す
- **何もしない**: 同型さは RFC-0023 では直らない

## Prior art

ADR-0072（distill を per-episode + register に戻して具体が残った）、ADR-0084（judge は成果物の後）、
skill `llm-pipeline-layering`、RFC-0025（wiki の平坦化の読み）。

## Unresolved questions

- 本文を合成にするか、行の引用（few-shot）にするか
- description を書くコールの入力は本文だけか、本文 + 行か

## Future possibilities

- 新様式で抽出した skill と旧様式の skill を選択ログで比べる（RFC-0014 の計器）

## Status

draft（2026-09-04）。RFC-0023 の読みの後に設計セッション（著者指示: 先に計測、型は後）。

## Next action

- RFC-0023 が accepted / blocked のどちらかに決まったら設計セッションで Unresolved 2 点を決めて `accepted`
