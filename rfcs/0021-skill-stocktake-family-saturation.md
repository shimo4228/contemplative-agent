---
state: in_progress 2026-09-07
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

## Next action（2026-09-07 以前）

- **2026-09-04 追記**: review-when の「RFC-0017 が withdrawn / rejected」は obsoleted で発火した（並列実験機構は
  [RFC-0025](0025-retire-wiki-mechanism.md) で退役）。前提を差し替える: 再開条件は
  [RFC-0023](0023-novelty-gate-retrieval-and-rare-lane.md)（候補検索 gate）の決着。family の判定者候補に
  **供給列**を足す — RFC-0023 の同じ検索で「各 skill に今も行が届いているか、最後はいつか」を code で数える。
  需要（選択ログ）も供給も無い skill が退役候補、供給が有るのに需要が無い skill は description が選択を
  引けていない（description 監査の対象をそこに絞る）。D8 の「wiki の pruning」は消える
- 再開条件（旧）: RFC-0017 の Proposer が shadow に入り（D10）、wiki の肥大読み値が 4 週分溜まること
- 照合先:   weekly findings の would-be 提案 4 週分 + `logs/skill-selection-*.jsonl` の幻覚率
- 成立時:   設計セッション（family の判定者と畳む単位を決める）→ accepted

## 2026-09-07 順序の再決定

RFC-0023 は切り替え（S9、`{known}` を cosine top-k に）を dispatch 済みで再開条件は成立。RFC-0024 の外部照合
（同日）で「読み手としての 4B 級は skill 数 10〜20 件超で選択が急落する（arXiv:2602.16653）、店の大きさが
抽出の型より先に効く」と読めたため、**RFC-0024 より先に本 RFC を設計セッションにかける**（著者判断）。

## 2026-09-07 決定（著者回答: 案 A — 決定論ゲート、archive のみ、gemma 判定は入れない）

`draft` → `accepted`。設計セッション（同日）で外部研究を照合し（as-of 2026-09-07、一次ソース fetch）、
Unresolved 3 点を決めた。

**判定者は code。** 退役研究は決定論ゲートが主流（Library Drift arXiv:2605.19576 / ASSAY arXiv:2606.15390 /
SLIM arXiv:2605.10923 / SkillOps arXiv:2605.13716 — いずれも LLM の verdict はログに残すだけで引き金にしない）。
LLM judge に退役を委ねた場合の破綻は The Blind Curator（arXiv:2607.07436、2026-08）が実証: false-pass
偏りが 0.45 を超えると退役が完全停止し集約指標に出ない。gemma を判定者にする案 B は入れない（入れるなら
先に欠陥注入で偏りを測る）。人間ゲートは承認権限として残す（pipeline が `--archive-names` のファイルを書き、
土曜ゲートは承認するだけ）。

**信号は「需要が無い AND 混同がある」。** CA にはタスク成否の ground truth が無いので寄与ベース（Library Drift
の (成功−失敗)/試行、ASSAY の masking）は移植できない。使えるのは SkillOps 型の AND（低 utility かつ重複あり —
唯一無二の能力を消さないため）:

- 候補 (i) never-selected strict（既存、ADR-0097 D5、床 600 judged exposures）
- 候補 (ii) **読み手の混同対**: selector の rejected name が語形変化 / 意味的取り違えで写像された先
  （`scripts/skillsel_reading.py::classify` の規則、RFC-0015 第 4 読み）を集計し、ある skill について
  「混同で名指された回数 ≥ 正しく選ばれた回数」かつ露出が床以上なら、混同の相手と対にする。対の中で
  選択数が少ない方が候補。2026-09-04 の読みでは `suspend-interpretation-upon-premise-doubt` 34 対 35、
  `identify-systemic-boundary-stressors` 23 対 30 がこの形
- 供給途絶（RFC-0023 の cosine 検索で最後に行が届いた週）は**読み値のみ**、引き金にしない。時間閾値で
  退役する skill library の論文は無い
- 証拠の床は必須: Library Drift A4 は証拠不足で退役すると店が 2 件に崩壊し無 skill を下回った

**単位は archive のみ、merge しない。** Retain or Consolidate（arXiv:2607.17545）: 生の本文が予算に収まる
緩い予算では全統合演算が負（CA の pass 1 は 57 行が窓に収まる）。逐次統合は崩壊する（arXiv:2605.12978:
AWM 0.64 → 0.20）。SkillCommit（arXiv:2608.15165）: 意味的類似で merge した ACE は 3 改善 24 劣化。
archive 型の先例は SLIM の inactive set。CA は `skills/.archive/` + `superseded_by` を流用。

**天井は数値キャップでなく読み手の読み値。** Skill Shadowing（arXiv:2605.24050）: 損失の 68% は誤選択・
非選択で文脈量の寄与はノイズ並み、小型は abandonment に倒れる。Library Drift の上限 50 に導出根拠は無い。
効果の読みは幻覚率が宣言帯 10〜25% に戻るか（RFC-0015 の計器、600 judged records の窓で 2 回）。
戻らなければ次は退役でなく**選択時の family 代表化**（Right Family, Wrong Skill arXiv:2606.10388: family
から代表 1 件だけ通して HSR@3 0.35 → 0.007）— 本 RFC の Future possibilities に置く。

副次の読み: ContinualSkillBench（arXiv:2608.03874）は skill 維持ありと素の ICL が 0.602 対 0.605 で差なし。
店の集約効果はゼロに近い可能性があり、退役の目的は性能でなく**読み手が区別できる店を保つ**こと（幻覚率）。

### 実装（build へ）

- weekly の stage 7b の隣に **confusion-pair reading**（code、read-only）: `skillsel_reading.py::classify` の
  規則を `core/` に移し（script は計測用に残す）、窓内の rejected name を写像先ごとに集計、上の条件で
  候補対を出す。出力は per-week JSON + findings の節（never-selected と同じ形）
- pipeline が候補（never-selected strict ∪ 混同対の少ない方）を `weekly-<end>-archive-candidates.txt` に
  書く。**store は触らない** — 土曜ゲートが `adopt-staged --archive-names` に渡す
- 消費計画（ADR-0101）: 読み手 = 土曜ゲート、毎週。幻覚率が帯に戻るかを 2 窓読んで天井仮説の当否を決める。
  満了 = 2 窓とも帯内 → 混同対の読みは維持、候補生成は continue。2 窓とも帯外 → family 代表化へ
- ADR 1 本（ADR-0097 D3 の部分 supersede: stocktake の退出経路に混同対を足す）

## 2026-09-07 build

決定を実装した（branch `task/confusion-pair-reading`）。所有 ADR は
[ADR-0105](../docs/adr/0105-skill-store-exit-confusion-pairs.md)（ADR-0097 D3 の部分 supersede）。
`core/skill_confusion.py`（規則は `core/selection_metrics.py` の
`classify_hallucination` / `nearest_catalog_name` を import、床と窓は
`core/never_selected_metrics.py` から共有）、weekly stage 7c
（`scripts/confusion_pair_reading.py`）、候補ファイル
`weekly-<end>-archive-candidates.txt`。本番ログへの read-only dry run は
[docs/evidence/adr-0105/dry-run-20260907.md](../docs/evidence/adr-0105/dry-run-20260907.md)
に凍結（14 日窓の混同対は 1 件で、never-selected strict に既にいる名前 — 第 2 の信号が
この週に足した名前は 0 件。上の「34 対 35 / 23 対 30」は 7 日窓の読みで、後者は 24 対 30 と出た）。
天井の 2 窓読みは未消化 — 消費計画と読み手の配線は ADR-0105 の `## Review-when` と
`.claude/skills/weekly-gate/SKILL.md` Step 6c。

## 2026-09-09 triage 照合（無人 cycle）

`in_progress` 維持。照合先（土曜ゲートの 2 窓読み）は未発火 — stage 7c は 2026-09-07 merge で、最初の窓は 2026-09-11 の weekly 走行後。
