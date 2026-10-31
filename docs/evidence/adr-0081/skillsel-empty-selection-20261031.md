# 空選択（`none`）の発火率 — 4 週を 1 回で読む（2026-10-31、ROADMAP P2-01.7）

問い: skill 選択の pass-1 が `none`（`config/prompts/skill_selection.md:19`）を返し、judged だが
選択 0 件（ADR-0081 Decision 3「an empty selection is a judgment, not a failure」）になることは
一度でもあるか。満腹信号として使える経路か、一度も発火しない abstain 経路か。

## 実行

```
python3 scripts/skillsel_reading.py --start 2026-10-03 --end 2026-10-30 --home ~/.config/moltbook
```

読んだのは `logs/skill-selection-*.jsonl` だけ（script が prefix で列挙し、`prompt_b64` /
`output_b64` は parse 時に捨てる）。生出力は同じフォルダの
[`skillsel-empty-selection-20261031.txt`](skillsel-empty-selection-20261031.txt)。日付は UTC 日。

計測経路の確認: `core/skill_selection.py:266-283` は `none` の行を飛ばし、残りが無ければ
`verdict: "judged"`・`selected: ()` を記録する。したがって `none` は script の
`judged-empty`（`scripts/skillsel_reading.py:267`、judged かつ `selected` が空）にそのまま数えられる
— この読みは構造的に盲目ではない。`rejected_names` だけの行（選択 0・幻覚名あり）も同じ列に入るが、
列が 0 なのでこの行も 0。

## 読み

| 週（土曜〜金曜、UTC） | judged | judged-empty | 95% 上限（rule of three, 3/n） |
|---|---|---|---|
| 10-03〜10-09 | 459 | 0 | 0.65% |
| 10-10〜10-16 | 645 | 0 | 0.47% |
| 10-17〜10-23 | 705 | 0 | 0.43% |
| 10-24〜10-30 | 698 | 0 | 0.43% |
| **4 週計** | **2,507** | **0** | **0.12%**（Wilson 上限 0.15%） |

- 窓の全行が `verdict: judged`・`enforced: true`（2,507/2,507）、fail-open 0。catalog は 53 本で一定。
- 選択数 p50 = 6、p90 = 10。毎回 6 本前後を選んでいて、0 本に寄る兆しは日次表にも無い。
- 参考: 保存されている全履歴（2026-07-10〜10-30）でも judged-empty 0/9,741。

## 判断（消費計画 (b) の分岐）

「0 が続く → ADR-0081 に dated note を書き、P2-01.5 の候補から外す」の側。ADR-0081 に 2026-10-31 の
note を足した。`none` 経路は存在するが、gemma4:e4b + 53 本の catalog では発火しない（95% 上限 0.12%）。
空選択を満腹信号として読む案と、空選択エピソードに限った insight 入力（「第 4 の手段」）は、
入力が来ないので成り立たない。

## n を縮めた理由

当初の計画は 4 週の手動 4 run（10-31）と 11-28 の 2 回目の読み = 8 週 2 読み。問いは「一度でも発火するか」
という存在の問いで、0 件のときに 1 回の読みで言えるのは上限だけ。4 週 2,507 件で上限は 0.12%、8 週に
伸ばしても約 0.06% になるだけで、分岐（0 か >0 か）の向きは変わらない。過去の 4 週はすでに記録済みなので、
未来の 4 週を待つ理由が無い（2026-10-31 のオーナー方針: 観察の n は問いが要る最小）。

## 撤去

消費計画 (c)「2 回で決めたら系列は撤去」: 決めたのでこの読みで撤去の条件が満ちた。
`scripts/self_regulation_reading.py` の `empty_sel` 列（`:33`, `:509`）の撤去は別 PR（コードとテストを
触るため、この読みの PR には含めない）。
