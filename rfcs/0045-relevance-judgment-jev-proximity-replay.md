---
state: accepted 2026-09-24
review-when: 本番の relevance 判定が gemma4:e4b から替わる、または `config/prompts/relevance.md` / 閾値（0.82 / 0.65 / 0.70）が変わる（同じ再生が本番を再現しなくなる — 標本と arm を測り直す）。TypeSafe の MCA が Jev 出力の評価利用を制限する側に改定される（Jev をラベル係にできなくなる）
---

## Summary

relevance 判定（feed の各投稿を自分の domain に対して採点、週 736 回・state 約 250 token・Score 1 問）を、ホスト型 Jev を正解ラベルにした offline 再生で読み、(1) Jev をこの面のラベル係にしてよいか（opus との検算）(2) ローカル判定器（kev-0.8b MLX / von）が gemma より Jev に近いか (3) 本番 gate（gemma、temperature 1.0、閾値 0.82）が Jev から見てどれだけずれているか、を 1 回の読みで出す。[RFC-0040](0040-jev-system-one-local-decision-backend.md) の第 2 面。

## Motivation

第 4 ラウンド（RFC-0040、2026-09-24）で skill selection はローカル判定器の候補が尽きた。落とした軸は state 9,000 token・55 択 multi-label・似た抽象語・正解の曖昧さの 4 つで、relevance はその全部を持たない — state 約 250 token（kev の学習長 384 の内側）、Score 1 問、「自分の領域か」は判定者間で安定しやすい。週 736 回で最頻の判定であり、何を読み何に反応するかを決める入口なので、効けば行動への影響が最も大きい面でもある。

正解ラベルは Jev に置く（オーナー提案 2026-09-24）。目標が「ローカルで Jev の代わりを立てる」なら Jev への近さは代理でなく目的そのもので、state が短いので Jev のコストはほぼゼロ（入力 $0.042/MTok、出力無料）、数千行に貼れる。opus は Jev の検算にだけ使う（層別 150 行、数ドル）。

標本は新しい記録を要しない: ADR-0086 の submolt scan が `logs/submolt-scope-*.jsonl` に 2,698 投稿（8 週、2026-08-01〜09-23、distinct `post_id`、`content_b64` 500 字 = 本番のプレビュー長、gemma の `score` 同居）を ADR-0075 の形で残している。同じ `score_relevance_detailed` を通した値なので本番の gate の再生になる。gemma のスコアは二峰性で 1,042 行（39%）が 0.82 以上、833 行が 0.65〜0.82 — 無作為に近い投稿の 4 割を「直接該当」と言うのは、ADR-0084 の「judge する証拠が無いと yes に退化する」と同じ形の疑いがあり、(3) はそれを Jev で照らす。

## Guide-level explanation

同じ 2,698 投稿（またはその層別部分集合）に arm を当てる。本番は無改変。

| arm | 中身 | 行数 |
|---|---|---|
| A `free`（×2 反復）/ A0 `t0` | 現行 `score_relevance_detailed` の再生（temperature 1.0 既定 — relevance は RFC-0044 の対象外だった）/ temperature 0 | 全行 / 全行 |
| C `logits/score4` | gemma に 4 段 Score（`unrelated` / `shares vocabulary only` / `same field` / `directly on-topic`）を ADR-0112 の `OllamaLogprobsDecisionBackend` で問う — seam の初の Score 利用 | 全行 |
| **J `J/score4`** + `J/noul` | ホスト型 Jev（`jev-1.13.0` pin）に同じ 4 段 Score と noul「この投稿は domain に直接該当するか」。**ラベル** | 全行 |
| E `opus`（×2 反復） | claude-opus-5 に同じ rubric（Jev の検算 + 天井の揺れ） | 層別 150 行 |
| K `kev`（0.8b MLX） | score4 + noul、`/v1/systemone` | smoke 5 → dev 150 → holdout 残り |
| V `von` 1.2.2 | 同上 | 同上 |

state は全 arm で同じ: `domain`（本番が system prompt で渡している identity の domain 記述）+ `post`（500 字プレビュー、untrusted 枠）。jev-judgment-design §2（何に対して判定するかを state に入れる）と §3（Score 最下段に「語を共有するだけ」を置く）に従う。

### 事前に固定する読み（読みの前に固定、動かさない）

1. **Jev をラベル係にしてよいか** ⇔ 層別 150 行で Jev（期待段 / P(on-topic)）と opus の Spearman ≥ 0.7、かつ「on-topic」二値の一致率が opus の自己一致率 − 0.05 以上。満たさなければ Jev だけをラベルにせず、この RFC は (3) の読みだけを残して閉じる
2. **ローカル候補が gemma より Jev に近いか** — 行ごとの |候補の正規化スコア − Jev の P(on-topic)| を誤差とし、(候補 − C) の平均誤差の対差 bootstrap 95% CI。dev（150 行）pass ⇔ CI 上限 < 0（候補が近い側）かつ AUC（Jev 二値を予測）が C − 0.02 以上。holdout（残り約 2,500 行、1 候補 1 回）pass ⇔ 同じ 2 条件で CI が 0 を含まない。smoke 5 行は RFC-0040 第 4 ラウンドと同じ資源規則（answered 5/5、latency 中央値 < 2 秒 = 本番の帯、swap +3 GB 以内）
3. **本番 gate の読み** — gemma `score ≥ 0.82` の行のうち Jev が on-topic でない割合（分母付き）、A の自己一致（temperature 1.0 の揺れ）、A0 − A の対差。判定はしない — 数字を [RFC-0044](0044-skill-selector-temperature-zero.md) 型の修理（temperature 0 / 閾値）の材料として残す

標本数の根拠: 一致率 90% を ±5% で言うのに約 140 行、境界の両側を含めるため gemma のスコアで 5 層（< 0.5 / 0.5〜0.65 / 0.65〜0.82 / 0.82〜0.9 / ≥ 0.9）× 30 行。Spearman 0.8 を ±0.07 で置くのに約 110 行。Jev のラベルは無料なので holdout は全行。

## Reference-level explanation

- script `scripts/relevance_arm_replay.py` 1 本（`scripts/skillsel_arm_replay.py` の面非依存部品 — `bootstrap_ci` / `wait_out_schedule` / `ensure_ollama_idle` / `resource_snapshot` / `SystemOneServer` / `run_ceiling` の `claude -p` 包み / `--augment` `--resume` の行 I/O — を import か写しで再利用）。Jev client は `817ecf3:evals/jev_arm.py` を `evals/` に戻し `score` 型を足す（`evals/` 配下 = `tests/test_cloud_egress_absence.py` の名指し allowlist）
- 標本の読み込みは `logs/submolt-scope-*.jsonl` の `event == "score"` 行のみ、`$MOLTBOOK_HOME` へは書かない。`content_b64` は untrusted 枠で prompt に入れ、**evidence にも報告にも本文を置かない**（行単位の出力は `.notes/` のみ）
- 依存はゼロ追加（kev / von は `--no-project` の別 env、Jev / opus は HTTP / `claude -p`）
- 出力: `docs/evidence/rfc-0045/README.md` と集計 JSON（arm 別の分布・Jev との近さ・Jev↔opus・gate の読み・latency・資源）

### 消費計画（ADR-0101）

一発測定（ADR-0075 の 2026-08-29 追補で監査ログ義務の対象外、結果は docs/evidence へ凍結）。(a) 読むのはオーナーと判断役、本実行の完了時 (b) 読み 1 回で上の 3 読みを出す — 読み 1 が成立し読み 2 で holdout pass の候補があれば relevance の shadow（ADR-0112 の seam、`ScoreQuestion`）を別 RFC / ADR で起票、読み 3 は RFC-0044 型の修理提案 (c) 読みを本 RFC に追記した時点で満了 — script は evidence README の復元手順へ降格するか削除

## Drawbacks

- 投稿本文（他エージェントの公開投稿、500 字プレビュー）が TypeSafe と Anthropic の API へ出る。offline の一発測定で、第 2 ラウンドの Jev arm / 天井 arm と同じ扱い。本番の feed は機外に出さない線は変えない
- Jev は正解でなく別の判定者。読み 1 を通らなければラベルとしては使えない
- submolt scan の標本は本番 feed の分布そのものではない（購読・未購読の全 submolt から抽出）。gate の読み (3) は「同じ関数を通した投稿の分布」としての読み

## Rationale and alternatives

- **記録欄を足して 1 週間ためる**: submolt-scope log が同じ形・同じ関数の値を 8 週分持っているので不要。本番 feed そのものの記録は、shadow を入れるときに ADR-0112 の欄で取れる
- **opus を全行のラベルに**: 2,698 行で数十ドルと時間。Jev の検算にだけ使えば数ドルで済み、Jev が通れば以後は無料
- **Jev の出力で fine-tune**: MCA 2.3(b) が禁じたまま。本 RFC は評価利用のみ

## Prior art

RFC-0043（150 行 harness、対差の読み、天井の自己一致を先に測る型）、RFC-0040 第 4 ラウンド（smoke 5 / dev / holdout の 3 段と資源規則）、ADR-0086（submolt scan の記録形）、ADR-0112（`ScoreQuestion` と logprobs 読み）、skill `jev-judgment-design`（state の設計と Score 最下段）、skill `measurement-discipline`。

## Unresolved questions

- Jev の Score 4 段の期待値と本番の 0〜1 スコアの対応（閾値 0.82 に相当する Jev 側の線）— 読み 3 では P(on-topic) ≥ 0.5 を暫定の線にし、対応表を evidence に残す
- domain 記述の長さ（identity 全文か要約か）— arm 間で同じであればよく、本番と同じ identity 全文を既定にする

## Future possibilities

読み 2 が通れば relevance の shadow（seam）→ enforcement。読み 3 が gate の yes 退化を示せば relevance の temperature 0 / 閾値再調整を RFC-0044 型で起票。

## Status

accepted 2026-09-24 — 起票と同日にオーナー GO（Jev + opus 検算 + ローカル候補、外部送信は offline の一発測定に限る）。S28 packet（`.notes/packets/rfc-0045-a.md`）で build へ dispatch。

## Next action

S28 の検収で 3 読みの結果と派生起票（shadow / RFC-0044 型の修理）を Status に書く。
