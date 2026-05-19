# ADR-0040: 週次自己内省レポートからのコード診断 findings の分離

## Status
accepted

## Date
2026-05-19

## Context

`scripts/weekly-analysis.sh` が生成する週次分析レポート (`claude -p` を呼び、`weekly-analysis.md` を system prompt、`principles.md` を user prompt に埋め込む) は、従来 F section に 3 つのサブセクションを含んでいた:

- **F1**: 構造的改善提案 (コード / スキーマ / パイプライン diff)
- **F2**: identity-level の open questions
- **F3**: 純粋な observations

このレポート生成 LLM が access できる input:

1. system prompt (`weekly-analysis.md`)
2. principles file (`principles.md`)
3. 期間内の daily comment reports
4. `git log` からの state diff (identity, constitution, skills, rules, knowledge.json)
5. 過去最大 3 週分の weekly レポート

access **できない** input:

- 現在のソースコード (`src/contemplative_agent/`)
- ADR (`docs/adr/`)
- identity / constitution / skills / rules の **現在の全文** (差分のみ)
- CODEMAPS (`docs/CODEMAPS/`)

この context gap が F1 で体系的失敗を生んでいた。`weekly-2026-05-17.md` の具体例 3 件:

- **F1.1 (num_predict)**: `num_predict` を入力長 proportional にする提案。`core/llm.py` を確認すると `num_predict = ceil(max_length/3) + 50 = 3384 tokens` (`MAX_COMMENT_LENGTH = 10000` 由来)。5月分 901 コメントの実 median 応答長は ~400 tokens (上限の 12%)。上限は制約として効いておらず、式を変えても応答長は変わらない。
- **F1.2 (入力境界)**: cut-off 幻覚抑制のため `<original_post>` で境界マークする提案。`core/llm.py::wrap_untrusted_content()` で外部入力は既に `<untrusted_content>...</untrusted_content>` ラップ済み (`_INJECTION_TOKENS` でサニタイズ込み)。重複追加。
- **F1.3 (MMR retrieval)**: echo chamber 緩和のため pattern retrieval に MMR で多様性導入の提案。`views._rank` の呼び出し元は `distill`, `insight`, `rules-distill`, `distill-identity` のみ。comment / reply 生成は `knowledge_section=""` で retrieval を経由しない。MMR は間接経路 (distill 経由) に効くだけで、レポートが指摘した直接的な reply echo は対象外。

`principles.md` の guard rail (Principle 1: post-generation filter 禁止、Principle 2: hardcoded block 禁止、Principle 4: repeated recommendation 禁止) は LLM が提案する F1 の *種類* を制約するが、F1 が **実装と整合しているか検証する context そのものが欠けている** 問題は補えない。

同じ context-gap は F2 (意味ある identity-level 質問は identity/constitution/skills/rules の現在の全文 + 過去 ADR が必要) と F3 (「self-sustaining pattern」「reproducible generation pattern」の判定には generation pipeline 構造の知識が必要) にも適用される。

## Decision

Weekly レポートは observation (A–E) に専念する:

- **A**: 定量サマリ
- **B**: Agent state snapshot (差分ベース、得られる範囲)
- **C**: engagement パターン (引用ベース)
- **D**: change point (定性的、E に grounded)
- **E**: 定性的 highlights (分析の中心)

コード診断 findings (旧 F section) は別途 `weekly-report-diagnosis` skill (`.claude/skills/weekly-report-diagnosis/`) が生成する。skill は weekly レポートの E section と、コードベース + ADR + 現在の identity/constitution/skills/rules を併読し、companion ファイル `weekly-{end-date}-findings.md` を出力する。

skill は `config/prompts/principles.md` の Principles 1-4 + Appendix を判定基準として適用する。`principles.md` は現在地に保存される (Principle 3 quote-based depth は upstream の weekly レポートにも適用継続)。

## Alternatives Considered

### Alternative 1: `weekly-analysis.sh` に codebase / ADR / 各層全文を attach

却下。Weekly cron は再現性のため安定 context が必要。CODEMAPS / ADR / 各層全文を inject すると、プロジェクト進化のたび prompt が変動する。トークンコストも膨張 (各層数千トークン、ADR 累積で context limit を超える)。

### Alternative 2: F1 のみ skill に分離、F2/F3 は weekly に残す

却下。3 層は Principle 1/2 で coupled (finding は principle 違反判定で F1→F2→F3 に再カテゴライズされる)。分離すると最初の層が F1 候補を捏造し、後段で reject できない。さらに F2/F3 も F1 と同じ context gap を持つ (上記具体例で検証済み) ため、partial 分離では root cause 解決にならない。

### Alternative 3: `principles.md` 廃止して skill に inline

却下。Principle 3 (quote-based depth) は upstream weekly レポート (C, D, E は引用ベースで grounded) に適用される。principles を全部 skill に移すと weekly レポートが methodological constraint を失う。

## Consequences

### Positive

- F1 提案が実コード状態 (file path + 行番号 + ADR 参照、skill の diagnostic checklist が必須化) に grounded
- 過去 weekly レポートを再診断可能 (新 ADR 起票後 / pipeline コード変更後)
- Weekly cron prompt がプロジェクト進化に対し安定 (ADR 追加で prompt 更新不要)
- skill の段階的 reading order (CODEMAPS → source → ADR → identity 層) で診断プロセスが audit 可能

### Negative

- skill 未実行時、weekly レポートが "incomplete" に見える。`weekly-{date}.md` ↔ `weekly-{date}-findings.md` のファイル対で mitigate (`reports/analysis/` で対が可視)
- operator が skill を手動 invoke する必要あり (cron 自動化は本 ADR の scope 外、現状は `user-invocable: true`)
- skill output には「operator が stale codebase view で実行」の guard がない (例: latest pull 前に実行)。skill の diagnostic checklist で operator 責任として明示

### Re-check trigger

2 週後 (2026-06-02 頃) に再評価。具体的に確認:

1. diagnosis skill output が F1 entry で具体ファイルパス + 行番号を参照しているか
2. F1 提案のうち少なくとも 1 件が実装可能まで到達するか (unaided weekly LLM の three-of-three 失敗率と比較)
3. F2 質問が現在の identity/constitution テキスト引用に grounded か、依然 state-diff-only references に留まるか

すべて no なら設計が誤り。再考が必要 (例: `weekly-analysis.sh` から skill 自動呼び出し、input contract 再構築)。

## References

- [ADR-0038](0038-moment-of-recognition-distill.ja.md) — Distill observation 拡張。本 ADR の「内省 → コード診断」対は同じ shape (内省は observation を生み、コード診断は構造的決定を生む)
- [ADR-0039](0039-novelty-score-lagrangian-self-post-gate.ja.md) — F1 形 (構造提案) が実際に ADR 化された事例。Lagrangian 定式化、admit_rate / fallback_rate モニタリングは unaided weekly LLM では出せない code-aware diagnosis が必要だった
- `.claude/skills/code-and-llm-collaboration/SKILL.md` — Pattern 1 (LLM → Code guard) の variant: LLM 内省 (A-E) → コード診断 guard (F)
- `.claude/skills/weekly-report-diagnosis/SKILL.md` — 本 ADR で導入された skill
- `config/prompts/principles.md` — F1/F2/F3 判定基準の正本 (現在地保持)
- `config/prompts/weekly-analysis.md` — Weekly レポート prompt (F section を本 ADR で削除)
- `~/.config/moltbook/reports/analysis/weekly-2026-05-17.md` — 系統的 context-gap 問題を露呈した source report
