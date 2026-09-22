# RFC-0043 evidence — skill selection の学習なし 5 arm offline 再生（2026-09-19〜20）

一発測定の凍結（ADR-0075 の適用範囲外 — read-only、`$MOLTBOOK_HOME` へは書かない）。読みは軸ごとに並べ、
合成スコアは作らない。判定は [RFC-0043](../../../rfcs/0043-skillsel-offline-arm-replay.md) の Status が持つ。

実行: `scripts/skillsel_arm_replay.py --n 150 --seed 20260919 --arms A,B,C,D,E --order-shuffle`、
2026-09-19 22:00 〜 09-20 04:55 JST（JST 0 時のセッション窓は待機）。150 / 150 行が完走。
生成は gemma4:e4b（Ollama 0.30.11）、arm D は `knowledgator/gliclass-modern-large-v3.0`（MPS）、
arm E は claude-opus-5。arm D の依存は `[dependency-groups] replay`。

| ファイル | 中身 |
|---|---|
| `skillsel-arm-replay-20260920.json` | 第 1 ラウンドの集計（arm 別の幻覚率・選択数・latency、自己一致、天井 arm との一致、skill 別 precision / recall、標本の `selection_id`、`replay_fidelity`） |
| `skillsel-arm-replay-round2-20260920.json` | 第 2 ラウンドの集計（同じ 150 行に arm を足したもの。評価者間一致、合議ラベル、順位指標、近傍を許す一致、較正、癖、cache をそろえた latency 副標本、資源、対の差、全平均の bootstrap 95% CI）。読みは下の「第 2 ラウンド」節 |

situation 本文・デコード済み prompt・LLM の raw 出力はここに置かない。行単位の出力とオーナー裁定用ファイルは
gitignored のローカルにある。下の「追加の読み」は行単位の出力から同日に計算した値で、JSON には入っていない。

## 再実行するときの注意

この測定の arm A（自由生成）は `core.skill_selection.select_applicable_skills` をそのまま呼ぶ。測定時点（commit `0dac8dd` まで）の
本番は temperature 1.0 だったが、RFC-0044 で本番が temperature 0 になった後は、同じ script の arm A も 0 で走り、
arm A0 と同じレジームになる（script 内の `PRODUCTION_TEMPERATURE = 1.0` という前提と、latency 副標本の arm A も食い違う）。
**ここに凍結した数字を再現するなら commit `0dac8dd` を checkout して走らせる。** 行データからの再集計（`--summarize-only`）は
モデルを呼ばないので、どの commit でも同じ結果になる。

## 標本

`verdict == "judged"` の行を、記録上の幻覚あり 75 / なし 75 に層別。`selection_id` の欄が 2026-09-09 以降にしか
無いため、21 日窓 1,664 行のうち 811 行を `no_selection_id` で除外し、残り 853 行から抽出した。
catalog は 53 件 7 行 / 54 件 105 行 / 57 件 38 行。全 arm が同じ行を見る対の設計。

## 再生の妥当性

arm A（現行と同じ自由生成）の幻覚率は rep1 28.7% / rep2 20.7%。production ログの同窓の値（19〜28%）と
同じ帯に入る。system prompt は今日の identity + 憲法から再構成しており、identity 蒸留より前の行は当時と
別の system prompt で再生されている（JSON の `replay_fidelity`）。

## 読み

### 1. 幻覚と選択数

| arm | 幻覚のある行 | 選択数 中央値 / 平均 / 最大 | 失敗 |
|---|---|---|---|
| A free rep1 / rep2 | 28.7% / 20.7% | 6 / 6.0 / 16、6 / 6.2 / 13 | 0 |
| B enum rep1 / rep2 / 順序入替 | 0% / 0% / 0% | 6 / 7.3 / 22、6.5 / 7.3 / 21、6 / 7.1 / 29 | `parse_failed` 1 / 2 / 1 |
| E ceiling | 0% | 6 / 6.0 / 26（none 3 行） | 0 |

enum 拘束で幻覚は構造どおり 0。選択数は中央値が同じで、平均が約 +1.2、最大が 16 → 22〜29 に伸びる。
自由生成には無かった `parse_failed`（約 1%）が新しく出る。

### 2. 自己一致（同じ入力に同じ arm を 2 回）

Jaccard 平均: A↔A 0.384、B↔B 0.390。A↔B は 0.360 で、A の自己一致とほぼ同じ —
**enum 拘束は gemma の判断を変えず、候補外の名前だけを消す。**

### 3. 天井 arm との一致

| arm | Jaccard 平均 | precision | recall |
|---|---|---|---|
| 無作為に k 件（偶然の床） | 0.056 | — | — |
| A free rep1 / rep2 | 0.143 / 0.144 | 0.249 / 0.249 | 0.263 / 0.268 |
| B enum rep1 / rep2 / 順序入替 | 0.158 / 0.157 / 0.154 | 0.252 / 0.246 / 0.249 | 0.313 / 0.318 / 0.308 |
| C logits @topk / @0.5 | 0.162 / 0.116 | 0.268 / 0.117 | 0.307 / 0.966 |
| D gliclass @topk / @0.5 | 0.058 / 0.108 | 0.102 / 0.126 | 0.131 / 0.492 |

- gemma の 3 arm（A / B / C@topk）は 0.14〜0.16 に並び、偶然の床の約 3 倍。互いの差は A の自己一致の
  ばらつき（行ごとに 0.0〜1.0）の中に埋もれる
- **D（GLiClass 未調整）@topk は偶然の床と同じ。** この判断を未調整では担えない
- 150 行すべてで、天井 arm といずれかの arm が割れた。「割れた行だけオーナーが裁定する」設計は
  全行裁定になり、絞り込みとして機能しなかった

### 4. 追加の読み（行単位の出力から）

- **C の確率は yes に張り付く。** skill ごとに単独で「該当するか」を問うと、全スコアの 89% が 0.5 以上、
  中央値 0.995。@0.5 で recall 0.97 / precision 0.12 になるのはこのため。@topk はほぼ同点の中の順位で、
  A との一致も 0.196 と低い。ADR-0084 の「judge する証拠が無いコールは yes に退化する」と同じ形
- **gemma は状況によらず同じ skill を選ぶ癖がある。** arm A は 150 行中 107 行（71%）で同じ 1 件を選び、
  上位 3 件で全選択の 30% を占める。天井 arm は上位 3 件で 18%、最頻でも 69 行。選択頻度の上位 10 件は
  A と B で 9 件が共通、A と E で 4 件が共通
- C@topk と D@topk の一致は 0.016 — 2 つの非生成 arm は互いにほぼ無関係なものを選んでいる

### 5. latency（1 判断あたり、中央値）

A rep1 17.9 秒 / rep2 4.7 秒（rep2 は prompt cache が効いた値）、B 7.1〜7.4 秒、C 51 秒（catalog 件数ぶんの
コール）、D 2.7 秒、E 17.8 秒。cache 条件が同じ A rep2 と B を比べると、enum 拘束は約 1.5 倍遅い。

## 測れなかったこと

- **天井 arm 自身の揺れ**: E は 1 反復だけ。E↔E の自己一致が無いので、0.14〜0.16 という低い一致が
  「gemma の判断が悪い」のか「『どの skill が該当するか』に安定した答えが無い」のかを分けられない
- 集合の一致（Jaccard）は、似た skill が family を作っている catalog では厳しすぎる可能性がある
  （隣の skill を選んでも 0 点）。family 単位の一致は測っていない

---

# 第 2 ラウンド（2026-09-20）

第 1 ラウンドと同じ 150 行に arm を足した（既存 arm は再実行していない。augment 前後で既存 arm の値が同一であることはテストで固定）。
実行は 09:03〜15:07 JST（JST 12 時のセッション窓は待機）、150 / 150 行が完走。生成は gemma4:e4b（Ollama 0.30.11）、
実行機は Apple M1・16 GB。

足した arm: `E2`（opus-5 の 2 反復目）/ `G`（claude-sonnet-5、E と同じ prompt）/ `A0`・`B0`（自由生成・enum を temperature 0）/
`F`（catalog 全件に 1 文字ラベルを振り、先頭トークンの logprob を 1 回で読む）/ `D2`（GLiClass、label を description のみに）/
`B/enum/shuffled2`（候補順の置換を記録する形での再実行）。

ホスト型の判断モデル（Jev）も同じ 150 行で実行したが、提供元の利用規約がベンチマーク・性能情報の公開を禁じているため、
その結果はここにも repo のどこにも置かない（[RFC-0040](../../../rfcs/0040-jev-system-one-local-decision-backend.md)「利用規約の制約」）。

## 読み

### 1. 天井 arm は自分自身とよく一致する — 一致の低さは「答えの無い問い」のせいではない

| 対 | Jaccard 平均 | precision / recall |
|---|---|---|
| opus-5 ↔ opus-5（2 反復） | **0.678** | 0.851 / 0.761 |
| opus-5 ↔ sonnet-5 | 0.436（もう一方の反復とは 0.475） | 0.850 / 0.471 |
| gemma の全 arm ↔ opus-5 | 0.143〜0.162 | 0.24〜0.27 / 0.26〜0.34 |
| 無作為に k 件 | 0.056 | — |

sonnet-5 は選ぶ数が少ない（平均 3.0 件、opus-5 は 5.3〜6.0 件）— 選んだものの 85% は opus-5 も選んでおり、recall だけが低い。
フロンティア 2 モデルは互いに、そして自分自身と、gemma より 3〜4 倍よく一致する。第 1 ラウンドで分けられなかった
「gemma の判断の質か、問いに安定した答えが無いのか」は、前者。

3 票（E・E2・G）の 2/3 多数決を合議ラベルとした場合も並びは同じ: gemma の arm は 0.134〜0.155
（合議に票を入れている 3 arm は、この比較から除外している）。

### 2. interface を変えても判断は動かない

対の差（行単位 bootstrap 95% CI、天井との Jaccard）:

| 差 | 平均 | 95% CI |
|---|---|---|
| 自由生成 t=1 − 自由生成 t=0（sampling の寄与） | −0.008 | [−0.023, +0.007] |
| enum t=1 − enum t=0 | −0.004 | [−0.017, +0.009] |
| 自由生成 − enum（enum が変えるもの） | −0.015 | [−0.032, +0.001] |

どの CI も 0 をまたぐか、かすめる。temperature も enum 拘束も logits 読みも、天井との一致をほとんど動かさない。
選択頻度の arm 間 Spearman も同じことを言う: gemma の生成 arm どうしは 0.84〜0.95、gemma と opus-5 は 0.52〜0.59、
gemma と sonnet-5 は 0.25。

### 3. 幻覚は temperature 0 だけでも大きく減る

| arm | 幻覚のある行 | 選択数 平均 | 失敗 |
|---|---|---|---|
| 自由生成 t=1（2 反復） | 28.7% / 20.7% | 6.0 / 6.2 | 0 |
| **自由生成 t=0** | **7.3%** | 6.3 | 0 |
| enum t=1（4 反復） | 0% | 7.1〜7.4 | `parse_failed` 1〜2 / 150 |
| enum t=0 | 0% | 8.1 | `parse_failed` 1 / 150 |

`parse_failed` は temperature 0 でも出るので sampling の揺れではない。enum は出力 tokens が自由生成の約 2 倍になり
（副標本の中央値 114 対 62 — JSON の枠と引用符のぶん）、`num_predict` に当たりやすい。

### 4. 癖は位置ではなく名前に付く

| arm | 最頻 skill が現れる行 | 上位 3 件のシェア | distinct |
|---|---|---|---|
| 自由生成 t=1 / t=0 | 71% / 77% | 30% / 33% | 46 / 40 |
| enum / enum（候補順を置換） | 78% / **82%** | 26% / 28% | 50 / 46 |
| logits 読み（分解） | 99% | 42% | 41 |
| logits 読み（1 回） | 68% | 30% | 42 |
| opus-5（2 反復） | 46% / 39% | 18% | 53 / 51 |
| sonnet-5 | 21% | 18% | 49 |

候補順を入れ替えても最頻 skill の出現率は下がらない（78% → 82%）。gemma の癖は catalog 内の位置ではなく、
特定の skill（の名前と説明）に付いている。

追加の読み（行単位の出力から 2026-09-20 に計算。JSON の `quirks.per_arm` は行数だけを持ち skill 名を持たない）:
gemma の生成 arm 8 本（自由生成 rep1 / rep2 / t=0、enum rep1 / rep2 / t=0 / 順序入替 2 本）の最頻 skill はすべて同じ 1 件
（`shifting-focus-from-state-to-process-mechanics`）。opus-5 と sonnet-5 の最頻は別の 1 件（`deconstruct-confidence-proxies`）。
opus-5 が gemma の最頻 skill を選んだのは 24 / 150 行と 21 / 150 行、sonnet-5 は 2 / 150 行。自由生成 rep1 がその skill を選んだ
107 行のうち、opus-5（1 反復目）も選んだのは 22 行。選択頻度の Spearman を全ペアで取ると、gemma の生成 arm 8 本どうしは 0.83〜0.98、
gemma ↔ opus-5 は 0.46〜0.60、gemma ↔ sonnet-5 は 0.16〜0.29、opus-5 の 2 反復は 0.98、opus-5 ↔ sonnet-5 は 0.76〜0.77
（上の「読み 2」の 0.84〜0.95 / 0.52〜0.59 / 0.25 は rep1 を軸にした部分集合の値）。
再生での幻覚は行に固有でない: 記録上の幻覚あり 75 行 / なし 75 行で、自由生成 rep1 の幻覚は 18 行（24.0%）/ 25 行（33.3%）、
rep2 は 17 行（22.7%）/ 14 行（18.7%）、t=0 は 8 行（10.7%）/ 3 行（4.0%）。「状況の側に偏りがあって誰もが同じ skill を選ぶ」では、gemma の 71〜84% を説明できない。

### 5. 順位で読むと差が出る — ただし 1 回読みの logits は分解版に届かない

| arm | AUC（95% CI） | 較正誤差 ECE | 観測できた catalog の割合 |
|---|---|---|---|
| logits 読み（skill ごとに分解、約 54 コール） | 0.728 [0.704, 0.750] | 0.766 | 100% |
| logits 読み（1 回） | 0.642 [0.620, 0.664] | **0.116** | **37%** |
| GLiClass（label = description のみ） | 0.627 [0.603, 0.649] | 0.403 | 100% |
| GLiClass（label = name — description） | 0.555 [0.530, 0.579] | 0.365 | 100% |

- Ollama の `top_logprobs` は上限 20（21 以上は HTTP 400）。53〜57 ラベルを 1 回では覆えず、1 回読みは上位 20 件だけが見える
  打ち切り測定になる（観測外は同点最下位として AUC を計算）。AUC が分解版より低いのは、この打ち切りのぶんを含む
- 1 回読みは較正が桁違いに良い（ECE 0.116 対 0.766）。分解版の「ほぼ全部に yes」は、skill を単独で問う形が作っていた
- 1 回読みは catalog の前方に寄る（選んだ skill の位置の中央値 11、他の arm は 21〜31）。ラベル文字の並びに引かれている疑いがある
- GLiClass は label の書き方で 0.555 → 0.627 に動く。未調整の 1 定式化で「届かない」と言い切るのは早かった。それでも gemma の分解版には届かない

### 6. 近傍を許す一致

skill の `name — description` を nomic-embed-text で埋め込み、天井が選んだ各 skill について arm が選んだ中の最大 cosine を平均した値
（soft recall、閾値なし）: 自由生成 0.755 / enum 0.777 / sonnet-5 0.817 / opus-5 の 2 反復目 0.924。無作為 k 件の床は JSON の `random_k_floor`。
Jaccard ほどの開きは無いが、並びは同じ。「隣の skill を選んでいるだけ」では差を説明しきれない。

### 7. latency — cache をそろえた副標本（30 行、arm ごとに行を横断する順）

| arm | 中央値 | 入力 tokens | 出力 tokens |
|---|---|---|---|
| GLiClass | 1.8 秒 | — | — |
| logits 読み（1 回） | 4.9 秒 | 約 3,030 | 1 |
| 自由生成 | 9.8 秒 | 約 3,000 | 62 |
| enum | 13.0 秒 | 約 3,000 | 114 |
| 本番ログの同じ呼び出し（参照、n=1,634） | 19.1 秒 | — | — |

gemma の生成速度は 15 tokens / 秒（t=0 の自由生成、150 行の中央値）。M1 のメモリ帯域幅（公称 約 68 GB/s）÷ ロード済みウェイト 3.3 GB の
理論上限 約 20 tokens / 秒の 75% で、帯域幅で頭打ち。約 3,000 tokens の prompt を読むのに約 4〜5 秒、残りが生成。
**enum は自由生成より遅い**（出力 tokens が倍になるため）。本番が単独コールの約 2 倍かかるのは、セッション中に他の呼び出しと
モデルを取り合うためと見ているが、これは測っていない。

行データ側の latency（第 1 ラウンドの自由生成 rep2 の 4.7 秒など）は、直前の arm が同じ prompt を読んだ cache が効いた値で、比較には使えない。

### 8. 資源とコスト

- gemma4:e4b は 3.32 GB・100% GPU。GLiClass は MPS で確保 1.6 GB（driver 2.2 GB）。測定プロセスの peak RSS 385 MB
- この測定は arm を行ごとに回したため gemma と GLiClass が同居し、16 GB の機体で swap が 17 GB まで膨らんで 1 行あたりの時間が
  約 1.8 倍に落ちた（同時に走っていた無関係な常駐を止めて回復）。複数モデルの測定は arm を直列に回すべきだった
- 評価者のコスト（`claude -p` の envelope が返す API 換算額、150 行）: opus-5 $26.26（1 行 $0.175、出力の中央値 1,373 tokens、API 側 15.3 秒）、
  sonnet-5 $9.30（1 行 $0.062、591 tokens、5.8 秒）

## 測らなかったこと

GPU 使用率（`powermetrics` は sudo が要る）、人間のラベル（正解の代理はフロンティア LLM の合議であって人間の判断ではない）、
本番の 19 秒の内訳、1 回読みの logits を `top_logprobs` の上限が無い経路（MLX / llama.cpp 直）で全ラベル読んだ場合。

---

# 第 3 ラウンド（arm 実装済み、実測待ち）

**この節の読みはまだ空**。arm と test と実行手順だけが 2026-09-22 に入り、150 行の実測は
まだ走っていない。数字が入るまで、ここに書かれた見出しは「何を読むと決めてあるか」であって
読み値ではない（[RFC-0040](../../../rfcs/0040-jev-system-one-local-decision-backend.md)
「第 3 ラウンドと shadow 計器」が読みの順序の正本）。

第 1・第 2 ラウンドと**同じ 150 行・同じ天井**（`E/ceiling` = claude-opus-5）に arm を足す。
既存 arm は再実行しない（`--augment`、既存 label の上書きは実行を止める）。

## 実行条件

- **3 家族を直列に、1 家族 1 呼び出し。** 16 GB の機体に 2 つのモデルを同時に載せない
  （第 2 ラウンドの読み 8: 同居で swap 17 GB・1 行 1.8 倍）。各家族の先頭で
  `ensure_ollama_idle` が常駐モデルに `keep_alive: 0` を投げ、`prelude-<family>` の
  資源 snapshot を aux に残す
- JST 0 / 6 / 12 / 18 時のスケジュールセッション窓は待つ（Ollama を呼ぶ arm のみ。既存の
  `wait_out_schedule`）
- checkpoint は事前に `hf download` し、計測は `HF_HUB_OFFLINE=1` で走らせる（summary の
  `hf_offline` に記録される）。測定中に hub へ出ると、事前に落としたものと別の revision を
  引きうる
- 依存: `[dependency-groups] replay`（`gliclass` と `laya`）。**kev は harness の依存ではなく
  別プロセスの server** で、起動はオペレータが行う

## 足した arm

| label | 何を読むか | 呼び方 |
|---|---|---|
| `H/logits` | 判定モデル（例 `qwen3.5:9b`）に skill ごとの yes/no を問い、first token の `top_logprobs` を読む。arm C と同じ interface・違うモデル | 1 行 catalog 件数ぶんの Ollama コール |
| `H/logits/onepass` | 同じモデルに catalog 丸ごとを 1 コールで問う。arm F と同じ interface | 1 行 1 コール |
| `H/logits/twostage` | `H/logits` の上位 20 件で `onepass`。`top_logprobs` の上限 20 が打ち切りでなく予算になる | 第 1 段を `H/logits` と共有（`latency_shared`） |
| `K/choice` | kev に catalog 丸ごとの choice を問い、`probabilities` から none を除く | 1 行 1 HTTP（`K/noul` と共有） |
| `K/noul` | 同じ応答の skill ごとの noul | 同上 |
| `L/noul` | Laya に skill ごとの noul。checkpoint 既定の 1,024 token 窓、situation は head を残して切る | 1 行 1 `predict` |
| `L/choice/ext` | 同じ agent の `max_len` / `head_max_len` を上げ、catalog 丸ごとの choice。**学習域外の長さ** | 1 行 1 `predict` |

対差（行単位 bootstrap 95% CI、天井との Jaccard@topk）は summary の `paired_differences` が
`H/logits − C/logits` / `K/choice − K/noul` / `K/choice − L/noul` / `K/choice − C/logits` /
`L/choice/ext − L/noul` を名前付きで出す。

## 読み

### 1. 系 A（gemma の logits 読み）を捨てるか — 未実測

### 2. 順位と較正（AUC / ECE / catalog coverage） — 未実測

### 3. 近傍を許す一致と癖 — 未実測

### 4. latency と資源（家族ごとの prelude snapshot つき） — 未実測

### 5. state を切った量（`L/*` の `state_coverage`） — 未実測

### 6. 本番配線に値するか（p ≥ 0.5 の集合が天井の選択にどれだけ入るか） — 未実測

## 測らなかったこと（第 3 ラウンド）

- **kev-4b / kev-9b**: 16 GB では 0.8b 以外を gemma と入れ替えながら回す余裕がない。
  0.8b の読みから上位モデルの値を外挿しない
- **kev の学習域内での挙動**: kev は state 384 token までで学習され、serving は
  「state + 質問 1 つ」で 8,192 token（README、2026-09-22 照合）。CA の situation は
  p50 約 400 / 最大 約 1,800 token なので、**全行が学習域外**。situation を 384 token に
  切って測り直す arm は置いていない（切った state は同じ arm 名を着た別の測定）
- **Laya の学習域内での choice**: `L/choice/ext` は `max_len` を 8,192 まで上げる。
  typed-decisions の既定は 1,024 / head 256 で、57 択だと 1 択あたり 3〜4 token になる
- 第 1・第 2 ラウンドの「測らなかったこと」はそのまま残る

## 実行コマンド

家族の順序は RFC-0040「第 3 ラウンドと shadow 計器」と同じ H → K → L。各呼び出しは
前の呼び出しの `rows.jsonl` を `--augment` で受ける（source は read-only）。

```bash
# 事前に checkpoint を落とす（計測は offline で走らせる）
hf download jaredpalmer/kev-0.8b
hf download convaiinnovations/laya-typed-decisions

# H — 判定モデルを替えた logits 読み 3 本
HF_HUB_OFFLINE=1 uv run --group replay python scripts/skillsel_arm_replay.py \
    --augment .notes/skillsel-arm-replay/round2/rows.jsonl \
    --arms H --decision-model qwen3.5:9b --decision-num-ctx 8192 \
    --require-prefix-cache --latency-subsample 0 --no-embed \
    --out-rows .notes/skillsel-arm-replay/round3-h/rows.jsonl \
    --out-summary .notes/skillsel-arm-replay/round3-h/summary.json \
    --out-aux .notes/skillsel-arm-replay/round3-h/aux.jsonl

# K — kev。server は別プロセス・別 project で起動する（この repo の依存ではない）
KEV_DTYPE=bf16 uv run --no-project \
    --with "kev[serve] @ git+https://github.com/jaredpalmer/kev@90990a5fac2995b9faa3190f7d437e84f2067768" \
    python -m kev.serve --run jaredpalmer/kev-0.8b --port 8009

HF_HUB_OFFLINE=1 uv run --group replay python scripts/skillsel_arm_replay.py \
    --augment .notes/skillsel-arm-replay/round3-h/rows.jsonl \
    --arms K --kev-endpoint http://127.0.0.1:8009 \
    --latency-subsample 0 --no-embed \
    --out-rows .notes/skillsel-arm-replay/round3-k/rows.jsonl \
    --out-summary .notes/skillsel-arm-replay/round3-k/summary.json \
    --out-aux .notes/skillsel-arm-replay/round3-k/aux.jsonl

# L — Laya（同一プロセス）。kev server は止めてから
HF_HUB_OFFLINE=1 uv run --group replay python scripts/skillsel_arm_replay.py \
    --augment .notes/skillsel-arm-replay/round3-k/rows.jsonl \
    --arms L --laya-device mps --latency-subsample 0 \
    --out-rows .notes/skillsel-arm-replay/round3/rows.jsonl \
    --out-summary .notes/skillsel-arm-replay/round3/summary.json \
    --out-aux .notes/skillsel-arm-replay/round3/aux.jsonl
```

`--no-embed` は H / K の呼び出しでだけ付ける（soft agreement の埋め込みは nomic-embed-text を
ロードするので、判定モデルと同居させない）。3 本目の L で全 arm が 1 ファイルに揃うので、
そこだけ埋め込みを許す。kev の commit は起動時に固定した HEAD（2026-09-22）。
