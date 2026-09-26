---
state: draft 2026-09-26
review-when: 2 face が enforce か retire に決着したらループの型を ADR + docs/CYCLES.md #5/#6 へ昇格し、この RFC は done。本番生成モデルが gemma4:e4b から替わる（face 台帳の lab 指標は gemma で測った値）。ADR-0112 の seam（`DecisionBackend` / `DECISION_FACES`）が変わる
---

## Summary

判断コール 1 つ = 1 face として、offline replay を本番行と row 単位で相関させ、行数 clock と enforce-first で 1 周を約 1 週にする改善ループの型と face 台帳。

Anthropic の「How we made Claude.ai faster」（2026-09-23）の 6 段ループ — Observation → Measurement → Implementation → Validation → Ratcheting → Continuation — をこの repo の語彙に写す。部品は全部ある（`evals/`、使い捨て replay、seam + shadow、週次読み値、`compare.py`）が、**face の一覧・lab ↔ 現場の相関段・face の出生と溶解の型・行数 clock** が無く、同じ手順を [RFC-0043](0043-skillsel-offline-arm-replay.md) → [0044](0044-skill-selector-temperature-zero.md)（skill selection）と [RFC-0045](0045-relevance-judgment-jev-proximity-replay.md) → [0046](0046-relevance-gate-score4-logprobs-shadow.md)（relevance）で名無しのまま 2 回手で回した。本 RFC はコードを増やさない。

## Motivation

- **速さ**: ブログの速さの源は 3 つ — lab 指標が決定論で秒単位、現場は連続 telemetry で日単位、指標を得た瞬間に登り始める。この repo は relevance shadow が 1 日 60〜105 行溜まる（2026-09-25〜26 実測 62 行 / answered 41）のに、ゲートは土曜にしか開かず、clock は「4 土曜 or answered 1,000 行の早い方」（ADR-0113）で 1 周 2〜3 週。事前登録した問いに要る n は 300 行 ≈ 3〜5 日で足りる（オーナー指示 2026-09-25「観察期間が長すぎる。shadow は良いが慎重すぎ」）
- **的**: 改善 ≠ 能力拡大（[ADR-0080](../docs/adr/0080-north-star-layered-end-state.md)）。的は本番読み値が示した欠陥の修理 — relevance の記録 ≥ 0.82 のうち 47% が domain 外（RFC-0045）、selector の幻覚 21〜29%（RFC-0043）。lab 指標が飽和した face は ratchet を凍結 baseline に落として止まる = 北極星の完成条件と同型
- **塩漬け**: 観測数の条件に到達率と予定日が無いと台帳で寝る。clock を暦から行数へ、ゲートを儀式から到達日へ

## Guide-level explanation

### 6 段 → repo の写像

| 段 | ブログ | 既にある | 無いもの（本 RFC が置く型） |
|---|---|---|---|
| Observation | 遅い区間を見つける | `/weekly-report` F1〜F3 診断、`instrument_census.py`、使い捨て replay の読み | face 名で起票する（Motivation 1 行目に face） |
| Measurement | lab benchmark。**現場指標との相関を証明してから guardrail、相関しない指標は捨てる** | `evals/`（Face A）、`scripts/*_arm_replay.py`、`docs/evidence/` 凍結 | **相関証明の段**（下）と label-once の lab 資産 |
| Implementation | 小 PR + flag（kill switch / ramp） | seam（ADR-0112）+ shadow（ADR-0113）、env が kill switch、build tier への dispatch | risk tier（下）— 低リスクは enforce-first |
| Validation | deploy 後の現場データ | shadow log（paired）、`scripts/relevance_shadow_reading.py` 等 | **行数 clock + 曜日不問の face gate** |
| Ratcheting | 退行しない CI gate | `evals/compare.py` regression = exit 1（手動）、`check_staleness.py`（advisory） | ratchet 規約（下） |
| Continuation | 同じ journey の次のボトルネック | rfcs/ 台帳、`claims.py ready` | face 台帳の「現在段」列と溶解条件 |

### face の粒度

**1 判断コール = 1 face**。prompt ファイル・backend seam（`DECISION_FACES` の単位）・閾値・記録 series・週次読み値がすべてこの粒度に付く。pipeline 段（feed → gate → comment → outcome）は複数 face をまたぐので lab 指標と現場読み値が混ざる（measurement-discipline「通過分だけで語らない」）— pipeline 段は次の face を選ぶ journey としてだけ使う。

### 現場の真値（lab 指標が相関を証明する相手）

型別に置く。**comment-outcome（返信・upvote）は従属変数にしない** — 報酬にした瞬間、環境の反応が値層を最適化する（[ADR-0051](../docs/adr/0051-retire-trust-weighting.md) の反転）。並記の読み値としてだけ載せる。

| 型 | 真値 |
|---|---|
| gate（relevance、novelty） | 本番 shadow 行 × opus の二値ラベル |
| 選択（skill selection、submolt） | 本番 selection log × opus の選択 |
| 生成（comment、reply） | 本番サンプル × adherence 判定器（`evals/judging.py` の named verdict） |

### 速度設計

**1. 行数 clock + face gate。** face ごとに事前登録した問いから n を導く。例（gate 型）: 「本番分布で would-be gate 率が offline の予測 ±6 pt に収まるか、latency p95 が cycle に乗らないか」→ 二項の 95% CI 半幅 ≈ 1/√n で n = 300（±5.7 pt）。到達率は読みのたびに実測して幅で書き、予定日を台帳の `再開条件` に添える。n 到達日に **face gate**（10 分の人間ゲート、曜日不問、`/weekly-gate` とは別）を開き、reading script の出力から enforce / kill / continue の 1 語を RFC の Status に書く。土曜 `/weekly-gate` は値層専用のまま。n 到達の検知は reading script を走らせるだけ（stdlib、秒）— scheduler は建てない。**stuck**: n が 14 日で満ちない face は延長でなく決める（retire か問いを小さく）。

**2. risk tier — 低リスク face は enforce-first。**

| tier | 定義 | 手順 |
|---|---|---|
| **L** | 既に許された行動のどれを取るかだけを変え、**誤りの向きが縮小側**（gate がより厳しくなり外向き作用が減る。取り逃した post は残るので後で拾える）、env 除去で以後の判定を戻せる | ① offline ラベルで閾値を事前登録 ② enforce に切替え、旧経路も n 行のあいだ並走させて両方記録（paired） ③ n 行で face gate → keep なら旧呼び出しを落とす / kill なら env 除去 |
| **H** | 誤りの向きが拡大側（post が増える）、publish する本文の形が変わる、値層に触れる、I/O 面が広がる | shadow-first（RFC-0046 の shadow 段の形）。n 行で enforce GO |

paired の限界: 同じ入力上の判定比較はできるが、post 済み対象は以後のセッションで除外される（`feed_manager.py` の除外規則）ので「旧経路だけで運用した履歴」は得られない。戻せるのは以後の判定で、出た post は戻らない — 現行 gate も同じ性質なので、比較すべきは誤りの向き。relevance は would-be 0.22〜0.39 対 live 0.58（2026-09-26 読み）で縮小側 = L。

**3. label once, score many。** face ごとに凍結ラベル集合（本番 shadow 行を post_id で dedupe して層化 150 行 × opus ラベル、1 回 $19〜24）を main tree の `.notes/labels/<face>/` に持つ（worktree 不可 — RFC-0045 の行データは worktree 削除で消えた。他エージェントの投稿本文を含むので `docs/evidence/` に置かない）。**ラベルは判定の入力ごと凍結する**: relevance は呼び出し時の identity 本文に依存し identity は月次で進化する値層なので、`evals/snapshot_assets.py` と同じ形で identity / prompt / model の sha を manifest に pin し、`check_staleness.py` と同じ決定論検査で失効を検出する。identity が adopt されたら再ラベル（月次程度）か ack。lab ratchet が測るのは「値層を固定したときの機構の退行」で、値層の正当な変化を退行と読まない。スコアラは決定論（logprobs、temperature 0、gemma ≈ 3 秒/行 → 150 行 7.5 分、$0）。prompt / 閾値 / seam を触る PR は pin した identity の下でこれを回し、AUC・一致率を baseline と比較する。集計は軸ごと、合成しない（ADR-0080 追補 B）。

**4. ratchet 規約。** 決定論（manifest sha / parser / schema / 出力形）は `.claude/verify.sh` で block。LLM eval（gemma 生成 + judge、凍結ラベル集合のスコア）は **face の prompt / code に触る PR の merge 条件** — build packet と task-triage の検収 checklist の 1 項目で、`compare.py` exit 1 相当なら merge しない。commit 境界には入れない（遅く確率的、one-run-not-evidence）。

**5. 並列。** face 数に上限を置かない（オーナー判断 2026-09-25）。衝突は run ごとに 3 事実で判定: 2 モデル非同居 / lab replay は本番窓 JST 0-6-12-18 を避ける / paired 列が増えた分の本番 latency は各 face の `decision_latency_ms` で読み、cycle の待ちに乗った時点で人間が優先順位を決める。

**6. 1 周の所要（Tier L）。** 現行: shadow 1,000 行 ≈ 10〜16 日 + 次の土曜 + enforce PR ≈ 2〜3 週。新: ラベルと enforce PR を先に用意 → 切替 → paired 300 行 ≈ 3〜5 日 → n 到達日に GO ≈ **1 週**。

### face 台帳（2026-09-26 snapshot）

standing register にしない（[ADR-0101](../docs/adr/0101-instrument-dissolution-mandate.md) D4）。再導出: `config/prompts/*.md` × 呼び出し元（`adapters/moltbook/llm_functions.py`、`core/`）の grep。「無」は Explore 時点の未検出で、未確認を含む。

| face | 住所 | 型 | tier | lab 指標 | 現場読み値 | 相関 | ratchet | RFC | 現在段 |
|---|---|---|---|---|---|---|---|---|---|
| relevance gate | `score_relevance_detailed` / relevance.md, relevance_score4.md | gate | L | AUC 0.944 対 0.82（rfc-0045。**3 条件 + 採点の問いが交絡、梯子 S31 で分離中**） | `relevance_shadow_reading.py`、本番 ON | 未 | 無 | 0046 | **pilot** |
| skill selection pass-1 | `select_applicable_skills` / skill_selection.md | 選択 | L | 5 arm、幻覚 21〜29% → 7.3%（rfc-0043） | `skillsel_reading.py`、never-selected | 未 | 無 | 0040・0044 | 2 番目 |
| comment 生成 | `generate_comment` / comment.md | 生成 | H | `evals/` baseline 09-12 | comment-outcome（並記のみ） | 未 | `compare.py` + staleness advisory | — | 3 番目 |
| insight novelty gate | `core/insight_novelty.py` / insight_novelty*.md | gate | L | novelty_replay_ab（rfc-0023） | 土曜の採用率、confusion-pair | 未 | 無 | 0023・0042 | Observation |
| reply / post title / cooperation / submolt / internal note / topic summary | `llm_functions.py` | 生成・選択 | H | 無 | comment reports、cross-day duplicate、submolt-scope | — | 無 | — | 未計測・着手しない |
| distill | `core/distill.py` / distill_*.md | 抽出 | — | 退役（ADR-0071/0072） | pattern store 読み | — | — | — | 止まった face。現場欠陥が出るまで開けない |
| verification solve | `verification.py` | 抽出 | — | verify-solve-model-compare | api-audit | 正解が決定論 | — | — | 固定 |

載せない face: identity distill / constitution amend / insight の命名・重複判定 — 値層の内容を書く判断コールで、eval の的にしない（observation-over-steering）。apparatus の故障（parse 失敗・truncation）だけを扱う。

### face の出生証明（型。実体は face の所有 ADR の `## Review-when` > `### Consumption plan`）

住所・型・tier / 観測した現場欠陥（読み値と日付）/ lab 指標（凍結ラベル集合の出所と層化、天井、判定規則を読みの前に固定、n。**候補 arm と本番の差を表で列挙し、測りたい差は 1 条件だけ — 2 つ以上なら梯子。審判の定義は著者確認の事前登録** — measurement-discipline §8）/ 相関証明（同一 row id で lab と現場を突き合わせ、事前に置いた下限未満なら lab 指標を撤去）/ 介入の形（seam・env、kill switch）/ clock（事前登録の問いと n、到達率、予定日、stuck 14 日）/ ratchet（決定論 block の対象、LLM eval を merge 条件にする範囲）/ ADR-0101 (a)(b)(c) / 溶解（lab 資産・paired 列・env 名を別々に撤去する条件、ラベルの失効 = pin した入力が変わり再ラベルしないと決めた時）/ 資源（本番窓・非同居・swap・$）。

### 人間の 3 役

ブログの ambition / taste / direction は、この repo の三役では 判断役 = 出生証明の受理と face gate の 1 語（enforce / kill / retire）、build = replay・enforce PR の実装、人間 = plist・`verify.sh`・ADR の gate。ループ自体の停止条件: 全 face が「乖離なし」か「未計測・着手しない」になったらこのループを溶解する（機構層の完成条件、ADR-0080 追補 A と同型）。

## Reference-level explanation

- 触るのは rfcs のみ。接続点（読むだけ）: `evals/compare.py` の exit 契約、`.claude/verify.sh` full mode の staleness advisory、`scripts/*_reading.py`、`adapters/moltbook/relevance_shadow.py`、`config/launchd/com.moltbook.agent.plist`、`docs/CYCLES.md` #5/#6、`.claude/skills/weekly-gate/SKILL.md`
- 昇格時に変わるもの（本 RFC では書かない）: ADR 1 本（ループの型）、CYCLES.md #5/#6 に face 台帳の再導出手順 1 行、task-triage 検収 checklist に merge 条件 1 行、`/face-gate` 項目 skill
- 規律の正本は harness 側: measurement-discipline §2（ゲートは暦でなく観測量で — n の導出と到達率）/ §6（戻せる変更は切替えてから観察する）/ §7（高い判定は 1 回買い、繰り返す測定は決定論で $0 に）。本 RFC は repo 固有の写像と台帳だけを持つ

## Drawbacks

- face 1 つに出生証明の儀式が乗る。ラベル $19〜24 / face、identity の adopt ごとに再ラベルか ack
- enforce-first は数日間 gate の挙動が変わる。Tier L の定義（縮小側・戻せる）で範囲を限る
- lab 指標への Goodhart。相関段と ADR-0080 のベンチマーク非還元条項で抑える
- 「測るものを増やす」衝動（ブログの最大レバレッジ）は ADR-0101 の出生証明でしか抑えられない

## Rationale and alternatives

- **ブログを文字通り**（latency を的に、CI で LLM eval を block、150 並列）: latency は 15 tok/s の帯域幅で頭打ち（CLAUDE.md）、LLM eval の commit gate は one-run-not-evidence に反する。並列無制限だけ採用
- **何もしない**: RFC-0046 が手で回している。3 回目も名無しで回し、clock は土曜のまま
- **全 face 共通の eval framework**: 機構増（ADR-0101）。face の部品は既にあり、無いのは型だけ
- **shadow-first を全 face に**: 1 周 2〜3 週。オーナー却下 2026-09-25
- **日次 launchd の readiness 通知**: 消費者が居ることが分かってから（Unresolved）

## Prior art

ブログ（2026-09-23）、[ADR-0089](../docs/adr/0089-llm-behavioral-eval-layer-on-deepeval.md)（Face A eval）、[ADR-0112](../docs/adr/0112-decision-backend-seam-and-shadow-skill-decision.md) / [ADR-0113](../docs/adr/0113-decision-faces-and-relevance-score4-shadow.md)（seam と shadow）、[ADR-0071](../docs/adr/0071-read-only-pattern-composition-instruments.md) / [ADR-0075](../docs/adr/0075-observability-by-default.md) / ADR-0101、ADR-0076（shadow の kill switch）、RFC-0043 / 0045 / 0046、harness skills measurement-discipline / llm-as-judge / loop-design-check、repo skills shadow-mode-validation / read-only-instruments。plan 段の cross-model 反証（codex、2026-09-26）で 3 点を採用: 現行 clock の所要を 2〜3 週に訂正、Tier L に誤りの向きを追加、ラベルの失効条件を追加。

## Unresolved questions

- 現場読み値の無い face（reply / post 系）の真値をどう置くか
- 「相関あり」の下限（最初の face で決めて記録する）
- readiness 通知（n 到達を機械が知らせる）の要否 — 消費者と cadence を書けたら `pipeline_watchdog.sh` に 1 行
- 使い捨て replay script を凍結ラベル集合 + 決定論スコアラに置き換えるか（ADR-0101 の消費者が居る間だけ）

## Future possibilities

2 face が決着したら ADR + CYCLES.md #5/#6 へ昇格し、本 RFC は done。face gate の checklist を `/face-gate` 項目 skill にする。

## Status

draft 2026-09-26 — 起票。pilot は RFC-0046（relevance）を本 RFC の型に当てはめて進める（0046 の消費計画を改定済み）。

## Next action

オーナー通読 → accepted なら pilot の手順は RFC-0046 の Next action が持つ（S30 で enforce 段のコードは main 入り `128fe60`、手順 0 = 梯子 S31 が進行中。**lab 指標が交絡していれば enforce-first の前に 1 条件ずつ分離する** — 相関証明の段の一部）。2 番目は skill selection の temperature 0（RFC-0044、Tier L）。
