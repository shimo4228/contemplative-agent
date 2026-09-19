# RFC-0041 evidence — insight の入口で何が件数を決めているか（2026-09-19）

一発測定の凍結（ADR-0075 の適用範囲外 — read-only、`$MOLTBOOK_HOME` へは書かない）。読みは軸ごとに並べ、
合成スコアは作らない。判定は RFC-0041 の Status が持つ。

対象は 2026-09-19 の insight run（`run_id 7f0b92e8…`、窓 09-05〜09-18 の 1,184 パターン → 154 クラスタ →
novelty gate で 71 covered → 83 抽出 → 75 候補）。同日の土曜ゲートの裁定は採用 0 / 却下 68 / 保留 7
（保留 7 は同日中に却下へ変更。ここでは「説明係 Claude が区別できると読んだ 7 件」の対照として残す —
オーナーの裁定ではなく標本も小さい）。

## ファイル

| ファイル | 中身 |
|---|---|
| `gate-labels-20260919.json` | cluster id ↔ staged 名 ↔ ゲート裁定。対応は insight run log の batch 順 − `no_title` abstain 8 件 = staged meta の seq 順 |
| `novelty-tiebreak-replay-20260919.json` | 抽出前 gate の再生、temperature 1.0（本番と同じ）。`scripts/novelty_tiebreak_replay.py` |
| `novelty-tiebreak-replay-t0-20260919.json` | 同、temperature 0 |
| `post-extraction-judge-replay-20260919.json` | 抽出後の重複判定の再生、temperature 1.0。`scripts/post_extraction_judge_replay.py` |
| `post-extraction-judge-replay-t0-20260919.json` | 同、temperature 0 |

候補本文（LLM 出力、untrusted 由来パターンの下流）はここに置かない。置くのは名前と verdict だけ。

## 読み 1 — 抽出前 gate の tie-break 文（「迷ったら NEW」）と temperature

16 chunk のログ済みプロンプトを byte 一致で再生し、末尾の tie-break 2 文だけを差し替えた。
arm: `new` = 現行文言 / `none` = 2 文を削除 / `covered` = 「迷ったら covered」に反転。各 arm 2 反復。

| arm | covered / 154（t=1.0、rep0 / rep1） | 反復間 Jaccard（t=1.0） | covered / 154（t=0、2 反復とも同値） | 却下 68 のうち停止（t=0） | 対照 7 のうち停止（t=0） |
|---|---|---|---|---|---|
| 本番ログ | 71 | — | — | 0（定義上） | 0（定義上） |
| `new` | 66 / 66 | 0.50 | 99 | 29 | 4 |
| `none` | 80 / 65 | 0.51 | 112 | 37 | 5 |
| `covered` | 91 / 105 | 0.57 | 127 | 44 | 6 |

- t=1.0 では同一プロンプトの 2 反復が covered 集合の半分しか共有しない。総数は安定（66 / 66）で中身が入れ替わる —
  本番を通過した 68 件のうち 17〜20 件は、同じ文言の再生で covered に変わった
- t=1.0 では文の削除は揺れの内側（80 / 65 が 66 を挟む）。t=0 では文の効果が出る（99 → 112 → 127）
- t=0 は反復間 Jaccard 1.0（決定的）。現行文言のままでも covered は 66 → 99
- どの arm も対照 7 件を却下 68 件と同等以上の率で止める — 抽出前 gate は件数を動かすが、区別はしていない
  （ADR-0084 の形: 成果物の前に置いた judge には比べる証拠が無い）

## 読み 2 — 抽出後の重複判定（temperature 1.0）

書かれた skill（name / description / Solution・When to Use の先頭 230 字）を、store の最近傍 5 件（nomic cosine）と
同じ投影で並べ、`duplicate` / `distinct` を enum 拘束で答えさせた。tie-break 指示はどちら向きにも入れていない。
陽性対照は leave-one-out: store 53 件を 1 件ずつ抜いて残り 52 件と比べる（全部オーナーが過去に採用したもの）。
gate 集団の最近傍は測定時点の store（53 件）— ゲート時点は 54 件で、同日 archive した 1 件ぶんずれる。

| 集団 | n | `duplicate`（rep0 / rep1） | 反復間一致 | 偶然一致 | κ |
|---|---|---|---|---|---|
| ゲート却下 | 68 | 30 / 34 | 0.62 | 0.50 | 0.24 |
| 対照 7 | 7 | 2 / 0 | 0.71 | 0.71 | 0.00 |
| leave-one-out（採用済み） | 53 | 15 / 16 | 0.60 | 0.59 | 0.04 |

- 退化していない（採用済みの ~7 割を `distinct`）。向きも合う（却下群の `duplicate` 率 > 採用済み群）
- 止めるのは却下群の半分。2 反復とも `distinct` で通るものが 75 件中 28 件
- 個々の verdict の再現性はほぼ偶然水準（κ 0.04〜0.24）— 群ごとに表の出る率が違うサイコロに近い
- leave-one-out の `duplicate` ~3 割が誤判定か store の実重複かは、この測定では分けられない

## 読み 3 — 抽出後の重複判定（temperature 0）と、抽出前 gate との重ね合わせ

同じ入力・同じプロンプトで temperature だけ 0 にした。256 コール、失敗 0、2 反復は全件一致（決定的）。

| 集団 | n | `duplicate`（t=0） | `duplicate`（t=1.0、rep0 / rep1） |
|---|---|---|---|
| ゲート却下 | 68 | 33 | 30 / 34 |
| 対照 7 | 7 | 0 | 2 / 0 |
| leave-one-out（採用済み） | 53 | 12 | 15 / 16 |

- 率は t=1.0 とほぼ同じ（却下群の半分を止め、採用済みの ~2 割を止める）。変わったのは再現性だけ
- t=0 で `duplicate` の却下 33 件のうち、t=1.0 で 2 反復とも `duplicate` だったのは 16 件、どちらかで `duplicate` だったのは 30 件

ラベルのある 75 件（= 本番の gate を通過して抽出されたもの）について、抽出前 gate（t=0）と抽出後判定（t=0）を直列に重ねた通過数:

| 抽出前 gate の arm（t=0） | gate 通過 / 75（却下 / 対照 7） | + 抽出後判定も通過（却下 / 対照 7） |
|---|---|---|
| `new` | 42（39 / 3） | 25（22 / 3） |
| `none` | 33（31 / 2） | 19（17 / 2） |
| `covered` | 25（24 / 1） | 16（15 / 1） |

- 抽出後判定だけなら 75 → 42
- この 75 件は本番（t=1.0）が通したものに限られる。t=0 の gate は本番が covered にしたクラスタの一部を通すが、それらは
  抽出されておらずラベルも本文も無い — 上の通過数は実際の件数の下限ではなく、ラベルのある部分集合での読み。
  154 クラスタ全体での gate 通過は読み 1 の表（`new` 55 / `none` 42 / `covered` 27）

