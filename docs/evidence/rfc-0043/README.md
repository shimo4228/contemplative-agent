# RFC-0043 evidence — skill selection の学習なし 5 arm offline 再生（2026-09-19〜20）

一発測定の凍結（ADR-0075 の適用範囲外 — read-only、`$MOLTBOOK_HOME` へは書かない）。読みは軸ごとに並べ、
合成スコアは作らない。判定は [RFC-0043](../../../rfcs/0043-skillsel-offline-arm-replay.md) の Status が持つ。

実行: `scripts/skillsel_arm_replay.py --n 150 --seed 20260919 --arms A,B,C,D,E --order-shuffle`、
2026-09-19 22:00 〜 09-20 04:55 JST（JST 0 時のセッション窓は待機）。150 / 150 行が完走。
生成は gemma4:e4b（Ollama 0.30.11）、arm D は `knowledgator/gliclass-modern-large-v3.0`（MPS）、
arm E は claude-opus-5。arm D の依存は `[dependency-groups] replay`。

| ファイル | 中身 |
|---|---|
| `skillsel-arm-replay-20260920.json` | 集計（arm 別の幻覚率・選択数・latency、自己一致、天井 arm との一致、skill 別 precision / recall、標本の `selection_id`、`replay_fidelity`） |

situation 本文・デコード済み prompt・LLM の raw 出力はここに置かない。行単位の出力とオーナー裁定用ファイルは
gitignored のローカルにある。下の「追加の読み」は行単位の出力から同日に計算した値で、JSON には入っていない。

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
