---
state: in_progress 2026-09-26
review-when: 本番の relevance 判定モデルが gemma4:e4b から替わる（AUC 0.944 は gemma で測った値 — shadow から読み直す）。`config/prompts/relevance.md` か閾値（0.82 / 0.65 / 0.70）が変わる。ADR-0112 の seam（`ScoreQuestion` / `OllamaLogprobsDecisionBackend`）が変わる
---

## Summary

relevance gate（feed の各投稿を自分の domain に対して採点し 0.82 / 0.65 で切る判定、週約 736 回）を、gemma に 0〜1 の数字を自由生成させる今の形から、同じ gemma に **4 段 Score（`unrelated` / `shares vocabulary only` / `same field` / `directly on-topic`）を A〜D で答えさせ先頭 token の logprobs を読む形**（ADR-0112 の `ScoreQuestion` + `OllamaLogprobsDecisionBackend`）へ替える修理。**2 段**: まず shadow（live の score の横に would-be の P(directly on-topic) を記録するだけ、行動は変えない）、shadow の読みの後に enforce（閾値を置いて gate を差し替える）を別途 GO。モデル交代なし。[RFC-0045](0045-relevance-judgment-jev-proximity-replay.md) 読み 3 の帰結。

## Motivation

RFC-0045（2,698 投稿の offline 再生、2026-09-25）で本番 gate の形が読めた:

- 記録スコア ≥ 0.82 の 1,042 行のうち **489 行（47%）を Jev は domain 外**と判定。gemma の順位づけ自体は単調（記録 ≤ 0.4 で Jev 該当率 3〜6%、0.9 で 54%）で、上の帯が甘い
- temperature 1.0 の揺れ: 同じ投稿への値は再生間で 36% しか一致せず、gate の上下でも 83%。**temperature 0 は効かない**（A0 − A の平均 +0.015 [+0.003, +0.027]）— RFC-0044 の手はこの面では無効
- 同じ gemma に 4 段 Score を logprobs で読ませる arm C は Jev の二値を **AUC 0.944 [0.903, 0.978]** で予測、自由生成の 0.821 を大きく上回る。決定的（temperature 0、sampling なし）で、揺れも消える
- ローカル Jev 型（kev / von）は AUC 0.43〜0.60 で候補外（RFC-0045 読み 2）。**モデルを替えずに生成形を替える**のが唯一の当たり

## Guide-level explanation

### shadow（本 RFC の範囲、S29）

- `feed_manager._judge_post` の live 判定（`score_relevance_detailed`）の直後に、decision backend が構成されていれば `ScoreQuestion`（4 段）を 1 問投げ、結果を **新しい自己書き込みログ `logs/relevance-{date}.jsonl`** に 1 行で残す。live の score・閾値・gate 判定は触らない（ADR-0076 型、観測専用 `-> None`、失敗は null 欄に degrade して生成を止めない）
- state は RFC-0045 の arm C と同じ形（`domain` = identity.md の本文 + `post` = untrusted 枠の 500 字プレビュー）。4 段の見出しと各段 1 文は `config/prompts/relevance_score4.md` に外出し（ADR-0054）— `scripts/relevance_arm_replay.py` の `LEVELS` をそこへ移し、harness は同じファイルを読む
- 面の切替: 新 env `DECISION_FACES`（comma 区切り、既定 `skill_selection` = ADR-0112 の現行挙動を保存）。オーナーは scheduled session の env に `DECISION_MODEL=gemma4:e4b DECISION_FACES=relevance` を置く（launchd の変更は人間ゲート）。判定モデル = 生成モデルなので `exclusive=False`、交代ゼロ
- 記録 1 行: `ts / run_id / session_id / post_id / author_known / live_score / live_reason / threshold_applied / live_gate / decision_backend / decision_model / decision_reason / decision_p（4 段）/ decision_p_top（P(directly on-topic)）/ decision_expected_level / decision_latency_ms / content_sha256 / content_b64（≤ 8 KB、`b64_audit_fields`）`。unconfigured なら decision 欄は null + `decision_reason: "unconfigured"`（記録自体は backend の有無によらず書く — relevance の再生可能な記録は ADR-0075 の積み残し）
- census（ADR-0107 / 0110）に series `relevance-` を登録、enum は `live_reason` / `decision_reason`
- 読み値 script `scripts/relevance_shadow_reading.py`（stdlib、read-only）: answered 率、live gate 率、閾値候補 t ∈ {0.3, 0.5, 0.7} での would-be gate 率と live gate との一致、`decision_latency_ms` p50 / p95、週別

### enforce（別 GO、本 RFC では設計だけ）

閾値は **opus の二値**（RFC-0045 dev 150 行の E ラベル、Jev は狭く取るので正本にしない）で置く。offline の事前値: arm C の P(directly on-topic) を E の on-topic で切った precision / recall を t ごとに evidence へ（S29 が RFC-0045 の凍結行から計算して ADR に書く）。enforce の形は `score_relevance_detailed` の中で backend が構成されていれば logprobs 経路を使い、`RelevanceScore.score` に P(top) を入れ `reason: "score4"`、閾値は `domain.relevance_threshold` を **別の値** `relevance_threshold_score4` に分ける（0.82 は自由生成の尺度で、P(top) の尺度と違う）。

Tier L（誤りの向きが縮小側 — 2026-09-26 の読みで would-be gate 率 0.22〜0.39 対 live 0.58）なので enforce-first: 切替時に旧自由生成の score も n 行のあいだ並走させて同じ行に記録し（paired）、face gate で keep なら旧呼び出しを落とす（[RFC-0047](0047-face-eval-loop.md) の risk tier）。

### 消費計画（ADR-0101、shadow）

(a) 判断役（オーナーか judge-tier セッション）が `scripts/relevance_shadow_reading.py` を走らせて読む — 曜日不問、n 到達日に face gate を開く（RFC-0047。土曜の weekly-gate は値層専用）。(b) **問い**: 本番分布で would-be gate 率が offline の予測 ±6 pt に収まるか、latency p95 が cycle に乗らないか、answered 率が落ちないか。**n = 300 行**（二項の 95% CI 半幅 ≈ 1/√n で ±5.7 pt）。到達率は実測 60〜105 行/日（2026-09-25〜26: 62 行 / answered 41）で 3〜5 日 — 読みのたびに更新する。閾値は shadow 行のラベル（Status）で**読みの前に**置く。(c) enforce の ADR が着地したら shadow 欄は本番記録に格上げ（ログは残る）。n が 14 日で満ちなければ延長せず retire — hook・env・census の enum を 1 commit で消す（`live_*` 欄は ADR-0075 の記録として残す）。ラベル集合は pin した identity が adopt で変わり再ラベルしないと決めた時に失効。

## Reference-level explanation

- 触る場所: `adapters/moltbook/feed_manager.py::_judge_post`（hook 呼び出し 1 行）、`adapters/moltbook/relevance_shadow.py`（新規: state 組み立て・decide・記録）、`config/prompts/relevance_score4.md`（新規）、`cli/runtime.py`（`DECISION_FACES` の読みと backend の配線 — 既存の `DECISION_MODEL` 分岐に面の集合を足す）、`core/skill_selection.py`（`DECISION_FACES` に `skill_selection` が無ければ shadow を呼ばない）、`scripts/_census_registry.py`、`scripts/relevance_shadow_reading.py`、`scripts/relevance_arm_replay.py`（`LEVELS` を prompt ファイルから読む）、`docs/CONFIGURATION.md`（+ `.ja.md`）、ADR-0113（新規: 面の切替と relevance shadow、ADR-0112 に注記）、`graph.jsonld`（ADR ノード）
- 依存ゼロ追加。外向きは既存の Ollama URL のみ。1 投稿あたり gemma 呼び出しが 1 回増える（RFC-0045 の C は cache 無しで中央値 2.9 秒。本番は live prompt と prefix が違うので cache は効かない前提で読む）
- `submolt_scope.py` の scan 経路には hook を掛けない（read-only 計器、週 380 行の GPU を倍にしない）

## Drawbacks

- 週 736 回 × 約 3 秒 = 約 35 分 / 週の GPU 追加。cycle の待ちに乗る分は `decision_latency_ms` で測る
- 記録ログに他エージェントの投稿本文（500 字）が base64 で入る — submolt-scope と同じ形。episode log と同じく Claude Code セッションの直読み対象にはしない（b64 なので平文注入面にはならない）
- shadow の間、gate は今のまま（47% の過剰通過は続く）

## Rationale and alternatives

- **enforce を直接入れる**: gate の変更は行動への介入。本番分布での would-be gate 率と latency を見ずに閾値を置くと、RFC-0044 と同じ「offline では成立、本番の代価は未測定」になる
- **temperature 0 だけ**: RFC-0045 で無効と実測（+0.015）
- **閾値の再調整だけ（0.82 → 0.9）**: 記録値が離散なので 0.9 以上は実質同じ行。甘さは値でなく生成形にある
- **ローカル Jev 型に替える**: RFC-0045 読み 2 で候補外

## Prior art

ADR-0112（seam、skill selection の shadow 欄）、ADR-0076（shadow の kill switch = 設定不在）、ADR-0086（submolt-scope の記録形）、RFC-0044（selector の temperature 0 — offline で成立した修理の先例）、RFC-0045（数字の出所）、skill `shadow-mode-validation` / `jev-judgment-design` §3。

## Unresolved questions

- 本番の state に憲法 axioms を入れるか（RFC-0045 の C は identity.md だけ。live の system prompt は identity + axioms）— shadow は C と同じ identity.md だけで始め、enforce 前に必要なら A/B
- `DECISION_FACES` の既定を `skill_selection` にするか空にするか — 既定 `skill_selection` で ADR-0112 の挙動を変えない

## Future possibilities

enforce 後、`RelevanceScore` が確率を持つので upvote-only 閾値（0.70）と known-agent 閾値（0.65）も同じ尺度に揃える。他の判定面（submolt selection、postgate）も同じ seam へ。

## Status

in_progress 2026-09-26 — **enforce 段のコードは main 入り**（S30、`128fe60`）: env `DECISION_ENFORCE`（既定空 = kill switch）、domain の `relevance_threshold_score4`（未設定なら enforce せず `enforce_no_threshold` を記録）、enforce 中も旧の自由生成を並走して同じ行に paired 記録（`gate_source` / `enforce_gate` / `enforce_reason` / `enforce_threshold`）、`scripts/relevance_shadow_reading.py` v2 の readiness 節（`--since` / `--n`）、`scripts/relevance_label_set.py`（sample / label / score / check、manifest に identity / prompt / model の sha）。本番挙動は不変（env 未設定・閾値未記入）。shadow は本番 ON のまま（2026-09-25 15:20 JST〜）。2026-09-26 09:00 の読み: 切替後 answered 66 行 / post_id dedupe 55 行 / 約 100 行/日。

**前提の交絡（オーナー指摘 2026-09-26）**: 本 RFC の根拠（C の AUC 0.944 対 A 0.82、≥ 0.82 の 47% を J が分野外）は、本番 A と 4 段の組で 3 条件（system prompt の identity + axioms / 0〜1 の問い / 数字の生成）と採点の問い（J は identity のみの domain）が同時に違う比較で、どの条件が差を担うか未測定（`docs/evidence/rfc-0045/README.md`「RFC-0040 JevK5」節の測らなかったこと 1 項目目）。identity.md は抽象的で瞑想・慈悲は axioms 側にあるため、47% の一部は「自分の分野」の定義のずれの可能性。**定義（identity のみ / identity + axioms）はオーナーの判断で未決**。オーナー決定: 定義を決める前に梯子（A → A0 → R1: 問いだけ 4 段 → R2: axioms を外す → C: logprobs、加えて Cx と J の identity + axioms 採点）を dev 150 で測る（S31、2026-09-26 着手、gemma 約 40 分 + J 約 $0.01）。**enforce の GO とラベルの state はこの読みの後**。

**梯子の読み（S31、2026-09-26、`docs/evidence/rfc-0045/README.md`「RFC-0046 の梯子」節、script は `830954c`）**: C − A = +0.116 [+0.056, +0.189]（対 J）のうち
**C − R2（生成 → logprobs 読み）が +0.101 [+0.059, +0.147] で 0.88 を担い、CI が 0 を含まないのはこの段だけ**。温度（+0.032）、問いの形（−0.004）、
axioms を外す（−0.014）はいずれも CI が 0 を跨ぐ。対 Jx でも同じ形（C − R2 が 0.95）。**定義**: 審判の domain に axioms を足しても分野外 → 分野内の
反転は 0 行（logged ≥ 0.82 の 30 行で 0、dev 全体で 0、逆向きは 6）、J と Jx の一致 0.960。**47% は定義のずれでは説明されず、本 RFC の機構の主張
（読み方を logprobs にする）は交絡を解いても残る**。Cx − C = −0.020 [−0.049, +0.005]: domain に axioms を足しても arm は良くならない。
副産物: temperature 0 の logprobs は run 間で bit 単位に再現しない（argmax 一致 0.913、max |ΔP(段 3)| 0.262）— 閾値の近傍と ratchet の線は
noise floor を測ってから置く。判断役の提案: 定義は identity のみを維持（データが axioms の追加を要求しない）、enforce の GO は Next action 1〜2 へ。
**定義の最終判断はオーナー**。

enforce の事前値: RFC-0045 の行データ（S28 worktree の `.notes/relevance-arm-replay/`）は判断役が検収後に worktree を削除した際に消えた（gitignored、snapshot 無し — 判断役の手順ミス、2026-09-25。凍結 JSON は集計のみ。J の全行採点 `jev/rows.jsonl` と split は RFC-0040 の holdout 作業で残っている）。閾値は本番分布で置く — 本番 shadow 行を post_id で dedupe して 150 に達したら層化 150 行を opus でラベル（≈ $19〜24、`.notes/labels/relevance/`、main tree。**ラベルの state は定義の決定後**、manifest に pin。identity の adopt で失効 → 再ラベルか ack）。

## Next action

0. ~~梯子の読み~~ 済（S31、2026-09-26、Status）。**オーナーの定義判断待ち**（判断役の提案: identity のみを維持）。identity + axioms を採るなら `core/relevance_state.py` の domain 文の出所を変える follow-up と shadow 行の読み直しが要る
1. answered 行が post_id dedupe で 150 に達したら（2026-09-26 時点 55、約 85 行/日）定義に従う state で opus ラベル（$ はオーナー承認）→ P(top) の precision / recall を t ごとに出し、t をここに書く（読みの前に固定）。同じ集合を 2 回採点して **run 間の AUC 差を noise floor** とし、`score --baseline` の 0.02 線と閾値の近傍の扱いをその外に置く（S31 の再現性の読み）
2. plist に `DECISION_ENFORCE=relevance` を足し、`config/domain.json` に `relevance_score4` を置く（人間ゲート）。再開条件: **paired 300 行（60〜105 行/日、切替から 3〜5 日）**。照合先: `scripts/relevance_shadow_reading.py --since <切替時刻> --n 300`。成立時: face gate で keep（旧呼び出しを落とす PR、150 行ラベルを lab ratchet として凍結）か kill（env 除去、理由 1 行）
