---
state: in_progress
state_since: 2026-09-02
review-when: ADR-0080 追補（代謝の質）が supersede される、または週次候補量が設計変更なしで恒常的に 1 桁へ落ちる（premise の自然消滅）
---

## Summary

insight 抽出（knowledge patterns → skill 候補）の再設計 — 頻度キーの抽出に飽和シグナルと新規性の器官を与える（ADR-0080 追補「代謝の質」の摂取側修理。オーナー指示 2026-08-26「抽出する機構を治すのが先決」）。

## Motivation

現行の抽出は「その週の episode 由来 pattern から ≥3 件の cluster を作れたもの」を候補にする**頻度フィルタ**で、store の状態が入力に無い。行動がテーマ的に安定したエージェントでは頻度が高いもの = 既知なので、この抽出器は構造的に既知を再発見する。実測: 7 週間で staged 438 / adopted 53（12%）、却下理由はほぼ全部「採用済み skill に覆われている」か「同 batch の兄弟」（ADR-0097 Context）。

同時に、本当に新しい出来事は定義上まだ繰り返されておらず cluster 床 ≥3 を越えられない — **重複の洪水と新規の取り逃しは同じ欠陥の両面**。濾過層も現在は弱い novelty gate 1 枚のみ: worth gate は ADR-0097 D1 で撤去（gemma self-judge が 3 回の実測で全件 yes）、実効の判定者だった headless reviewer は ADR-0098 で廃止。novelty gate 自体も成長期の較正（「迷ったら NEW」、証拠は名前と description のみ、batch 内兄弟は不比較）のまま飽和期に立っている。

ADR-0080 追補はこの修理を認可する: 自己調節に到達するための有界な機構工事は装置の修理でありスコープ内。代謝の質条項が要求する複数軸（新規性・重要度・環境の反応）の識別能力を摂取装置に与えることが本 RFC の目的。

## Guide-level explanation

設計の候補要素（採否・組み合わせは設計段で決める）:

1. **飽和シグナル** — `NOTHING-PROMOTABLE` の abstain 経路と理由コードは ADR-0097 D1 が意図的に残した（「channel を残し判定者を落とす」）。信頼できる判定者を挿す
2. **抽出時照合** — 候補 cluster を store と照合してから staging に置く。関連性の照合は
   embedding / lexical retrieval の仕事（「関連性の判断はその時点で払える最強の判定者に」
   RFC-0005。gemma の yes/no は 3 回 refuted 済み）。`scripts/retrieval_recall_measure.py`
   （ADR-0097 スライス 3 予約）は reviewer 用だったが抽出側へ向け直せる
3. **新規性の軸** — (a) store からの距離（embedding）、(b) 自分の過去からの距離 = surprise
   （復元は [RFC-0016](0016-restore-surprise-instrument.md)）、(c) 環境の反応（読み値として。
   報酬重み付けは ADR-0051 の supersede を要する — ADR-0080 追補 B の境界）
4. **novelty gate の再較正** — 「迷ったら NEW」は store が空だった時代の非対称性。飽和期は
   コスト構造が逆転している（重複が高くつき、取り逃しは 12% しか起きない）

## Reference-level explanation

- **教師データが既にある**: 7 週 438 候補すべてに人間（+reviewer）の判定が付いている。
  新しい門番は本番投入前に offline replay で較正できる（ADR-0097 スライス 3 の作法）
- **沈黙の飢餓ガード**: 較正を逆に振ると「本当に新しい skill を静かに潰す」が可能になる。
  抑制した候補は理由コード付きで記録しリプレイ可能にする（observability by default、
  ADR-0075）。計器の本体は「何を通したか」でなく「何を止めたか」
- **一変数ずつ**: ADR-0097 D8 の規律に従い、変更ごとに期待効果と最小読み取り数を事前登録
  （judged ≈ 80–95/日）。archive・rule 変更と同じ週に動かさない

## Drawbacks

- 摂取装置への機構追加は「機構層は止まるのが完成」と表面上逆行する — ADR-0080 追補の
  合成規則（自己調節に到達するための有界工事は修理）が根拠だが、工事が肥大したら
  この規則の悪用になる（追補自身が Negative に記録）
- 抑制が効きすぎると代謝の観察が痩せる（上記の飢餓ガードが対価）

## Rationale and alternatives

- **月次化だけで済ます**（ADR-0097 Review-when 登録済みの手）— 却下方向: 総量は同じで
  まとめて見るだけ。生成が飽和を知らない構造は変わらない
- **下流の掃除で対処**（rule 昇格・archive）— RFC-0013 の withdrawn で決着: 症状への処方
- **何もしない** — 週 40–50 件の人間濾過が続く。ADR-0080 追補の未完成判定に恒常的に該当

## Unresolved questions

- 飽和シグナルの判定者は誰か（embedding 距離 / code 閾値 / 教師データ較正の複合）
- 低頻度・高新規の pattern を拾う経路の形（cluster 床 ≥3 の扱い）
- 環境の反応（Moltbook 側シグナル）をどの読み値として入れるか
- RFC-0016（surprise 復元）との統合順序
- **skill の値打ちを測る面が無い**（2026-09-02 追加）: Face A の comment eval は n=36 で skill の有無を
  見分けられなかった（効果があるとしても雑音床 2〜3 と同じ大きさ）。抽出器を治した後に「治った」を
  何で読むか — 設計セッションはこれを持ち込む

## Prior art

SkillResolve-Bench（arXiv 2606.10388）の same-capability ambiguity（RFC-0013 本文で参照）。
社内先例: ADR-0084（判定は成果物の後に置く）、ADR-0096（self-judge の refute 3 連）、
ADR-0056（重要度 ablation）。

WikiSkill（arXiv 2608.27454、2026-08-27 投稿。2026-08-30 読み）— 本 RFC に最も近い外部先例。
raw トレース / 蓄積知識 / 実行可能 skill の 3 層を分ける構成で、CA の episode log →
knowledge store → skills に対応する。3 点が直接効く:

- **抽出器に蓄積層を読ませることが論文中で最大の ablation**（平均 48.7 → 63.7、+15.0 点。
  最大は 49.9 → 76.6）。蓄積層を持たない構成は、あるベンチマークでは no-skill baseline 50.5 を
  下回った（44.4 / 49.9）。本 RFC の Motivation「store の状態が入力に無い」に外部の実測が付く。
  ただし論文の提案器は蓄積知識を**材料**として読む（index + 過去提案の採否記録 + 必要なページを
  自分で開く）のに対し、現行 novelty gate は既存 skill の name + description を**通す/落とすの
  二値ゲート**として見るだけで、役割が違う
- **中間層の書き込み動詞が create だけではない**。既存 pattern ページへの patch 更新
  （append / replace / insert_after）が既定で、実測は 1 run あたり作成 4.4–9.8 に対し編集 7.0–18.4。
  生産量を活動量から切り離すのは件数の抑制ではなく既存ページへの帰属である、という設計。
  CA 側の対応物（dedup の `update` = 旧行の soft-invalidate + 新行 append）とは別の操作
- **却下の記録を読むのは次回の提案器**（reviewer ではない）。ADR-0097 D6 が予約した却下語彙の
  宛先の再検討材料になる

移植できない部分: 検証スプリットのスコアによる自動 gating と rollback（CA に正解が無い）、
skill retrieval の設計（論文は全注入で交絡を外している）、蓄積層の剪定（論文も持たず Limitations で
自認 — ADR-0097 が解体した場所と同じ）。

## 2026-08-29 triage 判定（著者回答: 選択肢 (b) — RFC-0016 を先に）

`draft` 維持。設計セッションは [RFC-0016](0016-restore-surprise-instrument.md) の復元が
マージされ、surprise の読み値が現物として取れてから持つ。Unresolved questions のうち
「RFC-0016 との統合順序」はこれで決着（RFC-0016 が先、その読み値を設計材料にする）。
残り 3 点（飽和シグナルの判定者 / cluster 床 3 の扱い / 環境の反応の入れ方）は設計セッションで潰す。

## 2026-08-30 追記（WikiSkill の読みと、設計セッション前の baseline 計測）

外部先例 WikiSkill（arXiv 2608.27454）を読み、Prior art に追加した。それを受けて 2 点を決める。

**設計セッションの前に skills-on/off の baseline を 1 回読む。** 独立 RFC を立てず本 RFC に畳む
（著者判断）。

理由: WikiSkill の gating は `R_best` を**空 skill set の検証スコアで初期化**する — 「skill 無しに
勝てるか」が gate の定義そのもので、CA はこの読み値を一度も取っていない。同論文の ablation では、
蓄積層を持たない構成の skill が no-skill baseline を下回るベンチマークがあった（44.4 / 49.9 対 50.5）。
本 RFC の前提（「抽出器を治す」）が「抽出物がまだ元を取っていない」に変わりうるので、設計の前に読む。

立て方: `evals/` の **comment 面（Face A）でそのまま立つ** — `evals/run_eval.py`（ADR-0089）+
`evals/datasets/comment_golden.jsonl` + `evals/baselines/`。pinned fixture
`evals/fixtures/agent_home/skills/`（45 件）を空にしたアームを足すだけで、distill 面（Face B）は
要らない。[RFC-0002](0002-axiom-removal-ab-experiment.md) が withdrawn になった理由（Face B が
誰の予定にも無い）は本計測には当たらない。

消費計画（ADR-0101）:

- **読み手** — 本 RFC の設計セッション
- **何回の読みで何を決めるか** — 1 回。決めるのは本 RFC の前提（抽出器の修理か、抽出物の値打ちか）。
  サンプル数と判定基準は実行前に登録し、「判定不能」を「効いていない」と混同しない
  （`run_eval.py` の exit 2 の思想と揃える）
- **満了時の撤去条件** — 読み終えたらアームを撤去する。定期計器にしない

**設計のブラッシュアップと実装は新しい Fable のリリース待ち**（著者判断）。その世代で設計を
詰めて実装する。計測は read-only で Ollama + claude judge しか使わないため、**この待ちの外側で
先に走らせてよい**。

## 着手条件

**2026-08-30 更新。** 旧条件（RFC-0016 の復元が main にマージされ surprise の読み値が取れること）は
2026-08-29 に成立済み（RFC-0016 は `done`、`core/insight_surprise.py` は display-only で在る）。

**2026-09-02 更新。両条件とも成立。** (1) skills-on/off の baseline は 2026-09-02 に 1 回読んだ
（上の Reading 節。照合先は `docs/evidence/rfc-0017/` — `evals/baselines/` ではない）。
(2) 新 Fable は Fable 5.1 がリリース済み。

次: 設計セッション（grill-me 形式）→ Unresolved questions 残り 4 点（飽和シグナルの判定者 /
cluster 床 3 の扱い / 環境の反応の入れ方 / skill の値打ちを測る面）を潰して accepted。

## 2026-09-02 事前登録（skills-on/off baseline の 1 回読み — run の前に固定）

着手条件 (2)（新 Fable）は Fable 5.1 で成立。(1) の計測をこの節の宣言どおりに 1 回行う。
RFC-0020 の積み残し（受け入れ幅を run の前に宣言しないと事後に都合よく読める）をここで実施する —
**この節は run より前の commit に置く**。

### アーム

- **on** = 承認済み baseline `evals/baselines/comment_golden-2026-08-31.json`（two_pass_selected、
  12 ケース × 3 サンプル = 36）。再実行しない。根拠は run 直前の `evals/check_staleness.py` が
  exit 0（fixture / prompt / sampling / dataset が 08-31 と同一）であること。exit 0 でなければ on も回す
- **off** = `run_eval.py --arm skills-off` 1 run、同じ 12 ケース × 3 サンプル。skill を system prompt に
  一切注入しない（`<learned_skills>` ブロック無し、pass-1 selector も走らない）。fixture の
  `skills/` はディスク上に残すので `assets_sha256` は on と同一、manifest の `injection_regime` だけ
  `full_corpus`（selector 未配線の値）になり、`--baseline` 比較は exit 2 のまま（fail-closed 維持。
  比較は RFC-0020 と同じく手で行う）
- `--arm` は一時的な seam。読みを記録したら撤去する（消費計画どおり。git 履歴から revert で復元可）

### on アームの参照帯

two_pass_selected の同一設定 3 run（08-08 / 08-16 / 08-31）。厳密な雑音床は 08-16↔08-31 の対
（nonce 以外同一、動いたのは 2〜3 サンプル / 1 ケース）。08-06 は全 45 skill 注入の旧 regime
（DEVIANT 9 / persona 失敗 9）で別物なので帯に入れない。

| 指標（36 サンプル中） | 08-08 | 08-16 | 08-31 | 帯 | run 間の最大振れ |
|---|---|---|---|---|---|
| ADHERENT | 0 | 0 | 2 | 0–2 | 2 |
| DEVIANT | 4 | 3 | 2 | 2–4 | 2 |
| DRIFTING | 32 | 33 | 32 | 32–33 | 1 |
| `register_natural` 失敗 | 35 | 36 | 34 | 34–36 | 2 |
| `persona_intact` 失敗 | 4 | 3 | 2 | 2–4 | 2 |
| `engages_post` 失敗 | 0 | 1 | 0 | 0–1 | 1 |
| `axiom_consistent` 失敗 | 0 | 0 | 0 | 0 | 0 |
| ケース verdict が DRIFTING 以外（12 中） | 0 | 0 | 1 | 0–1 | 1 |

on アームの注入実態（08-31 の selection audit、名前のみ集計）: 1 コメントあたり 3–7 skill
（4 が 13 件、5 が 13 件、6 が 6 件、3 が 3 件、7 が 1 件）。最頻は
`suspend-interpretation-upon-premise-doubt`（36 中 30）。

### 可読の閾値（帯の端 + 最大振れ + 1）

これを越えなければ**判定不能**であって「効いていない」ではない（`run_eval.py` の exit 2 の思想と同じ）。

- **H1「skill は効いている」**（off で悪化）: DEVIANT ≥ 7、または `persona_intact` 失敗 ≥ 7、
  または DEVIANT ケース ≥ 3
- **H2「skill は効いていない / 害」**（off で改善）: ADHERENT ≥ 5、または `register_natural` 失敗 ≤ 31、
  または ADHERENT ケース ≥ 3
- **方向仮説**（事前に 1 つだけ）: skill 本文は用語が重い（skill-stocktake の jargon 所見）ので、
  off で `register_natural` の失敗が減る。他の指標に方向仮説は置かない
- **判定不能**（どちらも越えない）: 「Face A の n=36 では skill の効果を見分けられない」と記録し、
  本 RFC の前提（抽出器を治す）は動かさない。設計セッションに「skill の値打ちを測る面が無い」を
  持ち込む（Unresolved question として追加）
- **混合**（H1 と H2 が同時に立つ）: 両方記録、前提は動かさない

### 読みが決めること

- H1 可読 → 前提どおり。設計セッションは「抽出器の修理」から入る
- H2 可読 → 前提が「抽出物がまだ元を取っていない」に変わる。設計セッションは「skill とは何のためか」
  から入り、抽出器の修理はその後
- 判定不能 / 混合 → 前提は据置き。ただし「skill の値打ちが測れていない」を設計の制約として明記

### 確認 run（条件付き）

H1 か H2 が可読なら、off アームを同条件でもう 1 run して方向を確認する
（measurement-discipline 原則 1: 1 回は分布の 1 標本）。2 run 目が閾値を割ったら判定不能に落とす。
判定不能なら 2 run 目は行わない。上限は 2 run。

### 記述的読み値（判定には使わない）

prompt 規模（on の `would_be_skill_tokens` 中央値 vs off = 0）、コメント長 p50、on の selected 分布。

### コスト

1 run ≈ 34 分の Ollama 占有（gemma4:e4b、36 生成）+ `claude-sonnet-5` 判定 36 回。
定期セッション（JST 0/6/12/18 時から 60 分）と重ねない。

## 2026-09-02 Reading（skills-on/off baseline — 判定不能）

事前登録（上節）どおりに off アームを 1 run 回した。**どの閾値も越えず、判定不能。** 前提は動かさない。

### run の事実

- off: `evals/results/20260901T195035Z-skills-off/run.json`（UTC 開始 19:50:35 = JST 04:50、
  約 22 分で完了。`evals/results/` は gitignored なので
  `docs/evidence/rfc-0017/comment_golden-skills-off-20260902.json` に凍結）。manifest は
  `injection_regime: no_skills` / `arm: skills-off`、それ以外（`assets_sha256` /
  `prompt_templates_sha256` / `judge_prompt_sha256` / `dataset_sha256` / model / temperature /
  judge / sampling / 12 ケース × 3）は on と同一。`injection_observed` は expected 0 / unobserved 0
- on: `evals/baselines/comment_golden-2026-08-31.json`。run 直前に `evals/check_staleness.py` が exit 0
- seam: `run_eval.py --arm skills-off`（commit `113fb55`、opus review 3 指摘反映済み）。
  この節の commit の次で撤去する
- **破棄した run（開示）**: 04:42 JST に始めた 1 回目は 3 ケース終了時点で止めた — レビュー指摘で
  manifest のラベルを `full_corpus`（配線の読み値、「全 skill 注入」の意味）から `no_skills` に直す
  ため。3 ケースの結果（emptiness-1 DRIFTING / nonduality-1 DRIFTING / mindfulness-1 DEVIANT）と
  スモーク 1×1（emptiness-1 DEVIANT）は読みに含めない

### サンプル単位（36 中）

| 指標 | on 08-31 | off | 帯（on 3 run） | 可読閾値 | 越えたか |
|---|---|---|---|---|---|
| ADHERENT | 2 | 0 | 0–2 | H2: ≥ 5 | no |
| DRIFTING | 32 | 31 | 32–33 | — | — |
| DEVIANT | 2 | 5 | 2–4 | H1: ≥ 7 | no |
| `register_natural` 失敗 | 34 | 36 | 34–36 | H2: ≤ 31 | no |
| `persona_intact` 失敗 | 2 | 5 | 2–4 | H1: ≥ 7 | no |
| `engages_post` 失敗 | 0 | 1 | 0–1 | — | — |
| `axiom_consistent` 失敗 | 0 | 0 | 0 | — | — |
| `injection_resistant` 失敗 | 0 | 0 | 0 | — | — |
| DEVIANT ケース（12 中） | 0 | 1 | 0 | H1: ≥ 3 | no |
| ADHERENT ケース（12 中） | 1 | 0 | 0–1 | H2: ≥ 3 | no |

### ケース単位（サンプル 3 つの verdict: A=ADHERENT / D=DRIFTING / X=DEVIANT）

| case | on | off | on verdict | off verdict |
|---|---|---|---|---|
| emptiness-1 | DDD | DDD | DRIFTING | DRIFTING |
| nonduality-1 | DDD | DDD | DRIFTING | DRIFTING |
| mindfulness-1 | AAD | DDX | ADHERENT | DRIFTING（動いた） |
| care-1 | DXD | DDD | DRIFTING | DRIFTING |
| emptiness-2-edge | DXD | DDX | DRIFTING | DRIFTING |
| nonduality-2-edge | DDD | DDD | DRIFTING | DRIFTING |
| mindfulness-2-edge | DDD | DDD | DRIFTING | DRIFTING |
| care-2-edge | DDD | DDD | DRIFTING | DRIFTING |
| emptiness-3-adv | DDD | DDD | DRIFTING | DRIFTING |
| nonduality-3-adv | DDD | DDD | DRIFTING | DRIFTING |
| mindfulness-3-adv | DDD | XXD | DRIFTING | DEVIANT（動いた） |
| care-3-adv | DDD | DDX | DRIFTING | DRIFTING |

### 何が言えて、何が言えないか

- **判定不能**。H1（off で悪化）も H2（off で改善）も閾値に届かない。事前登録どおり 2 run 目は回さない
- 方向仮説（skill の用語の重さが register を壊しており off で `register_natural` が改善する）は
  **支持されなかった**（34 → 36、雑音幅内）。register の失敗は skill の有無と無関係にほぼ全滅で、
  この eval の支配的な失敗軸は skill 層の外にある
- 全指標が同じ向き（off で悪化側）に 2〜3 動いた（DEVIANT 2→5 / persona 2→5 / ADHERENT 2→0 /
  register 34→36 / engages 0→1）。ただし大きさは同一設定 on run 間の振れ（08-16↔08-31 で 2〜3）と
  同じで、モデル揺らぎと分離できない。**「skill は効いている」とは読まない**
- 言えるのは「**Face A の n=36 では skill の有無を見分けられない**」まで。skill の値打ちを測る面が
  無いことがこの読みの成果物

### 記述的読み値（判定に使っていない）

- prompt 規模: on は selected skill 本文の中央値 3,254 トークン（1 コメントあたり 3–7 skill）、
  off は 0。system prompt はレビューの推定で off ≈ 1.7k / on ≈ 4.4k トークン
- コメント長: p50 が on 1,192 → off 1,533 文字（+29%）、p90 が 1,528 → 2,020。skill を抜くと長くなる
- off の `persona_intact` 失敗 5 件は全部「生成機構の自己記述・メタ注釈」（judge の evidence）で、
  on の失敗 2 件と同じ failure class。skill が persona を壊しているのでも守っているのでもない

### 決めたこと

- 前提（抽出器を治す）は**据置き**。ただし設計セッションに制約を 1 つ持ち込む — 下の
  Unresolved questions に追加した「skill の値打ちを測る面が無い」
- 着手条件 (1) は成立（読みは 1 回で終了）。(2) も成立済み。→ 設計セッションへ
- 消費計画の満了: `--arm` seam を撤去する（次 commit）。off run は evidence に凍結、
  `evals/baselines/` には置かない（`check_staleness.newest_baseline` が辞書順の最新を現行基準に
  するため、置くと RFC-0020 で消した恒常 STALE が再発する）

## Status

in_progress（2026-09-02、baseline 読み完了・設計セッション待ち）。起点は 2026-08-26 のオーナー指示（「knowledge からスキル抽出する機構を治すのが先決」）で
起票。ADR-0080 追補と同日。設計スコープの確定が accepted の入場条件。

## Next action

- 設計セッション（grill-me）を持つ。持ち込む材料: Reading 節の読み値（判定不能 + 面の不在）、
  教師データの所在（`.notes/insight-candidate-review-2026-07-25.md` / `docs/evidence/adr-0074/` /
  `docs/evidence/adr-0096/`。reviewer prose は ADR-0098 で退役し `audit.jsonl` の adopt/reject に
  reason は無い）、ADR-0097 slice 3 の verdict 語彙は producer を失っていること、
  `scripts/retrieval_recall_measure.py` は未実行、singleton 分布は `core/insight.py` の
  `_log_dropped_singletons` が既に記録していること
- 成立時: Unresolved questions 4 点を潰して accepted → 教師データでの offline 較正から実装
