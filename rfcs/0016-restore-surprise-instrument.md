---
state: done 2026-08-29
state_since: 2026-08-29
review-when: ADR-0080 追補の代謝の質条項が supersede される、または surprise 読み値を消費しない別の新規性機構が本採用される（消費者が再び消えたら本提案も終端化する）
---

## Summary

surprise 計器（ADR-0096 D10–12、`core/insight_surprise.py`）を復元する — 撤去理由「名指しの消費者がいない」が ADR-0080 追補（2026-08-26、代謝の質: 複数軸での価値判定）で消えたため。

## Motivation

ADR-0097 D1 は ADR-0096 の事前登録 fallback を実行し、promotion-worth の LLM 判定
（gemma self-judge、3 回の実測で全件 yes: 40/40、18/18、46/46 — refuted）と一緒に
surprise 計器を撤去した（commit `47616da`、導入は `e5dec38`）。ただし計器側の撤去理由は
判定の欠陥ではなく**消費者の不在**だった（ADR-0096 自身が撤去条件として事前登録）。

2026-08-26 の ADR-0080 追補が消費者を名指しした: 代謝の質の条項は「頻度単独では価値を
判定できない。複数軸（例: 新規性・重要度・環境の反応）で見分けられること」を要求する。
現行の insight 抽出は ≥3 pattern の cluster という頻度フィルタのみで、新規性の軸を測る
器官が無い — surprise はその軸の既実装だった。著者指示（2026-08-26、triage セッション）:
「あれは必要だったよ」。

## Reference-level explanation

復元スコープは**計器のみ**。gemma worth gate（`insight._worth_gate`、
`config/prompts/insight_worth.md`、`insight-worth.jsonl` writer）は refuted のまま復元
しない。復元対象の当時の形: `core/insight_surprise.py`（267 行）、staging sidecar の
`surprise` field、`adopt-staged` の surprise 表示、`tests/test_insight_surprise.py`
（181 行）。git 履歴から丸ごと復元可能（`git show e5dec38`）。復元時に ADR-0097 D1 への
部分 supersede 注記（日付つき）を残す。

読み値の消費先（新規性軸の判定材料としてどこで読むか — 抽出時 gate か、staging の
提示順か、土曜ゲートの表示か）は実装時の設計問題。ADR-0080 追補の規約により、
単一スカラーとしての自動判定には昇格させない（軸の一つとして提示する）。

## Rationale and alternatives

- **復元せず新規性軸を新設計** — 教師データ（7 週 438 候補の人間判定）で較正した
  embedding 距離等。復元と排他ではない: surprise は「自分の過去からの距離」、embedding
  照合は「store からの距離」で別の軸。両方ありうる
- **復元しない（現状維持）** — 代謝の質条項が要求する複数軸のうち新規性を測る器官が
  無いまま残る。北極星と機構の不整合が既知のまま放置される

## Unresolved questions

- 読み値の消費位置（抽出時 / staging / ゲート表示）
- sidecar `surprise` field の復元は ADR-0097 D3 の「採用は書き込みだけ」原則と両立する形
  （表示専用に留めるか）を要設計

## 2026-08-29 triage 判定（著者回答: 採用して dispatch）

`draft` → `accepted`。選択肢 (a) を採用 — 計器のみ復元し、消費位置は実装時の設計問題として
build セッションに委ねる。`gemma worth gate`（`insight._worth_gate` / `config/prompts/insight_worth.md` /
`insight-worth.jsonl` writer）は refuted のまま復元しない。sidecar の `surprise` field は
表示専用に留め、単一スカラーとしての自動判定へは昇格させない（ADR-0080 追補の規約）。
ADR-0097 D1 への部分 supersede 注記（日付つき）を同 PR で残す。

RFC-0017 との順序も同日に確定（RFC-0017 の 2026-08-29 判定を参照）: 本 RFC が先。

## 2026-08-29 dispatch（S3）

`accepted` → `in_progress`。worktree `task/restore-surprise`（branch `task/restore-surprise`）で build セッション `ca/s3-restore-surprise` を起動。
判断役 triage-ca が検収、merge はオーナーの言葉で ff-only。packet は判断役の scratchpad。

## 2026-08-29 done（merge 4838be2）

計器のみ復元（worth gate は refuted のまま不復元）。読み値は gate・閾値・並び替え・採否のどこにも入らない（表示専用をテストで固定）。ADR-0097 D1 に日付つき部分 supersede 注記。復元中に当時のコードの欠陥 2 件を修正 — sidecar の 400 桁整数が `OverflowError` で adopt-staged を落とす件（HIGH）と、`insight --full` で参照窓が全 mask のとき退化した読み値を出していた件（読み値を出さない挙動へ変更）。

検収は判断役（triage-ca）が独立に実施 — `git diff --stat`、worktree での `verify.sh` 再実行、commit body の chain 遵守と逸脱の名指しを確認。merge 後の main でも `verify.sh` exit 0。

## Status

draft — 2026-08-26 の triage セッションで著者指示により起票。復元の必要性は著者が明言
済みだが、消費位置・sidecar の扱いの設計が未着手のため draft。実装は task-triage loop
で別セッションに dispatch する。

## Next action

- 再開条件: 本 RFC の採否確認（著者）と、消費位置の設計判断
- 照合先:   本ファイルの state
- 成立時:   accepted → 復元パケットを dispatch（`git show e5dec38` 起点、計器のみ、
  worth gate 除外）
