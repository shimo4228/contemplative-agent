# Plan: DecisionBackend — gemma の判定コールをローカル判断モデルへ移す土台

## Context

Contemplative Agent は「判定だけ」の LLM コール（skill 選択 / relevance / submolt 選択 / distill postgate / insight novelty / insight duplicate）も gemma4:e4b に文章生成でやらせている。Jev（hosted）で skill 選択を再生した実験（Zenn 記事 2026-09-21）は opus との Jaccard 0.346・1 件 0.3 秒・幻覚 0 で、gemma の 0.14〜0.16 の 2 倍以上だった。Jev 本体はクローズド API のまま（2026-09-22 照合）だが、ローカルで動く同型モデル（kev / von / Laya / SemIf 系、30 本超、ほぼ全部 9/15 以降）が出た。オーナーの方針: **判定コールを DecisionBackend として抽象化し、gemma が判定している面をローカル判断モデルへ置き換えていく**。

決めた前提（本会話、2026-09-22）:

- **2 モデルを同時に常駐させない**（16 GB M1。GLiClass 同居で swap 17 GB の先例。対話中は gemma 無しでも swap 5〜6 GB）。機構は「交代」（Ollama `keep_alive: 0` で明示的に降ろす。gemma 再ロード実測 約 7 秒）と、後段の「段分け」（cycle 内で判定を全部→交代→生成を全部）
- Ollama は 0.34.2、`OLLAMA_MAX_LOADED_MODELS` 未設定 → 既定は「収まれば同時ロード」なので、**判定バッチの前に生成モデルを明示的に降ろす**のがコード側の必須動作（Ollama の eviction に頼らない）
- ローカル Jev 類似は Ollama では動かない（custom head）。**wheel の既定実装は Ollama logprobs 読み**（依存追加ゼロ、ADR-0109 の床を動かさない）。torch 系（kev / Laya）は sibling repo から `configure(decision_backend=...)` で注入（`-cloud` と同型）
- 最初の 1 面は **skill_selection**（150 行 harness・opus 参照ラベル・幻覚計器が揃っている）。shadow mode（ADR-0076 型）で入れる
- 実測（9 月ログ 1,075 行）: prompt 約 3,000 token（catalog 約 2,400 + situation p50 約 400 / max 約 1,800）。situation は英語（CJK 比 p90 = 0）— **日本語分割読みは不要**
- Laya は作者投稿 + model card で確認: backbone は RoPE で native 8,192、`max_len` / `head_max_len` は実行時に上げられる。ただし「学習長を超えると較正が落ちる」と card 自身が書く。choice は選択肢が `head_max_len` を分け合うので 55 件は要調整

実行者（オーナー決定 2026-09-22）: **コードは build-tier へ dispatch**。この Fable セッションは RFC-0040 追補・ADR 草稿・packet を書き、検収側に残る。

## 北極星との照合

機構層は「修理のみ」だが、これはオーナーが明示した能力方針（判定の分離）。RFC-0040 の「将来像」（用途別 decision / generation model + 薄い harness）の最初の実装段。shadow で入れ、enforcement は読みの後に別 ADR。

## Stage 0 — 台帳と設計文書（このセッション、種別 writing）

1. `python3 ~/.claude/scripts/claims.py claim RFC-0040 --label "DecisionBackend seam + round-3 arms"`
2. **RFC-0040 追補** [rfcs/0040-jev-system-one-local-decision-backend.md](../../rfcs/0040-jev-system-one-local-decision-backend.md) — 現行本文（着手条件 / 比較表 / 蒸留実験案 / MCA 制約 / RFC-0043 帰結）は残し、上書きせず追記:
   - frontmatter `state: blocked` → `state: accepted 2026-09-22`（`state_since` 更新）。`review-when` に「Jev 本体の open weights 公開（本体候補の再評価）/ Ollama が custom-head モデルを載せる（sibling 不要になる）」
   - 「着手条件」節に日付つき注記: Jev 本体待ちは解除。着手条件を「ローカル判断モデルの CA データでの読み（第 3 ラウンド）」に置き換える
   - 新節「設計の前提（2026-09-22）」: 同時起動しない（交代 → 段分け）/ 既定実装は Ollama logprobs / torch 系は sibling / 最初の面 skill_selection / DecisionBackend の 3 型（noul / choice / score、確率を返し閾値は code 側）
   - 比較表に kev / von / Laya / SemIf / open-alternative-jev を追記（2026-09-22 照合、系 A/B/C の 3 軸）。Laya の RoPE 注記
   - 「第 3 ラウンド（RFC-0043 evidence 側に置く）」の測定順と読み方（下 Stage 1 §読み）
   - ADR-0101 消費計画（shadow 計器）: (a) 読み手 = 土曜 weekly-gate、`skill-selection` 計器の DecisionReading (b) 週次 4 読み・answered 行 ≥ 200 で enforce / retire を決める。閾値は読みの後に置く（measurement-discipline） (c) 撤去 = enforcement ADR が着地して欄と hook を消す、または 4 読みで採らないと決めた commit で同時に消す
   - Status / Next action 更新
3. **ADR-0112 草稿**（skill: `adr-writer` の手順、adr-reviewer を通す）: "Decision backend seam; shadow decision on skill selection"。Stage 2 の設計を本文に。commit は Stage 2 のコードと同じ diff で build セッションが行う（鮮度規約）。`docs/adr/README.md` + `.ja.md`、`graph.jsonld` ノード
4. packet 2 本を `.notes/packets/` に書く（下の Stage 1 / Stage 2 がそのまま本文）。dispatch は `Agent(subagent_type: general-purpose, model: opus, isolation: worktree)`、Review 群も同じ build-tier 内で `/code-review medium`

## Stage 1 — 測定 arm 3 本（dispatch packet A、種別 prototype: 本番外の一発測定 script）

対象: [scripts/skillsel_arm_replay.py](../../scripts/skillsel_arm_replay.py)、[tests/test_skillsel_arm_replay.py](../../tests/test_skillsel_arm_replay.py)、[pyproject.toml](../../pyproject.toml) `replay` group、[docs/evidence/rfc-0043/README.md](../../docs/evidence/rfc-0043/README.md)

harness の制約（既存テストが pin）: subprocess 禁止（AST テスト `tests/test_skillsel_arm_replay.py:575-597`）→ kev はオペレータ起動の server に HTTP、`requests` の全 call site は `validate_trusted_url` を通し pin 集合 `:663-680` に追加。行ログに本文を書かない（`:56-66`）。1 家族 1 `--augment` 呼び出しで直列化（`run_row` は行内で arm を回すので、複数モデルを同時に足すと同居する）。

`ARMS` `:116` に `H, K, L`、`ARM_LABELS` `:130-153`:

| label | 中身 |
|---|---|
| `H/logits` | arm C `run_logits` `:1146` を `model=` / `num_ctx=` で parametrize（`_get_model()` 置換）。`--decision-model qwen3.5:9b --decision-num-ctx 8192`。`ollama_yes_no` `:1089` が `ollama_counters` `:965` も返し、行ごとに `prompt_eval_first / prompt_eval_median / prefix_reuse` を meta に。`--require-prefix-cache` で 1 行目後に reuse が無ければ `prefix_cache_absent` で中断（無いと 55 × 20 秒 = 18 分/行） |
| `H/logits/onepass` | arm F `run_logits_onepass` `:1299` をモデル差し替え。top-20 打ち切りは F と同じ記録 |
| `H/logits/twostage` | `H/logits` の上位 20 を shortlist → 20 件の sub-catalog で onepass（A–T）。`scores` = 観測ラベルの softmax、`scored_of=(observed, catalog)`。`_arm_plan` `:2784` で closure 共有（`order=order` `:2811` と同型） |
| `K/choice`, `K/noul` | 1 行 1 `POST /v1/systemone`（`--kev-endpoint http://127.0.0.1:8009`）。state は **文字列**（kev の `with_date_facts(req.state)`）、choice の criteria = 全 skill 説明 + "none of the above"、noul は skill ごと（文言は `_LOGIT_QUESTION` `:1078` と揃える）。meta: 応答の `model`、`usage.input_tokens`、`prefix_cache_hit`、`p_none`、`latency_shared=true`。422 → `kev_state_too_long`（silent truncation 禁止）。kev は state ≤ 384 token で学習・8,192 で serve なので `input_tokens` が学習域外の読み。`main` で 1 noul の preflight |
| `L/noul` | in-process、arm D `:1469-1547` と同型（optional import → `laya_not_installed`、module-level cache）。checkpoint 既定 `convaiinnovations/laya-typed-decisions`（英語 situation に合わせる。`--laya-checkpoint` で multilingual も可）。既定 `max_len 1024`（分布内）、situation は head を残し tail を切る（`truncate_state`、`--laya-margin 64`）。meta: `state_tokens_total / kept / coverage / truncated` |
| `L/choice/ext` | 同じ agent で `agent.cfg["max_len"]` を 8192、`head_max_len` を選択肢数 × 約 50 に上げ、catalog 丸ごと choice（分布外）。`--laya-ext-max-len` / `--laya-ext-head-max-len`。meta に cfg 値 |

依存: `replay` group に `laya`（pin は導入時の最新、torch / transformers を引く。コメントを「arms D と L」に更新）。kev は git-only・Python ≥ 3.12 なので project 外: `uv run --no-project --with "kev[serve] @ git+https://github.com/jaredpalmer/kev@<sha>" python -m kev.serve --run jaredpalmer/kev-0.8b --port 8009`（sha を evidence README に記録）。HF は事前 `hf download` → 計測は `HF_HUB_OFFLINE=1`。

メモリ規律: K / L の前に `ensure_ollama_idle`（`/api/ps` → 常駐モデルへ `{"model": m, "keep_alive": 0}` → 空になるまで ≤ 60 秒 poll → `resource_snapshot` `:1700`）。H は Ollama が gemma を降ろして qwen を載せる（同居はしない: 6.6 + 3.4 GB は Ollama の判定で収まる可能性があるので、H の前にも `ensure_ollama_idle` を通す）。`wait_out_schedule` は既存どおり。

新規 pure 関数（テスト対象）: `shortlist`, `kev_request`, `kev_scores`, `laya_questions`, `truncate_state`, `ensure_ollama_idle`。テスト: `TestArmH / TestKev / TestLaya / TestOllamaIdle`（`responses` は dev group に既にある）、`TestCli` 既定値、AST テストは緑のまま。

`summarize` `:2338` は label を自動検出。追加は `_paired_differences` `:2431` を `_collapsed_set(…, "topk")` にも通し、対を `H/logits − C/logits`、`K/choice − K/noul`、`K/* − L/*`、`K/choice − C/logits` と名付ける。CJK 分割は入れない（データが英語）。

**読み（オーナーが予約した判定規則、数値 cap でなく読み）**: H − C の対差（Jaccard@topk / AUC）の CI が 0 をまたぎ ECE の形が C と同じなら、系 A（凍結 LLM の logits）は捨てる。K vs L は同じ軸で frontier 帯（opus 自己一致 0.678、sonnet 0.44〜0.48）に対して読み、系 B の候補を決める。本番配線に値するのは、p ≥ 0.5 集合がほぼ全部 opus も選んでいて（記事の 1 位 100% 域）、Jaccard@topk の CI が gemma 帯 0.14〜0.16 を明らかに上回るとき。150 行 1 回は 1 読み — RFC 起票前に別 seed / 別窓で 2 回目を引く。

実行（オーナー / 検収セッションが直列に、JST 0/6/12/18 を避けて）:

```bash
uv run --no-sync python scripts/skillsel_arm_replay.py --augment .notes/skillsel-arm-replay/round2/rows.jsonl --arms H --decision-model qwen3.5:9b --decision-num-ctx 8192 --require-prefix-cache --latency-arms H --out-rows .notes/skillsel-arm-replay/round3/h/rows.jsonl --out-summary .notes/skillsel-arm-replay/round3/h/summary.json --out-aux .notes/skillsel-arm-replay/round3/h/aux.jsonl
```

```bash
uv run --group replay python scripts/skillsel_arm_replay.py --augment .notes/skillsel-arm-replay/round3/h/rows.jsonl --arms K --kev-endpoint http://127.0.0.1:8009 --latency-arms K --out-rows .notes/skillsel-arm-replay/round3/k/rows.jsonl --out-summary .notes/skillsel-arm-replay/round3/k/summary.json
```

```bash
HF_HUB_OFFLINE=1 uv run --group replay python scripts/skillsel_arm_replay.py --augment .notes/skillsel-arm-replay/round3/k/rows.jsonl --arms L --laya-device mps --latency-arms L --out-rows .notes/skillsel-arm-replay/round3/l/rows.jsonl --out-summary .notes/skillsel-arm-replay/round3/l/summary.json
```

概算: H 3〜4 時間（prefix reuse が効く場合）、K ≤ 1 時間、L 10 分〜2 時間。凍結は `docs/evidence/rfc-0043/skillsel-arm-replay-round3-<date>.json` + README「第 3 ラウンド」節（実行条件 / 足した arm / 読み / 測らなかったこと: kev-4b/9b、kev の学習域外 state 長）。

## Stage 2 — DecisionBackend seam + shadow on skill selection（dispatch packet B、種別 feat）

Stage 1 の結果に依存しない（Protocol の形は候補が何でも同じ）。TDD は C=Y（境界: top-20 超過 / logprobs 欠落 / keep_alive の送出条件 / unconfigured）。Security Review は不要（I/O 面は Ollama localhost の既存 allowlist のみ。ADR に「`keep_alive: 0` が共有 Ollama daemon からモデルを追い出す」副作用を 1 行）。

### 2a. `src/contemplative_agent/core/llm/decision.py`（新規、`core/llm/__init__.py:35-69` から再 export）

全部 `frozen=True`、tuple で持つ（`tests/test_frozen_dataclasses.py`）:

- `NoulQuestion(id, instructions)` / `ChoiceQuestion(id, instructions, options)` / `ScoreQuestion(id, instructions, levels)`；`DecisionQuestion` = Union
- `QuestionAnswer(id, probabilities: tuple[tuple[str, float], ...], reason, observed, truncated)`、`expected_level()`（score）。noul は `(("yes", p), ("no", 1-p))`
- `DecisionResult(model, latency_ms, answers, reason)`；`DecisionRequest(state, questions, caller)`（`request.py:29-65` の `GenerationRequest` と同型）
- 閉じた reason 語彙 `DECISION_REASONS = ("answered", "unconfigured", "circuit_open", "http_error", "bad_json", "logprobs_unavailable", "no_option_observed", "label_alphabet_exceeded", "backend_exception")`（ADR-0075）
- `@runtime_checkable class DecisionBackend(Protocol)`: `model -> str`、`decide(self, state: str, questions: tuple[DecisionQuestion, ...]) -> DecisionResult | None`
- core wrapper `decide(state, questions, *, caller)`: `_decision_backend is None` → `None`（kill switch = 設定不在）。`_circuit.is_open` を読むだけ（`record_*` は呼ばないので `circuit_shield` 不要）。例外 → `backend_exception`。`emit_llm_telemetry` `__init__.py:319-342` に 1 行（`kind: "decision"`, `caller`, `model`, `duration_ms`, `outcome`, `question_count`, `prompt_chars`, `prompt_norm_sha256`, `num_predict: 1`, `temperature: 0.0`, `decision_reason`）— census の `llm-calls-*.jsonl` 行 `_census_registry.py:116` が caller 別に拾う

注入: `configure(..., decision_backend: DecisionBackend | None = None)` `__init__.py:145-186`、global `_decision_backend`、`reset_llm_config()` `:189-197` で消す。**既定は None = 無効**（default-on にすると全 CLI 経路に 57 コール/生成が付き、設定不在が kill switch でなくなる）。配線は `cli/runtime.py:_configure_llm_and_domain` `:118-128` で、env `DECISION_MODEL` があるときだけ `OllamaLogprobsDecisionBackend(model=..., exclusive=(model != served_model()))` を作る。`DECISION_MODEL=gemma4:e4b` = 交代ゼロの「読み出しだけ」— shadow 第 1 週の設定。

### 2b. `OllamaLogprobsDecisionBackend`（同 module、frozen: `model`, `base_url=None`, `exclusive=False`, `timeout=(30, 300)`）

harness から**移して**（複製せず）import に切り替える: `_YES_TOKENS / _NO_TOKENS` `scripts/skillsel_arm_replay.py:1075-1076`、`binary_softmax` `:466-484`、`LABEL_ALPHABET / label_alphabet` `:528-544`、payload 形 `:1405-1429`。

- payload: `{"model", "prompt", "system", "stream": False, "think": False, "options": {"temperature": 0, "num_predict": 1, "num_ctx": NUM_CTX}, "logprobs": True, "top_logprobs": min(20, needed)}`。URL は `validate_trusted_url` `core/llm/guard.py:41`。**`num_ctx` を必ず送る**（Ollama 既定 2,048 の silent truncate を避ける — テストで pin）
- noul: `state + "\n\n## Question\n\n{instructions}\nAnswer with exactly one word: yes or no."`、first token の top_logprobs から yes/no 対 → `binary_softmax`。どちらも無ければ `no_option_observed`（0.5 を読まない）
- choice ≤ 20 / score ≤ 20 levels: 1 コール、ラベル A–T、観測ラベルだけで softmax、未観測は 0.0 + `truncated=True, observed=n`
- choice > 20: `label_alphabet_exceeded` で abstain。backend 内で noul に分解しない（choice は分布を約束する。分解と正規化は呼び出し側 = code 側の見える判断）。skill_selection 面は最初から **catalog 分の noul**（multi-label なので自然。AUC 0.728 の evidence と同じ問い方）
- 順序: `state` を prefix、question を suffix、`system` 固定、`num_ctx` 固定 → Ollama の KV prefix cache が効き、noul 1 問あたり約 40 token の追加処理
- **交代（`exclusive=True` のとき）**: バッチ前に `POST /api/generate {"model": served_model(), "keep_alive": 0}` で生成モデルを降ろし、バッチ最後のコールに `"keep_alive": 0` を付けて判定モデルを降ろす。gemma は次の生成コールで暗黙に再ロード（約 7 秒）。判定モデル = 生成モデルのときは一切送らない。`_post_ollama` `:720-778` は触らない（backend が自前で POST、`_circuit` に触れない）

### 2c. Shadow hook（skill_selection）

呼び出し位置: `observe_skill_selection_recorded` `core/skill_selection.py:575-684` の `result = select_applicable_skills(...)` `:653` の直後、judged レコード書き込み `:658` の前（`selection_id` / `catalog` / degrade-never-abort の try がある場所）。`select_applicable_skills` は触らない。新 `_shadow_decision(situation, catalog, live) -> dict`: catalog 1 件 = `NoulQuestion(id=name, instructions=_LOGIT_QUESTION の本文)`、`decide(..., caller="core.skill_selection.decision")`、`result.selected` には触れない（`-> dict` で選択を返さない）。

記録は**既存レコードの拡張**（RFC-0044 の `temperature` と同じ手。同じ行で `selected` と比べられる）: `decision_backend`（class 名）, `decision_model`, `decision_latency_ms`, `decision_reason`, `decision_p`（{name: p}、catalog 正準名、未観測は省く）, `decision_topk`（live の `selected_count` 件を p 順に — code 側の件数規則を記録時に焼く）。未設定時は全部 `null` + `decision_reason="unconfigured"`。`scripts/_census_registry.py:156-158` の `enum_fields` に `decision_reason`。

段分け（enforcement 用の (ii)）は本 stage に入れない: shadow は (i) backend 内交代で十分（gemma 判定なら 0 回、qwen なら selection バッチごとに 2 回 ≈ 10 秒。`decision_latency_ms` と次の生成行の `duration_ms` が交代費用を露出する）。(ii) は enforcement ADR で `feed_manager._judge_post` `:292-368` / `reply_handler` / `post_pipeline._run_dynamic_post` `:154` を判定ループと生成ループに割る変更として、relevance の `score` 化と一緒にやる。

### 2d. 適合キット `src/contemplative_agent/testing/decision_contract.py`

`backend_contract.py:173-222` を写す: `DECISION_BACKEND_MEMBERS = ("model", "decide")`、`inspect.signature(DecisionBackend.decide)` から正準呼び出しを導出（placeholder `{"state": "state", "questions": (NoulQuestion(...),)}`）、`check_decision_backend(backend) -> ConformanceReport`（`CheckResult / ConformanceReport` 再利用）、`__main__` に `--decision pkg.mod:Name`、`KIT_VERSION` を上げる。import-linter の forbidden contract `pyproject.toml:162-179`（testing は core だけ import）を守る。

### 2e. テスト

- `tests/test_decision_backend.py`（`responses`）: payload に `logprobs / top_logprobs ≤ 20 / num_predict 1 / temperature 0 / num_ctx` を pin、19 選択肢で top_logprobs が 20 を超えない、`exclusive` のとき前後の `keep_alive: 0`、同一モデルなら keep_alive 不送出、21 選択肢は HTTP なしで abstain、観測ラベル softmax と truncated、yes/no 表層読み、logprobs 欠落 → `logprobs_unavailable`、HTTP 400 → `http_error`、untrusted URL 拒否、unconfigured → None で POST なし、open circuit を尊重しカウンタ不変（`circuit_reading`）、telemetry 行の形、harness が出荷 helper を import する（`tests/test_jev_arm.py:41-54` の file-path load 方式）
- `tests/test_decision_contract.py`: member list が Protocol と一致、Ollama backend が適合、古い `decide` signature が bind 検査で落ちる
- `tests/test_skill_selection.py`: unconfigured で欄が null、p / topk / reason / latency が記録される、decision 失敗で `selected` 不変、catalog 1 件 1 noul、topk 件数 = live 件数
- 緑のまま: `test_frozen_dataclasses.py`, `test_architecture.py`, `test_dependency_floor.py`, `test_cloud_egress_absence.py`, `test_instrument_census.py`（enum 追加後）

### 2f. Doc sync（同じ diff）

ADR-0112（Stage 0 の草稿を着地）、`docs/adr/README.md` + `.ja.md`、`graph.jsonld`、`docs/CONFIGURATION.md` + `.ja.md` の env 表に `DECISION_MODEL`（未設定 = off）、`docs/otel-semconv-mapping.md:13` に `kind / decision_reason`、`scripts/skillsel_arm_replay.py` 冒頭コメント（helper を core から import）、CLAUDE.md の適合キット行に `--decision`。

## Stage 3（本 plan 外、ポインタのみ）

第 3 ラウンドの読み + shadow 4 週の読みの後: enforcement ADR（段分け (ii)、relevance を `score` 化、`decision_topk` を注入に使う）、sibling repo `contemplative-agent-decision-<model>`（kev / Laya を `configure(decision_backend=...)` で注入、`-cloud` と同型）、残り 4 面（submolt / postgate / novelty / duplicate）の順次移行。

## Verification

- Stage 1: `uv run pytest tests/test_skillsel_arm_replay.py -q`、`uv run ruff check scripts/ tests/`、`.claude/verify.sh`。実測 3 本は上のコマンドを直列に（各 arm 前に `ollama ps` が空であることを確認）。summary を `--summarize-only` で再集計して label が 6 本出ること
- Stage 2: `.claude/verify.sh`（tests / pyright / ruff / import-linter / dependency floor / secret scan）、`uv run lint-imports`、`python -m contemplative_agent.testing --decision contemplative_agent.core.llm.decision:OllamaLogprobsDecisionBackend`。手動 smoke: `DECISION_MODEL=gemma4:e4b` で `python -c` から `decide()` を localhost Ollama に 1 回投げ、`llm-calls-*.jsonl` に `kind: decision` 行と telemetry の形を確認。shadow 実走は通常の `/agent-run 30分` を `DECISION_MODEL=gemma4:e4b` 付きで 1 回、`skill-selection-*.jsonl` の新欄が埋まることを確認（本文は読まない — census 経路）
- 検収（このセッション）: 各 packet の worktree diff を `/code-review medium`（opus サブエージェント）→ adr-reviewer（ADR-0112）→ 上の verify → main へ ff-only

## 実行中の追記（2026-09-22 16:xx）

- H 初回は `prefix_cache_absent` で停止。probe で判明: qwen3.5:9b（hybrid 線形注意）は Ollama で部分 prefix の KV 再利用が効かず、
  `prompt_eval_count` は cache hit でも全 token 数を返す。**実行者の決定: `prefix_reuse` の指標を `prompt_eval_duration` に替える
  10 行の fix はこのセッションで直接行う（(b) packet 起票と worktree 往復のコストが修正本体より大きい）。Review は opus
  サブエージェントの `/code-review medium`。** 判定モデルは標準注意の `qwen3:8b` に替えて probe で cache を確認してから H を再開

## ついでに直す候補（別 commit、Doc Sync の範囲）

- CLAUDE.md の「Ollama 0.30.11」→ 実機は 0.34.2（2026-09-22 実測）。as-of を付けて更新
