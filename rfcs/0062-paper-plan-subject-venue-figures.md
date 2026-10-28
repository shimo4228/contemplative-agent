---
title: 論文計画 — 主題 A（harness 層の責任構造）を先に、B（建立時の 3 問い）は 2027-Q1 の読みのあと。投稿先・図表・問い→ファイル→版タグ
state: blocked
state_since: 2026-10-28
decide_by: 2027-02-13
next_check: 2027-02-13
review-when: 2027-02-13 の土曜ゲートで主題 B の着手を判断する（P3-01 / P3-03 の読みが揃っているか）、または 2027-Q2 の cutoff（P3-06.3）で版タグ表を固定する時
admitted-by: shimo4228 2026-10-24
alignment: instrument
---

## Summary

ADR-0080 は研究層の完成を「3 つの建立時の問いが論文として結晶し、機械参照圏に拡散され、派生されること」、最終成果物を「データセット + 論文」と置くが、論文の器も投稿先も無かった。本 RFC は器を置く: 主題 A を先に書き、B は A の後に読みが揃ってから判断する。資金・商用・査読料を要する経路は書かない。

決定: D-P3-06-1 = A 先行、B は 2027-Q1 の読みで判断、C（供出）は投稿先でなく並行の副産物（オーナー、2026-10-24。「推奨どおり」）。

## Motivation

- `docs/CYCLES.md` の Cycle #7 は成果物を「position papers → Zenodo / SSRN deposit」と既定済みで、投稿先は決まっているが、本リポジトリを主題とする論文の項目が `rfcs/` にも `docs/plans/` にも無い。
- 公開データの最終形（P3-05）と読みの事前登録（P3-01 / P3-06.2）は、論文が何を主張するかに依存する。主題を先に決めないと、どの読みを凍結するかが決まらない。

## Design

### 主題と順序

| | 主題 | 種別 | 状態 |
|---|---|---|---|
| A（先） | 人間ゲートを責任の行為として記録した 7 か月 — harness 層の責任構造 | 実証ノート（1 インスタンスの縦断記録） | 骨格は [docs/paper/subject-a/](../docs/paper/subject-a/outline.md)（見出しのみ）。主データは [ゲート縦断記録の事前登録](../docs/evidence/gate/preregistration.md) |
| B（後） | 建立時の 3 つの問い（憲法は小型ローカルモデルの行動を形づくるか・蒸留は複利するか・identity は安定するか） | データセット / 実証ノート | 骨格は [docs/paper/subject-b/](../docs/paper/subject-b/outline.md)（見出しのみ）。P3-01（問いの操作的定義）と P3-03（対照）の読みが揃うまで着手しない |

B に進む条件は 2027-02-13 の土曜ゲートで判断する（Q1 の読みが答えか「必要な計器と期日」を持っていること）。揃っていなければ B は書かず、A の後に残る問いとして記録する。

### 投稿先

SSRN（DOI・ORCID 連動）と Zenodo を主とし、arXiv は任意。論文 A の後に companion 記事を 1 本書く（「Why model-centric alignment papers miss the harness layer」、`zenn-content/` 側、Cycle #8 の成果物であって本計画の項目ではない）。

### 図表リスト（A）

| 図表 | 内容 | 出どころ |
|---|---|---|
| 表 1 | ゲートの指標 G1-G5 と事前登録した予測 | `docs/evidence/gate/preregistration.md` |
| 図 1 | 採用率の四半期推移（種別ごと）と、予測帯 | G1（公開集計 → 承認記録の投影が出たら四半期） |
| 図 2 | 推奨 ↔ 裁定の一致率と、不一致の種別分布 | G3 |
| 図 3 | 週次負荷（読み量・件数）の推移 | G5（P2-01 の定義） |
| 表 2 | 人間ゲートの位置（どの層で誰が何を決めるか） | ADR-0085 / ADR-0098 と `docs/GOVERNANCE.md`（P1-12） |
| 表 3 | 版の固定（コード・データ・rules・兄弟・装置） | `docs/evidence/paper-<id>/artifacts.md`（P3-06.3） |

### 問い → 使うファイル → 固定する版タグ → 必要な公開 projection

| 問い | 使うファイル | 固定する版タグ | 必要な公開 projection |
|---|---|---|---|
| A: ゲートは責任の行為として記録されているか（G1-G5） | `README.md` の集計、`pipeline/value-layer/*.json`、`docs/evidence/gate/preregistration.md` | 本体の release tag（cutoff 時）、データの版 DOI（P3-05.12 の規則） | 承認記録の投影（P2-05.2）。それまで G1-G3 の四半期行は非公開 |
| B-Q1: 憲法は行動を形づくるか | IPD two-arm・shadow・AILuminate の凍結読み（`docs/evidence/adr-0090/`・`adr-0092/`）、憲法の版系列（P3-04） | 憲法 4 版の sha・生成モデル・改正プロンプトの版 | 版ごとの憲法本文（`constitution/history/`、P3-04.2） |
| B-Q2: 蒸留は複利するか | `knowledge.json`、`pipeline/never-selected`・`comment-outcomes`（P3-02.3） | データの版 DOI | `knowledge.json`（埋め込みなし） |
| B-Q3: identity は安定するか | identity の版系列と距離系列（P3-04.2 / .8） | identity の版 sha | `history/identity/`（P3-04.2） |

版タグは cutoff 時（2027-Q2）に P3-06.3 の `artifacts.md` へ写す。それまでは表のとおり「何を固定するか」だけを持つ。

### 骨格と非目標

- 骨格は見出しのみ（本文なし）。本文は 2027-Q2 のドラフトで書く。
- 本 RFC は計器でも機構変更でもなく、既存の記録の凍結と公開の順序を決める。エージェントの挙動には触れない。

## 決定の記録

記録時点の経過（現在の state は frontmatter の `state:`）。

- 2026-10-24: D-P3-06-1 = 主題 A 先行、B は 2027-Q1 の読みで判断（オーナー、「推奨どおり」）。本 RFC を accepted にする。

## 2026-10-28 triage 照合 (by: judge)

verdict: hold

器（主題 A / B の骨格、投稿先、図表、版タグ表）は置かれ、次の読みは 2027-02-13 の土曜ゲート（主題 B の着手判断）。それまで build に出す作業は無い。`accepted` のままにするか、再開条件 2027-02-13 で `blocked` に移すかは digest でオーナーに聞く。

## 2026-10-28 著者回答 (by: owner)

一括 OK（triage digest）: 2027-02-13 まで build に出す作業が無いので `blocked` に移す。

## 着手条件

再開条件: 2027-02-13 の土曜ゲートで主題 B の着手を判断する（P3-01 / P3-03 の読みが揃っているか）
照合先:   2027-02-13 の `/weekly-gate` の `gate_record`
成立時:   accepted（主題 A の本文ドラフトは 2027-Q2）
