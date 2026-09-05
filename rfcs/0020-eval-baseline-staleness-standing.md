---
state: resolved
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

## Reading (2026-08-31, 再実行の読み — 再承認はしていない)

C の次の一手（= A の実行）として `uv run --group eval python evals/run_eval.py --baseline
evals/baselines/comment_golden-2026-08-16.json` を回した。生成 `gemma4:e4b`（ローカル Ollama）、
判定 `claude-sonnet-5`、12 ケース x 3 サンプル。所要 約 34 分（22:34-23:08 JST）。
run は `evals/results/20260831T133224Z/run.json`（`evals/results/` は gitignored なので
ローカルにしか無い — clone 先で必要な数値は下の表に全部写してある）。**baseline ファイルは書き換えていない。**

### まず出た事実: runner は差分を出さずに終了する

`--baseline` を渡しても比較は行われず、末尾でこう落ちた（exit 2 = cannot measure）:

```text
[eval] cannot measure: manifest mismatch — prompt_templates_sha256:
'd463f8d0…' != '412f4fbc…'
```

つまり **選択肢 A の「回して数値を読んでから判断する」は、runner の経路上そのままでは成立しない**。
comparability check が差分の手前にあり、hash が違う限り比較は拒否される（設計としては正しい —
比較不能なものを比較して「回帰なし」と言わせない fail-closed）。今回の delta は run.json と
baseline JSON を手で突き合わせて出した。この一手を選ぶ人は「回せば delta が出る」ではなく
「回した後に手で読む」ことを選んでいる。

### 手で突き合わせた delta

manifest で動いたのは 2 フィールドだけ（`created_at` と `prompt_templates_sha256`）。
`target_model` / `temperature` / `judge_model` / `judge_prompt_sha256` / `assets_sha256` /
`dataset_sha256` / `sampling` / `injection_regime` / `samples_per_case` / `deepeval_version` は
すべて baseline と同一。**変数は nonce 変更（+ モデルの揺らぎ）に絞れている。**

サンプル単位の verdict（36 サンプル）:

| verdict | baseline 2026-08-16 | 2026-08-31 |
|---|---|---|
| ADHERENT | 0 | 2 |
| DRIFTING | 33 | 32 |
| DEVIANT | 3 | 2 |

ケース単位（12 件）で動いたのは 1 件のみ: `mindfulness-1` が DRIFTING → **ADHERENT**。
残り 11 件は DRIFTING 据え置き（edge 4 件・adversarial 4 件は全サンプル DRIFTING で、baseline と同じ形）。

落ちたチェックの内訳:

| check | baseline | 今回 |
|---|---|---|
| `register_natural` | 36 | 34 |
| `persona_intact` | 3 | 2 |
| `engages_post` | 1 | 0 |

`register_natural` が実質全滅なのは baseline から変わらない（36 → 34）。これがこの eval の
支配的な失敗軸で、nonce 変更の前後で構造は動いていない。

injection 側の計器は `records: 36 / enforced: 36 / fell_back: 0 / unobserved: 0`。
起動時に出た full-corpus fallback の警告（clamp floor 割れ）は、実際には 1 サンプルも
fail-open していない。

### 何が言えて、何が言えないか

言えるのは「**方向としては悪化していない**」まで。ADHERENT が 0 → 2、DEVIANT が 3 → 2、
失敗チェック総数が 40 → 36。全部が同じ向きに 1〜2 動いている。

言えないのは原因の分離。これは本 RFC の Drawbacks が先に宣言したとおりで、今回それが実地で確認された:
`samples_per_case=3` は分散の推定であって原因の分離ではなく、nonce 変更の効果とモデルの揺らぎを
分ける設計になっていない。動いた量（36 サンプル中 2〜3）は**どちらの説明でも無理なく説明できる大きさ**で、
このデータから「nonce 変更が効いた」とは言えないし「揺らぎだけ」とも言えない。

Unresolved questions の 1 本目（受け入れ幅を先に宣言しないと事後に都合よく読める）は未解決のまま残る —
**今回の数値は受け入れ幅を宣言せずに出したので、これを根拠に再承認すると事後に都合よく読んだことになる**。
再承認は「今の値を正とする」宣言で人間の仕事なので、この build セッションはここで止めた。

### 次の一手（著者の判断待ち）

1. この読みを見て再承認する（`prompt_templates_sha256` を現行にした baseline を承認する）
2. 再承認の前に受け入れ幅を先に宣言する（例: ケース単位の verdict が N 件以上悪化したら承認しない）
3. B（hash scope の縮小）へ回す — ただし C の理由（eval は 1 本、対応表は早すぎる抽象化）は今も有効

## Resolution (2026-08-31)

著者が上の読みを見て承認した。`evals/results/20260831T133224Z/run.json` を
`evals/baselines/comment_golden-2026-08-31.json` として追加（既存の 08-06 / 08-08 / 08-16 は
そのまま残す — `check_staleness.py` はファイル名順の最新だけを現行基準として見る）。
`uv run python evals/check_staleness.py` が無出力・exit 0 になり、2 週間立ちっぱなしだった
4 行の警告は消えた。

選択肢としては **A（scope はそのままで再実行・再承認）** を採った。B（hash scope の縮小）は
採らない — eval が `comment_golden` 1 本しかない現在、「どのテンプレートがどの eval の入力か」の
対応表は早すぎる抽象化で、表が古びたときの故障方向（本物の staleness を見逃す）が今の
誤検知よりも悪い。この判断は eval が 2 本目を持った時点で見直す（本 RFC の `review-when` の
後半がその条件）。

構造的な問題は解決していない: 登録テンプレートが 1 本変わるたびに、それが
`comment_golden` の入力かどうかに関わらず同じ警告が立つ。今回で言えば
`insight_extraction.md`（コメント生成経路に乗っていない）の編集がそれに当たる。
次に同じ状態が来たときは、放置せず取り直す（今回 2 週間かかった原因は機構でなく運用）。

### 積み残し（次回のために）

Unresolved questions の 1 本目（受け入れ幅の事前宣言）は今回も未実施のまま承認した。
今回は悪化 0 件で、どんな妥当な条件を後から書いても結論が変わらないため実害はないが、
悪化が混じった回では同じ読み方ができない。常設するなら置き場所は `evals/README.md` か
ADR-0089 で、徹底するなら `evals/compare.py` に条件を実装して満たさないとき exit 1 にする。

## Status

`resolved`（2026-08-31）。発見は C901 予算引き下げ作業（`5be5ef6`）中に `verify.sh` を
3 回回した際、毎回同じ警告が出たことから。作業自体とは無関係で、`config/prompts/` には
触れていない。著者が選択肢 A（scope はそのままで再実行・再承認）を採り、上の Resolution 節の
とおり決着した。

判断役による照合（2026-09-02 triage）: `evals/baselines/comment_golden-2026-08-31.json` が
実在し、`uv run python evals/check_staleness.py` は無出力 exit 0。2 週間立っていた 4 行の
警告は消えている。

## Next action

なし（この行としては終端）。積み残し 2 点は `review-when` と上の「積み残し」節が持つ —
(1) 受け入れ幅の事前宣言は今回も未実施、(2) hash scope の構造問題（登録テンプレート 1 本の
変更で無関係な警告が立つ）は eval が 2 本目を持つまで据え置き。
