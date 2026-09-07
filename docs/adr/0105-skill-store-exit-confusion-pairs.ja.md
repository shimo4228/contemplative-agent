# ADR-0105: skill store の退出に第 2 の信号を足す — 読み手の混同対

## Status

accepted — partially-supersedes ADR-0097

## Date

2026-09-07

## Context

skill store の code 所有の退出路は 1 本しかなく、一度も発火していない。
[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.ja.md) D5 が never-selected
の読み（全履歴 0 回選択、かつ judged exposure 600 以上）を建て、weekly の stage 7b は
2026-08-22（`4163e43`）に入った。これまでに出た週次の読みは **2 回**
（`never-selected-2026-08-28.json` と `-2026-09-04.json`）。2026-09-07 時点で
`skills/.archive/` は 0 件、store は 57 件である。

2 回は薄い根拠であり、本 ADR もそれ以上を主張しない。言えるのは「建てた退出路がまだ人間の
動く候補を挙げていない」までで、「退出路を測って不活性だと分かった」ではない。第 2 の信号を
今足す理由は archive 件数ではなく次段落 — 重複を見られる機構が外れたまま代わりが無いこと。

理由は ADR-0097 D3 の後半にある。あの決定は LLM の grouping / merge / clean 統合器を退役
させ、同時に「この 2 件は同じものが 2 回入っている」と言える唯一の機構も落とした。D3 の
再提案ガードには失効条件「insight 生産側の変質」が付いており、それは 2026-09-02 の RFC-0017
で発火した。つまり問いだけが所有者不在で戻ってきた — store の重複に誰が気付くのか。

毎日それに気付いている読み手が、この repo が持つログの中に既にいる。pass-1 の selector は
`rejected_names`（カタログに無い名前を求めた記録）を出しており、RFC-0015 第 4 読み（窓
2026-08-23〜09-05、judged 1,030）はその 1 件ずつを最近傍の実在名に対して機構分類した —
語形変化 / 意味的取り違え / 値層テキストの混入。規則は 2 か所に凍結されている:
`scripts/skillsel_reading.py::classify`（evidence 文書を生成する手動計器）と
`core/selection_metrics.py::classify_hallucination`（weekly の読み）。読み手がある entry を
**名前を間違えながら指しに来る**のに滅多に選ばないなら、それは store 自身が「この entry は
唯一の消費者に区別されていない」と言っている。

**判定者は code であって local model ではない。** 2026-09-07 の設計セッションが当日時点の
退役研究を一次ソースで照合した:

- 決定論ゲートが主流である: Library Drift（arXiv:2605.19576）、ASSAY（arXiv:2606.15390）、
  SLIM（arXiv:2605.10923）、SkillOps（arXiv:2605.13716）— いずれも LLM の verdict はログに
  残すだけで引き金にしない。
- 引き金にした場合の破綻を The Blind Curator（arXiv:2607.07436、2026-08）が実測した:
  LLM judge の false-pass 偏りが 0.45 を超えると退役が完全に停止し、集約指標には出ない。
  `gemma` に委ねるなら先に欠陥注入で偏りを測る必要がある。
- 寄与ベースの信号は移植できない。Library Drift の (成功−失敗)/試行 も ASSAY の masking も
  タスク成否の ground truth を要し、このプロジェクトはそれを持たない。移植できるのは
  SkillOps 型の AND — 低 utility **かつ** 重複。この AND が、静かなだけの唯一無二の能力を
  消さないための条件である。
- 証拠の床は任意ではない。Library Drift の A4 は証拠不足のまま退役して store を 2 件まで
  崩壊させ、skill 無しの baseline を下回った。

**この予算では merge は archive より悪い。** Retain or Consolidate（arXiv:2607.17545）は、
生の entry が収まる緩い予算では全統合演算が負であると測った — CA の pass 1 は 57 行が窓に
収まる、まさにその予算である。逐次統合は劣化し（AWM 0.64 → 0.20、arXiv:2605.12978）、
SkillCommit（arXiv:2608.15165）は ACE の意味的類似 merge を 3 改善 24 劣化と測った。
archive 型の先例は SLIM の inactive set で、ADR-0097 D5 が既にここに建てている
（`skills/.archive/` + `superseded_by`）。

**天井は数値ではない。** Skill Shadowing（arXiv:2605.24050）は損失の 68% を誤選択・非選択に
帰し、文脈量の寄与はノイズ並みで、小型は abandonment に倒れるとする。Library Drift の上限
50 に導出根拠は無い。消費者側の読み値 — カタログサイズに対する幻覚率 — がこのプロジェクトが
既に持つ物差しであり、`measurement-discipline` 原則 4 はそれを数値キャップで置き換えることを
禁じている。系列は分母つきで、RFC-0015 第 4 読みの**全履歴の条件付け表 1 つから**取る
（行同士が比較できる形にするため）: 19 件 0.57%（n=1,410）→ 37 件 7.72%（n=609）→
48 件 17.38%（n=581）→ 45 件 20.16%（n=630）→ **57 件 24.95%（n=1,094）**。同じ読みの
窓別サマリは同じカタログを短い期間で切って 25.44%（n=1,030）と出す — 別の切り方なので
1 つの系列に混ぜない。エントリ数で単調ではない —
45 件は 20.16% で 48 件の 17.38% を上回り、1 日だけの 50 件レジームは n=23 で 34.78%
（CI [18.8..55.1]）、これがトークン数で見た単調性も破る点である（evidence 文書自身がそう
書いている）。この系列を引くときは分母を必ず一緒に引く。

この試み全体を冷やす読みが 1 つある: ContinualSkillBench（arXiv:2608.03874）は skill 維持
0.602 対 素の ICL 0.605 で差なしと報告する。store を整える集約効果はゼロに近いかもしれない。
したがってこの退出の目的は性能ではなく、**読み手が区別できる store を保つこと**である。

## Decision

weekly の stage 7c が読み手の混同対を読み、その週の archive 候補を書く。無人チェーンは
store に触れない。

1. **規則は code で、層ごとに家は 1 つ。** `core/skill_confusion.py` が読みを組み立て、
   機構分類と最近傍名の物差しは `core/selection_metrics.py` の
   `classify_hallucination` / `nearest_catalog_name` を **import する**（複製しない）。
   `scripts/skillsel_reading.py` は手動計器として残す — stdlib のみで venv の外から走る形が
   RFC-0015 の evidence 文書の前提だからである — そして
   `tests/test_skill_confusion.py` が機構ごとの fixture で両者を突き合わせる。

2. **信号は AND: 需要が無い AND 混同がある。** 直近 14 日の窓について、entry ごとに
   `confused_as`（最近傍がその名前で、機構が `wordform` / `semantic` の rejected 名の延べ数）
   と `selected_window`（それを選んだ judged records）を数える。候補になるのは
   `confused_as >= selected_window` かつ `confused_as > 0` かつ **全履歴**の judged exposure が
   床以上のとき。`value_layer` の混入はどの entry にも計上しない — 読み手が手を伸ばしたのは
   憲法であって skill ではない。

3. **床は ADR-0097 D5 のものを共有する（再導出しない）。** 全履歴 600 judged exposures、
   `NEVER_SELECTED_EXPOSURE_FLOOR` として import する。2 つの退出信号が 2 つの床を持つと、
   同じ週に同じ entry が「証拠十分」と「不十分」の両方になる。窓も同じく D5 の dormant cut
   （14 日）であり、これは下の消費計画が読む ≥ 600 judged records を担保する長さでもある。

4. **対と、どちら側を挙げるか。** 候補ごとに、そこへ計上された rejected 名を、その entry を
   除いたカタログに対してもう一度採点し、最も重い次点を相手とする。対のうち窓の選択数が
   少ない側を挙げる。変異が他のどこにも似ない候補は単独で立ち、自分が挙がる側になる。
   挙がる側が床未満なら、対は報告するが何も挙げない（`retire_blocked: below_floor`）—
   Library Drift A4 の破綻を構造で拒否する。

5. **archive のみ。merge も supersede も数値キャップも入れない。** pipeline は
   `weekly-<end>-archive-candidates.txt` を書く — never-selected strict と挙がった側の和集合、
   重複排除、ソート、1 行 1 件の **store のファイル名**（`adopt-staged --archive-names` が
   指すもの）。チェーンは store に触れない。土曜ゲートがそのファイルを渡すか、渡さない。

6. **fail-forward。** stage 7c の失敗は audit log の `CONFUSION_READING_FAILED` で、両方の
   成果物を消す（候補ファイルの無い JSON はゲートから「片側が空の完全な読み」に見える）。
   読みが答えられないものはすべて `CONFUSION_REASONS` の理由コードで abstain し、ログの
   1 日が失われたときは「対なし」ではなく withheld にする。

## Review-when

### Consumption plan（消費計画）

- **毎週の読み手**: 土曜ゲート（`/weekly-gate`）、Step 6c の never-selected の読みの隣。
  `confusion-pairs-{end}.json` を読み、`weekly-{end}-archive-candidates.txt` を
  `adopt-staged --archive-names` に渡すか、渡さない。
- **判定の読みを誰がいつ取るか**: 天井の読みは stage 7b/7c が出すものでは**ない**。
  `scripts/skillsel_reading.py`（手動計器）が出す幻覚率である。**ゲートが archive したその同じセッションで取る** —
  直近 2 週間についてそのスクリプトを走らせ、カタログ件数を添えた行を
  `docs/evidence/rfc-0014/` に追記する。archive が無ければ読みも due でない
  （下の前提）。手順は `.claude/skills/weekly-gate/SKILL.md` Step 6c が持つ — この配線が
  無ければ消費計画は無音のまま完了しない。それが ADR-0101 の防ぐ失敗である。
- **2 回の読みが決めること**: 天井の背後にあるカタログサイズ仮説の当否。≥ 600 judged records
  の窓 2 つが帯 10〜25% の内 → 仮説は立ち、読みは継続。2 つとも外 → 幻覚率が追っているのは
  カタログサイズではなく、次の一手は退役ではなく**選択時の family 代表化**
  （Right Family, Wrong Skill, arXiv:2606.10388: family から代表 1 件だけ通して
  HSR@3 0.35 → 0.007）— RFC-0021 の Future possibilities。
- **帯とその弱さを明示する。** 10〜25% は導出値ではなく、RFC-0021 の決定行が宣言した範囲で
  ある。現行の 57 件レジーム（24.95%、窓の切り方では 25.44%）は上端にちょうど載るか少し
  出ており、「帯の内」は最初から際どい問いである。これに対し RFC-0015 第 4 読みは、カタログも
  corpus も動かない窓の**日次**幻覚率を 18.67〜35.06% と測っている。窓内の揺れが帯の両端を
  またぐので、2 窓の読みでは判別できない可能性がある。これは後で発見される話ではなく、
  この計画の既知の限界である。2 回が決着しなければ、正直な結論は「帯では答えられない」で
  あって 3 回目ではない。
- **暗黙の前提を書いておく**: 「2 窓とも帯外 → カタログサイズではない」が言えるのは、
  その間にカタログが**動いた**ときだけである。archive 0 件のままなら、帯外という結果は
  「サイズが動かなかった」とも等しく整合する。したがって 2 回の読みは週数でなく
  **archive の後**に due であり、ゲートは各回のカタログサイズも一緒に記録する。
- **撤去条件**: 2 回の読みを取り上の判断を下した時点で、**天井の問い**は閉じる。読み自体は
  ゲートが動く候補を出し続ける限り残す。7b が既に挙げた名前しか出さない週が 1 年続いたら、
  第 2 の信号は何も足していないので stage 7c を module と test ごと撤去する
  （最後の 1 文は本 ADR 独自の締め込みで、RFC-0021 の決定は「2 窓とも帯内 → 継続」で止まる）。

### 失効条件

- 幻覚率の 2 窓がともに 10〜25% の帯の外 → 床を下げるのではなく family 代表化
  （arXiv:2606.10388）へ supersede する。
- selector が変わる（モデル / プロンプトの形 /
  [ADR-0081](./0081-skill-selection-two-pass-injection-enforcement.ja.md) の two-pass
  enforcement）→ `confused_as` は**その**読み手の読み値なので、対の規則は再測定するまで
  信用しない。RFC-0021 の 2026-09-07 の数値は歴史記録になる。
- 600 の床の根拠が変わる — ADR-0097 自身の Review-when 腕（strict never-selected で archive
  した skill が 2 回以上復元される）が発火する、または first-selection latency の分布を
  読み直す → import している同じ数なので本 ADR の床も一緒に動く。
- 混同対で archive した entry が復元される → 対の規則が人間の判断と食い違うものを挙げた。
  1 件は data、2 件目は `>=` の比較そのものが誤った形である。

## Alternatives Considered

### `gemma` を退役の判定者にする（設計セッションの案 B）

「この 2 件は同じ skill か」を local model の verdict で決める（退役した ADR-0097 D3 の
grouping と同じ形）。不採択: The Blind Curator（arXiv:2607.07436）が示す破綻は無音である —
false-pass 偏りが 0.45 を超えると退役が停止し、どの集約指標にも現れない — ので、採用するなら
先に欠陥注入で `gemma` の偏りを測る必要があり、それは退出そのものより大きな仕事になる。
周辺研究も verdict を引き金でなくログへ回している。

### family を 1 本に merge する

ADR-0097 D6 の `adopt-superseding` の語彙が既にあり、これを担える。上の実測
（arXiv:2607.17545 / arXiv:2605.12978 / arXiv:2608.15165）により不採択: 生の entry が収まる
予算では統合は負であり、CA の pass 1 はまさにその予算である。archive は可逆、merge は書き直し。

### store に数値キャップを置く

Library Drift の 50。不採択: 論文にその数の導出が無く、`measurement-discipline` 原則 4 が
消費者側の読み値をキャップで置き換えることを拒み、Skill Shadowing（arXiv:2605.24050）は
文脈量の寄与を誤選択に対してノイズ並みと測っている。ここでの天井は幻覚率の帯である。

### 供給途絶を第 3 の信号にする

RFC-0021 の 2026-09-04 追記が、RFC-0023 の検索で「各 skill に今も行が届いているか」を数える
案を出していた。読み値として残し、引き金にはしない: 時間閾値で退役する skill library の論文が
無く、供給が有って需要が無い skill は description の問題であって退出の問題ではない。

### 混同信号に別の床を置く

ADR-0097 D5 の床を import する方を採った。床が 2 つなら正当化すべき数も 2 つになり、
2 つの信号は結局 1 つのファイルに合流して人間が一度に読む。

### 何もしない

2026-08-22 以降の現状: 退出路 1 本、週次の読み 2 回、archive 0 件、store 57 件、そして
系列全体でカタログサイズと一緒に上がってきた幻覚率（19 件・judged 1,410 で 0.57% → 57 件・
judged 1,094 で 24.95%、全履歴の条件付け表）。不採択 — ただし本 ADR がどちらにせよ抱える弱さも書いておく:
読みが 2 回では「退出路が何も出さなかった」と「退出路がほとんど走っていない」を区別できない。

## Consequences

### Positive

- store が第 2 の退出信号を持つ。判定者は code、証拠の床は第 1 の信号と共有、出力は既存の
  承認経路がそのまま受け取るファイルである。
- どの成果物も持っていなかった事実が読めるようになる: カタログの唯一の読み手が区別できて
  いない entry はどれか。2026-09-07 の dry run が再現したのは **RFC-0021 の 2026-09-04
  追記**（RFC-0015 §4.4 の grouping 表ではない — あれは別の窓・別の数）で、その追記が
  取られた窓 2026-08-29〜09-04 において: 1 件は 34 対 35、もう 1 件は 24 対 30（追記は 23）。
  片方は一致、片方は 1 違い。14 日の運用窓では同じ 2 件が 70 対 78 と 41 対 77 で、どちらも
  候補にならない — pipeline が実際に取る読みはこちらである。
- `nearest_catalog_name` を rejected 名の集計から持ち上げたことで、物差しの第 3 の複製が
  発生しえなくなり、規則が住む 2 か所を parity test が名指しする。

### Negative / accepted

- **2 つの物差しは 3 つの理由で食い違いうる。** `SequenceMatcher.ratio()` が非対称で
  手動 script は被演算子を逆順に取る / core は `autojunk=False` を渡し script は既定のまま /
  core は `sorted(catalog_names)` を回し script は入力順のまま。2026-09-07 に本番ログの distinct rejected 54 件で実測: 機構の不一致
  0 件、最近傍の不一致 5 件、いずれも類似度 0.37〜0.57 — 語形変化の床 0.90 をはるかに下回る、
  そもそも「最近傍」が弱い主張になる帯である。それでも延べ 1 件がどちらの entry に計上される
  かは動き、2026-09-05 の窓では実際に動いた。解消せず test で固定して受け入れる — script の
  被演算子順を変えると `docs/evidence/rfc-0014/` の凍結値が動く。
- **延べ 1 件の対でも候補になる。** `confused_as >= selected` は窓の選択が 0 なら 1 件の
  誤名指しで候補を作る。そこと薄い退役の間に立つのは exposure の床だけである。2026-09-05 の
  窓で出た 1 対は既に never-selected strict に居る名前で、その週は第 2 の信号が何も足して
  いない — 初回運転の正直な読みである。
- **計上には類似度の床が無く、相手側が挙がる側になりうる。** `classify_hallucination` は
  値層トークンを含まない slug 形の名前をどんな距離でも `semantic` と呼ぶので、類似度 0.31 の
  延べも「たまたま表層が最も近い」entry に計上される。次点も類似度 0 超で採るため実カタログ
  では相手はほぼ常に存在し、その相手は候補条件を自分では一度も満たさないまま（要るのは
  露出の床と store のファイルだけ）退役側に挙がりうる。床を置かないのは置くべき導出値が無い
  からで（0.90 の語形変化の床は別の問いに答える数である）、代わりに証拠を出す: 各対は計上
  された延べの類似度の帯と、相手側の最良類似度を JSON と findings の行に持つ。0.3 台に座る
  対はゲートが割り引ける。
- ゲートが読む週次成果物が 1 対増える（ADR-0101 の義務に対して）。存在を許すのが上の消費計画で、
  撤去条件も書いてある。

### Neutral

- stage 7c は never-selected の側を 7b の JSON から受け取るが、混同の側では自分でログを
  歩く。7b と 7c は別プロセスであり、**週はログを 2 回 decode する**。
  `_scan_selection_history` の共有が買うのは速度でなく一致 — judged の定義、窓の切り方、
  rejected 名の正規化が 1 つになる。7b の JSON を読むことが買うのは、7b が落ちた週に
  7c が和集合の片側しか持たないことが JSON と findings の両方で
  `CONFUSION_NEVER_SELECTED_MISSING` と名指され、「候補なし」に見えないことである。
- 読みは窓、床は全履歴という 2 スコープ構成は never-selected の読みが既に持つ形であり、
  スコープはフィールド名が担う。

## References

- [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.ja.md) — D3（本 ADR が部分
  supersede: D3 の解体で手段を失った第 2 の信号を退出路に足す）、D5（never-selected の退出と
  600 の床、再利用）、D6（`adopt-superseding`、意図的に使わない）、D7（rule 昇格、維持）。
- [ADR-0099](./0099-weekly-report-instrument-redesign.ja.md) — findings 節が従う推奨語の禁則。
- [ADR-0101](./0101-instrument-dissolution-mandate.ja.md) — 上の消費計画はこの義務による。
- [RFC-0021](../../rfcs/0021-skill-stocktake-family-saturation.md) — 本 ADR が記録する
  2026-09-07 決定節と、その日時点の出典一覧。
- [RFC-0015 / RFC-0014 第 4 読み](../evidence/rfc-0014/skillsel-read-4-20260905.md) —
  機構分類、幻覚率の系列、§4.4 の grouping 表。
- [2026-09-07 の dry run](../evidence/adr-0105/dry-run-20260907.md) — コマンド、2 つの窓、
  物差しの一致測定、本番ログに当てた読みの中身。
