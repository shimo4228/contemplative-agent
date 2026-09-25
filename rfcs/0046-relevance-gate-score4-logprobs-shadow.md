---
state: in_progress 2026-09-25
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

### 消費計画（ADR-0101、shadow）

(a) 土曜の weekly-gate が `relevance_shadow_reading.py` の出力を読む。(b) 4 読み、または answered 行が累計 1,000 を超えた時点で enforce（閾値を確定して差し替え）か retire を決める — 判断材料は would-be gate 率と live gate 率の差、latency の p95 が cycle に与える追加、answered 率。閾値は読みの後に置く。(c) enforce の ADR が着地したら shadow 欄は本番記録に格上げ（ログは残る）。8 土曜で 1,000 行に届かなければ hook・env・census の enum を 1 commit で消す（記録ログの `live_*` 欄だけは ADR-0075 の記録として残す）。

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

blocked 2026-09-25 — **shadow 段は main に入った**（S29、`5cf42b7`、ADR-0113）。hook / recorder（`logs/relevance-*.jsonl`）/
`DECISION_FACES`（既定 `skill_selection`）/ prompt の外出し / census / 読み値 script / ADR-0113 と ADR-0112 への注記。verify exit 0、
smoke で `decision_reason: answered`・4 段の p を確認。本番は `DECISION_MODEL` 未設定のままなので decide は呼ばれず、
変わるのは `relevance-*.jsonl` が常時書かれること（live 欄 + b64）だけ。

**enforce の事前値は未計算。** RFC-0045 の行データ（S28 worktree の `.notes/relevance-arm-replay/`）は、判断役が検収後に
worktree を削除した際に一緒に消えた（gitignored、snapshot 無し — 判断役の手順ミス、2026-09-25）。凍結 JSON は集計のみ。
再計算するなら opus 150 行 × 1 反復 ≈ $19 + gemma C 150 行。**ただし enforce の閾値は本番分布で置くべきなので、shadow の行
（feed の実投稿）から 150 行を opus でラベルする方が筋がよく、事前値の再計算はしない**（判断役の提案 — 採否はオーナー）。
7b（rubric と logprobs の分離 arm）も同じ理由で未計算。

## Next action

**shadow は本番 ON（2026-09-25 15:20 JST）**: agent plist テンプレートに `DECISION_MODEL=gemma4:e4b` / `DECISION_FACES=relevance` を
焼き込み（`04a8e0a`）、`install-schedule` を全フラグで再実行して live plist に反映。最初の記録は JST 18 時のセッションから。
ADR-0113 の clock は最初の土曜（2026-09-26）から。eval baseline の staleness 警告はオーナー判断で ack せず（advisory のまま）。
待つもの: 土曜 4 読み or answered 1,000 行。照合先: `scripts/relevance_shadow_reading.py`。成立時: enforce（閾値は shadow 行 150 件の
opus ラベル ≈ $19）か retire。
