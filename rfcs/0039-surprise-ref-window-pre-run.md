---
id: T-SURPRISE-REF-WINDOW-PRE-RUN
state: draft
state_since: 2026-09-19
origin: gate
---

## タスク

insight の surprise 読み値（ADR-0096 D10、read-only 計器）は、run の窓が参照窓の大きさ
（`SURPRISE_REF_K = 1000`）に達すると全候補で値を出さない。`compute_surprise` は先に最新 1,000 行を
参照窓として取り（`insight_surprise.py:201`、`:139-176`）、その後で run の窓全体を候補ごとに
mask する（`insight.py:730-734` → `insight_surprise.py:226-247`）。run の窓が最新 1,000 行を覆うと
参照行が全部 mask され、全候補が「owns the whole reference window」分岐に入る。変更案: mask を
切り詰めより先に適用する。つまり run の窓に含まれない行のうち最新 1,000 行を参照窓にする。
呼び出し側のコメント（`insight.py:721-729`「reference was strictly what was distilled BEFORE the
run」）が既に述べている定義どおりにする変更。`--full` は除外後に何も残らないので今の挙動
（読み値なし）のまま。

producer: `src/contemplative_agent/core/insight_surprise.py:201`

## 詳細

- 診断: `weekly-2026-09-18-findings.md` の F1.2。出典は同週の観察文書 Exceptions 2 行目
- Source quote（`logs/insight-launchd.log`）: `:1291` *"Staging holds 2 unreviewed item(s) (2 of them
  explicitly held at a past gate) — skipping this insight run (ADR-0074)"*（2026-09-12）→ `:1292`
  *"Incremental mode: 1184 new patterns since 2026-09-05T00:06+00:00"* → `:1306-1388` 83 クラスタ
  全部で *"insight surprise: cluster-N owns the whole reference window — no reading"*
- 発火条件は決定論的: run の窓 ≥ 1,000 行。宣言済み baseline（+300..+700 行/週）では 1 週 skip
  すれば届く。skip は ADR-0074 の設計どおりの経路（hold された項目がある週）なので、
  計器の消費者（ADR-0080 追補の代謝の質軸、`rfcs/0016` が名指し）は hold の翌週にちょうど
  読み値を失う。`SURPRISE_REF_K` を上げても閾値が動くだけ
- 呼び出し元は 1 箇所（`insight.py:731`）。read-only のまま — 読み値は gate・並び替え・採否の
  どこにも入らない
- 関連: ADR-0096 D10（「most recent 1000 live patterns, masking the cluster's own members」に
  追補 1 行が要る）、`rfcs/0016`（done 2026-08-29、同じ分岐の `--full` 退化だけを直した）

## 2026-09-19 triage 照合（無人 cycle、stocktake 併走）

premise を照合: `core/insight_surprise.py:72` `SURPRISE_REF_K = 1000`、`:201` で `_reference_window` を mask より先に取る — 成立。ただし insight の週次 job は 09-19 に停止され、RFC-0041 の Future possibilities が本 RFC を `obsoleted` 見込みに挙げている（著者: 今は動かさない）。`draft` 維持、dispatch しない。

## 2026-09-23 triage 照合（無人 cycle）

premise を再照合: `core/insight_surprise.py:200` で `_reference_window` を mask より先に取る — 成立。RFC-0042 Unresolved questions の「4 と 6 が入った後に読み直す」が発火（S21 `cf04ec8` と週次再開 2026-09-19）。発火条件の実測: knowledge.json の週あたり新規 pattern は ISO 週 32〜38 で 583〜631 行、run の窓は 1 週 skip で約 1,200 行になり 1,000 を超える（2026-09-19 の run が `1184 new patterns since 2026-09-05`）。`--hold-names` は S20 で消えたが、未レビューの staging による skip（ADR-0074 の pending ガード）と launchd 停止は残るので、発火は「skip の翌週」に限られるが 0 ではない。採否は著者判断 → digest。
