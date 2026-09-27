# Archify 地図: episode / knowledge / skills / identity / constitution パイプライン

## Context

機構が複雑化し、著者と Fable が「同じものを見て」設計議論できない。code-grounded な
パイプライン地図を Archify（対話型 HTML 図）で 6 枚作り `docs/diagrams/` に置く。
file-level 構造は保存しない（ADR-0102）ので、ノードは **コマンド / store / ゲート / 計器 /
ADR 番号** の粒度にし、file path は card の「正本」行にだけ置く。CLAUDE.md 鮮度規約
（機構記述の複製は同 PR 更新義務）に図の JSON を組み込む。

決定済み: 全体図 1 + 詳細図 5、`docs/diagrams/` に JSON 正本 + HTML を commit、
日本語ラベル + 英語識別子（`meta.locale` 省略、Viewer UI は英語 fallback を index に明記）。

## 生成物

```
docs/diagrams/
  README.md                          # index。FRESHNESS ヘッダ（generated / source-commit / refresh 条件）、
                                     # 各図 1 行説明、「JSON が正本・HTML は deliver 出力」、Viewer UI 英語の注記
  pipeline-00-overview.dataflow.json / .html
  pipeline-01-distill.workflow.json / .html
  pipeline-02-insight-selection.workflow.json / .html
  pipeline-03-identity-constitution.workflow.json / .html
  pipeline-04-runtime-prompt.architecture.json / .html
  pipeline-05-weekly-gates.workflow.json / .html
```

CLAUDE.md「鮮度規約（mechanism 層）」に 1 文追加: 「該当する `docs/diagrams/*.json` も同 PR で更新」。
`docs/CYCLES.md` Sources 節に diagrams への 1 行ポインタ。

## 図ごとの内容（調査結果、正本 = 以下の file:line）

Archify 制約: 主要ノード ≤12、`meta.quality_profile: "showcase"`、dataflow は stage ≤5、
自動ルート開始、`via`/`labelAt` は diagnostic が出てから 1 修理 1 個。card は 3 枚以内で
「閾値 / ADR / 正本 file」を持たせる。

### 00 overview (dataflow, 5 stage: 運用 → 記憶 → 蒸留 → 値層候補 → 承認/注入)
ノード: Moltbook セッション `run`(6h) → `logs/YYYY-MM-DD.jsonl` (L1 episode, rich = comment/reply/post) →
`distill`(daily, 非ゲート) → `knowledge.json` (L2 patterns, 768-dim nomic) → 3 消費者
`insight`(週次) / `distill-identity`(27d) / `amend-constitution`(83d, 人間起動) → `.staged/` →
`adopt-staged`(ADR-0012 人間ゲート) → `skills/` `identity.md` `constitution/` `rules/` →
実行時プロンプト（two-pass skill 選択 ADR-0081）→ `run` に戻る閉ループ。
side: `shadow-constitution`(read-only, ADR-0092)、`skills/.archive/`(ADR-0097 D5)。
card: 3 層メモリ ADR-0004 / 非ゲート = distill のみ / 北極星「ループが人手なしで回る」ADR-0080。

### 01 distill (workflow)
`core/distill.py` L104-207 `distill()`: read_range(days) → drop `type==insight`(ADR-0052) →
`_is_rich_episode`(ADR-0060, `episode_render.py:69`) → per-episode LLM `distill.episode`
(`distill_episode.md`, gemma4:e4b think-OFF, num_predict 3000, schema `{"patterns":[str]}`) →
save-time gates: `_parse_patterns` / `_is_valid_pattern`(len<30, spaces<3, failure phrases) /
`_postgate`(ADR-0084 LLM 判定 `{"keep":[int]}`, fail-open, `MOLTBOOK_DISTILL_POSTGATE=0`) →
embed nomic → dedup `SIM_DUPLICATE 0.90` SKIP / `SIM_UPDATE 0.80` 更新（bitemporal ADR-0021）/
未満 ADD、`DEDUP_IMPORTANCE_FLOOR 0.05`(decay 0.95^days) → `knowledge.json` save。
abstain 理由コード（`llm_none`/`empty_render`/`shape_violation`/`nothing_durable`, ADR-0075）。
views: `self_reflection` threshold 0.66 / `constitutional` 0.55（`config/views/`, ADR-0071/0072）。
`--dry-run` → view_metrics 計器のみ。snapshot（ADR-0020, `snapshots/`）。

### 02 insight + selection (workflow, 2 レーン)
上レーン insight（`core/insight.py`）: `_refuse_if_pending`(ADR-0074 1 batch 不変) → live patterns →
cluster `CLUSTER_THRESHOLD_INSIGHT 0.70`, `MAX_BATCH 10`, `MIN_PATTERNS_REQUIRED 3` →
novelty gate（**抽出の前**、LLM coverage judge、既知 = `skills/` ∪ `insight-staged.jsonl`、
`insight-novelty.jsonl`。RFC-0023 BM25+nomic は accepted / 未実装と注記）→ 1 cluster 1 LLM
`insight.skill_extract`(think-ON, `NOTHING-PROMOTABLE` 棄権) → frontmatter `name/description`
（機械契約 2 欄）→ `.staged/<name>.md + .meta.json`（surprise ADR-0096）→ `adopt-staged`
（`--yes` non-TTY、`audit.jsonl`）→ `skills/`。退役: `--archive-names` / `remove-skill` → `skills/.archive/`。
下レーン runtime selection（`core/skill_selection.py`）: catalog（`strip_to_printable` 80 /
`scrub_control` 300）→ pass1 `core.skill_selection`(num_predict 400, `circuit_shield`) →
判定 `judged`(enforce) / `fail_open_*`(全量注入) → 幻覚名 `rejected_names` → pass2
`<learned_skills>` 注入 → `skill-selection-{date}.jsonl` → 読み値 never-selected
（`EXPOSURE_FLOOR 600`, dormant 14d）→ 土曜ゲートで退役判断。
card: ADR-0097 で退役した統合器（rules-distill / merge / clean）と wiki（RFC-0025 in_progress）。

### 03 identity / constitution / shadow (workflow, 3 レーン)
identity: `find_by_view("self_reflection")` → `distill.identity`(think-ON, 前 identity を seed
しない ADR-0057, 公理なし system ADR-0058) → `validate_identity_content` → `--stage` /
対話承認 → `identity.md`。月次 staging は weekly Stage 5b（due 27d, `.last_insight` ≤6h,
staging_pending==0, ADR-0091）。
constitution: `find_by_view("constitutional")` ≥3 → 現行 = `constitution/` 先頭 `*.md` →
`constitution.amend`(`constitution_amend.md`) → 承認 → 書換 + `.last_constitution_amend`。
due 83d は informational（ADR-0090、自動化しない）。
shadow: 同 retrieval、現行憲法を **入れない** `constitution_synthesize.md` → cosine vs 全
`constitution/*.md` → `constitution-shadow.jsonl`（ゲート無し、第 3 のゲート材料 ADR-0092）。
共通: `value_layer_due_check.py` → `pipeline/value-layer/value-layer-{END}.json` を土曜ゲートが直読。

### 04 runtime prompt assembly (architecture)
`core/llm/prompting.py`: base = `system.md` を `identity.md` が置換（validate 通過時）+ `---` +
公理（`configure_llm(axiom_prompt)`）→ `get_identity_system_prompt`（relevance / internal_note /
topic / submolt / skill 選択が使う）→ `build_system_prompt_with_skills`: `learned_skills_framing`
+ `<learned_skills>`(選択済み) + `learned_rules_framing` + `<learned_rules>`(`rules/` 全量)。
外部入力: `wrap_untrusted_content`(nonce frame, `injection-detect-{date}.jsonl`)、出力
`_sanitize_output`。**実行時に patterns は読まない**（retrieval は offline 値層コマンドのみ）。
security boundary として `core/llm/guard.py`、`_target_inside_data_root`。call sites
`llm_functions.py` comment / cooperation post / reply。budget 計器 `system_prompt_budget_reading`。

### 05 weekly chain + human gates (workflow)
`scripts/weekly-pipeline.sh`: materials(`weekly-analysis.sh`, episode 直読なし ADR-0083) →
1 headless `/weekly-report`（観察文書 6 節 + F1/F2/F3 診断 + rfcs draft 起票、working tree まで）→
valuelayer（due check + 条件付き identity staging）→ deadcode → docsscan → never-selected 7b →
`weekly-pipeline-audit.jsonl`。土曜 `/weekly-gate`（人間）: `adopt-staged`、退役、dead code、
rfcs 機微点検 + commit、`pipeline-metrics.jsonl`。launchd: agent 0/6/12/18 JST、distill +:30、
insight 週次、weekly Sat 09:00、watchdog。修理は task-triage loop（ADR-0098）。
card: 「チェーンは adopt / commit / push しない」不変。

## 手順

1. `docs/diagrams/` 作成。00 から順に JSON を書く（schema: `~/.claude/skills/archify/schemas/{dataflow,workflow,architecture}.schema.json`、
   workflow は `schema_version: 2`、例は `examples/`）。上の内容から主要ノード ≤12 に絞り、
   残りは card へ落とす。
2. 各図: `node ~/.claude/skills/archify/bin/archify.mjs validate <type> <json> --quality showcase --json`
   → 9 artifact checks / 0 error / 0 warning まで診断に従い修理（2 ラウンド改善なしで停止・報告）。
   → `deliver <type> <json> <html> --quality showcase --json` → `visual-check <html> --json`。
   1 枚目の候補後に `scripts/check-update.mjs` を 1 回実行（skill 規約）。
3. README.md（FRESHNESS ヘッダ = CYCLES.md 形式、source-commit は HEAD）、CLAUDE.md 鮮度規約 1 文、
   CYCLES.md ポインタ 1 行。
4. `.claude/verify.sh` 実行、`git status` 確認、`git-workflow` skill を読んでから 1 commit（main 直、push まで。
   memory: push-workflow）。

## Verification

- 6 図すべて `deliver` exit 0、receipt に 9 checks / 0 errors、SHA-256 記録
- `visual-check` exit 0（1440×900 / 1600×1000 / 1920×1080 で overflow なし）
- 各図の閾値・コマンド名を上記 file:line と突合（特に 0.90 / 0.80 / 0.70 / 0.66 / 0.55 / 600 / 27d / 83d）
- `.claude/verify.sh` PASS、docs_consistency_scan に新 doc が引っかからない
- 著者がブラウザで開いて議論に使えるかを最終判定（perceptual review は私ではできない）
