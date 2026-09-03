---
state: draft 2026-09-02
state_since: 2026-09-02
review-when: RFC-0017 が withdrawn / rejected になる（前提の並列実験機構が無くなる）、または selector の幻覚率が catalog サイズと無相関だと再読で分かる（天井の物差しが消える）
---

## Summary

skill-stocktake の再設計 — family 飽和（P2）による merge / supersede / 退役の提案を weekly の読みとして定期化し、店の天井を selector の幻覚率で決める（RFC-0017 D2 の切り出し。順序は RFC-0017 の観測の後）。

## Motivation

skill store は 57 件で、抽出段（RFC-0017）は総数を気にしない設計にした。総数の管理は
skill-stocktake の責務だが、現行は手動 CLI の advisory（品質レポート + usage 読み + description
監査。ADR-0097 D3 で grouping / merge / clean は退役）で、code 所有の退出経路は never-selected
（weekly stage 7b が毎週読む）だけ。**`skills/.archive/` は 0 件 — 退出は一度も発火していない。**
つまり「family が飽和している → 畳む」（2026-07-25 のレビューで採用 5 件を選んだ実際の規則。
採用は「構造へのピボット族**でない**少数派」だけだった）は今、誰の仕事でもない。

天井の物差しは selector の幻覚率（RFC-0015: catalog 19 件 0.57% → 37 件 7.7% → 50 件 34.8%、
corpus トークンに単調。幻覚の 9 割は実在名の語形変化で code が弾くので害は無く、読み値のみ）。
数値キャップでなく消費者側の読み値で天井を決める（measurement-discipline 原則 4）。

## Guide-level explanation

- **weekly は読みだけ**（stage 7b の never-selected と同型）: family の grouping 提案（同族群と
  その代表）+ 幻覚率の現在値 + corpus トークン数 を weekly findings に出す
- **実行は土曜ゲートの人間**: merge（ADR-0097 D6 の adopt-superseding の語彙）/ supersede /
  archive（D5 の `.archive/` + `superseded_by`）
- family の判定者: RFC-0017 と同じく code 閾値の embedding 抑制は置かない（ADR-0074 で反証済み）。
  候補は (a) co-selection（同じコメントで一緒に選ばれる対、ADR-0097 D7 の family 検出）、
  (b) LLM 単一コール grouping（skill-stocktake の旧 grouping、frontmatter summary を証拠に）。
  どちらを主にするかは設計セッションで決める
- RFC-0017 D8 の「wiki の pruning」もここに置く（論文が持たない機構。第 1 段の終了条件が発火してから）

## Reference-level explanation

- 触るもの: `cli/skill_stocktake*.py`、`scripts/weekly-pipeline.sh`（読みの stage 追加）、
  weekly findings の節、`core/never_selected_metrics.py` の隣に family 読み
- ADR-0097 との関係: D2（rules-distill 退役）は維持、D3（stocktake 縮小）は部分 supersede、
  D5（退出機構）は再利用、D7（rule 昇格 A′）は維持。「merge / clean を再提案しない」の失効条件
  「insight 生産側の変質」は RFC-0017 で発火済み
- 消費計画（ADR-0101）: 読み手 = 土曜ゲート、毎週。幻覚率が RFC-0015 の帯（catalog 45〜50 で
  17〜35%）から**下がる**かを ≥ 600 judged records の窓で 2 回読んで、天井仮説の当否を決める。
  ADR-0097 Review-when 第 1 腕（下がらなければ catalog サイズ仮説が誤り → family 単位の catalog へ）
  と同じ判定

## Drawbacks

- 店を畳む判断は不可逆に近い（archive は復元可だが、selector の学習は無いので影響は即時）
- RFC-0017 と同じ観測窓で動かすと効果が分離できない（順序を守る対価は時間）

## Rationale and alternatives

- 抽出段で P2 を持つ案は RFC-0017 の設計セッションで却下（抽出段が総数を気にすることになる）
- 何もしない案: 退出は 600 exposure の never-selected だけで、7 週で 0 件。店は増えるだけ

## Prior art

RFC-0017（D2 / D8 / D9）、ADR-0097（D3 / D5 / D6 / D7 と Review-when）、RFC-0015（幻覚率の 3 読み）、
ADR-0074（embedding 閾値の反証）、`docs/evidence/adr-0074/insight-candidate-review-20260718.md`。

## Unresolved questions

- family の判定者は co-selection か LLM grouping か、両方か
- 「畳む」の単位は skill 単位の archive か、family を 1 本に合成する merge か
- wiki の pruning をここに置くか、RFC-0017 第 2 段に戻すか

## Status

draft（2026-09-02）。RFC-0017 の設計セッションで「抽出段と店内は分ける、順序は抽出段が先」と
決まり切り出した。

## Next action

- **2026-09-04 追記**: review-when の「RFC-0017 が withdrawn / rejected」は obsoleted で発火した（並列実験機構は
  [RFC-0025](0025-retire-wiki-mechanism.md) で退役）。前提を差し替える: 再開条件は
  [RFC-0023](0023-novelty-gate-retrieval-and-rare-lane.md)（候補検索 gate）の決着。family の判定者候補に
  **供給列**を足す — RFC-0023 の同じ検索で「各 skill に今も行が届いているか、最後はいつか」を code で数える。
  需要（選択ログ）も供給も無い skill が退役候補、供給が有るのに需要が無い skill は description が選択を
  引けていない（description 監査の対象をそこに絞る）。D8 の「wiki の pruning」は消える
- 再開条件（旧）: RFC-0017 の Proposer が shadow に入り（D10）、wiki の肥大読み値が 4 週分溜まること
- 照合先:   weekly findings の would-be 提案 4 週分 + `logs/skill-selection-*.jsonl` の幻覚率
- 成立時:   設計セッション（family の判定者と畳む単位を決める）→ accepted
