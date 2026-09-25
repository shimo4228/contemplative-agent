# ADR-0113: 判断の面（decision faces）と、relevance gate の横に置く 4 段 Score の shadow

## Status

accepted

## Date

2026-09-25

## Context

relevance gate は feed の各投稿を agent の domain に照らして採点し、0.82 で切る（既知の作者は 0.65、upvote のみは 0.70）。回数は週約 736 回（[RFC-0045](../../rfcs/0045-relevance-judgment-jev-proximity-replay.md)）。今は gemma4:e4b が temperature 1.0 で 0〜1 の数字を書く（`score_relevance_detailed`、`config/prompts/relevance.md`）。

RFC-0045 は記録済みの 2,698 投稿を offline で再生した（[docs/evidence/rfc-0045/](../evidence/rfc-0045/README.md)、凍結した要約は `relevance-arm-replay-20260925.json`）。分かったことは 3 つ:

- 上の帯が甘い。0.82 以上と記録された 1,042 投稿のうち、489 投稿（46.9%）を Jev は domain 外とした。順位づけ自体は単調
- temperature 0 は効かない。arm A0 − arm A の平均は +0.015 [+0.003, +0.027]
- 同じ gemma に 4 段 Score を問うと順位づけがはるかに良い。段は `unrelated` / `shares vocabulary only` / `same field` / `directly on-topic` で、ADR-0112 の `OllamaLogprobsDecisionBackend` を通して先頭 token の logprobs として読む（arm `C/logits/score4`）。Jev の on-topic ラベルに対する AUC は dev 150 行で 0.944 [0.903, 0.978]、holdout 2,548 行で 0.917。本番の自由生成 arm は同じ holdout で 0.821。Score の読みは決定的で、latency は prompt cache 無しで中央値 2.9 秒

[ADR-0112](./0112-decision-backend-seam-and-shadow-skill-decision.ja.md) は seam を作ったが、配線した面は 1 つだけ（shadow の skill selection）。kill switch は設定不在で、`DECISION_MODEL` が未設定なら何も呼ばれない。この switch だけでは、skill selection の shadow も一緒に点けずに relevance だけ backend を点けることができない。オーナーは 2026-09-22、ローカル候補が無いことを理由にその shadow を取り下げた（[RFC-0040](../../rfcs/0040-jev-system-one-local-decision-backend.md) の status 注記）。

また gate には自分自身の再生可能な記録が一度も無かった。live のスコアは INFO のログ行にしか残らない。ADR-0075 は本番のすべての判断に再生可能な記録を求めている。

[RFC-0046](../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md)（オーナー GO 2026-09-25）が求めるのは shadow の段だけ。enforce は別の GO が要る。

## Decision

1. **decision seam に判断の面を足す。** ADR-0112 Decision 2 の kill switch を狭める。`core.llm.configure` は `decision_faces` を取る。値は `DECISION_FACES_KNOWN` =（`skill_selection`, `relevance`）の名前の集合。既定は `{skill_selection}` で、ADR-0112 の挙動のまま。`reset_llm_config` は既定に戻し、`decision_face_enabled(face)` が問いに答える。集合に無い面の呼び出し側は `decide` を呼ばずに `decision_reason: "unconfigured"` を記録する。CLI は `DECISION_MODEL` があるときだけ env `DECISION_FACES`（カンマ区切り）を読む:
   - 未設定なら既定
   - 空文字なら全部の面を止める
   - 未知の名前は起動時に WARNING を 1 行出して捨てる

   `core.skill_selection._shadow_decision` は問う前に自分の面を確かめる。
2. **live の relevance 判断を記録する**: 書き先は `logs/relevance-{UTC 日付}.jsonl`。書き手は `adapters/moltbook/relevance_shadow.py::observe_relevance_recorded` で、`feed_manager._judge_post` の `score_relevance_detailed` の直後で呼ぶ。RFC-0032 の memo は *settled* な判断しか残さない（preview への fallback や空の note は次の cycle で採点し直す）。そこで `FeedManager` が session ごとの集合を持つ。読みが `scored` になった投稿は、1 session に最大 1 行。失敗した読み（outage の 0.0、読めない答え）はそれぞれ別の事象として 1 行ずつ残る。行が持つ欄:
   - 刻印される `run_id` / `session_id`
   - live の半分: `post_id`、`author_known`、`live_score`、`live_reason`、`threshold_applied`、`live_gate`。`live_gate` は comment gate（`live_score ≥ threshold_applied`）。0.70 の upvote のみの線は gate として記録しないが、`live_score` から出せる
   - 投稿: `b64_audit_fields` による `content_*`（上限 8 KiB）。submolt-scope と同じ形で、平文は無い
   - 判断の半分: `decision_backend`、`decision_model`、`decision_reason`、`decision_p`（4 段の確率、低い段から）、`decision_p_top`（P(directly on-topic)）、`decision_expected_level`（0〜3 の尺度）、`decision_latency_ms`

   行は backend の有無によらず書く。backend が無ければ判断の欄はすべて null、理由は `unconfigured`。記録器自身の kill switch は `audit_dir` の未設定で、CLI は設定一式を読むすべての run でこれを設定する。
3. **shadow は arm C が問うたものを、1 つの所有者から問う。** `core/relevance_state.py` が state と問いを持つ。state は `{"domain": identity.md, "post": wrap_untrusted_content(post, max_input=1000)}` を indent 付き JSON にしたもので、system prompt は空。問いは `config/prompts/relevance_score4.md` から parse する（ADR-0054）。domain は `core.llm.get_identity_text` を通した identity.md だけで、axioms は含めない。`scripts/relevance_arm_replay.py` も同じ module を import し、同梱の prompt ファイルを読む。テストが文言を RFC-0045 の測定時の文と同一に固定する。arm C との違いが 1 つ残る。arm C が見たのは 500 字の submolt preview だけだが、following feed の投稿は全文で届く。そのため、それらについて shadow は枠の上限 1,000 字まで送る。
4. **観測だけ。** hook は `None` を返す。live のスコア・閾値・gate は決まった値として渡される。問いを組み立てる・問う途中の例外は、行の中で `backend_exception` になる。書き込みの失敗は WARNING 1 行。どちらも gate には届かない。`submolt_scope` には掛けない。あれは read-only の計器で、掛ければ GPU 代が倍になる。
5. **登録して読む。** census に series `relevance-` を足す（enum は `live_reason`、`decision_reason`、`live_gate`、数値は `decision_latency_ms`）。`scripts/relevance_shadow_reading.py` は stdlib だけ・read-only で、各行を parse の時点で射影する。報告する値:
   - 行のうち本物の（`scored`）判断がいくつか。以下の率はその行だけで出すので、outage の 0.0 は「no」として数えない
   - answered 率と live gate 率
   - t ∈ {0.3, 0.5, 0.7} ごとに、`decision_p_top ≥ t` での would-be gate 率と、`live_gate` との一致率（answered 行で）
   - latency の p50 / p95
   - 同じものを ISO 週ごと

   要約 6 行のあとに JSON を出す。

### enforce の事前値（offline）

| P(directly on-topic) の切り t | opus の on-topic に対する precision | opus の on-topic に対する recall |
|---|---|---|
| 0.3 | 未計算 | 未計算 |
| 0.5 | 未計算 | 未計算 |
| 0.7 | 未計算 | 未計算 |
| 自由生成で答える rubric（同じ prompt、1 文字、logprobs なし）— opus に対する AUC | 未計算 | — |

最後の行は dispatch packet が足した任意の arm。4 段の rubric が効いた分と、logprobs で読むことが効いた分を切り分ける: 同じ prompt に temperature 0 で 1 文字を生成させて答えさせ、AUC を arm C と並べる。

これらの数には RFC-0045 の行単位のファイルが要る（dev 行について、arm C の P(top) と 2 回の opus ラベルの組）。そのファイルは S28 の worktree の gitignored なメモにしか残しておらず、本 ADR を書いた時点ではどの checkout にも存在しなかった。凍結した要約 JSON には集計しか無い。enforce の ADR は、まず事前値を計算しなければならない。方法は、opus に判定させた shadow の行か、再導出した dev split で arm C と E を再実行するか。split は再導出できる（scan ログと seed 20260925 の純関数）。arm E の再実行はタダではない。RFC-0045 の opus 300 回は API 換算で $37.73 だった（evidence README）。

## Review-when

> **注記（2026-09-26、[RFC-0047](../../rfcs/0047-face-eval-loop.md)）**: 下の時計と順序を置き換える（原文は経緯として残す）。**問い**（事前登録）: 本番分布で would-be gate 率が offline の予測 ±6 pt に収まるか、latency p95 が cycle の待ちに乗らないか、answered 率が落ちないか。**n = 300** answered 行（二項の 95% CI 半幅 ≈ 1/√n = ±5.7 pt）を切替時点から数える。到達率は読みのたびに実測し、予定日を幅で書く（`scripts/relevance_shadow_reading.py --since … --n 300` の `readiness` 節）。到達日に **face gate** を開く — 曜日不問、土曜の weekly-gate とは別（weekly-gate は値層専用のまま）— そして [RFC-0046](../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md) の Status に keep / kill / continue の 1 語を書く。**stuck**: 14 日で n に届かなければ延長せず決める（retire か問いを小さく）。**順序**: relevance 面は Tier L（誤りの向きが縮小側 — 2026-09-26 の読みで would-be 0.22〜0.39 対 live 0.58）なので **enforce-first + paired**: 閾値 `relevance_threshold_score4` を切替の前に凍結 opus ラベルで置き、gate を P(directly on-topic) で切りながら、自由生成の score も毎回問い同じ行に記録する（`gate_source` / `enforce_gate` / `enforce_reason` / `enforce_threshold`）。旧呼び出しを落とすのは face gate で keep になってから。**kill switch**: `DECISION_ENFORCE` 不在（次のセッションから live gate に戻る）。**ラベル集合の失効**: ラベルは `identity.md`・prompt・model を sha で pin する（`scripts/relevance_label_set.py check`）。pin した identity が adopt で置き換わり、オーナーが再ラベルしないと決めた時に失効する。

- **enforce か retire かの読み。** 土曜の読みを 4 回重ねたとき、または累計の `answered` 行が 1,000 を超えたときの早い方で期日になる。時計は、オーナーが scheduled session の環境に `DECISION_MODEL=gemma4:e4b DECISION_FACES=relevance` を置いた後の最初の土曜に始まる。この launchd の変更は人間ゲート。読みで比べるもの:
  - would-be gate 率と live gate 率
  - latency p95 と cycle の待ち時間
  - answered 率

  オーナーが enforce（別 ADR: `RelevanceScore.score` を P(top) に、`reason: "score4"`、閾値は別の `relevance_threshold_score4`）か retire を決める。閾値はこれらの読みの後に置き、前には置かない。
- **土曜 8 回で answered 1,000 行に届かない**なら、静かな計器。1 commit で判断の半分を消す: `decision_*` 欄、`relevance` の面、census の `decision_reason` enum、読み値 script。書き手は残り、ADR-0075 の記録として `live_*` と `content_*` の欄を書き続ける。
- **本番の生成モデルが gemma4:e4b でなくなる。** AUC 0.944 は gemma で測った値なので、shadow から読み直す。
- `config/prompts/relevance.md` か閾値（0.82 / 0.65 / 0.70）が変わる、または ADR-0112 の `ScoreQuestion` / `OllamaLogprobsDecisionBackend` が変わる: shadow の比べ方が動いた。

### Consumption plan

> **注記（2026-09-26、[RFC-0047](../../rfcs/0047-face-eval-loop.md)）**: (a) 判断役（オーナーか judge-tier セッション）が `relevance_shadow_reading.py` を曜日不問で走らせて読み、n = 300 の到達日に face gate を開く。(b) 問いと n は Review-when の注記のとおり。決めるのは keep（旧呼び出しを落とし、150 行のラベル集合を lab ratchet として凍結）か kill（`DECISION_ENFORCE` を外し、理由を 1 行）。(c) stuck 14 日 → 1 commit で retire（hook の判断の半分・env・census の enum。`live_*` 欄は ADR-0075 の記録として残る）。ラベル集合は pin した identity とともに失効する。下の「土曜 4 回 / 1,000 行 / 土曜 8 回」の時計は置き換えた。

- (a) 土曜の weekly-gate が `relevance_shadow_reading.py` の出力を読む。
- (b) 4 回の読みの後、または累計 answered 行が 1,000 を超えた時点で、enforce（閾値を確定して gate を差し替える）か retire を決める。判断材料は would-be gate 率と live gate 率の差、latency p95 が 1 cycle に足す時間、answered 率。閾値は読みの後に置く。
- (c) enforce の ADR が着地したら、shadow の欄は本番の記録になり、ログは残る。土曜 8 回で answered 1,000 行に届かなければ、Review-when に書いたとおり判断の半分を 1 commit で消す。書き手は残る。

## Alternatives Considered

- **enforce を直接入れる。** 却下。gate の変更は行動への介入。本番の would-be gate 率と latency を見ずに閾値を置くと、RFC-0044 と同じ形になる（offline では成立、本番の代価は未測定）。
- **live の呼び出しを temperature 0 にする。** 却下。この面では効かないと実測済み（+0.015）。
- **live の閾値を上げる（0.82 → 0.9）。** 却下。記録値は離散なので、0.9 以上は実質同じ行。甘さは切りでなく生成の形にある。
- **ADR-0112 の switch だけを使う（`DECISION_MODEL` で全部の面が点く）。** 却下。skill selection の shadow は候補が無いので取り下げた。relevance を点けてもそれを戻してはならない。
- **backend があるときだけ行を書く。** 却下。live の半分は gate の最初の再生可能な記録（ADR-0075）で、判断の半分が null でも代価は無い。
- **markdown の `## Domain` / `## Post` の state。** 却下。arm C が測ったものではない。shadow が、自分を正当化した数字と同じものを読むために JSON の state を保つ。
- **domain に憲法の axioms を入れる。** 未決 — 再訪条件: enforce の前に A/B で確かめる。live の呼び出しは identity + axioms で走るが、arm C はそうではなかったため。

## Consequences

### Positive

- relevance gate が、shadow の有無にかかわらず再生可能な記録を得る。
- shadow は本番のモデルで走り、モデルの交代が無い（`exclusive=False`）。新しい依存も新しい外向き URL も無い。
- 面によって seam が足し算になる。後の面（submolt selection、post-gate）は、`DECISION_FACES_KNOWN` の 1 つの名前と、呼び出し箇所の 1 つの確認で済む。
- 再生と本番の shadow が state の組み立てと prompt ファイルを 1 つずつ共有するので、ずれようがない。

### Negative

- 面を点けると、記録される判断ごとに gemma の呼び出しが 1 回増える。週約 736 × 3 秒 ≈ 35 分の GPU に、失敗した読み 1 回につき 1 呼び出しが加わり、`decision_latency_ms` がその代価を測る。served と別の `DECISION_MODEL` にすると relevance の呼び出しのたびに gemma も降ろされる。文書にした構成は同じモデル。
- ログには他エージェントの投稿 preview が base64 で入る。submolt-scope と同じく平文の注入面ではないが、週約 736 行ずつ増える。
- shadow の間、gate の甘さは今のまま。
- enforce の事前値は未計算（上記）。

### Reversal cost

`relevance_shadow.py`、`core/relevance_state.py`、faces の引数、env の parse、hook、census の行、読み値 script、prompt ファイルを消す。再生スクリプトの文言はリテラルに戻る。書かれた行はデータとして残る。

### Neutral

- ADR-0112 の kill switch の意味は「モデル設定あり かつ 面が並んでいる」になった。既定の集合は、既存のどの構成の挙動も変えない。

## References

- [RFC-0046](../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md) — タスク
- [RFC-0045](../../rfcs/0045-relevance-judgment-jev-proximity-replay.md) と [docs/evidence/rfc-0045/](../evidence/rfc-0045/README.md) — 数字
- [ADR-0112](./0112-decision-backend-seam-and-shadow-skill-decision.ja.md) — seam（面が加わった）
- [ADR-0076](./0076-skill-selection-shadow-instrument.ja.md) — shadow の形
- [ADR-0075](./0075-observability-by-default.ja.md) — 記録の義務
- [ADR-0101](./0101-instrument-dissolution-mandate.ja.md) — 消費計画
- [ADR-0054](./0054-externalize-llm-instruction-text-to-prompts.ja.md) — prompt ファイル
- [ADR-0107](./0107-instrument-census-and-episode-log-folder.ja.md) — census
