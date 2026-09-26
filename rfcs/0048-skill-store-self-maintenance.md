---
state: draft 2026-09-26
review-when: RFC-0042 の再開後 3 週の読み（2026-10-10 まで）でゲートに届く候補数が週 30 件台に戻る（入口が絞れていないなら出口の自動化は順序が逆）、または本番生成モデルが gemma4:e4b から替わる（退役判定を LLM に委ねる案の前提が変わる）
---

## Summary

skill store の**出口**（退役）を、土曜ゲートの Claude が毎週手で実行する形から、エージェント自身が自己維持する形へ移す。入口（RFC-0042、ADR-0111）と同じ向きで、人間ゲートは権限として残し、負荷を 0 に近づける。

## Motivation

- 入口は 2026-09-19 に絞れた（再開後 1 回目の読み: 候補 0 件、ADR-0111）。出口は変わっていない —
  退役候補は毎週 `weekly-{end}-archive-candidates.txt` に機械が 1 件ずつ出し、土曜ゲートで Claude が説明し、
  人間が承認し、`adopt-staged --archive-names` を Claude が打つ。store の代謝の**片側だけ**が人間の手にある
- 北極星（ADR-0080 追補）の未完成条件は「ループがオーナーと Claude Code の日常的関与なく自己調節して回る」。
  出口が人間の手にある間、店は自律的に代謝しない（gate_record の `insight_adopted` と `skills_archived` を並べる読み —
  RFC-0021 の 2 窓読みの材料、2026-09-08 著者指示）
- 出口の判定材料はすでに機械が持っている: never-selected strict（ADR-0097 D5、Slote 床 600）、混同対（ADR-0105）、
  抽出後判定の store 同士の `duplicate` 読み（ADR-0111、leave-one-out）。今の土曜ゲートで Claude がしているのは
  これらを並べて説明するだけで、人間の裁定は 2026-09-19 / 09-26 とも機械の候補どおり（09-19 は推奨に反して退役）

## Guide-level explanation

出口を 3 層に分ける。どの層も**削除はしない**（`skills/.archive/` への移動、可逆 — ADR-0097 D5）。

1. **機械が退役する層**: 判定が決定論で決まるもの。never-selected strict（全履歴で 0 回選択かつ judged 露出 ≥ 600）は
   insight run の末尾か weekly stage で archive まで実行し、監査ログに理由コードを残す。人間ゲートには**件数と名前を報告**
   （承認を待たない — 可逆なので）
2. **エージェントが提案し、人間が承認する層**: 判定に読みが要るもの（混同対、`duplicate` の family）。今の形のまま
   候補ファイルに出す。ただし説明は Claude でなく機械が定型で付ける（軸ごとの数字だけ。推奨は書かない）
3. **人間だけの層**: 復元。`skills/.archive/` から戻すのは人間の操作のまま

反証条件（事前登録）: 層 1 で archive した skill が翌 4 週以内に復元される事例が **2 件**出たら、層 1 は止めて全件を層 2 に戻す
（ADR-0097 Review-when と同じ腕）。

## Reference-level explanation

未設計。決める点:

- 層 1 の実行位置（insight run の末尾 / weekly stage 7 の新しい段 / 独立の launchd job）と、pending ガード・staging との関係
- 層 1 の監査ログ（ADR-0075 — append-only JSONL、理由コード、run_id）。`audit.jsonl` の `direct-archive-auto` は既存の語彙
- 層 2 の定型説明を出す場所（候補ファイルの隣か、weekly-report の 1 節か）と、土曜ゲート skill の Step 6c の書き換え
- 混同対の「少ない側を退役」規則（ADR-0105）を層 1 に上げるか層 2 に残すか — 09-26 の候補は similarity 0.94〜0.96 の
  語形の揺れで、意味の重複でなく名前の綴りの問題（退役でなく改名が正しい可能性）
- gate_record の `skills_archived` に層 1 の件数を含める（入口 / 出口の縦断読みを切らない）
- 計器の溶解義務（ADR-0101）: 層 1 が読み値を出すなら消費計画を書く

## Drawbacks

- 出口を機械に渡すと、誤退役が無音で進む（ADR-0105 が gemma を退役の判定者にしない理由 — The Blind Curator の
  false-pass 偏り）。層 1 を**決定論の規則だけ**に限るのはそのため。LLM の verdict を層 1 に入れない
- 復元は人間の操作のままなので、誤退役の検出は「選択ログに出なくなった skill を人間が気づく」経路しか無い —
  反証条件が 2 件で発火するのはこの弱さの代償
- 店が飽和した今、出口が動いても入口（候補 0 件）が動かなければ store は縮む一方。縮むことが正しいかは
  価値層の問いで、機構層では答えない

## Rationale and alternatives

- **現状維持（毎週人間が承認）**: 負荷は週 1 件で小さいが、北極星の未完成条件を満たさない
- **全部を層 1 にする（LLM 判定を含む）**: ADR-0105 が却下。再提案しない
- **退役を止めて store を凍結**: RFC-0042 の review-when の側。出口の設計は凍結を選んだ場合には不要

## Prior art

ADR-0097 D5（archive は可逆、Slote 床）、ADR-0105（混同対、gemma を判定者にしない）、ADR-0111（抽出後判定と
leave-one-out の family 読み）、RFC-0021（family 統合 — 出口の設計に吸収されうる）、RFC-0042（入口）。

## Unresolved questions

- 層 1 の規則に混同対を含めるか
- RFC-0021（family 統合）をこの RFC に吸収するか
- 層 2 の定型説明を機械が出すとき、土曜ゲート skill の Step 1b（eli5 ブリーフィング）は退役候補について不要になるか

## Status

draft 2026-09-26 — 2026-09-26 の土曜ゲートで著者が起票を指示。設計は未着手。着手は RFC-0042 の再開後 3 週の読みの後
（review-when）。

## Next action

RFC-0042 の 3 回の読み（〜2026-10-10）を待ち、入口が絞れていることを確認してから設計セッション。設計が決まったら ADR。
