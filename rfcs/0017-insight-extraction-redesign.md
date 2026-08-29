---
state: draft
state_since: 2026-08-26
review-when: ADR-0080 追補（代謝の質）が supersede される、または週次候補量が設計変更なしで恒常的に 1 桁へ落ちる（premise の自然消滅）
---

## Summary

insight 抽出（knowledge patterns → skill 候補）の再設計 — 頻度キーの抽出に飽和シグナルと新規性の器官を与える（ADR-0080 追補「代謝の質」の摂取側修理。オーナー指示 2026-08-26「抽出する機構を治すのが先決」）。

## Motivation

現行の抽出は「その週の episode 由来 pattern から ≥3 件の cluster を作れたもの」を候補にする**頻度フィルタ**で、store の状態が入力に無い。行動がテーマ的に安定したエージェントでは頻度が高いもの = 既知なので、この抽出器は構造的に既知を再発見する。実測: 7 週間で staged 438 / adopted 53（12%）、却下理由はほぼ全部「採用済み skill に覆われている」か「同 batch の兄弟」（ADR-0097 Context）。

同時に、本当に新しい出来事は定義上まだ繰り返されておらず cluster 床 ≥3 を越えられない — **重複の洪水と新規の取り逃しは同じ欠陥の両面**。濾過層も現在は弱い novelty gate 1 枚のみ: worth gate は ADR-0097 D1 で撤去（gemma self-judge が 3 回の実測で全件 yes）、実効の判定者だった headless reviewer は ADR-0098 で廃止。novelty gate 自体も成長期の較正（「迷ったら NEW」、証拠は名前と description のみ、batch 内兄弟は不比較）のまま飽和期に立っている。

ADR-0080 追補はこの修理を認可する: 自己調節に到達するための有界な機構工事は装置の修理でありスコープ内。代謝の質条項が要求する複数軸（新規性・重要度・環境の反応）の識別能力を摂取装置に与えることが本 RFC の目的。

## Guide-level explanation

設計の候補要素（採否・組み合わせは設計段で決める）:

1. **飽和シグナル** — `NOTHING-PROMOTABLE` の abstain 経路と理由コードは ADR-0097 D1 が意図的に残した（「channel を残し判定者を落とす」）。信頼できる判定者を挿す
2. **抽出時照合** — 候補 cluster を store と照合してから staging に置く。関連性の照合は
   embedding / lexical retrieval の仕事（「関連性の判断はその時点で払える最強の判定者に」
   RFC-0005。gemma の yes/no は 3 回 refuted 済み）。`scripts/retrieval_recall_measure.py`
   （ADR-0097 スライス 3 予約）は reviewer 用だったが抽出側へ向け直せる
3. **新規性の軸** — (a) store からの距離（embedding）、(b) 自分の過去からの距離 = surprise
   （復元は [RFC-0016](0016-restore-surprise-instrument.md)）、(c) 環境の反応（読み値として。
   報酬重み付けは ADR-0051 の supersede を要する — ADR-0080 追補 B の境界）
4. **novelty gate の再較正** — 「迷ったら NEW」は store が空だった時代の非対称性。飽和期は
   コスト構造が逆転している（重複が高くつき、取り逃しは 12% しか起きない）

## Reference-level explanation

- **教師データが既にある**: 7 週 438 候補すべてに人間（+reviewer）の判定が付いている。
  新しい門番は本番投入前に offline replay で較正できる（ADR-0097 スライス 3 の作法）
- **沈黙の飢餓ガード**: 較正を逆に振ると「本当に新しい skill を静かに潰す」が可能になる。
  抑制した候補は理由コード付きで記録しリプレイ可能にする（observability by default、
  ADR-0075）。計器の本体は「何を通したか」でなく「何を止めたか」
- **一変数ずつ**: ADR-0097 D8 の規律に従い、変更ごとに期待効果と最小読み取り数を事前登録
  （judged ≈ 80–95/日）。archive・rule 変更と同じ週に動かさない

## Drawbacks

- 摂取装置への機構追加は「機構層は止まるのが完成」と表面上逆行する — ADR-0080 追補の
  合成規則（自己調節に到達するための有界工事は修理）が根拠だが、工事が肥大したら
  この規則の悪用になる（追補自身が Negative に記録）
- 抑制が効きすぎると代謝の観察が痩せる（上記の飢餓ガードが対価）

## Rationale and alternatives

- **月次化だけで済ます**（ADR-0097 Review-when 登録済みの手）— 却下方向: 総量は同じで
  まとめて見るだけ。生成が飽和を知らない構造は変わらない
- **下流の掃除で対処**（rule 昇格・archive）— RFC-0013 の withdrawn で決着: 症状への処方
- **何もしない** — 週 40–50 件の人間濾過が続く。ADR-0080 追補の未完成判定に恒常的に該当

## Unresolved questions

- 飽和シグナルの判定者は誰か（embedding 距離 / code 閾値 / 教師データ較正の複合）
- 低頻度・高新規の pattern を拾う経路の形（cluster 床 ≥3 の扱い）
- 環境の反応（Moltbook 側シグナル）をどの読み値として入れるか
- RFC-0016（surprise 復元）との統合順序

## Prior art

SkillResolve-Bench（arXiv 2606.10388）の same-capability ambiguity（RFC-0013 本文で参照）。
社内先例: ADR-0084（判定は成果物の後に置く）、ADR-0096（self-judge の refute 3 連）、
ADR-0056（重要度 ablation）。

## 2026-08-29 triage 判定（著者回答: 選択肢 (b) — RFC-0016 を先に）

`draft` 維持。設計セッションは [RFC-0016](0016-restore-surprise-instrument.md) の復元が
マージされ、surprise の読み値が現物として取れてから持つ。Unresolved questions のうち
「RFC-0016 との統合順序」はこれで決着（RFC-0016 が先、その読み値を設計材料にする）。
残り 3 点（飽和シグナルの判定者 / cluster 床 3 の扱い / 環境の反応の入れ方）は設計セッションで潰す。

## 着手条件

再開条件: RFC-0016 の復元が main にマージされ、surprise の読み値が 1 回取れること
照合先:   `core/insight_surprise.py` の存在と、staging sidecar の `surprise` field の実値
成立時:   設計セッション（grill-me 形式）→ Unresolved questions 残り 3 点を潰して accepted

## Status

draft — 2026-08-26 のオーナー指示（「knowledge からスキル抽出する機構を治すのが先決」）で
起票。ADR-0080 追補と同日。設計スコープの確定が accepted の入場条件。

## Next action

- 再開条件: 設計スコープの確定（上の Unresolved questions への回答。オーナーと設計セッション）
- 照合先:   本ファイルの state
- 成立時:   accepted → 教師データでの offline 較正から着手（read-only なので失敗が無料）
