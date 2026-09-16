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

- RFC-0021（店の天井）の決着後に設計セッション。柱は 3 つ（様式を外す / コール分割 / description に what + when）、「溶かせを外す」は落とす。Unresolved の「引用か合成か」は合成で決着（上の 2026-09-07 節）、残るのは description コールの入力（本文だけか）

## 2026-09-07 外部照合（vault wiki + 一次ソース fetch。as-of 2026-09-07）

著者指示で、様式を決める前に vault の wiki（concept 8 ページ + daily-research）と外部研究を read-only で
照合した。本 RFC の 3 本柱のうち 2 本は支持、1 本は根拠が逆向き。加えて本 RFC の期待値そのものを
下げる読みが出た。

- **固定様式を外す — 支持。** 意味内容を固定して表現だけ変えた統制実験（arXiv:2607.03048、2026-07）で
  節付き構造化レンダリングは −13.3 pp（95% CI [−22.5, −4.2]）、同実験の executor 交換は +26.7 pp。
  Anthropic Agent Skills 仕様は本文の節を規定せず機械契約は name / description のみ。**留保**: executor は
  gpt-5 級で 4B 帯の検証は無い
- **コール分割 — 支持。** Trace2Skill（arXiv:2603.25158）で失敗分析を単発コールから多ターン agent に変えて
  +12.2 pp、単発は cross-model 転移で劣化。vault に記録された抽出パイプラインは全部複数段（EDV は
  実行・蒸留・検証の同一 agent 担当を self-confirmation trap として分離）
- **「複数を 1 つに溶かせ」を外す — 根拠が逆。** CONTRAMEM（arXiv:2608.22533、2026-08）: 生軌跡の
  retrieval 45.8% / 1 本ずつ要約 47.2% / 複数軌跡の対比から因果境界を切り出したもの 77.5%。Trace2Skill も
  複数 patch に横断する pattern を merge した方が転移が強い。一般論化の原因は溶かすことでなく
  **1 コールで小型モデルが書くこと**。この柱は落とす
- **具体は本文でなく一段下の層に。** WikiSkill（arXiv:2608.27454）ablation: 具体を保持した中間層あり
  63.7% / なし 48.7%。Trace2Skill は references/ に隔離、CONTRAMEM は contrastive evidence 欄、SKILLER
  （arXiv:2608.10538）は参照軌跡を実行時に渡さない。CA では knowledge.json の行がこの層。本文に具体を
  盛る方向は取らない。行の引用も取らない（相手のやり取りの記録が行動指針として固定され公開される —
  2026-09-07 著者判断）
- **書き手を 4B 級に置く構成は文献上ほぼ支持されない — 期待値を下げる主因。** SkillsBench
  （arXiv:2602.12670）: frontier 級の自己執筆 skill ですら利得 ≈ 0（curated は +16 pp）。SkillAxe
  （arXiv:2606.10546）: LLM 執筆 skill の失敗は「過度に一般的でトリガーが不正確」。Trace2Skill の執筆側
  下限は 35B、SKILLER は 4B / 9B を読み手だけに置き書き手は GPT-5.4。**4B〜8B が書いた skill の品質を
  測った研究は無い。** RFC-0025 の読み（平坦化はモデル起因）と整合。小型向けに見つかった唯一の処方は
  SKILLER の「input grounding と self-validation の制約を skill に埋め込む」
- **読み手としての小型モデルは skill 数で壊れる。** Gemma-3-4B-it の skill 同定 0.78、tiny model は
  10〜20 件超で急落、description だけのルーティングは本文展開時より劣る（arXiv:2602.16653 /
  arXiv:2608.20389）。店は 57 本。形式より店の大きさ（RFC-0021）が先に効く

**読み**: 残す柱は 3 つ — 様式を外す / コールを分ける / description に what と when を書く。「溶かせを
外す」は落とす。効く順は 店を小さくする（RFC-0021）> 書き手を変える（gemma 固定なら不可）> 抽出の型
（本 RFC）。本 RFC は draft のまま RFC-0021 の後に回す（2026-09-07 著者判断）。

出典の確度: 2607.03048 と 2608.20389 はサンプルが小さい。SkillsBench の self-generated の数値は版差あり
（引用時に本文照合）。SkillAxe の数値は未確認。

## 2026-09-16 triage 照合（無人 cycle）

`draft` 維持。照合先 RFC-0021 は未決着（第 2 窓は 2026-09-18 走行後の土曜ゲート）。2026-09-07 著者判断の順序どおり待ち。新しい問いは無い。
