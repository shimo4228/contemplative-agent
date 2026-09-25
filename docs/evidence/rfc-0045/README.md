# RFC-0045 evidence — relevance 判定を Jev との近さで読む（2026-09-24〜25）

[RFC-0045](../../../rfcs/0045-relevance-judgment-jev-proximity-replay.md) の一発測定の凍結（ADR-0075 の 2026-08-29 追補で
監査ログ義務の対象外、read-only、`$MOLTBOOK_HOME` へは書かない）。集計は
[relevance-arm-replay-20260925.json](relevance-arm-replay-20260925.json)。投稿本文・decoded prompt・モデルの生出力は
ここにも JSON にも置いていない（行単位の出力は gitignore された `.notes/relevance-arm-replay/` のみ）。

**判定はここに書かない。** 事前登録した規則に数字を当てはめた draft までを置き、採否は RFC-0045 の判断役が書く。

## 事前登録（読みの前に固定）と、実行前に判断役が変えた 3 点

規則の正本は RFC-0045「事前に固定する読み」と packet S28。数字を見る前に判断役が変えたのは次の 3 点（2026-09-24）:

1. **層の切り方** — gemma の記録スコアは 0.1 刻みの離散値で、packet の層 0.82〜0.9 は 0 行だった。観測値に合わせて
   `<=0.4` / `0.5〜0.6` / `0.7` / `0.8` / `>=0.9` の 5 層 × 30 行に切り直した（seed `20260925`）。本番の閾値 0.65 と 0.82 は
   どちらも層の境目に来る。読み 3 の「score >= 0.82」は本番の閾値のまま — 値が離散なので実質「>= 0.9」と同じ行になる
2. **domain** — 本番の relevance の system prompt は identity.md（954 B）+ 憲法の axioms（3,103 字）で約 1,000 token。
   C / J / E / K / V の `domain` は **identity.md だけ**にした（問いは「自分の domain か」で、axioms は価値であって domain ではない。
   state は約 350 token で kev の学習長 384 の内側に収まる）。A / A0 は本番そのままの system prompt（identity + axioms）で再生した
3. **opus の費用上限** — packet の「≈ $10」は smoke の実額（1 行 $0.13〜0.16）から約 $40 に置き換えた。150 行 × 2 反復は変えていない

## 標本と split

- 標本: `logs/submolt-scope-*.jsonl` の `event == "score"` 行（8 ファイル、2026-08-01〜09-23）。2,698 行・2,698 distinct `post_id`、
  全行 `reason == "scored"`・`content_truncated == false`、`content_bytes` p50 = 500
- 層の母数: `<=0.4` 651 / `0.5〜0.6` 172 / `0.7` 299 / `0.8` 534 / `>=0.9` 1,042
- dev = 各層 30 行（150 行）。sub600 = 各層 120 行（600 行、dev を含む入れ子）。holdout = dev 以外の 2,548 行。
  どの層も割当に足りたので、隣の層からの補充は起きていない
- 層別の標本なので、dev・sub600 の上の率は母集団の率ではない（母集団の率は「全行」と書いた数字だけ）

## arm

| label | 中身 | 行 |
|---|---|---|
| `A/free/rep1` | 本番の `score_relevance_detailed` をそのまま呼ぶ（temperature 1.0） | 全 2,698 |
| `A/free/rep2` | 同じもう 1 回 | sub600 |
| `A0/t0` | 同じ関数で `generate` の temperature だけ 0 に固定 | sub600 |
| `C/logits/score4` | gemma に 4 段 Score を ADR-0112 の `OllamaLogprobsDecisionBackend` で問う | 全 2,698 |
| `J/score4` + `J/noul` | ホスト型 Jev（`jev-1.13.0`）に 4 段 Score と「directly on-topic か」の Noul を 1 リクエストで | 全 2,698 |
| `E/opus/rep1` `E/opus/rep2` | claude-opus-5（`evals/judging.py::run_claude_raw`、tools なし）に同じ 4 段を数字 1 つで | dev 150 |
| `K/kev/score4` + `K/kev/noul` | kev-0.8b（MLX）、`/v1/systemone` | smoke 5 → dev 150 |
| `V/von/score4` + `V/von/noul` | von 1.2.2（MPS）、`/v1/systemone` | smoke 5 → dev 150 |

4 段の見出しは RFC-0045 の文言（`unrelated` / `shares vocabulary only` / `same field` / `directly on-topic`）で、各段に
1 文の説明を付けた（本文は `scripts/relevance_arm_replay.py` の `LEVELS`）。

正規化: 4 段 Score は期待段 / 3、Noul は P(yes)、本番スコアはそのまま。Jev 側の on-topic 二値は P(`directly on-topic`) >= 0.5
（暫定。対応表は下の読み 3 の表）。E の on-topic は段 3 と答えたこと。

## 再生の妥当性

- A/free/rep1 の本番ゲート通過率は 0.371、同じ行の記録は 0.386。ゲートの判定（>= 0.82 か）が記録と一致した行は 0.755、値が
  完全に一致した行は 0.307。A の 2 回の間でも完全一致は 0.358、ゲート一致は 0.830（sub600）なので、記録との差は
  temperature 1.0 の揺れと同じ大きさ。**A は記録と同じ帯に入る**
- 分布の形は少し動いた: 記録は 1.0 が 424 行・0.9 が 618 行、再生は 1.0 が 164 行・0.9 が 836 行（ゲートの両側は同じ）。
  identity.md と憲法は今日のファイルで、記録した時点（最大 8 週前）のものではない — 時間は再現できない
- **A / A0 と他の arm は同じ state を見ていない。** A / A0 の system prompt には axioms が入り、C / J / E / K / V の `domain` は
  identity.md だけ（上の変更点 2）
- `wrap_untrusted_content` の区切りは呼び出しごとの nonce なので、同じ投稿でも arm ごとに区切り文字列は違う（中身は同じ）

## 実行条件

- 2026-09-24 22:36 〜 2026-09-25 08:25 JST。J（22:36〜22:46）と E（22:41〜23:11）は gemma の A / C と同時に走った
  （HTTP / `claude -p` だけで GPU は使わない）。gemma の arm は JST 0 時・6 時の窓（開始 10 分前〜60 分後）を script が待った
- gemma の A と C は行ごとに交互に呼んだので、C は毎行 prompt cache が効かない状態で測った（C の latency 中央値 2.9 秒）
- K / V は gemma の後に、Ollama を空にしてから（`/api/ps` が空）server を別プロセス・別 project で起動した。
  kev は commit `62c91838`・`on mps via mlx (bfloat16)`、von は `von-sdk==1.2.2`・`on Apple Silicon [MPS]`。
  **どちらも `huggingface_hub==1.16.1` に pin した**（第 4 ラウンドの env と同じ版）— 今回新しく解決された 1.33.0 / 1.32.0 は
  `HF_HUB_OFFLINE=1` でも cache の完全性確認で HF の tree API を呼び、kev の起動が失敗した
- 対話中の測定（オーナーの別セッションが同じ機体で動いている）。無人窓での値ではない

## 読み 1 — Jev をラベルにしてよいか（dev 150 行）

規則: Spearman(Jev, opus) >= 0.7 **かつ** on-topic 二値の一致率 >= opus の自己一致率 − 0.05。

| 比較 | 値 [95% CI] |
|---|---|
| Spearman `J/score4` 対 `E/opus/rep1` | 0.747 [0.658, 0.819] |
| Spearman `J/score4` 対 `E/opus/rep2` | 0.715 [0.613, 0.793] |
| Spearman `J/noul` 対 `E/opus/rep1` | 0.783 [0.708, 0.839] |
| Spearman `J/noul` 対 `E/opus/rep2` | 0.757 [0.676, 0.822] |
| on-topic 一致 `J/score4` 対 `E/opus/rep1` | 0.880 [0.827, 0.933] |
| on-topic 一致 `J/score4` 対 `E/opus/rep2` | 0.880 [0.827, 0.927] |
| opus の自己一致（on-topic、rep1 対 rep2） | 0.960 [0.927, 0.987] |
| opus の自己一致（段が完全一致） | 0.833 [0.767, 0.887] |

補助（判定に使わない）: on-topic の不一致 18 行（rep1）のうち 17 行は「opus は段 3、Jev は P(段 3) < 0.5」。opus が段 3 と答えた
44 行のうち、Jev の最頻段が 3 だったのは 32 行、2 だったのは 3 行、0 だったのは 7 行。

**規則への当てはめ（draft）**: Spearman は `J/score4` で 0.747 / 0.715 と 0.7 以上（点推定。rep2 の CI 下限は 0.61）。二値の一致は
0.880 で、線 0.960 − 0.05 = 0.910 に届かない → 事前登録の規則では**不成立**。不一致は Jev が on-topic を狭く取る一方向に偏る。

## 読み 2 — ローカル候補は gemma（C）より Jev に近いか

誤差 = |候補の正規化スコア − Jev の P(`directly on-topic`)|、対差は候補 − `C/logits/score4`、行単位 bootstrap 2,000 回。
AUC は Jev の on-topic 二値（dev で 28 / 150 行が陽性）を候補スコアで予測したもの。

smoke（dev の先頭 5 行、規則: answered 5/5・latency 中央値 < 2 秒・swap 開始時 +3 GB 以内）:

| 候補 | answered | latency 中央値 | swap（開始 → 最大） | 規則 |
|---|---|---|---|---|
| kev-0.8b（MLX） | 5 / 5 | 566 ms | 5.6 → 6.5 GB（+0.9） | pass |
| von 1.2.2（MPS） | 5 / 5 | 720 ms | 7.2 → 7.2 GB（増えず） | pass |

dev（150 行。規則: 対差の CI 上限 < 0 **かつ** AUC >= AUC(C) − 0.02。同じ 150 行の AUC(C) = 0.944 [0.903, 0.978] → 線 0.924）:

| label | 誤差 | 候補 − C | AUC | 規則 |
|---|---|---|---|---|
| `K/kev/score4` | 0.294 | −0.070 [−0.112, −0.028] | 0.604 [0.485, 0.720] | fail（AUC） |
| `K/kev/noul` | 0.265 | −0.100 [−0.147, −0.053] | 0.603 [0.494, 0.712] | fail（AUC） |
| `V/von/score4` | 0.373 | +0.009 [−0.028, +0.044] | 0.431 [0.303, 0.559] | fail（両方） |
| `V/von/noul` | 0.292 | −0.072 [−0.117, −0.026] | 0.511 [0.388, 0.628] | fail（AUC） |
| 参考 `C/logits/score4` | 0.364 | — | 0.944 | — |
| 参考 `A/free/rep1` | 0.445 | +0.081 [+0.049, +0.113] | 0.821 | — |
| 参考 `A0/t0` | 0.434 | +0.070 [+0.037, +0.102] | 0.821 | — |
| 参考 `J/noul` | 0.161 | −0.203 [−0.233, −0.175] | 0.988 | — |

kev と von の誤差が C より小さく出るのは、分布が段の間に平たく広がり（1 行目の kev の 4 段は 0.22 / 0.40 / 0.34 / 0.04）、
陽性の少ない dev で Jev の低い P(段 3) に近い値を返すため。順位（AUC）は無作為並みで、C の 0.944 と重ならない。

dev の資源: kev は 150 行を通して latency 中央値 562 ms だったが、swap は 5.6 GB から 14.2 GB まで増えた（dev には swap の
規則を当てていない。第 4 ラウンドの 12 GB と同じ形の膨張が、state 約 350 token でも起きた）。von は 728 ms・swap 7.0〜7.2 GB。

**規則への当てはめ（draft）**: 2 候補 × 2 label とも dev 不通過。**holdout は 1 候補も読んでいない**（holdout の読みの消費は 0 回）。
JSON の `reading2 holdout` にあるのは候補ではなく参考 label（A / A0 / `J/noul` 対 C）だけ。

## 読み 3 — 本番 gate を Jev から見る（数字のみ）

| 読み | 値 |
|---|---|
| 記録スコア >= 0.82 の行で Jev が on-topic でない割合（全行） | 489 / 1,042 = 0.469 |
| 同じく A/free/rep1（今日の再生、全行） | 410 / 1,000 = 0.410 |
| 同じく A0/t0（sub600 = 層別、母集団の率ではない） | 65 / 150 = 0.433 |
| A の自己一致（sub600）: 値の完全一致 / ゲート一致 | 0.358 [0.318, 0.395] / 0.830 [0.798, 0.858] |
| A0 対 A/free/rep1（sub600）: 値の完全一致 / ゲート一致 | 0.453 [0.415, 0.493] / 0.870 [0.842, 0.897] |
| A0 − A の平均スコア | +0.015 [+0.003, +0.027] |
| A0 − A の Jev との誤差 | +0.014 [+0.002, +0.025] |

記録スコアが 0.82 以上の 1,042 行で、Jev の最頻段は `directly on-topic` 624 行 / `same field` 309 行 / `shares vocabulary only`
12 行 / `unrelated` 97 行。

対応表（記録スコアの値ごとの Jev、全 2,698 行。on-topic = P(段 3) >= 0.5）:

| 記録スコア | 行 | Jev on-topic 率 | 平均 P(段 3) |
|---|---|---|---|
| 0.0 | 16 | 0.000 | 0.014 |
| 0.1 | 140 | 0.029 | 0.066 |
| 0.2 | 183 | 0.027 | 0.089 |
| 0.3 | 215 | 0.056 | 0.127 |
| 0.4 | 97 | 0.062 | 0.139 |
| 0.5 | 21 | 0.000 | 0.042 |
| 0.6 | 151 | 0.093 | 0.170 |
| 0.7 | 299 | 0.141 | 0.237 |
| 0.8 | 534 | 0.288 | 0.347 |
| 0.9 | 618 | 0.544 | 0.542 |
| 1.0 | 424 | 0.512 | 0.518 |

## コスト

- Jev: 2,698 リクエスト（+ 合成 state の probe 1 回）、入力 2,192,619 token（1 行 約 810 token）、入力 $0.042/MTok で約 $0.09。
  429 / 529 は 0 回。1 行の latency 中央値 209 ms
- opus: 300 回、envelope の API 換算額 $37.73（+ smoke 2 回 $0.28）。Max subscription の消費
- GPU: gemma 2026-09-24 22:37 〜 09-25 08:14（窓待ち 2 回を含む）、kev 08:17〜08:19、von 08:21〜08:25

## 測らなかったこと

- **holdout（候補）**: K / V とも dev を通らなかったので読んでいない
- **opus を全行に**: 読み 1 の検算の 150 行だけ
- **A0 の全行**: A0 と A/free/rep2 は packet の許可で層別 600 行に縮めた。A0 のゲート通過率を母集団の率として読まない
- **無人窓での latency / swap**: 対話中の値しか無い
- **Jev の on-topic の線**: P(段 3) >= 0.5 は暫定。`J/noul` の 0.5 線など別の線は事前登録していないので読んでいない

## 再実行するときの注意

script は RFC-0045 の消費計画どおり、読みを RFC に追記した時点で満了する。消されていたら、この evidence を足した commit の
親から `scripts/relevance_arm_replay.py`・`evals/jev_arm.py` とそのテストを checkout する。

```bash
uv run --no-sync python scripts/relevance_arm_replay.py --write-split          # seed 20260925
uv run --no-sync python -m evals.jev_arm relevance --resume                    # J（全行、HTTP のみ）
uv run --no-sync python scripts/relevance_arm_replay.py --arms A,C --subset all --resume
uv run --no-sync python scripts/relevance_arm_replay.py --arms A2,A0 --subset sub600 --resume
uv run --no-sync python scripts/relevance_arm_replay.py --arms E,E2 --subset dev --resume \
    --out-rows .notes/relevance-arm-replay/opus.jsonl

# K / V: Ollama を空にしてから server を起動（huggingface_hub は 1.16.1 に pin）
HF_HUB_OFFLINE=1 KEV_DTYPE=bf16 uv run --python 3.13 --no-project \
    --with "kev[serve] @ git+https://github.com/jaredpalmer/kev@62c91838b9a6adc5b386cbeae8ed73daa36ce220" \
    --with "huggingface_hub==1.16.1" python -m kev.serve --run jaredpalmer/kev-0.8b --port 8009
uv run --no-sync python scripts/relevance_arm_replay.py --arms K --subset dev --limit 5 --resume \
    --out-rows .notes/relevance-arm-replay/kev.jsonl                           # smoke → --limit を外して dev
HF_HUB_OFFLINE=1 uv run --python 3.13 --no-project --with "von-sdk==1.2.2" \
    --with "huggingface_hub==1.16.1" von serve --host 127.0.0.1 --port 8010
uv run --no-sync python scripts/relevance_arm_replay.py --arms V --subset dev --resume \
    --out-rows .notes/relevance-arm-replay/von.jsonl

uv run --no-sync python scripts/relevance_arm_replay.py --summarize-only \
    --augment .notes/relevance-arm-replay/jev/rows.jsonl --augment .notes/relevance-arm-replay/opus.jsonl \
    --augment .notes/relevance-arm-replay/kev.jsonl --augment .notes/relevance-arm-replay/von.jsonl \
    --out-summary docs/evidence/rfc-0045/relevance-arm-replay-20260925.json
```

## RFC-0040 JevK5 v0.3（2026-09-25〜26、同じ split に候補を 1 つ足した読み）

[RFC-0040](../../../rfcs/0040-jev-system-one-local-decision-backend.md) の「2026-09-25 実測 1 段目」節の事前登録を、上と同じ split
（seed `20260925`、`--sample-through 2026-09-23` で母数 2,698 / 651 / 172 / 299 / 534 / 1,042 が一致）で読んだ。集計は
[relevance-arm-replay-jevk5-20260926.json](relevance-arm-replay-jevk5-20260926.json)。RFC-0045 の行データは失われていたので、
**C と J は dev・holdout とも回し直した**（A / A0 / E / K / V は回していない — JSON の reading1 が空なのは opus 行を足していないため）。

**判定はここに書かない**（規則への当てはめ draft まで。判定は RFC-0040）。

### 実行条件

- script は `1b24abd`（arm K5 と `--sample-through`）。K5 は llama.cpp 0.5.0（Homebrew、build 11146）の `llama-server -c 8192 -ngl 99`、
  GGUF `jevk5-4b-v0.3-Q8_0.gguf`（SHA256 `aea43388…d4a30`、card の `SHA256SUMS` と一致）、client は jevk5 0.3.2（`--no-deps`、git `7b97499`）、
  temperature 1.22（card の GGUF 表）。問いは K / V / J と同じ 2 問（`systemone_request`）を 1 問 1 pass
- dev（2026-09-25 18:50〜19:25 JST）: C → J（並走、HTTP のみ）→ K5。K5 の server は既定の `--cache-ram 8192`
- holdout（2026-09-25 19:54 〜 09-26 03:45 JST）: J（並走）→ K5 → C。K5 は `--cache-ram 0`、JST 0 時の窓をまたがないよう 23:40 に server を
  止め 01:05 に再開（2,415 行 + 133 行の 2 回）。C は K5 の後に単独で
- 対話中の測定（オーナーの別セッションが同じ機体で動いている）。スケジュールセッションとは重ねていない

### smoke（dev の先頭 5 行）

| label | answered | latency 中央値 | swap（開始 → 最大） | 事前登録の規則（< 2 秒） | 改定後の規則（C の 1.5 倍以内） |
|---|---|---|---|---|---|
| `K5/jevk5/score4` | 5 / 5 | 2,936 ms | 8.1 → 8.0 GB | fail | pass（1.2 倍、C の dev 中央値 2,450 ms） |
| `K5/jevk5/noul` | 5 / 5 | 2,413 ms | 同上 | fail | pass |

server 側の prompt eval は 215 token/秒、入力は中央値 580 token（最大 730）。答えの文字が top-k から漏れた回数（`letters_missing`）は
dev・holdout とも 0。latency 規則の改定は smoke の後・holdout の前（RFC-0040 の同節、commit `5a1e912`）。

### dev（150 行、陽性 30）

規則: 誤差の対差（候補 − `C/logits/score4`）の CI 上限 < 0 **かつ** AUC ≥ AUC(C) − 0.02。AUC(C) = 0.928 [0.876, 0.970] → 線 0.908
（RFC-0045 の同じ 150 行では 0.944）。

| label | 誤差 | 候補 − C | AUC | 規則 |
|---|---|---|---|---|
| `K5/jevk5/score4` | 0.223 | −0.143 [−0.177, −0.109] | 0.912 [0.855, 0.957] | pass |
| `K5/jevk5/noul` | 0.176 | −0.190 [−0.236, −0.143] | 0.867 [0.798, 0.926] | fail（AUC） |
| 参考 `C/logits/score4` | 0.366 | — | 0.928 | — |
| 参考 `J/noul` | 0.157 | −0.209 | 0.994 | — |

### holdout（2,548 行、陽性 766）— `K5/jevk5/score4` の 1 回

AUC(C) = 0.915 [0.904, 0.926]（RFC-0045 の holdout では 0.917）→ 線 0.895。

| label | 誤差 | 候補 − C | AUC | 規則 |
|---|---|---|---|---|
| `K5/jevk5/score4` | 0.224 | −0.120 [−0.128, −0.112] | 0.902 [0.890, 0.914] | pass（AUC の余裕 0.007） |
| 記録のみ `K5/jevk5/noul` | 0.193 | −0.151 [−0.164, −0.139] | 0.867 [0.853, 0.881] | —（dev 不通過） |
| 参考 `C/logits/score4` | 0.344 | — | 0.915 | — |
| 参考 `J/noul` | 0.149 | −0.195 | 0.994 | — |

latency 中央値: K5 score4 3,199 ms / noul 2,330 ms、C 3,142 ms、J 204 ms。

**規則への当てはめ（draft）**: `K5/jevk5/score4` は改定後の smoke・dev・holdout を通る。順位（AUC）は C より 0.013 低く、
Jev の確率への近さ（誤差）は C より 0.12 小さい。`K5/jevk5/noul` は dev で落ちる。

### 資源

- **dev の swap 8.0 → 14.3 GB** は llama-server 既定の host RAM prompt cache（`--cache-ram` 既定 8,192 MiB、ログに
  「making room for prompt cache entry」）。server の RSS は 4.67 GB で一定。止めても swap は減らなかった（押し出されたのは他の process）
- **holdout（`--cache-ram 0`）の swap** は 14.6 GB から 1 回目の途中で最大 18.9 GB まで上がり、1 回目の終わりに 14.4 GB へ戻った。
  同じ時間帯に他の process も動いており、原因は切り分けていない。JSON の `swap_used_mb_first_max` は subset の行順（post id）の
  先頭と最大で、時系列の開始値ではない
- 2 つのモデルは同居させていない（K5 の前に Ollama を空にし、C は server 停止後）

### 測らなかったこと

- **4 段の組と本番 A の条件差**: A は identity + axioms の system prompt・0〜1 の問い・数字の生成で、4 段の組（J / E / C / K / V / K5）は
  identity だけの `domain`・4 段の問い。採点者 J も 4 段の問いで答えている。K5 対 C は条件が揃っているが、4 段の組と A の比較
  （RFC-0045 の読み 3、RFC-0046 の根拠）は 3 条件と採点の問いが交絡している。1 つずつ変える arm（問いだけ 4 段 → axioms を外す →
  logprobs = C、加えて axioms 入り state の J）は未測定
- Q5_K_M / Q4_K_M、無人窓での latency、Ollama 経由の読み出し（RFC-0040 の 2 段目）

### 再実行

```bash
uv run --no-sync python scripts/relevance_arm_replay.py --write-split --sample-through 2026-09-23
uv run --no-sync python -m evals.jev_arm relevance --subset dev --sample-through 2026-09-23 --resume   # holdout も同じ
uv run --no-sync python scripts/relevance_arm_replay.py --arms C --subset dev --sample-through 2026-09-23 --resume
uv pip install --no-deps "jevk5 @ git+https://github.com/allebee/jevk5@v0.3.2"
llama-server -m <jevk5-4b-v0.3-Q8_0.gguf> -c 8192 -ngl 99 --host 127.0.0.1 --port 8080 --cache-ram 0
uv run --no-sync python scripts/relevance_arm_replay.py --arms K5 --subset dev --sample-through 2026-09-23 --resume
uv run --no-sync python scripts/relevance_arm_replay.py --summarize-only --sample-through 2026-09-23 \
    --augment .notes/relevance-arm-replay/jev/rows.jsonl \
    --out-summary docs/evidence/rfc-0045/relevance-arm-replay-jevk5-20260926.json
```
