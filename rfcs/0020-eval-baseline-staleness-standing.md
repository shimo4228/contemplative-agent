---
state: draft
state_since: 2026-08-31
review-when: comment_golden の baseline が再承認された（この RFC の前提が消える）、または PromptTemplates 登録が 1 プロンプト 1 eval に分割された（scope 問題が構造的に解消する）
---

## Summary

`comment_golden` の eval baseline が 2026-08-17 頃から STALE のまま立ちっぱなしで、ADR-0089 の回帰ゲートが現行システムを測っていない。再実行して再承認するか、staleness hash の scope を狭めるかを決める。

## Motivation

`.claude/verify.sh` を回すたびに毎回この 4 行が出る:

```text
[eval-staleness] baseline comment_golden-2026-08-16.json is STALE — the regression gate
[eval-staleness] no longer measures the current system (ADR-0089 re-run trigger):
[eval-staleness]   prompt_templates_sha256: baseline 'd463f8d0…' != current '412f4fbc…'
[eval-staleness] run: uv run --group eval python evals/run_eval.py --baseline evals/baselines/comment_golden-2026-08-16.json  (then re-approve)
```

fail-soft なのでゲートは通る。通るからこそ問題で、**警告が常設になった時点で情報量がゼロになる** —
次に本当の staleness が来ても同じ 4 行に埋もれる。ADR-0089 が再実行トリガーを機械化した意図が、
「毎回出る飾り」に退化している。

放置期間が長いこと自体より、この 4 行を全員（人間と agent の両方）が読み飛ばす習慣が付くことが実害。

## Guide-level explanation

`prompt_templates_sha256` は `PromptTemplates` に登録された 30 個のテンプレート
（+ `config/domain.json`）を全部まとめて 1 つの hash にする。baseline の 2026-08-16 以降に
変わった**登録済み**テンプレートは 2 つだけ:

| ファイル | 変更 | comment 生成経路 |
|---|---|---|
| `config/prompts/untrusted_wrapper.md` | `c2cc013`（2026-08-16）— 閉じ区切り子に呼び出しごとの nonce | **乗っている**。コメント対象の投稿を包む |
| `config/prompts/insight_extraction.md` | `e5dec38`（2026-08-17）— promotion-worth の abstain 経路 | **乗っていない**。insight 抽出専用 |

つまり片方は本物の staleness、もう片方は無関係な編集による誤検知。
`comment_golden` は 4 公理 × 3 ケースのコメント生成を測る eval であって、insight 抽出は測らない。

この非対称が構造的な問題を指している: **hash の scope は「登録された全テンプレート」なのに、
eval が実際に触るのはそのうち数本**。登録が増えるほど誤検知の頻度は上がり、
警告は「常に立っている」状態へ漸近する。今がその状態。

## Reference-level explanation

- 判定器: `evals/check_staleness.py`（`.claude/verify.sh` から fail-soft で呼ばれる）
- hash の定義: `evals/run_eval.py::prompt_templates_sha256` / `hashed_prompt_paths`
  — `dataclasses.fields(PromptTemplates)` の stem に一致する `config/prompts/*.md` を
  名前とバイト列で順に digest し、`config/domain.json` を足す
- baseline: `evals/baselines/comment_golden-2026-08-16.json`（`manifest` に上記 hash）
- 再実行のコスト: 12 ケース × 3 サンプル、生成 `gemma4:e4b`（ローカル Ollama）、
  判定 `claude-sonnet-5`。依存は `--group eval`（deepeval 4.1.5、既定同期に入らない）

### 選択肢

**A. 再実行して再承認する（scope はそのまま）**
`untrusted_wrapper.md` の nonce 変更は本当に生成入力を変えているので、どのみち一度は測り直す
必要がある。最小の作業で警告は消える。ただし次に登録済みテンプレートが 1 本変わった時点で
同じ状態に戻る — 恒久解ではない。

**B. hash の scope を eval が実際に読む経路へ狭める**
`comment_golden` が触るテンプレート（`system` / `comment` / `untrusted_wrapper` /
`untrusted_marker_*` / `relevance` あたり）だけを hash する。誤検知は消えるが、
「どのテンプレートがどの eval の入力か」という対応表を誰かが維持することになり、
その表が古びると**逆向きに壊れる**（本物の staleness を見逃す）。A より危険な失敗方向。

**C. A を今やり、B は eval が 2 本目を持った時に判断する**
現状 eval は `comment_golden` 1 本。scope 問題は「eval が増えたら効いてくる」問題で、
1 本しかないうちに対応表を作るのは早すぎる抽象化。

## Drawbacks

再実行は LLM 判定を伴うので、通せば数値が動く。数値が動いた時に
「nonce 変更のせいか、モデルの揺らぎか」を分離できる設計にはなっていない
（`samples_per_case=3` はあるが、これは分散の推定であって原因の分離ではない）。
再承認は「今の値を正とする」宣言なので、そこは人間が引き受ける。

## Rationale and alternatives

「警告が常設になったら情報量が消える」は
[skill: measurement-discipline](https://github.com/shimo4228/claude-harness/blob/main/skills/measurement-discipline/SKILL.md) の
saturated-guard と同じ形。飽和したガードは外すか作り直すかで、放置は選択肢に入らない。

「警告を抑制する」（閾値を上げる・出力を捨てる）は採らない — ADR-0089 の再実行トリガーは
機械化された失効条件そのもので、消せば ADR の担保が消える。

## Prior art

- ADR-0089（eval ハーネスと再実行トリガー）
- [RFC-0008](0008-instrument-read-at-event-boundaries.md) — 計器の読みを「比較が壊れる境界」で
  記録する。今回は逆側の事例: 境界は検出されたが読みに行く人がいなかった

## Unresolved questions

- 再実行の数値が baseline から動いた場合、どこまでを「nonce 変更の効果」として受け入れるか。
  受け入れ幅を先に宣言しないと、事後に都合よく読める
- eval が 2 本目を持つ予定はあるか（B の判断時期に効く）

## Status

`draft`（2026-08-31）。C901 予算引き下げ作業（`5be5ef6`）中に `verify.sh` を 3 回回した際、
毎回同じ警告が出ることから発見。作業自体とは無関係で、`config/prompts/` には触れていない。

## Next action

著者が A / B / C を選ぶ。C を選ぶなら、それは「A を実行する」と同じ次の一手
（`uv run --group eval python evals/run_eval.py --baseline evals/baselines/comment_golden-2026-08-16.json`
を回し、数値を読んでから再承認するか判断する）。実行はローカル Ollama を長時間占有するので、
スケジュールセッション（JST 0/6/12/18 時）を避けた窓で。
