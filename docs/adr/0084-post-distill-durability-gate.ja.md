# ADR-0084: 蒸留後の durability ゲート — エピソードではなく、生成されたパターンを judge する

## Status

accepted

## Date

2026-07-26

## Context

`distill` はエピソードあたりほぼ一定量を吐いている。2026-07-26 に実測 (launchd stderr
の 1,700 エピソード、`knowledge.json` の live 4,031 行):

| 読み値 | 値 |
|---|---|
| エピソードあたり pattern 数の中央値 | **2.00** (1:313 / 2:985 / 3:392 / 4-6:8) |
| ゼロ件で返したエピソード | **1,700 件中 2 件 = 0.1%** |
| 14 日間の日次 pat/ep | 1.82–2.18 (ほぼ一定) |
| `_is_valid_pattern` による棄却 | 0.7% |
| live pattern の流入 | 約 121/日、800/週 |

プロンプトは以前から abstain を用意していた —「空リストを返せ、空白を埋めるために pattern を
でっち上げるな」— が、1,700 件中 2 件しか発火しなかった。1 日約 68 回の SNS 行動を取る
エージェントが、その 99.9% で durable な何かを学ぶことはない。**出力量は学習量ではなく
活動量の関数になっていた。**

構造的な原因はプロンプトの返却行に 2 つ見えていた
(`{"patterns": ["pattern1", "pattern2"]}` — 1 to 3 patterns、または `{"patterns": []}`):
abstain が判断ではなく出力形式の縮退ケースになっていたこと、そしてそれが件数帯と
**2 要素の例示**と同じ行に置かれていたこと。観測された中央値は例示のアリティと一致した。

ここに至ったのは T-INSIGHT-NOVELTY の再診断からである。元のタスクは weekly novelty gate の
判定軸 (intra-batch を比較しない / name と description の文字列でメタ動作の同一性を見ない) を
欠陥としていた。両方とも棄却した: 2026-07-18 の候補 106 件は staged ledger 経由で
2026-07-25 の run では既に**既知側**に居り (known 166 テーマ、ledger 238 名のうち 121 が同一の
語彙ファミリー)、それでも gate は 97 中 13 しか covered と判定しなかった。第 1 の軸が発火して
いない状態を第 2 の軸は説明しないし、weekly gate は上流で製造された一般性の下流にある。

同じ形は一層上にもある。`insight_extraction.md` は
`Synthesize the learned patterns below into ONE reusable skill.` で始まり、`_extract_skill` は
LLM 失敗とタイトル無しでしか drop しない。したがって ADR-0053 が insight 時点に正本化した
「promotion worth」の判断は「タイトル付き文書を書けたか」を答えている — gate を通った 84
クラスタのうち 78 が skill を生み、**worth を理由に落ちたものは 0 件**。この層は別タスク
(T-INSIGHT-WORTH) で追跡し、本 ADR では触れない。ADR-0056 が「パイプラインの変数は一度に
一つ」を確立している。

## Decision

1. **`distill_episode.md` は変更しない。** このプロンプトを書き換えるたびに、abstain 率と
   出力 register が同時に動いた (Alternatives 参照)。判断はこのプロンプトの中で調整するのでは
   なく、外へ出す。

2. **蒸留後の durability ゲートを追加する** (`config/prompts/distill_postgate.md`、
   `distill._postgate`)。`_is_valid_pattern` の後、1 回の LLM コールがエピソードと番号付きの
   pattern 群を受け取り、`{"keep": [1, 3]}` を返す。judge は成果物を手元に持つ —
   **パターンを実際に書くことが証拠の要求である。**

3. **エピソード単位でなく pattern 単位。** 2 件出したエピソードで 1 件だけが根拠を持つなら
   1 件を残す。これは同時に、収量を distill プロンプトの例示アリティから切り離す —
   件数の指示はどこにも要らなくなる。

4. **judge するものがあるときだけ走らせる** — 空の抽出は既に判断であり、そこにゲートコールを
   使っても何も買わない。

5. **fail open、ただし理由コード付き。** LLM 失敗・parse 不能・shape 不正はすべて全 pattern を
   残し、`reason=postgate_llm_none | postgate_parse | postgate_shape` を記録する。このゲートは
   蒸留器が既に生成した行を*取り除く*ことしかできないので、壊れたゲートは現行の挙動に
   縮退しなければならない。黙って刈り取れば研究データが痕跡なく消える
   (`no-delete-episodes` の感性、ADR-0075 の silent fallback 禁止)。範囲外の添字と bool は
   clamp せず捨てる: judge は見せられていない pattern を残せない。

6. **judged abstain を第一級の理由コードにする。** `ABSTAIN_NOTHING_DURABLE` は 3 つの fault
   理由に加わるが、それらとは**別に集計**され (`FAULT_ABSTAIN_REASONS`)、circuit breaker の
   失敗には数えず、モデル自身が `[]` を返した場合とゲートが最後の 1 件を落とした場合の
   どちらも同じ経路に着く。集計行 `all N episodes produced output` は、常時出力される yield 行
   (yield したエピソード数 + `nothing_durable`) に置き換える — 旧行は judged abstain を
   output として数えており、それこそが 0.1% という欠陥そのものを不可視にしていた。

7. **既定は on、`MOLTBOOK_DISTILL_POSTGATE=0` で opt-out。** ADR-0081 は対応するフラグを
   既定 off で出荷し、本番は launchd plist の `EnvironmentVariables` 経由で通していた。この
   機構は**黙って元に戻る**: `install-schedule` はテンプレートから plist を再生成し、フラグを
   再出力するのは呼び出し元 shell にそれが export されている場合だけである
   (`cli/schedule.py`。コメント自身が "without it to turn it back off" と記している)。素の
   shell から再インストールすると、エラーもログ行もなく enforcement が無効化される — だから
   こそ 2026-07-25 に live plist と手で照合する必要が生じた。distill 側の plist には env の
   配管がそもそも無く、同じ経路を使えばこの故障モードをゼロから作り足すことになる。既定を on
   にすればこの種類ごと消える: 走るのは検証済みの設計であり、opt-out は明示的な行為であって
   失念ではない。ゲートは全経路で fail open なので on であることのコストは現行挙動で上限が
   付き、落とした pattern は再導出可能である — エピソードは永久保存なので、その日のログに
   対して distill を再実行すれば復元できる。

### 測定

決定論的にサンプリングした 40 エピソードの固定集合に対するオフライン A/B replay
(`.notes/replay-distill-abstain-20260726.py`、read-only・本番非配線)。baseline アームが本番の
読み値を再現した (中央値 2、ゼロ率 0.0%、平均 1.83 に対し本番 1.82–2.18)。これが他アームの
差分をその変更に帰属させる根拠になる。register の baseline は本番 890 pattern で、LLM
コールなしで測定。fault は全アームでゼロ。

| | baseline | v2 併合/判定フレーム | v3 併合/蒸留フレーム | v4 前置ゲート | **v5 後置ゲート** |
|---|---|---|---|---|---|
| distill プロンプト | — | 書換 | 書換 | 無改変 | **無改変** |
| judged abstain | 0.0% (本番 0.1%) | 15.0% | 2.5% | 0.0% | **5.0%** |
| pattern 総数 | 74 | 50 | 50 | 81 | **59** |
| pat/ep 中央値 | 2.0 | 1.0 | 1.0 | 2.0 | **1.0** |
| 一人称 | 96.7% | 90.0% | 98.0% | 98.8% | **98.3%** |
| moment 冒頭 | 85.7% | 80.0% | 90.0% | 88.9% | 83.1% |
| `I <知覚動詞>` | 72.8% | 54.0% | 66.0% | 70.4% | **86.4%** |
| 長さ中央値 | 357 | 318.5 | 354.5 | 363 | **358** |

v5 は register を代償にせず量を減らした唯一のアームであり、`I <知覚動詞>` が baseline を
上回るのは幸運ではなく機構的な帰結である — ゲートが落とすのはまさに具体的な瞬間を持たない
pattern なので、削ることで残りの質が上がる。

## Alternatives Considered

### `distill_episode.md` を書き換えて abstain を第一級の選択肢にする (v2)

タスクを判定として枠づけ直す ("Read the episode and decide whether it evidences anything
durable") と、測定した中で最大の abstain 率 15% が出た。独立した 2 回の run で正確に再現
(どちらも 6/40)。棄却理由: 全指標で register が劣化した唯一のアームである —
`I <知覚動詞>` 54% (baseline 72.8%、n=50 で約 3σ)、長さ中央値 318.5 (baseline 357)。
ADR-0072 はその register を意図的に導入し、上流の指示が出力を測定可能に動かすことを実証した。
これはその効果が逆向きに働いた形である。

### 件数帯と 2 要素例示だけを外す (v3)

register は baseline のまま (98.0% / 90.0% / 354.5 字)、総量も v2 と同じだけ減った (74 → 50)。
棄却理由: abstain 率がほとんど動かなかった (2.5%)。分布の峰が 2 から 1 に移っただけで、
「常に 2」が「常に 1」に置き換わった。これは同じ構造的欠陥を低い定数で繰り返すもので
(量は依然として活動量を追う)、しかも変更が実際には解決していない指標 (総数) によって
「欠陥は直った」と宣言されてしまう。

### durability の問いを蒸留の**前**に置く (v4)

エピソードだけを見る独立ゲートで、distill プロンプトは baseline とバイト単位で同一。
測定により棄却: **40 エピソード中 abstain 0 件**、gate fault もゼロなので fail-open が本物の
判断を覆い隠していたのでもない。診断で配線の正常性 (エピソードの差し込み、JSON parse、
`durable` が本物の bool) と非 degenerate 性 (中身のないコントロールは `durable: false` を返した)
の両方を確認済み。yes と答えるのは、**実際に書く義務が無ければ「価値ある瞬間」を名指す
コストがゼロだから**である。この結果こそがゲートを生成の後ろへ動かした理由であり、分割を
動機づけた推論そのものを訂正した — 生成フレームは*バイアス*だと仮定していたが、実際には
*証拠の要求*だった。

### distill 時の LLM importance 採点を再導入する

収束した実践 (Generative Agents の poignancy 採点、D-MEM の Critic Router) が件数ではなく
item ごとの importance 値で収量を制御しているため検討した。棄却: ADR-0053 Decision 1 は
あらゆる価値判断を「その入力が存在する唯一の時点」に置き、生き残っている 2 つの判断時点は
どちらも読み出し時である (query 時の cosine、insight 時の promotion worth)。Decision 4 は
stored score を write-once とし、post-hoc rescoring を self-reingestion echo loop の書き込み面
として棄却している。ADR-0056 はその後、2 回の ablation (n=764 で Kendall tau 0.851、n=822 で
0.843、top-3/top-5 のバッチ順は完全一致) を経て write 時の採点を撤去した。write 時の固定値は
ADR-0019 が検索を views へ移した時点で消費者を失っている。件数の問題は本 ADR では
pattern 単位の判断で解いており、stored score を必要としない。

### 外部メモリフレームワーク (mem0 / Letta / Zep) を採用する

`/search-first` Phase 0。棄却: いずれもサーバ・外部 API・大きな依存木を要求し、
`requests`+`numpy` と security-by-absence の境界 (ADR-0007 / ADR-0015) に反する。**採用した**
収束実践は mem0 の「abstain を出力形式の縮退ケースではなく明示的な action にする」という形。
**意図的に採用しなかった**実践は「atomic normalized fact で書け」で、これは ADR-0072 が
echo 対策として導入した一人称・moment-indexed register と正面衝突する。

`Verdict: Extend — custom (実践を採用、パッケージは非導入)。`

## Consequences

- nightly の distill run は、pattern を生んだエピソードごとに短い LLM コールが 1 本増える。
  実測コスト: 現在このジョブは約 68 エピソードで 03:30 → 約 03:46。ゲートで約 8〜10 分増え、
  04:00 より十分前に終わり、0/6/12/18 JST のセッション窓とも衝突しない。
- durable store の成長は遅くなり (replay: −20%)、行はより強く moment-indexed に
  なる。したがって本 ADR の前後で書かれた pattern は**均質ではなく**、corpus を遡って
  揃え直すことはできない。これは研究記録であり、この不連続は均すのではなくここに記録する。
- judged abstain 率が本番で初めて可読になる。次回の weekly の読み (2026-08-01 頃、n≈470) に
  対する事前登録の撤回条件は、上記 890 pattern の baseline に対して: judged abstain 率が 2%
  未満、または一人称が 90% 未満、または pattern 長中央値が 320 未満のいずれか。
- pattern を生むエピソードでは fault surface が倍になる (2 コール、2 parse 層)。双方を chaos
  fault column がカバーする (`tests/test_distill_chaos.py::TestPostGate`、8 ケース: 選択的
  keep、全 drop → judged abstain、範囲外添字、使用不能な verdict 5 形の fail-open、空抽出時に
  ゲートを呼ばないこと、直接呼び出しは明示 opt-in)。加えて `TestPostGateDefault` が
  スイート全体の上書きを外して本番既定が実際に on であることを assert する — 既定を戻す変更が
  黙って通らないようにするため。
- 測定の誤りを意図的に記録する。結論を左右しかけたためである。最初の register proxy は
  先頭 80 字だけを `I` / `my` で走査していた。プロンプトは各 pattern に**具体的な瞬間を
  名指す**ことを要求し、その結果として長い従属節が先頭に来る — 最初の `I` の出現位置は
  中央値 102 字で、57% の pattern で窓の外に落ちる。proxy は節の長さを測っており、本文全体を
  走査すれば 98% のところを 40% と報告した。この artifact に基づいて候補を 1 つ不合格にし、
  余分なアームを 1 本回した。**register の proxy は pattern 全体を走査すること**、そして
  結論を左右する proxy は、結論を出す前に proxy 対象の実物と突き合わせて検証すること。
- 既存の品質問題が浮上したが、意図的にスコープ外とする: 本番 pattern の 2.9% が終端句読点を
  持たず、1.3% が括弧不均衡である (`_is_valid_pattern` をすり抜けた途中切れ)。この率は全
  アームで同水準なので、回帰ではなく background である。
