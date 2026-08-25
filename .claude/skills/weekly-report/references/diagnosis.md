# 診断手順（F1 / F2 / F3）— 旧 weekly-report-diagnosis の移植

判定基準の正本は `config/prompts/principles.md`。ここは読む順・必須要素・self-check。

## Required reading order

Context 膨張を避けるため以下の順で読み、途中で十分なら止める。全ファイルを最初から読まない。

### Step 1. Always（必須）

- 生成した weekly report の全文（特に E）— ただし F の根拠は materials の原資料へ立ち返る
- `config/prompts/principles.md`
- `docs/CODEMAPS/INDEX.md`、`docs/adr/README.md`
- タスク台帳 `rfcs/NNNN-*.md`（正本）と `.notes/tasks/T-*.md`（pipeline の移送先、dual-read 中）
  — 1 エントリ 1 ファイル。frontmatter `state:` を Glob + Read で
  確認する — この無人セッションに Bash は無いので `claims.py` は使えない）。2 つの理由で必須:
  (1) `blocked` / `draft` 行が今週のシグナルを既に予約・却下していないか（重複起票 /
  再提起の防止 — `.notes/archive/tasks/` の終端記録が「operator-facing データからは判定
  できない」を閉じることも多い）、(2) 観察系タスクがこの診断の入力になっていないか。
  開状態は `draft` / `accepted` / `in_progress` / `blocked` の 4 つ（ADR-0095 Amendment）

### Step 2. F1 候補が出たら（構造提案）

- 該当 CODEMAP entry → 該当ソース（`src/contemplative_agent/core|adapters`）→
  該当 prompt（`config/prompts/*.md`）→ 関連 ADR（accepted 優先、withdrawn / superseded は
  履歴として）→ パラメータ定義（`core/thresholds.py`, `core/config.py`)

**判断基準**: 「コードを読まないと妥当性を判定できない」介入なら必ず該当コードを open
する。読まずに書いた F1 は principles.md Principle 1/2 で reject されるか実装と乖離する。

### Step 3. F2 候補が出たら（identity-level question）

- `config/identity/*.md` / `constitution/*.md` / `skills/*.md` / `rules/*.md` の現在全文
- 関連 ADR（特に Worldview 系: ADR-0002, 0007, 0017 等）

**判断基準**: `What current state addresses (or does not)` が load-bearing。各層を読まずに
書くと state diff から推測した表面的な答えになる。

### Step 4. F3 候補が出たら（pure observation）

- 過去 N 週（default 3）の `weekly-*-findings.md` の F3（重複検出と trend 追跡）

## F1 / F2 / F3 判定基準（要点。正本は principles.md）

| 種類 | 内容 | 必須要素 |
|---|---|---|
| F1 | コード / スキーマ / パイプライン diff として表現できる介入 | `Source quote (E #N)`, `Code reference` (file:line), `Structural change`, `Why structural not symptomatic` |
| F2 | Identity / Constitution / Rules / Skills 層の編集に関する question form | `?` で終わる問い, `What current state addresses (or does not)`（現テキスト引用） |
| F3 | 介入提案なし、来週 watch 用 | `Observation`, `What to watch next week` |

### Principle violations の再カテゴライズ

- **Principle 1**: post-generation filter（`block` / `reject` / `gate` / forbidden words /
  cosine gate / hash dedup）を F1 で提案 → F2 か F3 へ
- **Principle 2**: 固有名詞・特定フレーズ・数値閾値の enforcement → 再カテゴライズ
- **Principle 4**: 過去 2 週以上 state change なしで repeat → F2（オーナーが判断していない
  理由を問う）か F3 へ

### F1 妥当性 self-check（必須 — Phase 4 起票の入場条件）

- [ ] 該当コードファイル + 行番号を `Code reference` に含めたか
- [ ] そのコード変更が既に実装済みでないか（例: cut-off 境界マークは
      `wrap_untrusted_content()` で実装済み）
- [ ] そのパラメータが既に effective でないか（例: `num_predict` は median 応答 ~400 tokens
      に対し 3384 tokens の上限で 12% しか使われていない）
- [ ] 関連 ADR で同じ提案が withdrawn / rejected されていないか（ADR-0022 / 0034 retrieval、
      ADR-0028 forgetting 等）
- [ ] `rfcs/` / `.notes/tasks/`（pending）と `.notes/archive/tasks/`（終端）に同じ介入が無いか。
      既にある介入は起票せず、findings に台帳行への参照 1 行を残す
- [ ] retrieval / shared state を触る提案なら、呼び出し元を grep して間接経路か直接経路か
      確認したか（例: `views._rank` は distill 系のみから呼ばれる）
- [ ] 「re-reply / same-post duplicate」型は、当該 `post_id` の相手が日ごとに別人でないかを
      検証できたか。**このセッションは episode log（`logs/YYYY-MM-DD.jsonl`）を読めない**
      （injection 境界の Read deny）ので、materials の Cross-Day Duplicate Scan digest で
      判定できなければ**未検証 = F1 にしない**（F3 で watch に落とす。2026-06-15 の先例:
      「6 日連続 re-reply」は 6 人の別 agent だった)

## 出力契約

出力先: `$MOLTBOOK_HOME/reports/.private/weekly-{end-date}-findings.md`（staging —
完全性検査後に pipeline が `reports/analysis/` へ promote）。
weekly レポート本体は touch しない。日本語版 `weekly-{end-date}-findings.ja.md` を必ず併出
（冒頭に `> 日本語版（自動翻訳）。英語正本: …` の 1 行。quote・`path:line`・識別子は英語の
まま、地の文だけ普通の日本語で。構造は 1:1）。

`### F1.N. {title}` の見出し形式と `**Code reference**:` ブロック（バッククォートの
`path:LINE`）は維持する。旧 parse_findings.py は退役したが、Code reference は Phase 4 の
起票が producer 引用として転記する正本であり、崩すと起票の入場条件を満たせない。

### フォーマット

```markdown
# Weekly Diagnosis — {end-date}

**Source report**: weekly-{end-date}.md
**Diagnosis date**: {YYYY-MM-DD}

## F1. Structural (code / schema / pipeline diff)

### F1.1. {short title}

**Source quote (E #{n})**: {1 line}
**Code reference**: `path/to/file.py:LINE`
**Structural change**: {what would change}
**Why this is structural, not symptomatic**: {1-2 sentences}
**Related ADR**: {ADR-NNNN or 'none'}
**Filed**: {T-SLUG | not filed — 理由（self-check 未達の項目名 / 台帳既存）}

## F2. Identity-level open questions

### F2.1. {label}

**Source quote (E #{n})**: {reference}
**Open question**: {…?}
**What current state addresses (or does not)**: {current text quote}
**Related ADR**: {if applicable}

## F3. Pure observations

### F3.1. {label}

**Source quote (E #{n})**: {reference}
**Observation**: {descriptive}
**What to watch next week**: {confirm / refute condition}

## Diagnosis Metadata

- **Codebase files read**: {…}
- **ADRs read**: {…}
- **Identity/Constitution/Skills/Rules sections read**: {…}
- **Past findings consulted**: {…}
- **Task ledger consulted**: {T-XXXX, …}
- **Tasks filed**: {T-SLUG, … | none}
```

## Out-of-scope

- 実装そのもの（F1 は plan であって code 変更ではない）
- 過去レポートの bulk 再診断、weekly レポート本体への追記
- **値層（skills / rules / identity / 憲法）の内容がセキュリティ境界を侵すという指摘** —
  構造的に成立しない。封じ込め・サニタイズはすべてコード側にあり
  （`cli/adopt.py::_target_inside_data_root` / `core/llm/guard.py` /
  `core/episode_render.py` / `core/skill_selection.py`）、値層は生成文に影響するだけで
  これらを動かせない（security by absence）。値層について書くなら軸は生成文の質・
  一貫性・観察対象としての意味であり、それは F2 / F3 に属する（2026-08-15 著者指示）

## 出力前 self-review

- [ ] 全 F1 に `Code reference`、全 F2 が `?` 終わり、全 F2 が現テキスト引用、全 F3 に watch
- [ ] Principle 1/2 違反は再カテゴライズ、過去 N 週と重複なし（Principle 4）
- [ ] 読んでから書いたか — 推測で書いていないか
- [ ] 各 F1 が self-check 全項目を満たし、`Filed:` 行が起票結果と一致しているか
- [ ] 値層を「セキュリティ境界」軸で論じていないか
- [ ] Diagnosis Metadata に実際に読んだファイルを列挙したか
