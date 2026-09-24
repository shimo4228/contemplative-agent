# RFC-0043 evidence — skill selection の学習なし 5 arm offline 再生（2026-09-19〜20）

一発測定の凍結（ADR-0075 の適用範囲外 — read-only、`$MOLTBOOK_HOME` へは書かない）。読みは軸ごとに並べ、
合成スコアは作らない。判定は [RFC-0043](../../../rfcs/0043-skillsel-offline-arm-replay.md) の Status が持つ。

この測定を実行した harness（`scripts/skillsel_arm_replay.py`、Jev arm の client `evals/jev_arm.py`、
それぞれのテスト、`pyproject.toml` の `[dependency-groups] replay`）は RFC-0043 の後始末（S26）で撤去した。
下の実行コマンドを再現するなら撤去 commit の親 `817ecf3` から取り出す —
`git checkout 817ecf3 -- scripts/skillsel_arm_replay.py evals/jev_arm.py tests/test_skillsel_arm_replay.py tests/test_jev_arm.py`、
replay group は `git show 817ecf3:pyproject.toml` から該当節だけ写す。公開ツリーに非公開 arm の label が
入らない検査（`tests/test_jev_results_stay_private.py`）は撤去後も残してある。

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

# 第 3 ラウンド（2026-09-22 実測 — ローカル判断モデルは gemma に届かない）

凍結 JSON: `skillsel-arm-replay-round3-20260922.json`（L の完走 summary。第 2 ラウンドの全 label を
`--augment` で引き継いだ 150 行の上に `L/noul` / `L/choice/ext` が乗る。H は 4 行、K は 25 行で
打ち切ったので凍結せず、数字だけを下に書く）。天井は第 1・第 2 ラウンドと同じ `E/ceiling`
（claude-opus-5）。読みの順序の正本は [RFC-0040](../../../rfcs/0040-jev-system-one-local-decision-backend.md)
「第 3 ラウンドと shadow 計器」。

**結論**: 3 家族とも本番配線の候補にならない。系 A（別の凍結 LLM の logits）は latency で失格、
Laya は質が無作為と区別できず、kev は Apple Silicon で 1 リクエストを serve できない。詳細は読み 1〜6。

## 実行条件

- 3 家族を直列に、1 家族 1 呼び出し（`--augment` 連鎖）。各家族の先頭で `ensure_ollama_idle` が
  常駐モデルを `keep_alive: 0` で降ろし、`prelude-<family>` の資源 snapshot を aux に残した
- **対話中の測定**（オーナーが同じ機体で作業中）。swap は測定開始時 6 GB、Laya 走行中 9.5〜13 GB。
  20:07〜20:37 JST は別セッションの全ディスク検索（`bfs`）と重なり、その間の L の行（約 100〜116
  行目）は latency が 2〜5 倍に膨れている。20:38 に L のプロセスを作り直して（`--resume`）元の帯に戻った。
  **latency は条件付きの読み**で、質（scores）は影響を受けない
- JST 18 時の本番セッションは L を 17:48 に止め 19:05 に `--resume` で避けた（in-process の arm は
  `wait_out_schedule` を通らない — harness の穴。下の「測らなかったこと」）
- checkpoint は事前に `hf download`、計測は `HF_HUB_OFFLINE=1`（summary `hf_offline: 1`）。Laya は
  `convaiinnovations/laya` の snapshot `1c5edc17` の `typed-decisions`（agent 自身の tokenizer を使う。
  Hub の tokenizer 読みは subfolder 構成で失敗した — commit `f54c8dd`）。kev は commit `90990a5f`、
  base `Qwen/Qwen3.5-0.8B-Base` revision `dc7cdfe2`
- Ollama 0.34.2、gemma4:e4b は判定側では使わない

## 足した arm

| label | 何を読むか | 実際に走った形 |
|---|---|---|
| `H/logits` | 判定モデルに skill ごとの yes/no を問い first token の `top_logprobs` を読む（arm C と同じ interface） | **qwen3:8b**（当初の qwen3.5:9b は hybrid 線形注意で Ollama の prefix cache が効かず 1 コール 5.3 秒 → 1 行 288 秒で `prefix_cache_absent` 停止）。qwen3:8b は cache が効き 1 行 43〜74 秒。**4 行で打ち切り** |
| `H/logits/onepass` | catalog 丸ごと 1 コール（arm F と同じ interface） | qwen3:8b、1 行 24〜44 秒、4 行 |
| `H/logits/twostage` | `H/logits` の上位 20 で onepass | 4 行 |
| `K/choice` | kev に catalog 丸ごとの choice | **分割リクエスト**（`--kev-questions choice --kev-noul-batch 14`）。設計どおりの 1 リクエスト（約 6,000 token）は MPS で 12.5 GiB を要求し全行 HTTP 500。choice 単独（約 2,300 token）は 1 行 5.4〜8.2 秒で通るが、server の MPS allocator がリクエスト間で解放されず 17 行目以降が全滅。**25 行で打ち切り** |
| `K/noul` | 同じ行の skill ごとの noul | 未実測（1 noul 約 1 秒 → 1 行 55 秒。本番の形にならないので後回し） |
| `L/noul` | Laya typed-decisions に skill ごとの noul、1,024 token 窓、situation は head を残す | 150 行完走 |
| `L/choice/ext` | 同じ agent の `max_len` 8,192 / `head_max_len` 選択肢数 × 50 で catalog 丸ごと choice（学習域外） | 150 行完走。Laya 自身が「choice の選択肢 11 件以上の bucket は temperature 範囲外で confidence 未較正」と警告 |

## 読み

### 1. 系 A（別の凍結 LLM の logits 読み）— 質を測る前に latency で捨てる

| arm | 1 行 | 現行（本番ログ、第 2 ラウンド §5） |
|---|---|---|
| `H/logits`（qwen3:8b、54 コール、prefix cache あり: 初回 14.2 秒・以降中央値 0.63 秒） | 43〜74 秒（4 行） | 19.1 秒 |
| `H/logits/onepass`（1 コール、約 3,000 token） | 24〜44 秒 | — |
| gemma enum（arm B、cache をそろえた副標本） | 13.0 秒 | — |

8〜9B の凍結 LLM に 55 件の判定を logits で読ませると、prefix cache が効いても現行の 2〜4 倍遅い。
H − C の対差（質）は 4 行では読めないが、RFC-0040 の判定規則は「latency が本番の窓に収まる」を
前提に置いていたので、系 A はここで落ちる。qwen3.5 系（Gated DeltaNet の hybrid）は Ollama で
部分 prefix の KV を再利用できず（probe: 同一 prompt 再送 0.3 秒、suffix 違いは 7〜9 秒）、判定用途に
最も向かない。`prompt_eval_count` は cache hit でも全 token 数を返すので、harness の reuse 判定は
`prompt_eval_duration` に替えた（commit `5eed66e`）。

### 2. 順位と較正 — Laya は無作為と区別できない

| arm | Jaccard@topk（95% CI） | AUC（95% CI） | ECE | soft precision（床 0.695） |
|---|---|---|---|---|
| `C/logits`（gemma、第 2 ラウンド） | 0.162 [0.141, 0.182] | 0.728 [0.704, 0.750] | 0.766 | 0.766 |
| `L/noul` | **0.075 [0.062, 0.089]** | 0.587 [0.561, 0.611] | 0.469 | 0.701 |
| `L/choice/ext` | **0.051 [0.041, 0.061]** | 0.477 [0.455, 0.499] | 0.091 | 0.686 |
| 無作為に同じ件数 | 0.056 | 0.5 | — | 0.695 |

`L/noul` の確率は 0.5〜0.7 に固まり（8,207 判定のうち 6,382）、その bucket の hit rate は 10〜14%。
`L/choice/ext` は 54 択で確率がほぼ全部 0.1 未満（8,204 / 8,207）、順位は当てずっぽう以下（AUC 0.48）。
ECE が小さく見えるのは全部低い確率に張り付いているからで、較正が良いのではない。
拡張窓の choice は noul より悪い（対差 −0.025、CI [−0.041, −0.008]）。

### 3. 近傍を許す一致と癖

soft precision は L の両 label とも床（0.695）の上に乗らない。gemma の各 arm は 0.75〜0.78、
opus の自己一致は 0.95。隣の似た skill を選んでいるのでもなく、選び方が situation と相関していない。

### 4. latency と資源

| arm | 1 行 中央値（150 行） | 最小 | 副標本（30 行、arm-major） |
|---|---|---|---|
| `L/noul`（54 問を 1 `predict`、MPS） | 39.4 秒 | 6.8 秒 | 49.5 秒（19.7〜809 秒） |
| `L/choice/ext`（1 `predict`） | 10.5 秒 | 1.7 秒 | 25.1 秒（1.9〜95 秒） |
| `K/choice`（kev、分割、25 行） | 6.9 秒 | 5.4 秒 | — |

Laya の公表値（T4 で 1 問 33 ms、batch 7 ms、CPU 190〜460 ms）に対し、この機体の MPS では
1 問 0.35〜0.65 秒。中央値は対話中の swap（9.5〜13 GB）と別セッションの検索が乗った値で、
プロセスを作り直した直後の帯は noul 10〜20 秒・choice 1.7〜2.1 秒。最小値がその機体の素の値に近い。
kev-0.8b は `flash-linear-attention` が CUDA 専用のため MPS では reference kernel に落ち（server の
起動ログ）、系列長で 2 乗に膨らむ。wired は Laya 走行中 3.2 GB、別の GPU 利用が重なると 5.8〜7.9 GB。

### 5. state を切った量

`L/noul` の `state_coverage` は中央値 1.0、平均 0.990、最小 0.514（切ったのは 1 割の行）。
`L/choice/ext` は窓を伸ばしたので 1.0。入力の欠落が質の説明にならない。

### 6. 本番配線に値するか — 該当なし

RFC-0040 の判定規則（候補 − `C/logits` の Jaccard@topk の CI が正の側で 0 を含まない）を満たす
候補は無い。L は負の側（−0.09 前後）。K は 25 行で CI を引かない。H は 4 行。

**帰結**: 2026-09-22 時点で、ローカルで動く判断モデルのうち skill selection で gemma4:e4b の
自由生成（temperature 0）を質で上回るものは見つからなかった。ADR-0112 の seam は
「読み出し専用に留め、sibling backend は作らない」の側で読む（同 ADR Review-when 第 3 項）。
候補が変わる条件は 3 つ — kev の MLX backend（Apple で 1 リクエストが serve できる）、
Laya を CA の decision trace で fine-tune する（学習は禁止でない — 教師は gemma でなく opus の合議）、
Jev 本体の open weights。

## 測らなかったこと（第 3 ラウンド）

- **kev-4b / kev-9b**: 16 GB では 0.8b 以外を gemma と入れ替えながら回す余裕がない。
  0.8b の読みから上位モデルの値を外挿しない
- **kev の学習域内での挙動**: kev は state 384 token までで学習され、serving は
  「state + 質問 1 つ」で 8,192 token（README、2026-09-22 照合）。CA の situation は
  p50 約 400 / 最大 約 1,800 token なので、**全行が学習域外**。situation を 384 token に
  切って測り直す arm は置いていない（切った state は同じ arm 名を着た別の測定）
- **Laya の学習域内での choice**: `L/choice/ext` は `max_len` を 8,192 まで上げる。
  typed-decisions の既定は 1,024 / head 256 で、57 択だと 1 択あたり 3〜4 token になる
- **K/noul と H の質**: K は 25 行、H は 4 行で止めた。どちらも本番の形（latency）で落ちたので
  質の CI を引くだけの行を回していない
- **in-process arm の窓待ち**: `wait_out_schedule` は Ollama arm だけを gate する。L / K は本番
  セッションと同居しうるので、手で止めて `--resume` した。harness 側の 1 行修正は未着手
- **無人窓での latency**: 対話中の swap と別セッションの負荷が乗った値しか無い。素の値は各 label の
  最小値を目安にする
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

# 第 4 ラウンド（2026-09-24〜 — kev-MLX と von を dev 30 / holdout 120 で読む）

読みの順序と判定規則の正本は [RFC-0040](../../../rfcs/0040-jev-system-one-local-decision-backend.md)。
harness は `817ecf3` から復元し、arm `V`（von）・K / V の窓待ち・候補の対差（候補 − `C/logits`、
候補 − `B/enum/rep1`）を足した（commit `9e259df` / `bdfdd1c` / `2e48b41`）。天井 arm（E / E2 / G）は
再実行しない — 第 1・第 2 ラウンドの label をそのまま使う。

## split（候補を走らせる前に固定）

- 元: 第 3 ラウンドの 150 行（`L` まで全 arm の label 入り）
- seed `20260924`、`stratified_sample` と同じ層別（記録上の幻覚あり / なし、`selection_id` 順に並べてから抽出）で
  **dev 30 行（幻覚あり 15 / なし 15）**、残り **holdout 120 行（60 / 60）**。行は元ファイルのまま写した
- 再集計は `--days 30`（150 行は 2026-09-09〜19 の log。既定 21 日だと 2026-09-30 以降に窓から外れる）

## 基準線（候補より先に凍結 — 2026-09-24 20:45 JST）

天井 `E/ceiling`（claude-opus-5）に対する Jaccard@topk（k = 同じ行の `A/free/rep1` の選択数。
set arm はそれ自身の集合）の平均と行単位 bootstrap 95% CI（2,000 回）。`E/ceiling` 自身の行は
定義上 1.0 なので、天井の揺れとして opus の自己一致（`E2/ceiling/rep2` 対 `E/ceiling`）を置く。

| split | `B/enum/rep1` | `C/logits` | opus 自己一致（E2 対 E） | `G/rater/sonnet` 対 E |
|---|---|---|---|---|
| dev（30 行） | 0.177 [0.136, 0.223] | 0.175 [0.128, 0.224] | 0.672 [0.590, 0.746] | 0.442 [0.353, 0.535] |
| holdout（120 行、B は 119） | 0.154 [0.132, 0.175] | 0.159 [0.137, 0.182] | 0.680 [0.640, 0.721] | 0.434 [0.399, 0.472] |

併記（判定に使わない）: `C/logits` の AUC は dev 0.750 [0.702, 0.796] / holdout 0.723 [0.696, 0.748]、
ECE 0.742 / 0.772。近傍を許す一致（soft precision）は dev で `C/logits` 0.781・`B/enum/rep1` 0.774・
無作為床 0.704、holdout で 0.762・0.751・0.696。

## 事前登録した判定規則（読みの前に固定）

- **smoke（dev の先頭 5 行）pass** ⇔ 5 行すべて answered、1 行 latency 中央値 < 20 秒、走行中の
  `vm.swapusage` used が開始時 +3 GB 以内
- **dev（30 行）pass** ⇔ (候補 − `C/logits`) の Jaccard@topk 対差の bootstrap 95% CI 下限 > −0.02 **かつ** 平均 > +0.05
  （AUC と ECE は併記、判定に使わない）
- **holdout（120 行）pass** ⇔ (候補 − `C/logits`) と (候補 − `B/enum/rep1`) の対差 CI がともに正側で 0 を含まない。
  p ≥ 0.5 集合の天井に対する precision を分母付きで併記
- holdout は 1 候補 1 回、ループ全体で 3 回まで。choice / noul の 2 label は同時に走らせ label ごとに規則を当てる

## 実行条件

- 2026-09-24 20:53〜21:17 JST、**対話中の測定**（オーナーの別セッションが同じ機体で稼働）。JST 0/6/12/18 時の窓には
  かからなかった（K / V は今回から harness の窓待ちを通る）。swap は測定開始時 4.3〜7.8 GB — 前の候補の膨張が
  macOS に回収されきらないまま次へ進むので、swap の規則は各走行の**開始時からの増分**で読んだ
- 各候補の先頭で gemma と nomic-embed-text を `keep_alive: 0` で降ろした（`ollama ps` が空であることを候補ごとに記録）。
  server は候補ごとに別プロセス・別 project（`uv run --python 3.13 --no-project --with …`）で起動し、checkpoint は
  事前に `hf download`、serve は `HF_HUB_OFFLINE=1`
- **kev**: commit `62c91838`（2026-09-24 HEAD）。kev-0.8b は起動ログで `on mps via mlx (bfloat16)` を確認（MLX backend、
  torch に落ちていない）。kev-0.5b（Qwen2.5-0.5B の attention-only 試作）は `jaredpalmer/kev-0.5b@9ce2fd39` を
  `on mps via torch (bfloat16)` で serve — kev README が Qwen3.5 以外に文書化している PyTorch MPS 経路。
  serving temperature は 1.00 と表示された（モデルカードの T = 1.47 は反映されていない）
- **von**: `von-sdk==1.2.2`、checkpoint `wfzyx/von@5df8185a`（`option_marker.pt`、input-conditioned calibration map を
  ロード）、`on Apple Silicon [MPS]`。実機の 1 リクエストで kev と同じ JSON 形（`answers{id: {noul} | {probabilities}}`）を
  確認。von は server 側の例外をすべて HTTP 422 で返すので、arm V では 422 を長さ超過として読まない
- 埋め込み（soft agreement）は smoke / dev では取っていない（`--no-embed`）。候補が holdout に届かなかったので
  近傍を許す一致は測っていない

## 候補ごとの読み

形の記号: **1 本** = 設計どおり choice と全 noul を 1 リクエスト（2 label が latency を共有）、
**分割** = `--kev-noul-batch 14`（choice 単独 + noul 14 件ずつ。label に `/split`）。

| 候補 | 段 | 形 | answered | 1 行 latency 中央値 | swap（開始 → 最大） | 規則 |
|---|---|---|---|---|---|---|
| kev-0.8b（MLX） | smoke | 1 本 | 5 / 5（入力 約 9,100〜9,400 token） | 22.7 秒 | 4.3 → 15.2 GB（+10.9） | **fail**（latency・swap。+6 GB の打ち切り線も超え） |
| kev-0.8b（MLX） | smoke | 分割 | 5 / 5 | choice 2.1 秒 / noul 6.7 秒 | 7.1 → 11.8 GB（+4.8） | **fail**（swap。同じ失敗 2 回で候補を落とす） |
| von 1.2.2（MPS） | smoke | 1 本 | 5 / 5 | 28.0 秒 | 6.8 → 6.8 GB（増えず） | **fail**（latency） |
| von 1.2.2（MPS） | smoke | 分割 | 5 / 5 | choice 1.4 秒 / noul 29.3 秒 | 6.5 → 6.5 GB | `V/choice/split` pass、`V/noul/split` **fail**（latency 2 回目で落とす） |
| von 1.2.2（MPS） | dev | choice のみ | 30 / 30 | 1.4 秒 | 6.1 → 6.1 GB | 下表 — **fail** |
| kev-0.5b（torch MPS） | smoke | 1 本 | 3 / 5（2 行 MPS out of memory → HTTP 500） | 22.6 秒 | 6.0 → 9.7 GB（+3.8） | **fail** |
| kev-0.5b（torch MPS） | smoke | 分割 | 5 / 5 | choice 2.5 秒 / noul 8.7 秒 | 7.8 → 7.8 GB | pass |
| kev-0.5b（torch MPS） | dev | 分割 | choice 22 / 30、noul 21 / 30（22 行目以降 MPS out of memory） | choice 2.5 秒 / noul 8.6 秒 | 6.5 → 10.2 GB（+3.7） | 下表 — **fail** |

dev（30 行）の対差（行単位 bootstrap 95% CI、2,000 回。n は候補が答えた行）:

| label | Jaccard@topk | − `C/logits` | − `B/enum/rep1` | AUC | ECE | dev 規則（下限 > −0.02 かつ 平均 > +0.05） |
|---|---|---|---|---|---|---|
| `V/choice/split` | 0.048 [0.027, 0.070]（n 30） | −0.127 [−0.168, −0.087] | −0.129 [−0.172, −0.092] | 0.531 [0.482, 0.577] | 0.117 | fail |
| `K/choice/split`（kev-0.5b） | 0.138 [0.088, 0.195]（n 22） | −0.044 [−0.101, +0.021] | −0.047 [−0.119, +0.023] | 0.650 [0.594, 0.709] | 0.109 | fail |
| `K/noul/split`（kev-0.5b） | 0.120 [0.061, 0.198]（n 21） | −0.063 [−0.128, +0.015] | −0.075 [−0.151, +0.012] | 0.635 [0.578, 0.690] | 0.046 | fail |

同じ dev 30 行の基準線は `C/logits` 0.175、`B/enum/rep1` 0.177、無作為に同じ件数を選んだ場合は第 3 ラウンドで 0.056。
von の choice は無作為と区別できず（AUC 0.53）、kev-0.5b は gemma を下回る側に平均が寄る（CI は 0 をまたぐ）。
**holdout には 1 候補も進んでいない**（holdout の読みは 0 回消費）。

## 読み

1. **kev の MLX backend は catalog 丸ごとの 1 リクエストを serve できるようになった**（第 3 ラウンドは MPS で全行 HTTP 500）。
   ただし 0.8B のモデルに対して server の phys_footprint が 12 GB に達し、16 GB 機では swap が 1 リクエスト目から
   +11 GB 膨らむ。分割しても +4.8 GB。kev の serve に MLX のメモリ上限を与える設定口は無い（env は `KEV_PREFIX_CACHE` 等のみ、
   2026-09-24 の source で確認）ので、この機体では質を読む前に資源の規則で落ちた
2. **von は資源では通るが質で落ちる**。ModernBERT 395M で swap は増えず、choice は 1 行 1.4 秒。ただし 55 問の noul は
   問ごとに forward するので 1 行 29 秒、choice の順位は無作為並み（AUC 0.53、Jaccard 0.048 は無作為の 0.056 以下）
3. **kev-0.5b は 3 候補で唯一 gemma との差が 0 をまたぐ**が、平均は負の側（−0.04〜−0.06）で dev 規則の +0.05 に遠い。
   torch MPS の allocator がリクエスト間で解放されず、22 行目から OOM が続いた（第 3 ラウンドの kev-0.8b と同じ症状）
4. **帰結（draft — 判定は RFC-0040 の判断役）**: 2026-09-24 時点で、この機体でローカルに動く System One 型判断モデルのうち
   skill selection で `C/logits`（gemma の logits 読み）を dev 規則で上回るものは無かった。第 3 ラウンドの帰結は変わらない

## 追加探索（2026-09-24 照合、1 回）

出所: [systemonemodels.org/examples/alternatives/](https://systemonemodels.org/examples/alternatives/)（2026-09-24 取得）と
Hugging Face の検索（`jev` / `systemone` / `system-one` / `kev`、2026-09-22 以降に更新されたもの）。入場条件は 5 つ —
(1) Apple Silicon runtime を一次資料に明記 (2) checkpoint を取得できる (3) 判定目的で学習または較正し数字を公開
(4) 明示ライセンス + origin repo (5) Jev の出力で学習したと明言していない。

- **入れた（1 件）**: `jaredpalmer/kev-0.5b`（HF 上の写し `Terom/kev-0.5b` が 2026-09-24 に更新されて見つかった。本体の最終更新は
  2026-09-20 なので「2026-09-24 以降の新顔」ではない — 逸脱として記録）。MPS で学習・serve と明記、ECE 0.031（温度較正後）、
  Apache-2.0、origin `github.com/jaredpalmer/kev`、「LLM 生成データなし」
- **落とした**:
  - `mpuig/system-one-qwen3-0.6b` — 合成シナリオの確率目標を pinned jev-1.13.0 で作ったと明記（条件 5）
  - `chaoliangUNSW/Jev-Style-Qwen3.5-2B-Decision-v2`（MLX bf16 版あり）— choice は A〜Z の 26 択上限で 54〜57 択が載らず、
    `/v1/systemone` を出さない。origin repo は HF のみ（条件 4）
  - `Heman10x-NGU/openJev-verdict-2.0` — Apple Silicon の記述なし（条件 1）、重みは Git LFS pointer 管理
  - `bnsd55/jevmlx`・`r-ms/mini-jev`・drinkmoonshine の Parallel Constrained Decoding — 凍結モデルの logits 読みで判定用の学習・較正なし（条件 3）
  - `RoderickQiu/kev-4b-mlx-8bit` — kev-4b の量子化版。packet の kev-4b の条件（0.8b が dev を通る / swap に余裕）を満たさない
  - `mlboydaisuke/system-one-qwen3.5-4b-scorer-CoreAI` — CC BY-NC 4.0、CoreAI（macOS 27）runtime で harness に client が無い
  - CLM / NanoJev / openjev-sglang / Decider / SemIf — CUDA / datacenter GPU 前提（条件 1）。Tev1 / jev-on-a-laptop — ライセンス未宣言（条件 4）

## 測らなかったこと（第 4 ラウンド）

- **holdout（120 行）**: 候補が dev を通らなかったので 1 回も読んでいない。holdout はまだ未使用のまま残る
- **kev-4b / kev-9b**: kev-0.8b の MLX footprint（12 GB）から、16 GB で gemma と入れ替えて回す余裕は無いと読んだ。外挿はしない
- **kev-0.8b の質**: 資源の規則で smoke 止まり。Jaccard を読む行を回していない
- **kev-0.5b の OOM を除いた 30 行**: server を行ごとに作り直せば 30 行揃うが、答えた 22 行の平均が規則から離れているので回していない
- **無人窓での latency / swap**: 対話中の値しか無い
- 学習域: kev は state 384 token までで学習、CA の situation は p50 約 400 / 最大 約 1,800 token なので全行が学習域外（第 3 ラウンドと同じ）

## 実行コマンド（第 4 ラウンド）

```bash
# harness（817ecf3 から復元 + arm V・窓待ち・候補対差）。repo の依存は増やさない
uv run --no-sync python scripts/skillsel_arm_replay.py --help

# split と基準線（.notes/skillsel-arm-replay/round4/split.py は stdlib のみ、seed 20260924）
python3 .notes/skillsel-arm-replay/round4/split.py
uv run --no-sync python scripts/skillsel_arm_replay.py --augment round4/dev.jsonl --out-rows <dev.jsonl の写し> \
    --summarize-only --days 30 --out-summary round4/baseline-dev.json ...   # holdout も同じ

# 候補ごと: gemma / nomic を降ろす → server 起動 → smoke → dev
curl -s http://127.0.0.1:11434/api/generate -d '{"model":"gemma4:e4b","keep_alive":0}'
HF_HUB_OFFLINE=1 uv run --python 3.13 --no-project \
    --with "kev[serve] @ git+https://github.com/jaredpalmer/kev@62c91838b9a6adc5b386cbeae8ed73daa36ce220" \
    python -m kev.serve --run jaredpalmer/kev-0.8b --port 8009      # kev-0.5b は --run jaredpalmer/kev-0.5b@9ce2fd39db3a397c89733f94af948e3d1fdfffcd
HF_HUB_OFFLINE=1 uv run --python 3.13 --no-project --with "von-sdk==1.2.2" von serve --host 127.0.0.1 --port 8010

uv run --no-sync python scripts/skillsel_arm_replay.py --augment round4/dev.jsonl --augment-limit 5 \
    --arms K --kev-endpoint http://127.0.0.1:8009 [--kev-noul-batch 14] \
    --no-embed --latency-subsample 0 --days 30 --out-rows … --out-summary … --out-aux … --adjudication …
# von は --arms V --von-endpoint http://127.0.0.1:8010。dev は --augment-limit を外す（von は --kev-questions choice）
```
