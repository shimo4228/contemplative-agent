---
title: 本番 Mac の運用作業と復旧ドリル（オーナー同席、2026-11-14〜20）
state: accepted
state_since: 2026-10-31
review-when: ドリルを実施して runbook に日付と結果を書き、下の運用作業が済んだ
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: repair
---

## タスク

本番機での手作業と、オーナー同席の復旧ドリルをまとめる。ドリルの時期は 2026-10-31 にオーナーと 11-09〜13 で合意した。

## 詳細

持つ行: P2-04.19、P2-04.22、P2-04.5、P1-07.11、P0-05.10。

- P2-04.19: 復旧ドリルを実施し、日付・かかった時間・credentials の行を runbook に書く。installer / rotation を変えるかもここで決める。
- P2-04.22: 本番の `install-schedule` の全引数と手書き plist を release runbook に宣言する。
- P2-04.5: 手書きの ollama-restart plist を直した版で入れ直す。
- P1-07.11: Ollama アプリの自動更新を切り、serving-changes に 1 行書く。
- P0-05.10: Ollama の最小版を 1 回確かめるか、検証済みの 0.34.2 のまま閉じる。

完了: 上の各行が済み、runbook に日付がある。

- P1-10.9（RFC-0068 から移した、2026-11-07）: `docs/runbooks/credential-rotation.md` の Moltbook 行を差し替える。オーナーの操作。

## 2026-11-04 triage 照合 (by: judge)

verdict: hold

ドリルはオーナー同席で 11-09〜13 の合意。今日は 11-04。

## 2026-11-07 triage 照合 (by: judge)

verdict: hold

ドリルはオーナー同席で 11-09〜13 の合意。今日は 11-07。

## 2026-11-11 triage 照合 (by: judge)

verdict: ask-owner

ドリルの合意期間 11-09〜13 の中にいるが、`docs/runbooks/` に 11-08 以降の日付の記録は無い。期間内に行うか、延ばすかを digest で聞く。

## 2026-11-11 著者回答 (by: owner)

triage digest 2026-11-11 を推奨どおり承認（日付の答えは空欄）。ドリルの期間を 11-09〜13 から 2026-11-14〜20 に延ばす。日付は空き窓の都合で、待つ理由ではない。
