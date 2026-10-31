---
title: 同一 pattern から amend-constitution を gemma と cloud で各 3 run させ、改正文の構造差を読む
state: draft
state_since: 2026-10-24
review-when: D-P1-11（cloud 兄弟の処遇）と D-P1-11-4 の結論が出る、または amend-constitution の生成モデルが替わる（ADR-0069）
---

## Summary

同一の 50 pattern から `amend-constitution` を gemma と cloud で各 3 run させ、改正文の構造（例外節率・条項数・section 数）を**記述的に**比べる（P3-03.8 (c)）。仮説は「大型モデルは例外節を足して原則が拡散し、小型は原則のまま」。

## 前提の変更（必須の節）

| 前提 | 現状 | この案 |
|---|---|---|
| ゼロ API | 改正生成は gemma ローカル（think-ON、[ADR-0069](../docs/adr/0069-gemma-production-model-and-think-on-value-layer-pipelines.md)） | cloud アームは 50 pattern と現行憲法本文を第三者 API へ送る |
| 値層は承認ゲートの向こう | 改正は staged → 人間承認 | 本案の出力は**採択に使わない**。専用 home に出し、staging にも入れない |
| cloud 兄弟は研究実験用途のみ | 凍結方向（D-P1-11-1 = B） | cloud アームには兄弟を一度動かす必要がある |

### 送信内容の列挙（cloud アームのみ）

- 送る: 固定した 50 pattern の本文（untrusted 由来の本文を含みうる。入力は script がサニタイズ済みの凍結ファイルにする）、現行憲法本文、改正プロンプト（`config/prompts/constitution_amend.md`）
- 送らない: identity、skills、API key、`MOLTBOOK_HOME` のパス
- 回数: 3 run（cloud）。実験 1 回限り

## Reference-level explanation

### 事前登録する代理指標

| 指標 | 定義（機械判定） | 仮説との関係 |
|---|---|---|
| 例外節率 | 条項あたりの `but / unless / except / however / provided that` を含む文の割合 | 「原則の拡散」の語彙代理 |
| 条項数 | section あたりの条項の数（プロンプトは `Keep 1-4 clauses per section` と指示、`constitution_amend.md:13`） | 指示への従順 |
| section 数 | 出力の section の数 | 構造の拡張 |

**読みは記述的**: 各 3 run では区間が引けない。差の向きと大きさを表にして並べるだけで、仮説の検定とは書かない。盲検の人手評定や 10 run 以上は採らない（コストが読みに見合わない）。例外節率は語彙代理であり、「原則が拡散した」ことの証明ではない。

### 先行情報

プロンプト側の指示 `Keep 1-4 clauses per section` の構造制約は過去に外されたことがある（P3-07.5 が経緯を記録する予定。2026-08-16 より前の履歴はオーナーの full clone でしか辿れない）。この比較は現行プロンプト（制約あり）で行う。

## 判断

D-P3-03-4 = C（オーナー、2026-10-24）: cloud への価値層送出は P1-11 と同時に決める。cloud が凍結方向のため、**cloud アームは走らせる予定が無い**。gemma 3 run の側（ベースライン記録）は egress が無く、単独でも意味を持つ（同一 pattern での run 間のばらつき）。`draft` のまま、cloud 部分は D-P1-11 の結論で決める。

## 消費計画 (ADR-0101)

(a) オーナーが決定後に 1 回（2027-Q1）。(b) 1 回の読みで accepted か withdrawn。(c) 撤去条件: 結果を固定したら script を撤去し、cloud 送信は実験 1 回限りで常設しない。

## 2026-10-28 triage 照合 (by: judge)

verdict: hold

RFC-0059 と同じく D-P1-11-1（10-31）/ D-P1-11-4（12-05）待ち。gemma 3 run 側だけを先に切り出すかは、その決定後に聞く。

## 2026-10-31 triage 照合 (by: judge)

verdict: hold

D-P1-11-1（cloud repo の処遇、期限 10-31 の土曜ゲート）の結論が、今日の `gate_record`（gate-2026-10-30）と今日の commit のどちらにも見当たらない。D-P1-11-4（12-05）も未決。採否を聞くのは D-P1-11-1 の記録が入った後。

## 2026-10-31 著者回答 (by: owner)

D-P1-11-1 は 10-31 には決めず、次の土曜ゲートへ持ち越す（triage digest の 2B）。本 RFC は `draft` のまま、その決定を待つ。

追記（2026-10-31 後刻）: 同日、オーナーが D-P1-11-1 を **B（凍結）** で確定した（`docs/plans/roadmap-2026-10/decisions.md` の「決定の記録」）。上の「持ち越し」はこれで置き換わる。本 RFC の採否は次の triage で聞ける（D-P1-11-4 は 10-24 の一括決定で推奨どおり A）。
