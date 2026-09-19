---
state: accepted 2026-09-19
review-when: 再開後 3 週の土曜ゲートの読みで、insight からゲートに届く件数が停止前の水準（週 30 件台）に戻っている（絞りが本番で再現しなかった — 凍結か再設計かを読み直す）、または本番生成モデルが gemma4:e4b から替わる（温度・拘束・コール分割の前提を測り直す）
---

## Summary

insight の入口を小さな変更で絞る — 判定コールを temperature 0 と enum 拘束にし、抽出の前に「再確認 / 材料不足 / 手直し / 新規」を名乗らせ、書かれた skill を store と突き合わせる判定を 1 段足す。RFC-0041（根本再設計）の代わり。

## Motivation

store は 7〜8 月に 19 → 57 件へ育って飽和した。飽和した store では「毎週ほぼ全件却下」が正常な定常状態で、
ADR-0074 が insight の役割を「新しい安定テーマの検出」と定義した時の想定（静かな週は 0 novel clusters）でもある。
異常だったのは採用 0 ではなく、その全件却下を人間が毎週 30〜75 件読んで手で実行していたこと
（土曜ゲート 4 週で却下 142 件）。問題は歩留まりでなく**ゲートに届く量**で、量は小さな変更で動くと
2026-09-19 の read-only 再生で読めた（[docs/evidence/rfc-0041/](../docs/evidence/rfc-0041/README.md)）:

- 抽出前 gate（`insight_novelty`）は temperature 1.0 で走っており、同一プロンプトの 2 反復が covered 集合の
  半分しか共有しない（Jaccard 0.50）。temperature 0 は決定的で、covered は 66 → 99 / 154
- プロンプト末尾の「迷ったら NEW、over-report が安全」は t=1.0 では揺れに埋もれ、t=0 では効く
  （削除で 112、反転で 127 / 154）。over-report の根拠（ADR-0074 D6「抑制されたテーマは二度と見えない」）は、
  同じ ADR の D5（本物のテーマは新パターン経由で戻る、再発性の実測）と食い違う
- 抽出前 gate はどの文言でも、ゲートが却下した候補と対照を区別しない（書かれる前の判定には比べる証拠が無い —
  ADR-0084 の形）。書かれた skill を store の最近傍 5 件と並べる判定は向きが合う: t=0 で却下 68 件の 33 を
  `duplicate`、対照 7 件は 0、採用済み（leave-one-out 53 件）は 12
- 直列に重ねると、ラベルのある 75 件（2 週分）→ 16 件
- enum で拘束した 512 コールに enum 外・parse 失敗は 0。RFC-0027 の 3 回目の run で出た書式違反
  （target 名の日付接尾辞落ち 5/5、evidence id の取り違え 2/12）は、どちらも欄が無拘束の `string` だった

## Guide-level explanation

```text
クラスタ
  → 抽出前 gate          temperature 0、tie-break は covered 向き
  → 名乗りコール         temperature 0、kind / target / evidence_ids を enum 拘束
       reconfirm / insufficient → ここで終わり（候補を出さない。観察として残る）
       revise / new            → 本文コールへ
  → 本文コール           自由記述（temperature は現行のまま）
  → description / name   別コール、拘束つき。様式違反は保存時に拒否（切断しない）
  → 抽出後の重複判定     temperature 0、verdict と最近傍名を enum 拘束
       duplicate → 候補にしない（最近傍名つきで監査ログへ）
       distinct  → staging へ
  → 土曜ゲート           承認 / 却下（保留なし）
```

ゲートに届くのは週に数件で、`revise` は既存 skill への差分として届く。抽出後判定が store 同士に出す
`duplicate` の対（leave-one-out の読み）は、退役候補の**列挙**として土曜ゲートに並べる — 判定者にはしない
（ADR-0105 が gemma を退役の判定者にする案を不採択にした理由は生きている）。

## Reference-level explanation

作業項目（dispatch の単位は triage が切る）:

1. 抽出前 gate: `insight_novelty` の判定コールを temperature 0 に。`config/prompts/insight_novelty.md` の
   tie-break 2 文を covered 向きに差し替える。ADR-0074 D6 に日付つき追補
2. 名乗りコール: RFC-0027 の `insight_revision_reason` を本番経路へ。`target_skill` は供給名の enum、
   `evidence_ids` は観察 id の enum 配列。temperature 0
3. 本文と frontmatter のコール分割（RFC-0024 の柱: 様式を外す / コール分割 / description に what + when）。
   保存時の拒否は code 側
4. 抽出後の重複判定段。プロンプトは `config/prompts/` へ（測定スクリプトの inline 文言が出発点）。
   本番経路なので ADR-0075 の監査ログ（append-only JSONL、untrusted 由来本文は b64 + sha256、理由コード）を同じ PR で
5. 保留の撤去: `adopt-staged --hold-names` と、pending ガード（ADR-0074 D4）の「保留 item」経路。
   ガード本体（未レビューの batch を上書きしない）は残す。weekly-gate skill は 2026-09-19 に対応済み
6. insight 週次スケジュールの再開（2026-09-19 から停止中）は 1〜5 の後。再開後 3 週、ゲートに届く件数を
   土曜ゲートで読む（review-when の読み）
7. RFC-0027 の消費計画の満了: 比較専用の実行経路（`scripts/insight_revision_compare.py` ほか選定・描画・
   テスト）の撤去。2 で本番へ移す部品を取り出した後に行う
8. 測定スクリプト 2 本（`scripts/novelty_tiebreak_replay.py` / `scripts/post_extraction_judge_replay.py`）は
   一発測定。4 が入った時点で撤去する（evidence は残る）

鮮度規約: 段構成が変わるので、所有 ADR（ADR-0074 追補か新設）と `docs/diagrams/` の該当図、
`docs/CYCLES.md`、CLAUDE.md の CLI 節を同じ PR で同期する。

## Drawbacks

- 根拠は 1 run（154 クラスタ、2 週分の窓）の再生。ここからプロンプトを詰めるとその run への過適合になる —
  文言はこれ以上いじらず、再開後の実数で読む
- 対照 7 件は説明係（Claude）の読みで、オーナーの裁定ではない。抽出後判定が「良い候補を通す」側の証拠は弱い
- 抽出後判定は採用済み skill の ~2 割を `duplicate` と言う。誤判定か store の実重複かは未分離で、
  本当に新しいテーマも同じ率で落ちうる（再発性に頼る）
- 名乗りの再現性は未測定（RFC-0027 の 12 問は各 1 回、temperature 1.0 相当）。`revise` 本文の質は誰もまだ読んでいない
- LLM コールが候補あたり 2〜3 回増える。ただし reconfirm / insufficient は ~20 秒の名乗りだけで終わる
  （RFC-0027 3 回目: 12 問中 7 問）

## Rationale and alternatives

- **RFC-0041（knowledge のスキーマからの根本再設計）**: withdrawn。動機だった「入口が何も通さない」は
  故障でなく飽和の定常状態で、量の問題は上の変更で 1/5 になると読めた。スキーマ変更は消費者が多く、
  この問題に対して過大
- **store を凍結して insight を退役**: 再開後の読みで件数が戻らなければこちらへ倒す（review-when）
- **抽出前 gate の変更だけ**（temperature 0 で 75 → 42、tie-break 反転まで入れて 25）: 件数は動くが区別をしない

## Prior art

ADR-0074 / ADR-0104（週次 staged insight と novelty gate）、ADR-0084（judge は成果物の後に置く）、
ADR-0105（gemma を退役の判定者にしない）、RFC-0024（コール分割）、RFC-0027（名乗りの比較 3 run、
`docs/evidence/rfc-0027/`）、skill `llm-pipeline-layering`（constrained decoding は enum から）。

## Unresolved questions

- 名乗りコールに渡す「既存 skill」は何件か（RFC-0027 は 3 件、抽出後判定は 5 件）
- `revise` をゲートでどう見せるか（差分の形、承認すると何が置き換わるか、前版の保全）
- 抽出後判定の `duplicate` を、候補を落とす理由として監査ログに残すだけでよいか、週次の読みに入れるか
  （計器にするなら ADR-0101 の消費計画が要る）
- RFC-0021（family 統合）/ RFC-0023（候補検索と希少レーン）/ RFC-0039（surprise 参照窓）の扱い —
  4 と 6 が入った後に triage で読み直す。0039 は保留が無くなると発火条件（窓 ≥ 1,000 行）がほぼ起きなくなる

## Future possibilities

抽出後判定の store 同士の読みが安定するなら、RFC-0021 の family 統合の材料を毎週無料で出せる。

## Status

accepted 2026-09-19 — 同日の土曜ゲートの対話でオーナーが方針を決定（temperature 0 + gemma 判定 1 段で
週 ~8 件は妥当、RFC-0027 の書式違反はコール分割と拘束で消える見込み）。RFC-0041 は withdrawn、
RFC-0024 と RFC-0027 は本 RFC に吸収して resolved。実装は未着手、insight 週次は停止中。

## Next action

triage が作業項目 1〜5 を dispatch 単位に切る（1 は単独で小さい。2〜4 は段構成の設計を 1 回固めてから）。
