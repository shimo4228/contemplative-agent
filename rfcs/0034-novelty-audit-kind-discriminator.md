---
state: accepted 2026-09-12
review-when: insight-novelty.jsonl の書き手が 1 つに戻ったら（deferral 行を別ファイルへ出す等）、判別子は不要になる
---

## Summary

`insight-novelty.jsonl` に 2 種類のレコードが判別子なしで混在しており、下流のリプレイが
deferral 行を verdict `"None"` として数えている。

## Motivation

同じファイルに 2 つの書き手がいる:

- `insight._append_deferral_audit` → `{ts, reason: "review_budget_deferred", cap, deferred}`
- `insight_novelty._append_novelty_audit` → `{ts, verdict, clusters, known_selection, ...}`

共通キーは `ts` だけ。`extract_insight` は同じパスを両方に渡している。

結果として `scripts/novelty_replay_ab.py` の
`verdicts_logged = sorted({str(r.get("verdict")) for r in records})` は、deferral 行ごとに
文字列 `"None"` を verdict 集合へ入れる。`verdict != "judged"` のフィルタは「既知だが
興味のない verdict を飛ばす」つもりで、実際には**別の事象ファミリ**を吸収している。

## Guide-level explanation

同じ問題は隣のモジュールで既に解かれている: `skill_selection` は `kind`
（`SELECTION_RECORD_KIND` / `PUBLISH_RECORD_KIND`）を持ち、`kind` の無い旧行は歴史的
ファミリとして既定解釈する。同じ判別子を novelty の監査ログにも入れる。

## Reference-level explanation

- 両方の書き手が `kind` を出す（deferral 行は別の kind）
- 読み手は `kind` でフィルタする
- `kind` 不在は novelty-judge ファミリとして既定解釈（後方互換）
- あわせて `insight.py` 側の 3 本目の JSONL emitter を `insight_novelty` の writer へ
  寄せられるか検討する（byte cap / base64 / best-effort ラッパは既にそちらにある）

## Drawbacks

- 既存行には `kind` が無く、リプレイの過去分は既定解釈に依存する（`skill_selection` と同じ）

## Status

draft — 2026-09-12 の simplify 走査（core insight 群の altitude レビュー）で同定。
過去の読み値（RFC-0023 のリプレイ証拠）がこの混在の上で取られている点は要確認。

## Next action

既存の evidence（docs/evidence/rfc-0023/）が deferral 行の混入で歪んでいないかの確認。
歪んでいれば再集計、していなければ実装のみ。

## 2026-09-12 triage 照合（無人 cycle）

`draft` 維持（同日の simplify 走査で起票、premise は起票時点の main で検証済み）。採否は著者判断（digest に提示）。

## 2026-09-12 決定（著者回答）

`draft` → `accepted`。S12 として dispatch（RFC-0029 と同梱、worktree `task/s12-audit-records`）。先に docs/evidence/rfc-0023 の歪み確認、次に実装。
