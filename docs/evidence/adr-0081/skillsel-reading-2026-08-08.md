# T-SKILLSEL: skill-selection 第 2 読み（2026-08-08）— enforcement 後の窓

窓: 2026-07-09〜08-08（30 日、9,357 レコード）。ADR-0081 enforcement 本番 ON（2026-07-24 13:00 JST）を跨ぐ。
ソース: `report --days 30 --skill-selection` + ad-hoc 集計 2 本（scratchpad、read-only、b64 原文は decode せず）。
前回: `skillsel-reading-2026-07-24.md`（窓 07-10〜07-23、enforcement 前。作業ノートのみで未昇格）。

> このファイルは `.notes/skillsel-reading-2026-08-08.md` の昇格コピー（`skillsel-cache-ab-2026-08-05.md` と同じ扱い）。
> ADR-0081 の 2026-08-08 amendment が依拠する測定成果物。

**この窓の読み方の注意**: 30 日窓は enforcement rollout（07-24）と skill corpus の 2.4 倍成長（19→45）を
両方跨ぐ。集計値を窓全体で 1 個の数字にすると、どちらのレジーム変化も平均に溶けて「安定した定常状態」に
見える。実際、報告される fail-open 率 70.9% と幻覚率 2.2% はどちらもこの罠の産物だった（§1・§3）。
**以下はすべて日次に割った上での読み。**

## 1. Verdict サマリ

| 指標 | 窓全体（30 日） | enforcement 後（07-25〜08-08、judged 1,316） | 読み |
|---|---|---|---|
| enforced / judged | 1,403/2,726 = 51.5% | **1,316/1,316 = 100.0%（15 日連続）** | §2。**完全回復** |
| fail-open 率 | 6,631/9,357 = 70.9% | **0/1,316 = 0%** | 見かけの 70.9% は全量が 7/12 の 1 インシデント（前回と同一の 6,631 件）。07-13 以降 **26 日連続 0 件** |
| fail_open_parse | 0 | 0 | 累計ゼロを維持 |
| judged-empty | 0 | 0 | 「判定したが 0 件選択」は一度も出ていない |
| 幻覚率（rejected_names 非空） | 60/2,726 = 2.2% | **52/1,316 = 3.95%** | §3。カタログサイズと強く相関。前回 0.5% から**上昇** |
| selected/action | p50 5.0 / p90 6.0 / max 12 | p50 5.0 | カタログ 2.4 倍でも不変 |
| would-be 削減 | p50 83.8% / p90 90.1% | **p50 87.0% / p10 78.8% / p90 91.4%** | 絶対 p50 ≈17,503 tok。前回 78.9% から上昇（カタログ成長で分母が増えたため） |

## 2. enforced 比率 — 台帳の前提が誤っていた

日次の enforced/judged はロールアウトの階段がそのまま出ている:

| 日 | judged | enforced | enf/judged |
|---|---|---|---|
| 07-10〜07-22 | 58〜116/日 | 0 | 0.0% |
| 07-23 | 116 | 14 | 12.1% |
| 07-24 | 97 | 73 | 75.3% |
| **07-25〜08-08** | 21〜103/日 | 同数 | **すべて 100.0%** |

**T-PLIST-FLAG-REVERT が根拠にしていた「judged 2,141 件中 818 件 = 38% しか効いておらず、残り
1,323 件はフラグ不在によりフル注入に戻っていた」は測定アーティファクトだった。** 2026-08-01 時点の
30 日窓は 07-02〜08-01 で、その 22 日分は enforcement 本番 ON（07-24）**以前**のレコードである。
非 enforced 1,323 件は「フラグが消えた」ではなく「まだ ON になっていなかった」。実際、ON 後の 15 日間で
enforced でない judged は **1 件も無い**。

つまり:

- **フラグ喪失は 30 日窓で一度も起きていない**。`install-schedule` の silent env loss（`cli/schedule.py:142`）は
  機構としては実在するが、被害の実測は存在しない。台帳の「被害が実測された（2026-08-01）」は取り消される
- 同時に、**ADR-0081 の 83% 削減は設計どおり効いている**（ON 後 p50 87.0%）。台帳の「実効は判定成功分の
  4 割弱」「効果測定そのものを歪めている」も同じ理由で取り消される
- ロールアウトは完了している: 15 日連続 100%、fail-open 0、judged-empty 0、幻覚の伝播 0

**→ T-PLIST-FLAG-REVERT の選択肢 (c)「フラグ自体を退役させて enforcement を無条件にする」の着手条件
（"ADR-0081 の rollout が完了しているなら"）を、この読みは満たす。** (a)(b) は (c) を採るなら不要になる。

## 3. 幻覚率 — カタログサイズと相関（新規の発見）

窓全体の 2.2% は、カタログが 19→24→37→45 と成長する過程を平均している。条件付けると:

| catalog_count | judged | 幻覚 | 率 | corpus tok | 期間 |
|---|---|---|---|---|---|
| 19 | 1,410 | 8 | **0.57%** | 20,156 | 〜07-24 |
| 24 | 686 | 4 | **0.58%** | 22,994 | 07-25〜07-31 |
| 37 | 609 | 47 | **7.72%** | 31,009 | 08-01〜08-07 |
| 45 | 21 | 1 | 4.76%（n=21、不安定） | 35,992 | 08-08〜 |

19→24 では動かず、**24→37 で 13 倍**。enforcement の ON/OFF とは境界が一致しない（enforcement は
07-24、跳ねたのは 08-01）ので、**enforcement ではなくカタログサイズが説明変数**。

幻覚名の内訳（上位）は、ほぼ全てが**実在 skill 名の語形変化**であって作話ではない:

| 幻覚名 | 件数 | 実在名 |
|---|---|---|
| `identify-structural-tensions-via-system-metaphors` | 25 | `identifying-…`（gerund） |
| `suspending-interpretation-upon-premise-doubt` | 9 | `suspend-…` |
| `translate-structural-authority` | 8 | `trace-structural-authority` |
| `detecting-abstract-operational-constraint-shifts` | 8 | `detect-…` |
| `interpretative-process-audit` | 4 | `internal-process-audit` |
| `scoping-failure-diagnosis` / `fluids-contextual-anchoring-loop` / `suspension-…` / `interpretive-…` 他 | 各 1 | 同型 |

自由文の混入は 3 件のみ（前回は 3/7 件が自由文）。**selector は名前を逐語コピーせず生成している**、
そしてカタログが長くなるほどコピー精度が落ちる、という読みになる。

**伝播はゼロ**（全件 rejected 止まり、設計どおり）。実害は「選ばれるはずだった skill が落ちる」= 選択の
取りこぼしであって、非カタログ内容の注入ではない。

**未解決の交絡**: 既存 skill store の frontmatter `name` とファイル名の不一致 17/24 件（T-SKILLNAME-BACKFILL、
承認済み・読み後実施）。selector が見るのは frontmatter `name` なので、名前空間の非一貫性が語形変化を
誘発している可能性がある。**backfill は幻覚率の自然実験になる** — 適用前後で 37〜45 件カタログの幻覚率を
比較すれば、「カタログ長」と「名前の非一貫性」を切り分けられる。

## 4. 寡占 — カタログ 2.4 倍でもシェアは落ちない

judged 2,726 件に対する選択シェア（上位）:

| skill | 選択回数 | judged に占める割合 | 前回（19 件時） |
|---|---|---|---|
| `detect-abstract-operational-constraint-shifts` | 2,104 | **77.2%** | 82.1% |
| `cross-reference-foundational-claims` | 2,011 | **73.8%** | 70.8% |
| `extracting-simulation-boundaries` | 1,788 | **65.6%** | 78.1% |
| `fluid-contextual-anchoring-loop` | 881 | 32.3% | — |

**カタログが 19→45（2.4 倍）に増え、selected/action は p50 5 のまま不変**。つまり選択枠は増えていないのに
上位 3 件のシェアはほぼ維持されている。新規 26 件は全て薄い尾に押し込まれた。前回「description 過広の疑い」と
書いた仮説は、この窓で**より強い証拠を得た** — 競合が 2.4 倍になっても勝ち続ける description は、
状況に反応しているのではなく常に真になる条件を書いている。

（2026-07-26 の参照ノートどおり、pass-1 は `name—description` のみを見る。SkillRouter が報告する
「本文を除くと top-1 精度 29〜44pt 落ち」の条件下で動いているので、識別信号が description しかない以上
広い description が勝つのは機構的に予想される挙動。）

**介入は今回やらない**: stocktake の description 監査は 2026-07-24 に実装済みで、必要なのは新規実装でなく
実行。かつ値層への介入は T-CONST-AMEND / T-SKILLNAME-BACKFILL と同時に動かすと帰属不能になる
（ADR-0056「変数は一度に一つ」）。

## 5. never-selected — 4 件、ただし実質 1 件

report は 4 件を挙げるが、露出レコード数で条件付けると 3 件は単に新しい:

| skill | 選択 | 提示された judged レコード数 | 初出 |
|---|---|---|---|
| `pre-processing-state-validation` | **0** | **1,316 / 2,726** | 07-25 |
| `assume-perfect-adversarial-understanding` | 0 | 630 / 2,726 | 08-01 |
| `introducing-intentional-systemic-ambiguity` | 0 | 630 / 2,726 | 08-01 |
| `recognizing-boundary-declarations-in-content-flow` | 0 | 21 / 2,726 | 08-08 |

（露出は **judged レコードのみ**で数える。判定に至らなかった呼び出しで提示された skill は
「拒まれた」のではない — 全レコードで数えると、7/12 のように 1 件も判定が無い窓で
「105 件中 100 回提示」という退役シグナルが出てしまう。実装当初これを取り違えており、
Review で捕捉して修正した。）

**真の never-selected は `pre-processing-state-validation` 1 件**（15 日・1,316 回の機会でゼロ）。
report 自身の注記「check records count first」が正しく機能しており、これは計器が人間に投げている宿題
（§7）。

低選択の尾で意味があるのは、露出が長いのに選ばれない 2 件:

- `anchor-analysis-using-embodied-signals` — judged 2,726 件で 5 回（前回窓で 2 回。30 日でも 5 回）
- `translating-temporal-gaps-into-structural-utility` — judged 2,726 件で 16 回
- `affirm-cognitive-possibility` — judged 1,316 件で 1 回
- `pivot-to-non-optimization-framework` — judged 1,316 件で 7 回

これら 4 件 + `pre-processing-state-validation` が stocktake usage 次元の次回入力。

## 6. fail-open 退避先（T-FAILOPEN-OVERFLOW）

**実発生率は 26 日連続 0**（07-13〜08-08、judged 2,657 件で fail-open 0）。窓内で唯一の発生は 7/12 の
breaker-open インシデントで、これは前回の読みで機序が特定済み（Ollama 側障害、selector は `is_open` を
尊重、publish は無傷）。

一方で**発生時の帰結は変わった**。audit ログ自身の `full_skill_tokens` が corpus 成長を記録している:

| catalog | full_skill_tokens | NUM_CTX 32,768 との関係 |
|---|---|---|
| 19 | 20,156 | 収まる |
| 24 | 22,994 | 収まる |
| 37 | 31,009 | 辛うじて収まる |
| **45** | **35,992** | **超過**（-3,224） |

（前セッションの `_estimate_tokens` による見積 34,264 とは算法差で ~1.7K 違うが、結論は同じ。）

つまり ADR-0081 が設計した fail-open = full-corpus 注入への劣化は、**08-08 以降は budget_exceeded の
skip になる**。読みの分岐条件（台帳: 「稀なら実害は小さく、頻発しているなら (a) の優先度が上がる」）に
照らすと:

**→ 稀（26 日 0 件）。選択肢 (c)「現状を仕様として明記し fail-open = skip を受け入れる」を支持する。**
(a) の退避先設計（直近の判定済み選択・固定サブセットへの退避）は、この読みでは支持されない — signal-first
の原則で、発生していない障害の退避先を先に作らない。

同じ壁は**フラグの off 位置**にも当たっていた: 「selector は動かすが corpus は全量注入する」— それこそが
off の意味であり、45 件ではその構成が窓に入らない。**フラグ退役で失うロールバック先は、退役より前に、
かつ退役とは独立に既に失われていた。**

一方 **kill switch（`configure_skill_selection` の `audit_dir` 未設定）はこれに当たらない**。当初「kill switch を
引くと生成が止まる」と書いたが、Review で誤りが判明した: 本番でこの状態に到達する経路は
`cli/runtime.py:99` の skills ディレクトリ不在の分岐だけで、その分岐は `configure_llm(skills_dir=...)` も
同時に飛ばす。注入する corpus がそもそも存在しないので溢れず、生成は「学習 skill ゼロ」で通る。
kill switch は注入を広げるのでなく**対象を取り除く**ことで selector を無効化する。

## 7. 計器自体の欠落（今回 ad-hoc が必要になった理由）

この読みで `report --skill-selection` だけでは答えられず、ad-hoc スクリプト 2 本を要した集計:

1. **enforced の集計が report に無い** — `enforced` フィールドは全レコードにあり、`observed_injection_outcomes()`
   が集計関数を持つが、窓指定が無く CLI からも呼ばれない。T-PLIST-FLAG-REVERT の判断材料そのものが
   計器から読めない
2. **日次内訳が無い** — 単一集計は窓を跨ぐレジーム変化を平均に溶かす。この窓では fail-open（§1）と
   幻覚率（§3）の**両方**で読み違えを誘発した。前回の読みでも同じ罠に fail-open で嵌りかけている
   （2 窓連続で同じ失敗モード）
3. **never-selected に露出レコード数が付かない** — report は「check records count first」と人間に投げるが、
   その records count を report 自身が持っていない（§5）

1 と 3 は前回 §7 で挙げた「幻覚率が report に出ない」と同型で、あの指摘は ADR-0081 に同乗して解決された。
同じ扱いが妥当。2 は前回には無かった新しい欠落で、**窓が長くなるほど致命的になる**（次の窓は corpus が
さらに育つ）。

**3 点とも同 PR で計器に入れた**（`enforced` 比率 / 日次内訳 / never-selected の judged 露出）。
併せて judged-empty の行と列も足した — ADR-0081 は rollout 完了の判定基準の 1 つにこれを挙げているのに、
report からは読めなかった。日次表は `records = judged + fell-back` が恒等式になるようにしてあり、
fail-open 系だけを数える列にすると catalog 消失の日が「平穏」に見えるのを避けている。

## 8. 次の読み

- **窓**: 次回は 2026-08-22〜09-05 頃。読む対象は (a) 幻覚率のカタログサイズ相関が T-SKILLNAME-BACKFILL
  適用で動くか（自然実験、§3） (b) 寡占が stocktake description 監査で動くか (c) `pre-processing-state-validation`
  が依然 never-selected か
- **交絡管理**: T-SKILLNAME-BACKFILL と T-CONST-AMEND は値層への介入なので一方ずつ。適用日を記録して
  前後を分けて読む（§3 の表がそのままテンプレートになる）
- **自己言及ループ**（選択→生成→蒸留→skills）は、この窓では corpus 成長が交絡して読めなかった。
  カタログが落ち着いてからでないと分離できない
