---
state: in_progress 2026-09-20
review-when: 本番生成モデルが gemma4:e4b から替わる（temperature の効き方を測り直す）、または skill selection の prompt / catalog の形が変わる
---

## Summary

skill selection の判断コールを temperature 0 にする（幻覚のある行が 21〜29% → 7.3%、速度・選択数・判断は不変）。その上で enum 拘束を第 2 段として、受入条件つきで入れるかを決める。[RFC-0043](0043-skillsel-offline-arm-replay.md) の判定 1 の帰結。

## Motivation

`core/skill_selection.py::select_applicable_skills` は temperature 指定なし（既定 1.0）で skill 名を自由生成させ、code が catalog と照合する。catalog に無い名前は弾かれるので伝播は 0 だが、選ばれるはずの skill が落ちる。RFC-0043 の 150 行 offline 再生（[evidence](../docs/evidence/rfc-0043/README.md)「第 2 ラウンド」）で:

| arm | 幻覚のある行 | 選択数 平均 | opus-5 との Jaccard | cache なしの latency |
|---|---|---|---|---|
| 自由生成 t=1（現行、2 反復） | 28.7% / 20.7% | 6.0 / 6.2 | 0.143 / 0.144 | 9.8 秒 |
| **自由生成 t=0** | **7.3%** | 6.3 | 0.151 | 同じ経路 |
| enum 拘束 t=1 | 0% | 7.1〜7.4 | 0.154〜0.158 | 13.0 秒 |
| enum 拘束 t=0 | 0% | 8.1 | 0.162 | — |

temperature を 0 にしても天井との一致は変わらない（対の差 −0.008、95% CI [−0.023, +0.007]）。変更は定数 1 つ。[RFC-0042](0042-insight-entrance-narrowing.md) が insight の判定コールに入れたのと同じ手（`insight_novelty._NOVELTY_TEMPERATURE = 0.0`）。

これは修理であって能力の拡大ではない（北極星の機構層の審査）。gemma の判断の質そのもの — 71〜82% の行で同じ skill を選ぶ癖、opus-5 との一致 0.15 — は temperature でも enum でも動かず、本 RFC は触れない。

## Guide-level explanation

**第 1 段（本 RFC の本体）**: selection コールに temperature 0 を渡す。prompt・catalog・照合ロジック・監査レコードの形は変えない。

**第 2 段（第 1 段の本番読みの後に判断）**: enum 拘束（`format=` に catalog 名の enum 配列）。幻覚は構造的に 0 になるが、RFC-0043 で代価が 3 つ見つかっている — 出力 tokens が約 2 倍（114 対 62）で自由生成より遅い / `parse_failed` が約 1%（temperature 0 でも出る。`num_predict=400` に当たる）/ 選択数が平均 +1〜2 件、最大 16 → 22〜29。入れるなら受入条件は: `num_predict` を引き上げて `parse_failed` が 0、選択数の上限側が自由生成の分布を超えない、latency の増分が本番の窓に収まる。第 1 段で幻覚が 7% 前後まで下がった後に、残りを消す価値が代価に見合うかを本番の読みで決める。

## Reference-level explanation

- 変更点: `core/skill_selection.py` の `generate(...)` 呼び出しに temperature 0（定数は `insight_novelty` と同じ流儀で名前を付ける）。`generate` が temperature を受けるかは着手時に確認（RFC-0043 の replay は localhost 直叩きで t=0 を渡した — production の wrapper が引数を露出していなければ、そこが変更点になる）
- 監査: `logs/skill-selection-*.jsonl` のレコードに temperature を 1 欄足す（変更前後のレジームを読みで分けるため。ADR-0075）
- 所有 ADR: ADR-0081（two-pass enforcement）に追補。`llm-calls-*.jsonl` は既に `temperature` を持つ
- 本番の読み: 既存の週次計器（`classify_hallucination` を使う skill selection の読み）で、変更後 2 週の幻覚率が offline の 7.3% と同じ帯に入るかを見る。新しい計器は足さない

## Drawbacks

- temperature 0 は同じ状況に同じ選択を返す。gemma の癖（同じ skill への偏り）が固定される方向に働く可能性がある — offline では最頻 skill の出現率が 71% → 77% に上がった。選択の多様性が値層の観察に効いているなら、これは損失
- offline 再生は今日の identity / 憲法で system prompt を再構成しており、本番の過去時点と完全には一致しない

## Rationale and alternatives

- **enum 拘束を先に入れる**: 幻覚は 0 になるが遅く、`parse_failed` と選択数の膨張を連れてくる。temperature 0 は代価なしで幻覚の 2/3〜3/4 を消すので、先に入れて残りを測るのが安い
- **何もしない**: 伝播は 0 なので害は「取りこぼし」だけ。ただし 5 行に 1 行以上で起きている
- **判断モデルを替える**: RFC-0043 の読みでは、判断の質を動かすのは interface ではなくモデル。ただし本番生成モデルの交代は ADR-0069 の再判断で、本 RFC の範囲外

## Prior art

RFC-0042（insight の判定コールを temperature 0 と enum 拘束に）、RFC-0015（幻覚の 3 機構: 語形変化 / 意味的取り違え / 値層の混入）、RFC-0043（本 RFC の根拠となる測定）、skill `llm-pipeline-layering`。

## Unresolved questions

- temperature 0 で残る 7.3% の内訳（RFC-0015 の 3 機構のどれか）。offline の行データから分類できる
- 選択の固定化が、下流（生成されるコメントの多様性）に見える形で効くか

## Status

in_progress — 第 1 段は 2026-09-20 に本番へ入った（`4159264` + レビュー指摘の修正、main `90ab113`）。`_SELECTION_TEMPERATURE = 0.0`、
selection の監査レコードに `temperature` 欄（judged と fail-open は 0.0、呼び出し前の abstain は null、欄が無い行は旧レジームの 1.0）、
ADR-0081 に追補。temperature 0 が Ollama の `options` まで届くことは呼び出し経路を追って確認済み（falsy として落とす分岐は無い）。

build の検収で訂正された点が 2 つある。(1) offline の 7.3% は本番の目標値ではない — 150 行は記録上の幻覚あり / なしを 75 / 75 に
層別した標本で、本番の幻覚率は直近 14 / 21 / 30 日で 23.1% / 24.3% / 23.6%。反証条件は「変更後も 20% 前後に留まる」
(2) 「速度は不変」は測っていない（cache をそろえた副標本に t=0 の arm が無い）。第 1 段の最初の本番稼働は同日 18 時のセッションで、
Ollama は同日 0.30.11 → 0.34.2 に更新されている（v0.31.2 が thinking 無効時の structured output を修正、v0.34.0 が Apple Silicon での
structured output の性能を改善 — 第 2 段の latency は 0.34.2 で測り直す）。

## Next action

第 1 段の本番 2 週の読み（2026-10-04 の土曜ゲート以降）: 既存の skill selection の読みで、`temperature` 欄が 0.0 の行の幻覚率を見る。
20% 前後に留まれば第 1 段を読み直す。下がっていれば、残りを enum 拘束（第 2 段）で消す価値が代価に見合うかをオーナーが判断する。
