# docs/CODEMAPS/ の退役（C-lite）

## Context

発端は「codemap を graph 形式にすべきか」。前提照合の結果、問いは「codemap はそもそも要るか」に変わった。

確認した事実（2026-09-05、すべて再検証可）:

- docs/CODEMAPS/ は 6 枚（記述の 5 枚は誤り。adapters-moltbook.md が抜けていた）、205 KB。architecture.md 単体 119 KB ≈ 30k token（header の推定 15,600 は 08-01 の値のまま）。header は 2,000 字の Updated ログ、INDEX.md は 9,000 字の再走査履歴
- 6 月以降 src 197 commit に対し CODEMAPS 159 commit。ほぼ毎 PR で同期している
- 著者は読まない。想定読者は次セッションの LLM だが、読まれた証拠は無い
- src 70 ファイルが ADR 番号を直接引用（69 ADR）。設計理由は docs/adr/ 101 本が持つ
- Claude Code の LSP tool（pyright）がこの repo で動く: workspaceSymbol / findReferences / incomingCalls を実走確認。grimp / import-linter は既に導入済み
- 外部ツール調査（scout、as-of 09-05）: 構造（モジュール一覧・LOC・import・call）は全部コードから導出可。導出できないのは「ファイル横断の段構成」と「incident 理由」だけ。code-graph MCP 群（2026 製、常駐 index = 新 drift 源）と Archify（LLM が書いた図の検証器、コード導出ではない）は不採用
- architect 独立判定: **縮退 B は同じ罠の縮小版**（Data Flow 自体が inline changelog。hook が残れば 1 ヶ月で再肥大）。Data Flow 節を実読した結果、大半はコードの再述（ゲート順は「コードの順どおり」と本文が自認、reason code は chaos test が pin、weekly 段構成は `scripts/weekly-pipeline.sh` 2〜17 行に既在、wiki 4 節は RFC-0025 で退役済み機構）。残渣は incident 理由のみで、それは ADR / docstring の内容

決定: **全削除。残す散文は ADR に無い incident 理由だけを ADR / module docstring へ移す。harness からも codemap 機構（update-codemaps skill / codemap-writer agent / context-sync Phase 0 / release-doi の再生成）を撤去する**（architect は per-repo opt-out を推したが、著者が「機構として再生産されないように」と global 撤去を指示。2026-09-05）。

graph.jsonld（concept 層、コードノード 0）は設計どおり別物で、本件の対象外。

## 執行者

判断は済んでいる。実作業は削除 + 導線書き換え + ADR 1 本 + 短い監査で、機構追加は無い。build-tier への dispatch が既定（planning.md）だが、削除対象と導線の一覧が本プランに揃っており委任オーバーヘッドの方が大きいので、in-session 実装で可。rfcs/ への起票は不要（提案でなく決定。ADR が記録を持つ）。

## 手順

### 1. ADR-0102 を書く（adr-writer skill）

`docs/adr/0102-retire-codemaps.md`（+ `.ja.md`）。Context は上の事実、Decision は C-lite、Alternatives に A 現状維持 / B 縮退 / D 何も残さない、Review-when に「LSP tool が Python で使えなくなった」「段構成の読み違いによる修理事故が 2 件」「2 repo 目が同結論に達したら harness global 変更」。graph.jsonld に ADR ノードを追加（CLAUDE.md の両面更新規約。HF mirror 同期は次 release の release-doi に載せる）。ADR は adr-reviewer に通す。

### 2. incident 理由の監査（bounded、移送でなく差分だけ）

`docs/CODEMAPS/architecture.md` の Data Flow 節（237〜1297 行）にある日付つき括弧 / `T-…` / `ADR-…` 参照を列挙し、各項目について「その理由が ADR 本文か該当 module の docstring に既にあるか」を確認。無いものだけ、guard の隣の docstring か所有 ADR に 2〜3 行で書く。architect が挙げた例: T-FEED-PACING、6,621 候補時間、LEDGER_DELTA_INVALID の順序理由。目安 10 件以下。移す先が判断できないものは commit message に 1 行残して捨てる（ADR-0095 の規律）。

### 3. 削除

- `docs/CODEMAPS/`（6 枚）
- `.claude/hooks/codemap-freshness-check.sh`、`.codex/hooks/codemap-freshness-check.sh`（symlink）、`.claude/settings.json:9` と `.codex/hooks.json:9` の配線、`.gitignore:90-94` の un-ignore 行
- `tests/test_doc_stats.py`（INDEX.md の統計表を読む）
- `tests/test_codemap_freshness_hook.py`（hook 自体が消えるので全部）
- `scripts/docs_consistency_scan.py`: `codemaps_freshness()`（324〜）、`mechanism_freshness()`（393〜）、`_ONELINE_FRESHNESS_RE`、docstring 20〜32 行、呼び出し 478〜486 行。対応する `tests/test_docs_consistency_scan.py` の 199〜302 行のケースも削除。JSON 出力から 2 読みが消えるので、weekly-pipeline.sh stage 6b（765 行付近）が両キーを参照していないことを確認
- `tests/test_tracked_paths_resolve.py:3-4` は hook symlink の存在を見ている可能性 — 読んで、hook 削除で赤になるなら該当ケースを落とす

### 4. 生きた導線の書き換え（ADR 38 本・CHANGELOG・evidence は歴史記録として触らない）

書き換え先の定型: 「構造（どこに何が・誰が呼ぶ）は LSP tool / grimp、理由は ADR（src が番号を引いている）、段構成は各 script の header」。

- `CLAUDE.md`: 5 / 7 / 9 / 12 / 14 / 16 行の CODEMAPS 導入節と graph.jsonld 対比、69 / 86 / 87 / 105 / 111 / 136 行。**鮮度規約（mechanism 層）節は削除**し、代わりに「段構成を変えたら該当 script header と ADR を同 PR で」に置き換える。「アーキテクチャ詳細は CODEMAPS を参照（正本）」を上の定型へ
- `README.md:123,127`、`README.ja.md:123,127`
- `docs/CYCLES.md:12,49,89,167`
- `docs/CONFIGURATION.md:431`、`docs/CONFIGURATION.ja.md:262`
- `docs/runbooks/README.md:30`
- `llms.txt:45-50,71,97`、`llms-full.txt:5,83,275`（docs_consistency_scan の範囲外なので手で確実に）
- `.claude/skills/weekly-report/references/diagnosis.md:14,25`（F1〜F3 診断の入口を「ADR index + LSP」へ）
- `src/contemplative_agent/adapters/moltbook/feed_manager.py:282` docstring
- `rfcs/0017:551`、`rfcs/0025:47` の change-scope チェックリスト行（1 行注記で可）
- `graph.jsonld:527,1303,2532` の description 内の言及（ADR-0102 ノード追加と同時に文言修正）

### 5. harness から codemap 機構を撤去（著者指示 2026-09-05: 「機構として再生産されないように」。global 正本 `~/.claude/` を編集、公開 copy は harness-sync）

architect は「1 repo の読みで global を変えない」と判定したが、著者が再確認して global 撤去を選んだ。理由を harness ADR に残す: 読者が LSP を持つ世代では codemap は導出可能な構造の保存であり、producer を残す限り context-sync が全 repo で再生成を要求し続ける（Scaffold Dissolution の Downward）。

削除:
- `~/.claude/skills/update-codemaps/`（SKILL.md / scripts/codemap_evidence.py / tests / pyproject.toml / uv.lock）
- `~/.claude/agents/codemap-writer.md`
- 公開 copy `~/MyAI_Lab/claude-harness/agents/codemap-writer.md` は harness-sync で消える（skill 側も同様）。README / llms.txt の一覧行は harness-sync の整合ステップで落とす

書き換え:
- `~/.claude/skills/context-sync/SKILL.md`: Phase 0（Codemap Freshness Pre-check、55〜110 行）を削除。role table（179〜196 行）と 3 / 33 / 37 / 123 / 215 / 263 / 297 / 313〜329 行の CODEMAPS 言及を「file-level は保存しない。構造は LSP / grimp、理由は ADR」へ。`scripts/context_checks.py` の `_codemaps_prose()`（587〜591）、`concepts_not_in_codemaps_prose`（657〜666）、`llms_txt.codemaps_dates`（728〜730）、472 行の CODEMAPS 例外を削除し、`tests/test_context_evidence.py` の対応 fixture（32 / 34 / 342 / 343）を落とす。`context_parsing.py:75,80` の CA 由来コメントは削除
- `~/.claude/skills/jsonld-knowledge-graph/SKILL.md` 34〜58 行「CODEMAPS との関係」節: 「concept 層 = graph.jsonld、file 層は保存せず LSP / grimp で毎回導出」に書き換え。365 / 385 / 391 / 392 行も同様
- `~/.claude/skills/implementation-chain/SKILL.md:90-91` Doc Sync 行: 「機構・段構成の変更 → 所有 ADR の Mechanism 節 / script header」「ADR 新設・廃止 → knowledge graph」に。`skill-comply/results/implementation-chain.spec.yaml:76,79` の文字列も同期
- `~/.claude/skills/release-doi/SKILL.md`: Phase 2 の再生成（81〜91 行）、Phase 4 の `git add docs/CODEMAPS/*.md`（179 行）、3 / 18 / 190 / 394 / 447 行の言及を削除
- `~/.claude/skills/harness-sync/SKILL.md:162` の公開 agent 一覧から codemap-writer を除く
- `~/.claude/skills/grill-me/SKILL.md:58`、`repo-asset-stocktake/SKILL.md:139`、`agent-stocktake/SKILL.md:175`、`readme-writer/SKILL.md:185`、`llms-txt-writer/SKILL.md:262` の 1 行言及を削除または LSP へ
- `~/.claude/skills/readme-writer/evals/fixtures/ca-readme-2026-08-19.md` は凍結 fixture なので触らない
- harness ADR は手順 6 で書く。CA ADR-0102 と相互リンク
- `harness_lint.py` と context-sync / update-codemaps 以外の skill tests が通ることを確認。`skill-stocktake/results.json` / `agent-stocktake/results.json` は生成物なので次回 stocktake で更新
- 最後に `harness-sync` で公開 repo へ

### 5b. 他 9 repo の docs/CODEMAPS/（本プランの範囲外、記録のみ）

他 9 repo に CODEMAPS が残る。producer が消えるので以後は更新されない静的文書。各 repo の次回接触時に削除し導線を書き換える（CA ADR-0102 を参照先にする）。harness ADR の Consequences に一覧を載せる。

### 6. 記録の 2 面（著者指示 2026-09-05）

- **harness global ADR**（手順 5 の最終項を独立ステップに格上げ）: `~/.claude/docs/adr/` の次番号。Status accepted、ADR-0060 を supersede、ADR-0010 / 0016 の codemap-writer 部分に日付つき注記。Context に CA の実測（159/197 commit、30k token、読者証拠ゼロ、LSP 実走）、Decision に「file-level の構造文書は保存しない。構造は LSP / grimp、理由は ADR、段構成は script header」、Review-when に「LSP tool が主要言語で使えない repo が出た」「段構成の読み違い事故 2 件」「CODEMAPS を持つ残り 9 repo の削除完了」。adr-reviewer に通す
- **AKC への記述**（`~/MyAI_Lab/agent-knowledge-cycle`）: `docs/scaffold-dissolution.md` の Evidence 節に日付エントリ `### 2026-09-05 — dissolution by platform absorption (hand-maintained codemaps → LSP)` を追加（既存 4 エントリと同じ体裁、5〜10 行）。要点: file-level codemap は読者の LLM が symbol index を持たなかった世代の scaffold。substrate が LSP を native に持った時点で構造部分は redundant（downward / platform absorption、information differential ≈ 0）、残った散文は git log の inline 写しで負の差分（保守 159 commit）。完了証拠は held-out ではなく「読者側の instrument 実走 + 保守コストの実測」なので、scaffold-dissolution の Completion Criterion に対しては**必要証拠止まり**であることを明記し、transfer 証拠（他 repo で codemap 無しに構造問いが解けること）は残り 9 repo の削除時に得る、と書く。`.ja.md` も同時更新。AKC repo 自身にも `docs/CODEMAPS/` があることを同エントリに 1 行注記（再帰例。削除は AKC 側の次回接触時）。AKC の commit は本プランの CA commit とは別 repo なので個別に commit → push

### 7. Verify

- `.claude/verify.sh` 全 PASS（pytest / ruff / pyright / import-linter）
- `python3 scripts/docs_consistency_scan.py` を手で走らせ、broken_link が 0 で、JSON に codemaps_freshness / mechanism_freshness キーが無いこと
- `grep -rn 'CODEMAPS' --include='*.md' --include='*.py' --include='*.sh' --include='*.txt' --include='*.json' .` の残りが docs/adr/ / CHANGELOG / docs/evidence / rfcs の歴史行だけであること
- LSP の実走 1 回（`workspaceSymbol distill` と `incomingCalls`）を ADR-0102 の evidence に凍結（`docs/evidence/adr-0102/lsp-probe.md`）
- Review: `/code-review`（chore 種別、settings.json / hooks を触るので Code Review Y）。Security Review は hook 削除のみなので不要
- Doc Sync 確認後 `git status` → main 直 commit → push（push-workflow memory）

## 見送り（記録のみ）

- graph 化: 導出可能な構造を別形式で保存するだけで drift 構造が同じ。不採用
- Aider 型 repo-map の抽出（~200 行）: LSP + Glob で足りる間は不要。cold start の一覧が要るという実害が出たら search-first から
- code-graph MCP: 2026 製・単独メンテ・常駐 index。12 ヶ月後に再評価可
