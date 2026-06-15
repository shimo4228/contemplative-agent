---
name: weekly-report-diagnosis
description: Weekly レポート (A-E) を入力に、コードベース + ADR + identity/constitution/skills/rules を読んで F1 (構造提案) / F2 (identity-level questions) / F3 (observations) を別ファイル (weekly-{end-date}-findings.md) として生成する。weekly-analysis.sh が生成する自己内省レポートに対するコード診断 companion。Use when a new weekly report has been generated, or when refreshing F section of past reports after new ADRs land or pipeline code changes.
origin: shimo4228
user-invocable: true
---

# Weekly Report Diagnosis

`weekly-analysis.sh` が生成する weekly report は LLM 内省 (A-E) に専念する設計。コードベース、ADR、各層の全文を持たないため、構造的改善提案 (F1)、identity-level の問い (F2)、pure observations (F3) を妥当に書けない (ADR-0040)。

このスキルは、weekly report の E section を起点に、コードベース + ADR + 各層の全文を read して F1 / F2 / F3 を別ファイル (`weekly-{end-date}-findings.md`) として生成する。

---

## When to use

- `scripts/weekly-analysis.sh` が新規 weekly report (`reports/analysis/weekly-{date}.md`) を生成した直後
- 過去 weekly の F セクションを refresh したいとき (新 ADR が起票された / コード変更があった後)
- A-E は変えずに F のみ再生成したいとき

## Input contract

- **Required (optional argument)**: weekly report path (例: `~/.config/moltbook/reports/analysis/weekly-2026-05-17.md`)
- 引数省略時: `$MOLTBOOK_HOME/reports/analysis/` 配下の最新 `weekly-YYYY-MM-DD.md` を自動検出。`$MOLTBOOK_HOME` の default は `~/.config/moltbook/`
- 過去レポート対象でも動作する (再診断用)

---

## Required reading order

Context 膨張を避けるため、以下の順序で読む。途中で十分なら止める。**全ファイルを最初から読まない**。

### Step 1. Always (必須)

- 引数 weekly report の全文 (特に E section)
- `config/prompts/principles.md` (methodology guard)
- `docs/CODEMAPS/INDEX.md` (codebase index, file-level)
- `docs/adr/README.md` (ADR index, decision history)

### Step 2. F1 候補が出たら (構造提案)

E quote が示す症状を構造として診断するための raw material:

- 該当する CODEMAP entry (例: 症状が retrieval 関連なら `docs/CODEMAPS/core-modules.md`)
- 該当ソースファイル (`src/contemplative_agent/core/*.py`, `src/contemplative_agent/adapters/*`)
- 該当 prompt ファイル (`config/prompts/*.md`)
- 関連 ADR (index から status `accepted` のものを優先、withdrawn / superseded は履歴として確認)
- 該当パラメータ定義 (`core/thresholds.py`, `core/config.py`)

**判断基準**: F1 候補が「コードを読まないと妥当性を判定できない」介入なら必ず該当コードを open する。読まずに書いた F1 は principles.md Principle 1/2 で reject されるか、実装と乖離する。

### Step 3. F2 候補が出たら (identity-level question)

operator が判断する「問い」を立てるための material:

- `config/identity/*.md` (現在の Identity 全文)
- `config/constitution/*.md` (現在の Constitution 全文、四公理込み)
- `config/skills/*.md` (現在の Skills 全文)
- `config/rules/*.md` (現在の Rules 全文)
- 関連 ADR (特に Worldview ADR: ADR-0002, ADR-0007, ADR-0017 等)

**判断基準**: F2 の `What current state addresses (or does not)` セクションが load-bearing。各層を読まずに書くと、state diffs から推測した表面的な答えになる。

### Step 4. F3 候補が出たら (pure observation)

「次に何を watch するか」を意味のある形で書くため:

- 過去 N 週 (default 3) の `weekly-*-findings.md` の F3 セクション (重複検出と trend 追跡)
- 該当する generation pipeline の構造理解 (Step 2 で読んだ範囲で十分なことが多い)

---

## F1 / F2 / F3 判定基準

`config/prompts/principles.md` を正本とする。要点:

| 種類 | 内容 | 必須要素 |
|---|---|---|
| F1 | コード / スキーマ / パイプライン diff として表現できる介入 | `Source quote (E #N)`, `Code reference` (file:line), `Structural change`, `Why structural not symptomatic` |
| F2 | Identity / Constitution / Rules / Skills 層の編集に関する question form | `?` で終わる問い, `What current state addresses (or does not)` (具体的な current text 引用) |
| F3 | 介入提案なし、来週 watch 用 | `Observation` (記述形), `What to watch next week` (確認 / 反証条件) |

### Principle violations の再カテゴライズ

- **Principle 1 violation**: post-generation filter として `block`, `reject`, `gate`, `forbidden words`, `cosine gate`, `hash dedup` を F1 で提案 → F2 (open question として再フレーム) か F3 (observation として記述) に
- **Principle 2 violation**: hardcoded proper noun, specific phrase, numeric threshold を enforcement target にする → 再カテゴライズ
- **Principle 4 violation**: 過去 2 週以上同じ提案が state change なしで repeat → F2 (operator が判断していない理由を問う) か F3 (現象として observe) に

### F1 妥当性 self-check (必須)

各 F1 で以下を確認:

- [ ] 該当コードファイル + 行番号を `Code reference` に含めたか
- [ ] そのコード変更が既に実装済みでないか (例: cut-off 境界マークは `wrap_untrusted_content()` で実装済み)
- [ ] そのパラメータが既に effective でないか (例: `num_predict` は median 応答 ~400 tokens に対し 3384 tokens の上限で 12% しか使われていない)
- [ ] 関連 ADR で同じ提案が withdrawn / rejected されていないか (ADR-0022 / ADR-0034 retrieval 関連、ADR-0028 forgetting 関連等)
- [ ] retrieval / shared state を触る提案なら、呼び出し元を grep して間接経路か直接経路か確認したか (例: `views._rank` は distill 系のみから呼ばれる)
- [ ] 「re-reply / same-post duplicate」を F1 化する前に、`$MOLTBOOK_HOME/logs/YYYY-MM-DD.jsonl` で当該 `post_id` の interaction レコードを grep し、相手 (`agent_name`) が日ごとに別人かを確認したか。別人なら多者間スレッドであって re-reply ではない → F3 / drop (2026-06-15 検証済み: #836e1237 の「6 日連続 re-reply」は 6 人の別 agent だった。post 単位 reply dedup は principles.md Appendix で rejected)

---

## Output contract

### 出力先

`$MOLTBOOK_HOME/reports/analysis/weekly-{end-date}-findings.md`

weekly レポート本体 (`weekly-{end-date}.md`) は touch しない。

### 出力フォーマット

```markdown
# Weekly Diagnosis — {end-date}

**Source report**: weekly-{end-date}.md
**Diagnosis date**: {YYYY-MM-DD when this skill was run}

## F1. Structural (code / schema / pipeline diff)

### F1.1. {short title}

**Source quote (E #{n})**: {1 line referencing the E example}

**Code reference**: `path/to/file.py:LINE` (具体ファイル + 行)

**Structural change**: {what code or schema would change, with before/after snippets if applicable}

**Why this is structural, not symptomatic**: {1-2 sentences}

**Related ADR**: {ADR-NNNN if applicable, or 'none'}

(repeat for F1.2, F1.3, ...)

## F2. Identity-level open questions

### F2.1. {short question label}

**Source quote (E #{n})**: {reference}

**Open question**: {question form, ends with ?}

**What current state addresses (or does not)**: {specific Identity / Constitution / Skills / Rules text quote}

**Related ADR**: {if applicable}

(repeat for F2.2, ...)

## F3. Pure observations

### F3.1. {short observation label}

**Source quote (E #{n}, optionally multiple)**: {reference}

**Observation**: {descriptive, what is happening}

**What to watch next week**: {what confirms or refutes this is a stable pattern}

(repeat for F3.2, ...)

## Diagnosis Metadata

- **Codebase files read**: {list of paths consulted in Step 2}
- **ADRs read**: {list of ADR numbers consulted}
- **Identity/Constitution/Skills/Rules sections read**: {list}
- **Past findings consulted**: {list of past weekly-*-findings.md files}
```

### Out-of-scope outputs

このスキルは以下を出力しない:

- 実装そのもの (F1 提案は plan であって code 変更ではない)
- 過去レポートの bulk 再診断 (1 weekly に対する診断のみ)
- weekly レポート本体への追記

---

## Diagnostic Checklist (self-review before output)

- [ ] すべての F1 に `Code reference` (具体ファイル + 行番号) があるか
- [ ] すべての F2 が `?` で終わる question form か
- [ ] すべての F2 の `What current state addresses` が **現在のテキストを引用**しているか (state diff の要約だけになっていないか)
- [ ] すべての F3 に `What to watch next week` があるか
- [ ] F1 候補のうち principles.md Principle 1/2 違反は F2 / F3 に再カテゴライズしたか
- [ ] 過去 N 週の findings と重複していないか (Principle 4)
- [ ] CODEMAP / ADR / 各層を「読んでから」F を書いたか — 推測で書いていないか
- [ ] F1 妥当性 self-check を各 F1 で満たしているか
- [ ] Diagnosis Metadata セクションに実際に読んだファイルを列挙したか

---

## Related

- `scripts/weekly-analysis.sh` / `config/prompts/weekly-analysis.md` — このスキルの input を生成する upstream
- `config/prompts/principles.md` — F1/F2/F3 判定基準の正本
- `.claude/skills/code-and-llm-collaboration/SKILL.md` — Pattern 1 (LLM → Code guard) の variant: LLM 内省 (A-E) → コード guard (F)
- ADR-0040 — このスキルが分離された決定の記録
