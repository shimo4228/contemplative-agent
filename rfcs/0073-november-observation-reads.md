---
title: 挙動を変えた後の 11 月の読みと ADR-0080 追補（2026-11）
state: blocked
state_since: 2026-10-31
decide_by: 2026-11-28
next_check: 2026-11-28
review-when: 次の identity 採用から 7 日と、2026-11-06 / 11-13 の本番週次 2 回が出た
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: instrument
---

## タスク

挙動を変えた後の観察が要るロードマップの行をまとめる。待つ理由は観察（OBS）だけで、コードで先にできる部分は待たずに入れる。

## 詳細

持つ行: P2-06.1、P1-15.2、P1-07.10、P2-01.5、P2-01.3、P1-03.9、P1-03.8。

- P2-06.1: Exceptions の行数が本番週次 2 回で減ったか（構造の確認だけなら 10-30 の 1 回で足りる、という選択肢もある）。
- P1-15.2: enforce 後の母集団（post 単位）で t=0.3 を再読し、identity 採用の前後 ±7 日の gate 率を読む。
- P1-07.10: path ごとに llm-calls が 1,000 行たまったら token 推定器を再較正する（PR2）。
- P2-01.5: 自己調節の読み値のうち使わない列を落とす。
- P2-01.3 / P1-03.8: 追補（2026-11）に読み方の段落を書き、必要なら追補（2026-12）。
- P1-03.9: `scripts/self_regulation_reading.py` の候補行に基礎率を併記する — コードなので待たずに入れる。
- 済の行に残る WAIT（P1-15.3 の投票行、P2-04.9 の late_minutes、P1-01.1 の 4 週の転記）も同じ読みで拾う。

完了: 各読みが記録され、追補が採択されている。

## 2026-11-04 triage 照合 (by: judge)

verdict: dead-band

blocked のまま（照合先が未成立）。

照合先: 次の identity 採用は無い（`audit.jsonl` の `distill-identity` approved の最終は 2026-10-10）、本番週次 11-06 / 11-13 はまだ。本文の「コードで先にできる部分は待たずに入れる」に当たる P1-03.9 の残り（`scripts/self_regulation_reading.py` の候補行・下限行への基礎率の併記と test 1 本、`docs/plans/roadmap-2026-10/STATUS.md:230`）は build に出せる。今回は WIP 3 を RFC-0066 / 0067 / 0068 に使うので、次の cycle で開始の OK に出す。

## 2026-11-07 triage 照合 (by: judge)

verdict: ready

待ちの 1 つが成立した: identity を 2026-11-07 に採用（`audit.jsonl` stage-adopted-names、content_hash `012114a54fb5ac3d`）。P1-15.2 の ±7 日の gate 率は 11-14 以降の週次（weekly-2026-11-13 / 11-20 の relevance face reading）で読める。コードで先にできる P1-03.9（`scripts/self_regulation_reading.py` の候補行・下限行への基礎率の併記と test 1 本）は cloud build に出せる。公開 repo なので開始は digest の OK を待つ。

## 2026-11-11 検収と照合 (by: judge)

P1-03.9 を main に取り込んだ（S51、[packet](../docs/plans/rfc-0073-s51-selfreg-base-rates.md)、`25d69c00` と索引の再生成 `5f300448`、ff-only）。候補行に `base_rate_zero_load=k/n`、下限行に `base_rate_no_change=k/n` が付き、n ≥ 10 のときだけ Wilson 区間を添える。差し戻し 1 回: ADR-0080 に注記を足したのに索引を再生成しておらず、生成物の検査 4 件が落ちていた（build は sandbox の要因と報告していた）。判断役の verify exit 0、別プロセスの review で correctness の指摘 0 件。review の optional のうち読み方に関わるもの: 週次チェーンは `--weeks` を渡さないので窓は 8 週で、区間は週次では出ない。floor に達した週は no_change が構造上 8/8 になる。ADR-0080 の表の率（changes.json の 13 週の代理指標）とは測るものが違う。

verdict: dead-band
残りの行が対象。

照合先: identity 採用（2026-11-07）から 7 日 = 2026-11-14、本番週次 weekly-2026-11-13 はまだ出ていない。P1-15.2 の ±7 日の gate 率は weekly-2026-11-13 / 11-20 の relevance face reading で読む。

## 2026-11-14 triage 照合 (by: judge)

verdict: ask-owner

照合先が成立した（next_check 2026-11-14）: identity 採用（11-07）から 7 日と、本番週次 11-06 / 11-13 の 2 回。

- P1-15.2: adopt 窓の読みは `reopen`（post 単位の gate 率 前 204/389 = 0.524 → 後 229/713 = 0.321、差 −0.203、区間 [−0.263, −0.142]、帯 ±0.06 の外。weekly-2026-11-13 の materials）。findings F3.1 が挙げた R34（11-11T15:00Z）との重なりは、R34 より前だけの切り出しで読んだ: `relevance_shadow_reading.py --start 2026-11-07 --end 2026-11-10 --since 2026-11-07T02:30:22Z` が would 0.272（441 行）で、下がりは R34 の前に出ている。ADR-0113 Amendment 6 の Review-when は reopen で adopt 後の 150 post の再読（新しい label set）を開く。第 3 の読み（「次の identity 採用の前」）は採用までに取られていない（`docs/evidence/rfc-0046/` に 2026-09-28 の label set しか無い）。label の run はオーナーの操作（閉じた API）。1 つの label set で両方に答えるかを digest で聞く。
- P1-15.3 の WAIT: weekly の margin 読みは 5 週分ある（W42〜W46: 0.038 / 0.046 / 0.064 / 0.031 / 0.048）。Review-when の「4 週分」に届いたので、多数決・ヒステリシスの規則を足すか「足さない」かの 1 行を書く。既定の「足さない」を digest に出す。
- P2-06.1: Exceptions の行数は 99（10-30）→ 80（11-06）→ 114（11-13）で、2 回続けては減っていない（`self_regulation_reading.py --end 2026-11-14`）。carried の畳み込みは毎週 1 行に収まっている（carried 4/1、2/1、3/1）。読みの扱いを digest に出す。
- P1-07.10 PR2: P1-15.2 の第 3 の読みが条件の片方で、まだ揃っていない。
- P2-01.5 / P2-01.3 / P1-03.8: 追補（2026-11）の段落は上の 3 つの裁定の後。

## 2026-11-14 著者回答 (by: owner)

triage digest 2026-11-14 を推奨どおり承認。

- P1-15.2: 採用後の母集団から 150 post の label set を 1 本作り、第 3 の読みと reopen の再読を兼ねる。読むのは 2026-12-05 のゲート（Jev 1.13.0、label はオーナーの run）。
- P1-15.3: 多数決・ヒステリシスは足さない（ADR-0113 に注記）。`margin` 列の撤去は次の build 行。
- P2-06.1: 済（2026-11-14、構造の確認 — carried は毎週 1 行に畳まれている。行数 99→80→114 は読み値として残す）。
- next_check を 2026-11-21 に進めた。

## 2026-11-18 triage 照合 (by: judge)

verdict: dead-band

next_check 2026-11-21（11-14 の著者回答で進めた）。P1-15.2 の label set は 12-05 のゲート。`margin` 列の撤去（次の build 行）は RFC-0071 の計測と同じ窓に重ねず、次の cycle で packet に切る。

## 2026-11-21 triage 照合 (by: judge)

verdict: ready

next_check 2026-11-21 に達した。いま動かせる行は 11-14 の著者回答が「次の build 行」とした `margin` 列の撤去（P1-15.3）だけで、S56 として Agent build（worktree、opus）に出した（packet は branch の最初の commit で `docs/plans/rfc-0073-s56-retire-margin-column.md`）。P1-15.2 の label set は 12-05 のゲート、P1-07.10 PR2 は P1-15.2 の第 3 の読み待ち、P2-01.5 / P2-01.3 / P1-03.8 の追補（2026-11）は decide_by 11-28。next_check を 11-28 に進めることを digest に出す。

## 2026-11-21 著者回答 (by: owner)

triage digest 2026-11-21 を推奨どおり承認: next_check を 2026-11-28 に進めた。

## 2026-11-21 検収 (by: judge)

P1-15.3 の `margin` 列を撤去した（S56、[packet](../docs/plans/rfc-0073-s56-retire-margin-column.md)、`019ef9f8`、ff-only）。`scripts/relevance_shadow_reading.py` から `MARGIN_HALF_WIDTH` / `margin()` と JSON の `margin` を外し、週次の 8 行目は Ollama の版だけを出す `ollama_line` になった（schema 6 → 7）。`--t` は adopt window の判定に使うので残した。読む側（`scripts/weekly-analysis.sh`、`config/prompts/weekly-analysis.md`、`docs/CYCLES.md`、`docs/runbooks/model-swap.md`）と ADR-0113 の注記も同じ commit。判断役の verify は rebase 後の先頭で exit 0（6515 passed）。別プロセスの review は correctness の指摘 0 件（optional 6 件は文言・表示の提案で採らない）。build が残した判断: ADR-0113 追補 6 の Review-when の「`[ollama changed]` の週に margin の比率が区間を超えて動いた」は確かめようがなくなった — 言い換えるか外すかを次の digest で聞く。state は blocked のまま（残りの行）。

## 2026-11-25 triage 照合 (by: judge)

verdict: dead-band

next_check 2026-11-28。11-21 の検収が残した問い（ADR-0113 追補 6 の Review-when の「`[ollama changed]` の週に margin の比率が区間を超えて動いた」は、margin 列の撤去で読むものが無くなった）を今回の digest で聞く。既定は「外す」: 11-21 の注記（`docs/decision-history/0113-decision-faces-and-relevance-score4-shadow.md:598`）に、この項目は退役したと 1 文足す（.ja.md も）。

## 2026-11-25 著者回答 (by: owner)

triage digest 2026-11-25 を推奨どおり承認: ADR-0113 追補 6 の Review-when の「`[ollama changed]` の週に margin の比率が区間を超えて動いた」は外す。11-21 の注記（英語版と .ja.md）に退役の 1 文を足した。next_check は 11-28 のまま。
