# Contemplative Agent: LLM Behavioral Eval 層の新設（DeepEval pilot）

## Context

CA はレビュー・リント（verify.sh の 7 ゲート）は手厚い一方、**LLM 出力品質を測る eval 層が無い**。実態は `.notes/` の replay-distill v2〜v5 / sampling_probe 目視比較という手動ワークフローで、これを形式化する。ハーネス全体の構造欠落（verify-bootstrap に eval 軸が無い）の pilot として CA で先行し、効いたら verify-bootstrap へ一般化（一般化はスコープ外）。

- Phase 0 (scout, as-of 2026-08-06): **Adopt DeepEval 4.1.5**（Apache 2.0、2026-07-31 リリース）。ADR-0077 は agent-chaos の依存としての却下であり、eval 層での採用は別判断 — ADR に明記
- Judge 設計は skill `llm-as-judge` 準拠: **binary checks を証拠に、名前付き holistic verdict 1 つ。スコア集計禁止**
- pilot 対象は **Face A: Moltbook `generate_comment()`**（llm_functions.py:217、実運用経路）のみ。distill 品質は既存 benchmark_distill.py を正本のまま後送

## 設計の要点

1. **配置は top-level `evals/`**。tests/ 配下は conftest.py が module load 時に `OLLAMA_BASE_URL=port 1`（LLM 即死）を仕込むため不可
2. **決定論コアと deepeval の分離**（TDD 成立の必須条件）: `evals/dataset.py` / `judging.py` / `generation.py` / `compare.py` は **stdlib + contemplative_agent のみ** import（dev group の pytest で回る）。deepeval を import するのは `adapter_deepeval.py` と `run_eval.py` の配線層だけ
3. **依存は新設 `[dependency-groups] eval`** に隔離、実行は `uv run --group eval`。verify.sh の type 行だけ `--group eval` 化（pyright include に evals 追加とセットで矛盾解消）。pip-audit の監査面が deepeval 推移依存に拡大するのは受容し ADR に明記
4. **prompt 資産の pin**: 自己改訂される 4 資産（identity / constitution / skills / rules）を `evals/snapshot_assets.py` で `evals/fixtures/agent_home/` へスナップショット（sha256 manifest 付き、commit 前に人間レビュー + secret scan）。テンプレ層は MOLTBOOK_HOME を fixture dir に向ければ repo commit 自体が pin。**MOLTBOOK_HOME は import 前に env 設定必須**（module load 時捕捉のため）。identity の無言 default フォールバック対策に**センチネル行 assert の preflight**（無ければ exit 2）
5. **skill selection は configure しない** = selection None = フル system prompt。現 production は shadow モードなので**本番と bit 一致**。enforcement 常時化を ADR の revisit trigger に記載
6. **judge = claude -p subprocess**（DeepEvalBaseLLM subclass）。隔離: `--setting-sources ""` + scratch cwd + `--strict-mcp-config --mcp-config '{}'` + ツール禁止 + `--max-turns 1` + `--model` pin。prompt は stdin、`--output-format json`、timeout 300s、`DISABLE_AUTOUPDATER=1` 等。parse 失敗は 1 再試行後 fail-loud。judge prompt には snapshot した constitution を判定基準として同梱（Claude の一般知識に判定させない）
7. **verdict**: 公理別 binary checks（Yes/No + 1 行証拠）→ enum {ADHERENT, DRIFTING, DEVIANT}。DeepEval score には verdict→{1.0, 0.5, 0.0} 写像のみ（集計しない）
8. **確率性**: production 温度 1.3 のまま case あたり 3 サンプル、多数決（tie / 全バラけ → 最悪値）。**生成失敗は verdict と分離**: sample に `status: ok | generation_failed`、ok<2 の case は INCOMPLETE、INCOMPLETE 含む run は exit 2 で baseline 化不可（偽 regression 防止）
9. **baseline 比較は自前の正規化 JSON が契約**（DeepEval TestRun スキーマに結合しない）: `{manifest: {model, temperature, judge_model, asset_sha256s, deepeval_version}, cases: [...]}`。`compare.py` は manifest 不一致 → exit 2（比較不能）、verdict 悪化遷移あり → exit 1。承認済み baseline は `evals/baselines/` に commit。DeepEval results folder はデバッグ用副産物
10. **telemetry opt-out 強制**: `DEEPEVAL_TELEMETRY_OPT_OUT=true`（telemetry.py:37 で短絡確認済み）を run_eval 冒頭で設定。`.deepeval/` cache も evals/results/ 配下へ閉じ込め
11. verify.sh には入れない（遅い・確率的・delta 判定）。発火は prompt 資産 / model / sampling / 生成経路の変更時に手動

## 実装ステップ

**Step 0 — API 照合**: context7 で DeepEval 4.1.5 の evaluate() / DisplayConfig / BaseMetric / DeepEvalBaseLLM / 結果保存の表面を確認（DisplayConfig(results_folder=) は未確認表面）

**Step 1 — ツールチェーン配線**
- `pyproject.toml`: `eval = ["deepeval==4.1.5"]`、pyright include + ruff known-first-party に "evals"
- `.claude/verify.sh`: full の format/lint 2 行に `evals` 追加、type 行を `--group eval` 化
- `.markdownlint-cli2.jsonc`: ignores に `"evals/fixtures/**"` / `.gitignore`: `evals/results/`

**Step 2 — snapshot**: `evals/snapshot_assets.py` 新規 → 実行 → 人間レビュー + secret scan → fixture commit

**Step 3 — TDD（決定論コア、dev group で回る）**
- `tests/test_eval_dataset.py` → `evals/dataset.py`（JSONL ローダ、id 重複拒否）
- `tests/test_eval_judging.py` → `evals/judging.py`（Verdict enum、judge JSON パース、多数決 + INCOMPLETE 規則）
- `tests/test_eval_compare.py` → `evals/compare.py`（manifest 検査、悪化遷移列挙、新規/削除 case）
- `tests/test_eval_generation.py` → `evals/generation.py`（FakeBackend 注入で 3-sample ループ + status 分類。tests/test_llm_backend.py:26 の FakeBackend を再利用）

**Step 4 — judge クライアント**: judging.py の subprocess 部 + `evals/fixtures/judge/comment_judge_prompt.md`

**Step 5 — adapter + CLI**: `evals/adapter_deepeval.py` + `evals/run_eval.py`（env 設定 → import → configure → preflight → 生成 → judge → 正規化 JSON。`--cases` / `--samples` / `--compare` フラグ — full run は 40〜90 分想定なので絞り込み必須）

**Step 6 — golden dataset**: `tests/fixtures/sampling/comment_suite.jsonl`（4 件）を種に `evals/datasets/comment_golden.jsonl` を 4 公理 × {normal, edge, adversarial(injection 系 — wrap_untrusted_content が経路にあるので有意)} で 12〜16 件

**Step 7 — 初回 run + baseline**: smoke（1 case × 1 sample）→ full → 人間レビュー → `evals/baselines/` commit

**Step 8 — Doc Sync**: ADR-0089（.md + .ja.md、index、graph.jsonld ノード）、CODEMAPS INDEX Statistics 再計測 + architecture.md、README(+ja) / llms.txt / CHANGELOG、`.notes/TASKS.md` 追記

## Chain（implementation-chain: feat）

TDD → Code Review（code-reviewer + python-reviewer）∥ Security Review（telemetry / subprocess 隔離 / 新依存）∥ Cross-Model Review（codex-review）→ ADR は adr-reviewer + codex-review → Doc Sync → Verify

## 検証

1. `uv run pytest -q` — dev group のみで決定論テストが通る（deepeval 非依存の証明）
2. `.claude/verify.sh` 全通過
3. smoke run で正規化 JSON 出力 / Ollama 停止で exit 2 / identity 汚染で exit 2（preflight）
4. self-compare → exit 0、baseline 手動悪化 → exit 1、manifest 改変 → exit 2
5. 実運用 `~/.config/moltbook` に run 前後で書き込みが無いこと
6. full run × 2 で verdict の run 間安定性を実測（不安定なら samples=5 を検討）
