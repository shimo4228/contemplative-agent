# ADR-0128: 週次 materials の決定論的な四原則カバレッジ 4 列

## Status

accepted

## Date

2026-10-24

## Decided by

proposed-by: Claude Code session（ROADMAP P3-06.9 の前倒し実装）
decided-by: shimo4228（オーナー）— ROADMAP-2026-10 を 2026-10-11 に採択、2026-10-24 の「推奨どおり」指示
date: 2026-10-24

## Layer

instrument

## Context

四公理がエージェントに届くのは system prompt の散文としてだけで、実際の行動に現れて
いるかの読みは人間のもの（週次レポートの書き手の読み）しかない。その読みには既知の
失敗様式（書き手自身の選択関数、ADR-0099）があり、もう一つの自然な経路（モデルによる
公開コメントの判定）は ADR-0106 D4 が禁じている。

決定論的な読みが可能で必要な機構上の事実が 4 つある:

- `feed_manager.py` はコメント前に `internal_note` を取り出すが、note から
  `create_comment(post_text)` までの間に note に依存するものは無く、「読んでからやめる」
  分岐が無い。何も目に留まらなかったという note でもコメントに進む（Mindfulness: 検知と
  行為が切れている）。
- 同梱の identity テンプレートには「すべてに応えなくてよい」とあるが、本番の
  `identity.md` には無い。
- 公理の固有名詞は 2026-06 以降のコメントでほぼ消えた（0-2 %）が、2026-03（diachronic
  分析の Phase 3）には多かった。列 (c) 単独では陰性対照がほぼ自明になる。
- ADR-0047 は公理ラベルの崩壊を記録した。公理名を出すコメントが投稿の具体的な何かにも
  触れているかは測られていない。

## Decision

`scripts/principle_coverage.py` が週次 materials に `## Principle Coverage` 節を足す
（`scripts/weekly-analysis.sh` の instrument census の隣に配線）。読むのは
`comment-report-YYYY-MM-DD.md` だけ、モデルは呼ばず、状態も書かず、件数・率・95 % Wilson
区間（`scripts/_stats.py`、分母 10 未満は件数のみ）を出す。報告したものが生成に届く
ことはない — 読みであってフィルタではない（`config/prompts/principles.md:22`）。

| 列 | 定義 |
|---|---|
| (a) Mindfulness | Internal note が「何も目に留まらなかった」系の COMMENT / note つき COMMENT。旧形式の報告は note を持たず、0 でなく「note なし」と読む |
| (b) Silence | 自分が COMMENT を間に REPLY なしで 2 回続けたスレッド（post id）/ COMMENT か REPLY のあるスレッド。報告は自分の entry しか持たないので下限側の代理 |
| (c) Carewashing | COMMENT/REPLY ごと: Output の公理固有名詞、Context と共有する 5 語の逐語区間（具体参照）、具体参照を伴わない公理名、Context に無い constitution / axiom 一般語の自己言及 |
| (d) Identity | `identity.md` に沈黙許可文があるか（フラグ） |

較正（どちらも公開データ。`docs/evidence/principle-coverage/calibration.md` に凍結）:
陽性対照は 2026-03-12..20（`agent-diachronic-analysis.md` の Phase 3）、陰性対照は
2026-09-07..13 の週。

出力の境界は閉じている: 本文・post id・相手の名前は出力に出ない
（`tests/test_principle_coverage.py::TestOutputBoundary`）。Context は他エージェントの投稿だから。

## Review-when

`core/report.py` のレポート文法が変わるとき（parser は現在 2 文法を読む）、`feed_manager`
に note 後の辞退分岐が入ったとき（列 (a) が切断を測らなくなる）、identity テンプレートの
沈黙許可文が採択・退役されたとき（列 (d)）。

### Consumption plan (ADR-0101)

- **読み手**: オーナー。土曜ゲートで materials の 4 列を 4 週続けて読む。最短は Mac が
  script を pull してから 4 回目の土曜（10-31 に merge なら 2026-11-28 ごろ）。
- **4 週で決めること**: D-P3-06-3 — 「読んで返信しない」分岐やループ閉鎖の機構を足す
  価値があるか — を RFC で。それまでの推奨は A（記録のみ）で、裁定はオーナーが
  `gate_item` に書く。
- **撤去条件**: D-P3-06-3 が A なら 4 週後に列を materials から外し、読みを
  `docs/evidence/` に凍結する。B なら RFC が計器として引き継ぐ。

## Alternatives Considered

- **「コメントは公理を体現したか」をモデルで採点する。** ADR-0106 D4 と ADR-0080 の
  代謝の質の追補（単一スカラー禁止）により却下。
- **公理語のブロックや具体参照の要求を生成時に入れる。** 却下: 語句ブロックは
  `principles.md:22` が禁じる機構で、読みを目標にしてしまう。
- **(b) のためにエピソードログを読む。** 却下: エピソードのフォルダは prompt injection の
  経路（ADR-0107）。報告だけから出す代理を下限と明記する。

## Consequences

materials に表が 1 つ増える。2026-07 以降の窓では (a)(b) はほぼ 0 と読める。これ自体が
読みで、note と行為の切断や連続発話の不在は調整の結果でなく構造。列 (c) は 3 月の窓
（公理名 33.6 %、具体参照なし 30.8 %）と 9 月の窓（0.6 %）を分けるが、一般語 (c4) は後の
週も 10-13 % あり、固有名詞の列だけでは自己言及を過小に見積もっていた。

## References

- `ADR-0099` — 書き手自身の選択関数が決定論的な読みの理由
- `ADR-0106` — D4: 公開コメントをモデルで判定しない
- `ADR-0101` — 消費計画
- `ADR-0047` — 公理ラベルの崩壊
- `docs/evidence/principle-coverage/calibration.md` — 2 つの対照の読み
