# ADR-0096: insight 時の promotion-worth abstain — 生成された skill を judge し、surprise は材料として列挙する

## Status

partially-superseded-by ADR-0097（Decision 2 と 10–12 — 抽出後の worth 判定者と surprise 計器 — は、初回本番の読みが 46/46 promote だったことで本 ADR 自身の事前登録 fallback により 2026-08-22 に退役。Decision 1 と 4–8 — in-band の NOTHING-PROMOTABLE abstain、理由コード、yield 行、fault / verdict の制御分岐 — は効力を保つ）

## Date

2026-08-17

## Context

[ADR-0053](./0053-importance-encoding-time-significance.ja.md) 決定 1 は 3 つの判断点を
「その入力が存在する唯一の瞬間に置く」形で正本化している（うち 1 つ目は後に ADR-0056 が
退役させ、残ったのは 2 つ）。残った側の 1 つが **promotion worth** — insight 時、LLM、
クラスタ全体を入力とする判断で、根拠として `insight.py` 自身の docstring
「LLM extraction drops the cluster if no skill can be distilled」を引いている。
**この引用は実装について一度も真でなかった。** ADR-0053 はここでは意図的に改訂しない —
一度も成り立たなかった根拠をどう扱うかは、本 ADR がオーナーに委ねる判断の一部である。

実装にその経路は無かった。`config/prompts/insight_extraction.md:1` は
`Synthesize the learned patterns below into ONE reusable skill.` という産出命令
（代替の選択肢なし）で、`_extract_skill` が落とす条件はちょうど 2 つ — LLM 呼び出しの失敗と、
タイトルが取れない出力。実際に答えていた問いは **「タイトル付きの文書を書けたか」** だった。

2026-07-25 の run がその差を測っている。ADR-0074 の novelty gate が判定した 97 クラスタのうち
84 が novel として生存、78 が候補を生成し、生成しなかった 6 件はすべて LLM 失敗か無題側 —
**worth を理由に落ちたのは 0 件**（84 − 78 = 6 ちょうど。6 件全部が fault だというのは
当時のコードが持っていた 2 つの drop 条件からの演繹であって、別途の実測ではない）。その後オーナーは 5 件を採用し 73 件を却下した。同 run の
レビューが理由を残している: 候補の約 6 割が 1 つのメタ動作の言い換え（「表層から
構造・制約・境界へ焦点を移す」）だった。2026-08-14 の weekly も独立に同じ読みに達している —
「the whole batch sits between 0.756 and 0.878 cosine against its nearest adopted skill …
the batch is one theme restated 49 ways」、採用 5 / 却下 44。

これは [ADR-0084](./0084-post-distill-durability-gate.ja.md) が 1 層下で直した欠陥そのもので、
同 ADR は本層を次の対象として名指ししたうえで、ADR-0056「パイプラインの変数は一度に一つ」に
従って保留した。その条件は満たされた: distill 側のゲートは 2026-07-26 に land し、以降
weekly が 3 回（08-01 / 08-08 / 08-14）通っており、`core/distill.py` と distill プロンプトに
その後の変更は無い（両者に触れた最後の commit は今も `7b094fc`）。

ADR-0074 決定 8 も同じ絵の一部だ。あの決定はこのプロンプトに「Naming and vocabulary」節を
足した — skill の**名前の付け方**についての実質的な規律で、**存在すべきか**は問わないまま
だった。register collapse は止まらなかった。欠陥が語の選択でなく産出圧力であるなら、
命名の修理はまさにそう振る舞う。

もう 1 つの問いが同行する。2026-07-18 の再設計ノートと D-MEM の Critic Router
(arXiv:2603.14597) はいずれも **surprise**（候補が直近の蒸留結果からどれだけ離れているか）を
この判断の材料として挙げている。ADR-0074 が棄却したのは埋め込みの閾値だが、棄却したのは
*被覆*の主張（「cosine ≥ 閾値 ⇒ 既出」）であり、surprise は*分布*の主張なので射程外である。
設計に入れる前に、2026-08-17 にオーナー自身の 78 件のラベルに対して較正した — LLM ゼロ・
本番非配線で、audit ログの `source_ids` から 78 件すべてのクラスタ centroid を復元した
([`surprise-calibration-20260817.py`](../evidence/adr-0096/surprise-calibration-20260817.py)。
入力は `$MOLTBOOK_HOME` 配下にあり clone には存在しないので、再現可能な成果物はデータでなく
スクリプトの方である):

| 読み値 | 値 |
|---|---|
| `s_mean` の AUC（採否に対して、k=100/300/1000） | 0.786 / 0.762 / 0.767 |
| 順列検定 p | 0.015 / 0.025 / 0.023 |
| 採用 5 件の順位中央値（78 中） | 19（ランダム期待 39.5） |
| 生の max-cosine の幅 / p50（k=1000） | **0.108 / 0.806** |
| 同じ幅を Z 正規化した後 | **約 4.95 sd** |

そこから 2 つのことが出て、向きが逆を向いている。surprise は無情報ではない。そして採否を
再現しない — 陽性 n=5 であり、どの k でも最も surprise の高い候補はオーナーが**却下した**
`operationalizing-systematic-absence` で、まさにオーナーが「飽和している」として刈った
ファミリーの 1 件だった。珍しいことは効くことではない。D-MEM が Utility judge に拒否権を
持たせ、novelty だけでは順位付けしない理由がこれである。Z 正規化の行はより鋭い警告で、
生の分布はこの store の歴史的な最近傍天井で潰れているのに、Z 化は幅 0.1 の帯から
5 シグマの分離を製造する。

## Decision

1. **`insight_extraction.md` に abstain を開ける。ただしタスクの枠組みは変えない。**
   新設の "If there is no skill here" 節により、抽出コールは skill の代わりに
   `NOTHING-PROMOTABLE` の 1 行を書ける。1 行目はバイト単位で不変にする — ADR-0084 の v2
   アームは、生成プロンプトを abstain の問いで*枠組みごと書き換える*と register が全軸で
   劣化することを示した。ここでの病は register collapse そのものであり、治療ではない。
   これは `distill_episode.md` との等価回復でもある（あちらは常に abstain を持っていた）
   — 必要な経路であり、そして ADR-0084 が測ったとおり十分ではない経路。

2. **抽出後の worth ゲートを足す**（`config/prompts/insight_worth.md`、
   `insight._worth_gate`）。抽出・identity-content 検査・パス解決（書き込み先の無い候補は
   ゲートコールを使う前に落とす）の後、1 回の LLM コールが
   生成された skill とそのクラスタ pattern 群を受け取り `{"promote": true|false}` を返す。
   **成果物を生成したことが証拠要件である**: ADR-0084 の v4 アームは durability の問いを
   産出*前*に置き、40/40 で "yes" を得た — 書かなくてよいなら価値を認めるのはタダだからだ。
   1 層上でも同じ形が成り立つと仮定し、それを試すのが下のオフライン確認である。

3. **ゲートは採用済み skill コーパスを見ない。** テーマが既出かどうかは ADR-0074 の
   novelty gate の担当で、抽出の*前*に走る。本ゲートは内在的な問い（そもそも再利用可能な
   behavior があるか）に答える。コーパスを渡せば被覆を二重に数えたうえで worth は依然
   未問のまま残り、audit H6 が生成系の判断をコーパスから隔てている線も曖昧になる。

4. **judged abstain を一級の理由コードにし、fault と分けて集計する。**
   `ABSTAIN_NOTHING_PROMOTABLE` は 4 つの fault 理由（`llm_none` / `no_title` /
   `forbidden_content` / `path_unresolved`）と並ぶが、それらを収容する
   `FAULT_ABSTAIN_REASONS` からは意図的に外れている。抽出コールが in-band で辞退した
   場合もゲートが辞退した場合も同じ経路に着く。平常の週と
   バックエンド障害が同じに読めてはならない。

5. **常時出力する yield 行。** `Insight extraction yield: N/M cluster(s) yielded skills
   (nothing_promotable=K)`、fault があるときだけ追加の WARNING。本 ADR 以前は候補を出さない
   クラスタは*常に*失敗だったので、judged decline が現れうる行が存在しなかった — worth-drop
   率 0% が、それ自体が欠陥の全体でありながら不可視だった理由がこれである。CLI サマリにも
   同じ分割を入れる。

6. **fault / verdict の分割は log だけでなく制御フローを決める。** fault を含む空の run は
   従来どおりエラー文字列を返し、呼び出し側は `.last_insight` を進めない（バックエンド障害で
   窓を消費しない）。fault の無い空の run は空の `InsightResult` を返し、マーカーは進む —
   窓は実際に「検討された」からで、ADR-0074 が all-covered の novelty 判定に適用した論理と
   同じである。

7. **既定 on、`MOLTBOOK_INSIGHT_WORTHGATE=0` で opt-out。** ADR-0084 決定 7 と同じ理由:
   既定 off の flag を launchd plist の `EnvironmentVariables` 経由で運ぶ方式は、
   `install-schedule` が export していない shell から plist を再生成した瞬間に無言で戻る。
   ゲートは全段で fail open なので、on であることの代償は ADR-0096 以前の挙動で上限が付く。

8. **fail open、理由コード付き。** LLM 失敗・parse 不能・`promote` が bool でない場合は
   候補を promote し、`reason=worthgate_llm_none | worthgate_parse | worthgate_shape` を
   記録する。本ゲートは抽出器が既に生成した候補を*取り除く*ことしかできないので、壊れた
   ゲートは今日の挙動へ degrade しなければならない。parse エラーで無言に辞退すれば 1 週間分の
   レビュー材料が痕跡なく消える（ADR-0075、silent fallback 禁止）。

9. **判定は作用させる前に必ず記録する**（`logs/insight-worth.jsonl`、
   `insight._append_worth_audit`）。ゲートコール 1 回につき 1 レコード — topic、クラスタの
   `pattern_ids`、prompt と生出力を base64 + sha256 で — promote も decline も fail-open も
   同じく残す。novelty gate の記録が立つ論拠が 1 段あとでより強く効く: 辞退された候補の
   **本文はどこにも残らない**（残るのは材料の pattern だけ）ので、記録が無ければ良い候補を
   辞退し始めたゲートを診断する材料が無く、yield 行はどれが落ちたかを言えない（ADR-0075）。
   他の audit writer と同じ best-effort で、書き込み失敗は warning のみで run を壊さない。

10. **surprise は列挙する。適用しない**（`core/insight_surprise.py`）。生存した各クラスタに
   ついて、直近 `SURPRISE_REF_K = 1000` 件の live pattern に対する
   `s_mean = 1 − mean cos` と `s_nn = 1 − max cos` をコードで計算する（クラスタ自身の
   メンバーはマスクする — マスクしないと最近傍 cosine が 1.0 に張り付き全候補が同じ値に
   なる）。LLM コールなし、閾値なし、`batches` は不変: 読み値によって落とす・繰り延べる・
   並べ替えることはしない（`read-only-instruments` 不変条件 1、`patterns.md` — 列挙は
   code、決定は LLM か人間）。順位付けは `s_mean` で行う。較正では `s_nn` より安定で
   `k` 依存も小さかった — 最近傍は store の天井に張り付くが、分布の中心は張り付かない。

11. **値は cosine スケールのまま、順位はバッチ内の位置。** Z 正規化しない。sd 尺度の
    フィールドを持たない。各読み値は由来した生の参照分布（`ref_cos_p50` / `ref_cos_spread`）
    を必ず携える — そもそもどれだけの識別力があったかを読み手が見られるようにするためで、
    `read-only-instruments` 不変条件 2 の ambiguity note にあたる。バッチの log 行にも
    その旨を文で書く。**どの分布かに注意**: `ref_cos_p50` / `ref_cos_spread` は
    **候補ごと**の値で、その候補の参照窓に対する cosine の分布である。Context 表の
    0.108 / 0.806 は **78 候補にまたがる**幅で、別の問い（この候補の近傍はどれだけばらけて
    いるか vs このバッチはどれだけ分離可能か）に答えている。互いに比べてはならない。
    バッチ側の値を sidecar のフィールドにしないのは、それが run の性質であって
    レビュアーが手に持っている item の性質ではないからである。

12. **新しい配送機構を足さない**（ADR-0095）。読み値は staging の sidecar `*.meta.json` に
    同乗する。そこは既にレビュアーが候補と出会う場所である（`adopt-staged` が読み、
    `weekly-pipeline.sh` stage 5 が insight-review プロンプトへ丸ごと inline する）。
    run 時には既存の dropped-singleton 計器の隣にバッチ一覧も log する。

### Measurement

2026-07-25 の候補を新しい経路で再抽出したオフライン確認（ローカル Ollama、本番非配線、
staging への書き込みなし・マーカー不変）。クラスタの pattern は `logs/audit.jsonl` の
`source_ids` から `knowledge.json` を引いて復元した（却下された候補の本文はもう存在しないが、
その入力材料は残っている）。標本: オーナーが採用した 5 件全部 + 却下側の決定論的
stride サンプル、n=20。

**結果: ゲートは 1 件も辞退しなかった。この標本では設計は反証されている。**

| 読み値 | 値 |
|---|---|
| 再抽出した候補 | 20（オーナー採用 5 + 却下側の stride サンプル 15） |
| promote | **18** |
| `nothing_promotable` — in-band の辞退 | **0** |
| `nothing_promotable` — worth ゲートの辞退 | **0** |
| fault（`no_title`） | 2（`affirm-cognitive-possibility` / `cross-domain-tension-mapping`） |
| 候補あたりの所要時間の中央値（抽出 + ゲート） | 80.5 秒 |
| 合計 | 27 分 |

オーナーが採用した 5 件は全部生き残った（これは検査の弱い方の半分）。強い方が落ちている:
**この標本の 15 件はオーナーが却下した候補で、ゲートはその全部を promote した。**
promote されなかった 2 件は verdict でなく `no_title` fault であり、2/20 = 10% は
同じ段が 2026-07-25 に示した 6/84 ≒ 7% の fault 率の近くなので、プロンプトの新しい節が
持ち込んだものではない。

理由は、おそらく ADR-0084 が見つけたのと同じ形が 1 軸ずれて出ている。決定 3 は採用済み
コーパスを渡さないので、judge は「これは carry する価値があるか」を、**no と答えうる材料が
入力に無いまま**問われている — 候補は構成上その材料 pattern の忠実な統合なので、
「pattern に根拠がある」は常に真になる。オーナーの 2026-07-25 の実際の基準は
*「この register は既に飽和しているか」*、すなわちバッチの残りと既存 skill 集合との比較で、
それこそがこのゲートに見せないと決めたものである。**worth は内在的でないかもしれない。**
そうだとすれば、durability に効いた「証拠要件」の修理は、ここでは無改変では効かない。

これが許すこと・許さないこと:

- **経路**は本物で、欠けていたのはこれである: 理由コード、fault と分けた集計、yield 行、
  marker 前進の規則、replay ログ。judge が発火するか否かと独立に正しく、独立に検査済み。
- **judge** は機能が示されていない。既定 on で走らせる代償は候補あたり短いコール 1 回
  （週 ~50 件）で、得られるのは率の本番読み値 — 下の事前登録がまさに求めているもの。
  1 週間としては妥当だが、常設機能としては妥当でない。
- **accept 時にオーナーが決める**: (i) 計器として 1 週間 default-on で merge、
  (ii) 基準を見直すまでゲート default-off で merge、(iii) 決定 3 を改めて judge に
  バッチかコーパスを見せる — これは 2 つ目の被覆軸になるので、prompt の編集ではなく
  ADR-0074 の論拠の再開を要する。

run 自体の留保: ここに書いたゲートプロンプトのままだが `wrap_untrusted_content` の枠と
audit レコードを足す**前**に走らせた（プロンプト本文は同一、枠は後付け）。n=20 で陰性 15 件は
小さい標本であり、モデルは本番の `gemma4:e4b` — したがってこれは*この judge* についての
読みであって、問いそのものについての読みではない。

## Alternatives Considered

### プロンプトだけ直して終わりにする

欠陥の字義どおりの読み（「1 行目が産出命令である」）。誤りではなく**不十分**として棄却し、
決定 1 としてゲートと*併せて*採用した: `distill_episode.md` は常に abstain を持っていて、
1,700 エピソード中 2 件（0.1%）しか発火しなかった — それが ADR-0084 の発見である。
生成コールに同居する abstain は産出の指示と競合する。同じコールが書きたいと辞退したいを
同時には持てない。1 行のコストで in-band の「no」を残す価値はあるが、それだけに頼るのは
実測済みの失敗を繰り返すことになる。

### 抽出前の worth ゲート

抽出コールを使う前に「このクラスタに promotable な skill はあるか」を問う（辞退したクラスタは
生成しないので安い）。ADR-0084 の v4 実測により棄却: この問いの産出前の形は、ゲート fault
ゼロで 40/40 のエピソードに "durable" を返した。これが所見である。別途置かれた
**内容のない対照エピソードは `durable: false` を返しており**、それがゲートの故障を除外し、
40/40 を配線ミスでなく実際の判定として読むことを許している。
節約は本物で、判定は degenerate である。

### surprise で順位付けして裾を切る

AUC 0.79 の信号の自明な使い道。較正の数字自身により棄却: 陽性 n=5 では区間の下端がほぼ 0.5 に
届き、どの `k` でも 1 位は却下された候補で、しかもオーナーの選別基準（「この register は
既に飽和しているか」）自体が分布判断なので、相関の一部はオーナーの推論の写しであって独立した
証拠ではない。切ることは `read-only-instruments` 不変条件 1 にも反する。列挙なら人間は使うも
無視するも自由で、閾値は幅 0.1 の cosine 帯に「何がレビューされるか」を決めさせることになる。

### 可読性のために surprise を Z 正規化する

実測により棄却。本 ADR が踏みかけた罠なので記録する。78 件を Z 化すると生の幅
0.108–0.129 cosine が 4.88–6.13 sd になる。何も発見されていない — 表示が、データに無い分離を
製造しているだけで、しかも 2026-08-14 の weekly が独立に「識別できない」と呼んだ分布の上で
そうしている。一般化すると: 生の幅が潰れていないことを示してからでなければ正規化しない。

### 外部の skill 選別手法を採用する

`/search-first` Phase 0（as of 2026-08-17）。最も近い外部研究は
**SkillBrew: Multi-Objective Curation of Skill Banks for LLM Agents**
(arXiv:2605.29440) で、skill bank に対する Pareto 型の多目的選別。手法としての公開で
インストール可能な成果物は無く、候補ごとの abstain ゲートも持たない。採用不能として棄却:
入れるものが存在せず、枠組み（bank を複数目的に対して最適化する）がここでの問い
（*この*候補は入るべきか）と別である。同じ機構クラスの memory framework 走査
（mem0 / Letta / Zep）は 3 週間前の ADR-0084 Phase 0 で実施済みで、server / 依存木の理由
（ADR-0007 / ADR-0015）により棄却されている。その制約は変わっていない。実際に借りている
実践は mem0 の形（abstain を出力フォーマットの縮退形でなく明示的な行為にする）と、
D-MEM の「novelty 信号と utility の拒否権を分ける」構成のままである。

`Verdict: Extend — custom (practice adopted, no package).`

### worth の判断を全部人間のゲートに残す

何もしない案。オーナー自身のレビューが既に 78 件中 73 件を落としており、基準は存在し
適用されている。棄却でなく**記録**として置く — 下の測定がこの案を強くしているからだ。
それでも*経路*を書き残す理由は、ADR-0053 がこの判断は insight 時に起きると主張しており、
コードがそれを実行できなかったこと自体が、機械が発火するか否かに関わらず
アーキテクチャの偽記載だからである。だが、オーナーがうまくやっている判断の一部を小型の
ローカルモデルへ回すのは judge の格下げであり、gemma4:e4b がこの基準を保てる証拠は
何も出ていない。ゲートの本番率が 0% のままなら、ADR はこの案へ戻る — 決定 4〜9
（理由コード・集計・制御フロー・replay ログ）は残したまま。それらこそが、人間だけの基準を
沈黙させず**読めるもの**にしている部分である。

### ADR-0074 の novelty gate に worth を相乗りさせる

既存の抽出前 grouping コールに「worth」軸を足し、候補あたり 1 コール節約する。棄却:
2 つの問いは入力も証拠要件も違う。被覆は生成前に名前と description から答えられるが、worth は
成果物を要する。統合すれば worth の判断が v4 で degenerate と測られた産出前側へ戻り、
どちらか一方の fail-open が両軸の fail-open になる。

## Consequences

- 週次の insight run は、候補を生成したクラスタごとに短い LLM コールを 1 回増やす。直近の
  出来高で週約 50 候補、1 回数秒で、think-ON かつ `num_predict=3000` の抽出コールに比べれば
  小さい。
- **プロンプトの変更が本番に効くのは merge 時ではなく次の土曜ゲートから。** repo の
  `config/prompts/*.md` は同梱既定であり、`$MOLTBOOK_HOME/prompts/` の配備済みコピーが
  優先される（`domain._read_prompt_with_fallback`）。そのコピーが更新されるまで、worth ゲートは
  旧い抽出プロンプトに対して走る — 整合はしている中間状態（発火する方の半分がゲート）だが、
  測定した状態ではない。
- judged worth-abstain 率が本番で初めて読めるようになる。次の weekly に向けた事前登録の読み
  （2026-07-25 の基準 = 84 クラスタから 78 候補、worth-drop 0%）: 率と候補数を報告する。
  両方向を事前登録する。**率 0%**: ゲートは発火しておらず、設計は調整でなく**反証**で
  あり、戻り先は上の「何もしない案」（経路は残し judge を落とす）であって、新しい読みの
  無いままプロンプトを編集しての 2 回目の挑戦ではない。**オーナーなら採用したはずの候補が
  `insight-worth.jsonl` に `verdict: decline` で現れたら**: そちらの方が高くつく失敗で、
  その日のうちにゲートを止める根拠になる。検査できるのは決定 9 が辞退された本文を
  残しているからである。候補数が週 10 件を下回るならレビューバッチは別の問題
  （選ぶものが無い）に置き換わったので、ゲートの基準を採用 5 件に照らして読み直す。
- **辞退された候補は staged theme ledger に載らない。**`_append_insight_ledger`
  （`cli/memory_cmds.py`）が生存した skill を走査するためである。そのテーマは ADR-0074 の
  novelty gate にとって「検討済み」にならず、後の窓で再来し、think-ON の
  `num_predict=3000` 抽出とゲートコールをもう一度払う — まさにゲートが刈るために在る
  飽和テーマについて、毎週。これは ADR-0074 が deferred cluster に定めた規則
  （「人間が見ていないテーマに『検討済み』を与えない」）と同じなのでそのまま採るが、
  反復コストは実在するので後から発見させずここに記録する。
- 候補を生成したクラスタでは fault 面が増える（2 コール、2 parse 層）。chaos の fault column
  （`tests/test_insight_chaos.py::TestWorthGateFailsOpen` 6 ケース: 使えない判定 4 形が
  fail open、散文の判定は parse fault、動いているゲートの辞退は verdict）と、opt-out で
  ゲートコールが 1 度も出ないことを主張する `TestWorthGateDisabledPath`、本番既定が本当に on
  であることを主張する `TestWorthGateDefault`（戻したら黙って通らない）でカバーする。
- surprise は候補あたり最大 1000 件の保存済み埋め込みに対する cosine 1 パスを足すだけで
  （LLM コールに比べれば無視できる）、staging sidecar にフィールドが 1 つ増える。名前の付いた
  消費者を持つ計器である（土曜ゲートの人間と、sidecar を読む weekly insight reviewer）。
  どちらも使わないなら、`read-only-instruments` の signal-first 則に従って温存せず撤去する。
- merge で eval の baseline が失効する。`verify.sh` の advisory な
  `eval-staleness` 検査は `prompt_templates_sha256` を鍵にしており、
  `insight_extraction.md` の編集と `insight_worth.md` の追加でそれが動くので、
  `evals/baselines/comment_golden-2026-08-16.json` は現行システムを測らなくなる
  （ADR-0089）。ゲートではなく advisory だが、eval の再実行と再承認は accept 判断の
  後ではなく一緒に置くべきものである。
- prompt の inventory は 39 → 40 テンプレートになる。正本の件数は
  `docs/CONFIGURATION.md` にあり同じ変更で更新する（`tests/test_packaged_assets.py` が
  dataclass と突き合わせている）。
- 2026-07-25 のバッチは較正集合の正本であり続けるが、それは 1 人が 1 回レビューした 1 run で
  ある。その 5 件の採用は「そのオーナーがその週に欲しかったもの」の ground truth であって、
  promotion worth 一般の ground truth ではない。
