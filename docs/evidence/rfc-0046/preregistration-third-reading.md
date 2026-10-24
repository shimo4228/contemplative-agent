# RFC-0046 evidence — 3 回目の読み（t=0.3 を enforce 後の母集団・post 単位で再読）の事前登録

P1-15.2 / D-P1-15-1 = C（owner、2026-10-24 の「全部推奨で」）。**読みの前に固定する**（結果を見てから規則を選ばない）。
この文書は事前登録であって、読みの結果ではない — 結果は読みの後に同じディレクトリへ追記し、事前登録の本文は書き換えない。

## 問い

score4 gate の閾値 t=0.3（[ADR-0113](../../adr/0113-decision-faces-and-relevance-score4-shadow.md) 追補 1）は、enforce 前の母集団
（S35: 2026-09-28、S36: 2026-10-03）で置いた。enforce が feed を変えた後の母集団で、同じ規則を当てて t を確認する。
**変わったのは母集団で、規則ではない**（D-P1-15-1 C の理由）— 規則は
[RFC-0046](../../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md) の 2026-09-28 事前登録をそのまま再適用する。

## 母集団・単位・n

- 母集団: 2026-10-07（S40、live 半分の廃止）以降の feed 行（`source: "feed"`）、`post_id` で dedupe（`relevance_label_set.py sample` が最初の行を残す）。
  domain は `identity+axioms`、pin は sample 時点の identity / axioms / `relevance_score4.md` の sha（manifest に入る）。
- **主要単位は post**（`rfcs/0046` S38 の教訓。行単位の読みは補助で、主要な読みにしない）。
- n = 150 post、`P_TOP_STRATA` の 5 帯で層化（`strata_key: decision_p_top`）、seed は読みの日付で固定。150 に届かなければ `sample` は書かずに終わる（待つ）。
- 母集団の帯の重みで戻した読み（`cuts_weighted`）を**主要な読み**に使う。非加重の `cuts` は併記のみ。
- 同じ読みの前提: identity adopt（月次、ADR-0091）の**前**に 1 回。adopt で domain が変わると閾値と母集団の 2 変数が同時に動く。

## 真値 judge

D-P1-15-2 = A: **Jev `jev-1.13.0`** が既定（版 pin、manifest の `judge` / `judge_version`）。on_topic = Jev の 4 段 Score で P(`directly on-topic`) ≥ 0.5。
Jev が使えない時だけ opus `claude-opus-5` を代替にし、その場合は集合を `--judge opus` で作り直す（一つの集合は一人の judge。混在は `label` / `score` が拒否する）。
judge を変えた読みは前の読みと比べない（装置境界）。

## t の規則（再適用）

候補は t ∈ {0.3, 0.5}（0.7 は 2026-09-28 の読みで recall が 0.5 まで落ちており、読む理由がない）。
本番が記録した `decision_p_top`（enforce が閾値と比べる値そのもの）を、母集団の帯の重みで戻した読みで、

1. precision が下限以上の t のうち **recall 最大**を選ぶ。どの t も下限に届かなければ、t=0.3 を維持せず判断役が裁く（12-05 の土曜ゲート）。
2. precision と recall は合成しない（[ADR-0080](../../adr/0080-north-star-layered-end-state.md) 追補 B）。
3. 区間は Wilson 95%（`scripts/_stats.py`）。分母 10 未満は件数のみで率を書かない。

**下限の置き方（この登録が決めること）**: 2026-09-28 の規則の下限は「live gate の precision」（0.362、S35 の重み付け）だった。2026-10-07 以降の行に live の半分は無く、
同じ行から live precision は読めない。そこで下限は **凍結した S35 の値 0.362 をそのまま使う**（新しい母集団で動かさない）。
注意として、この規則は recall が t の増加で単調に下がるので、**下限を満たす限り常に最小の t（0.3）が勝つ**。したがって読みが実際に決めるのは
「t=0.3 の precision（Wilson 下限でなく点推定）が 0.362 以上か」の一点で、t=0.5 が勝つ場合は無い。判断役がより強い下限（例: Wilson 下限 ≥ 0.362）を望むなら、
**読みの前に**ここへ追記する — 読みの後には変えない。

## 検出力の 1 行（読む前に知っておく幅）

S36 は on_topic が 10 / 150（`rfcs/0046:175`）。recall 1.000 の Wilson 95% は [0.72, 1.00]、precision 0.532 は ≈ [0.32, 0.73]。
予測値（n=150）の半幅は ≈ ±7.6 pt（p=0.346、非加重の計算。`cuts_weighted` の加重ではさらに広い）。
したがって「±6 pt に収まるか」は**点でなく差の区間が 0 を含むか**で判定し、150 post では小さな差は検出できない（検出できないことは「差がない」ではない）。

## adopt 前後の窓（週次の計器、判断ではない）

`scripts/relevance_shadow_reading.py --adopt-from-audit`（週次 materials の「Relevance face reading」節）は、直近の identity adopt の前後 7 日の
**post 単位 gate 率**を Wilson 区間つきで、差を Newcombe 区間で出す。帯は ±6 pt:

| 差の区間 | verdict | 動作 |
|---|---|---|
| どちらかの側が 10 post 未満 | `counts_only` | 件数だけ。何もしない |
| 区間が帯 [-6, +6] pt に収まる | `hold` | 何もしない |
| 区間が帯の外に完全にある（下限 > +6 か上限 < -6） | `reopen` | ADR-0113 Review-when: adopt 後の 150 post で再読を開く |
| 区間が帯の縁をまたぐ | `indeterminate` | 何もしない（判定不能。P2-01.9 の「帯をまたぐ区間は判定不能」） |

ロードマップの文言「差の区間が ±6 pt を含まない時に再読を開く」は、帯の**内側**（動いていない）でも「含まない」になりうるので曖昧である。
上の表は「検出できる大きさで動いた時だけ再読を開く」と解釈した（`hold` で再読を開いても、動いていないものを読み直すだけになる）。

## 実行（MAC・オーナー、本番ログと閉じた API を使うので cloud では回さない）

```bash
cd <main tree>
# 1. 150 post を抽出（identity adopt の前に。Ollama 不要、read-only）
uv run --no-sync python scripts/relevance_label_set.py sample \
    --home ~/.config/moltbook --since 2026-10-07T00:00:00Z --n 150 --seed <YYYYMMDD> \
    --judge jev
# 2. Jev でラベル（約 $0.01、閉じたホスト API への送信 = ADR-0015 の現行の研究用途扱い。
#    12-05 に D-P1-11-4 の分類で事後記録）
uv run --no-sync python -m evals.jev_arm relevance-labels --dir .notes/labels/relevance/<YYYY-MM-DD>
# 3. 再採点（gemma。セッション窓 JST 0/6/12/18 時を避け、他のモデルを同居させない）
uv run --no-sync python scripts/relevance_label_set.py score --dir .notes/labels/relevance/<YYYY-MM-DD>
```

`summary.json` の `cuts_weighted`（t=0.3 / 0.5 の P / R）・`calibration`（reliability 5 帯と ECE）・`label_judge` / `manifest.judge_version` を、
`docs/evidence/rfc-0046/` に凍結する（`label-set-2026-09-28.json` と同じ形、`home` は `~`）。**本体の rows / labels は `.notes/` から出さない。**
