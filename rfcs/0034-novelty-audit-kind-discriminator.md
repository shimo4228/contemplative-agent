---
state: done 2026-09-12
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

## 2026-09-12 build（S12、branch `task/s12-audit-records`）

**Next action の確認結果: 歪みなし、再集計不要。** 本番 `logs/insight-novelty.jsonl` は
2026-09-12 時点で 27 行あり、内訳は judge 行のみ（`judged` 26 / `fail_open_llm` 1）で
deferral 行は 0 件。`docs/evidence/rfc-0023/novelty-replay-ab-20260905.json` の run meta も
`records_total == records_judged == 10` / `verdicts_logged == ["judged"]` で、混入の痕跡が無い
（混入していれば `known_themes_count` の欠けた行が「2 つの inventory 規模」として
`_records_for_run` を停止させていたはずで、run が完走している事実とも整合する）。
既存 evidence ファイルは書き換えていない。

入れたもの:

- `core/insight_novelty.py` が log の record grammar を持つ（`selection_window` と同じ役割分担）:
  `NOVELTY_JUDGE_RECORD_KIND = "novelty_judge"` /
  `NOVELTY_DEFERRAL_RECORD_KIND = "review_budget_deferral"` /
  `is_novelty_judge_record`（`kind` 不在は judge ファミリ）
- judge 行と deferral 行の両方が `kind` を出す
- Reference-level explanation の 4 点目（emitter を寄せられるか）は **寄せた**:
  `append_novelty_audit_record(audit_path, record, *, what)` を `insight_novelty` に置き、
  `insight._append_deferral_audit` はそこを通す。best-effort の except は 1 箇所になった。
  base64 / byte cap は judge 行に固有（deferral 行に長文フィールドが無い）なので共有しない
- `scripts/novelty_replay_ab.py::_records_for_run` が judge ファミリだけを返す。落とした行は
  件数と kind を stderr に出す（silent drop にしない）

回帰: `tests/test_novelty_audit_kind.py`（6 本）。

Review（`/code-review` medium、2026-09-12）で直したもの:

- `kind` 不在を無条件に judge ファミリと解釈していたのが誤り。deferral の書き手は
  fail-open cap の導入以来この同じファイルへ kind 無しの行を書いてきたので、過去ログ
  （バックアップ・別 `MOLTBOOK_HOME`・archive）に deferral 行があれば、リプレイの regime
  guard が `sorted({485, None})` で `TypeError` を投げて停止条件ごと壊れる。`reason` の
  有無で構造的に判定するようにした（本番ログに 0 件なのは latent であって fixed ではない）
- `client_error_guard` の `on_failure` を try/except で包んだ（RFC-0029 側の seam。
  guard の契約は「失敗した write はこの層で致命でない」なので、ぶら下げた recorder が
  それを覆せない形にする）

## 2026-09-12 merge（判断役の検収 → 著者の merge 語）

`accepted` → `done`。S12 `cf0b87b` を ff merge（main `aa2f667`）。先行確認: 既存 evidence（rfc-0023）に deferral 行の混入なし、再集計不要。ADR-0074 に追補。 判断役の再検収: worktree / main とも `verify.sh` exit 0。diff 外 LOW は commit body に残す（起票なし）。
