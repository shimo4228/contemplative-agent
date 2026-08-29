---
state: blocked
state_since: 2026-08-16
origin: instrument
parent: T-CAND7
---

## タスク

**計器の読みを、毎スケジュール実行ではなく「比較が壊れる境界」で記録する。**
T-CAND7（毎回配線）を落とした際の置き換え。cross-model review（Codex、2026-08-16）の提案。

## なぜ境界だけで足りるか

計器の読み（view supply / diversity）は事後に再計算できるが、**厳密には再現しない**。
再現が破れる原因は 3 つとも**特定のイベントの瞬間に起きる**（詳細と file:line は T-CAND7）:

| 再現が破れる原因 | 起きる瞬間 |
|---|---|
| 埋め込みの in-place backfill（timestamp 無し） | `restore-embed-knowledge.py` 実行時 |
| view centroid / threshold の変化（版管理されていない） | seed 文・憲法・view 定義の変更時 |
| 元ベクトルの喪失（export が落とし restore が再導出） | backup / restore 時 |
| 計器コード・埋め込みモデルの変更 | モデル差し替え・実装変更時 |

毎回記録すればこれらは自動的に跨げるが、**境界の前後だけ記録しても同じことが達成できる**。
しかもログ量は介入の頻度に比例するので、無人運用で増え続けない。

## 検討すべきこと（`draft` の理由）

**消費者がまだ名前を持っていない。** T-CAND7 を落とした理由がそのままここにも当たるので、
「イベント駆動なら建てていい」と自動的にはならない。最初の消費機会になりうるのは:

- **T-GAP1 の A/B**（distill prompt に mode 7/8/9 を足すか）— プロンプト変更の前後は
  まさに「介入の境界」で、A/B の 4 本がそれ自体 before/after の読みになる。
  ただし A/B は `--dry-run` の既存経路で読めるので、**この仕組みが無くても回る**
- 次回の埋め込みモデル差し替え / backfill

つまり「T-GAP1 を回すときに、ついでにこの形が要ると分かるか」を見てから決めるのが安い。
先に建てると、また消費者のいない計器になる。

## 着手条件（2026-08-16 夜に書き直し。第一候補の消費者が消えたため）

**旧条件「`T-GAP1` の A/B（4 本）が終わること」は永久に成立しない。** T-GAP1 は A/B を
実行せず `withdrawn` になった。この行が `:62-64` で警告していた罠（願望で名付けた行が閉じない）を、
**自分の再開条件で踏んでいた** — ただし踏み方は願望ではなく、**イベントで書いたこと**だった。
イベントは中止されうる。同日 `T-ENDSTATE-TERM` は状態（「計器が代謝の定常状態を示すこと」）で
書かれていたため無傷だった。**再開条件は状態か、producer のある実イベントで書く。**

再開条件: 埋め込みモデルの差し替え、または `restore-embed-knowledge.py` による backfill が
          次に行われること（producer のある実イベント。この 2 つが上表の再現破れの主因）
照合先:   実行の直前・直後に `distill --dry-run` の `dry-run instrument:` 行を 1 本ずつ取れたか
成立時:   `accepted`（そのとき「何が読めなかったか」という名前の付いた消費者ができる）

判定基準は据え置き: **境界の前後で、既存の `--dry-run` 経路では読めなかったものがあったか。**
無かった → `withdrawn`（設計は親 T-CAND7 の決着文に file:line 込みで残る）。

## 2026-08-16 の部分照合 — この行の心配には当たらなかった

T-GAP1 Phase 1 で、**介入境界を跨いだ計器の読み直しを 1 回実行した**: 07-03 の mode 別分類を
08-16 に同じ view・同じ n=30 で再現した（間に ADR-0072 の register 介入 `5912f5b` が挟まる）。
**5 秒で完全に再現した。**

しかしこれは**この行が心配している計器ではない**。読み直せたのは mode 分類（保存済みテキストを
読んで人が分類する — 原理的に何度でも再現する）で、上表が挙げる再現破れ 4 原因は**どれも
埋め込み由来の計器**（view supply / diversity）に効くもの。テキスト分類の成功は
埋め込み計器の再現性を何も保証しない。

つまり 2026-08-16 は**判定基準を当てる機会にならなかった**。`withdrawn` の根拠にも
`accepted` の根拠にもしない。

## 詳細

親 T-CAND7（`.notes/archive/tasks/T-CAND7.md`）（反証の全文と file:line）、skill `read-only-instruments`（signal-first）、
`core/view_metrics.py`、ADR-0071

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。2026-08-17 以降、埋め込みモデル差し替え・`restore-embed-knowledge.py` backfill のいずれも実行記録なし（main の commit 4 件はいずれも該当せず）。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。2026-08-19 以降、埋め込みモデル差し替え・`restore-embed-knowledge.py` backfill の commit / 実行記録なし。

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。2026-08-22 以降、埋め込みモデル差し替え・backfill の commit / 実行記録なし。

旧 ID: T-INSTRUMENT-EVENT-READ（.notes/tasks から 2026-08-25 移送）。
本文中の `.notes/…` はローカルの作業ノート（gitignored、clone 先には存在しない）を指す。

## 2026-08-26 triage 照合（無人 cycle）

未成立 → `blocked` 維持。08-24 以降、埋め込みモデル差し替え・`restore-embed-knowledge.py` 実行の commit / 記録なし。

## 2026-08-29 triage 照合（無人 cycle）

未成立 → `blocked` 維持。08-26 以降、埋め込みモデル差し替え・`restore-embed-knowledge.py` 実行の commit / 記録なし。

## Status

blocked — 消費者がまだ名前を持たず、2026-08-16 の部分照合も判定基準を当てる機会に
ならなかった（2026-08-25）。直近の照合 2026-08-24 も未成立（埋め込みモデル差し替え・backfill
の commit / 実行記録なし）。

## Next action

- 再開条件: 埋め込みモデルの差し替え、または `restore-embed-knowledge.py` による backfill が
  次に行われること（producer のある実イベント）
- 照合先: 実行の直前・直後に `distill --dry-run` の `dry-run instrument:` 行を 1 本ずつ
  取れたか
- 成立時: accepted（そのとき「何が読めなかったか」という名前の付いた消費者ができる。無かった →
  withdrawn）
