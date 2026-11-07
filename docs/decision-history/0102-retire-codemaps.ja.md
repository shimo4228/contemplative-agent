# ADR-0102: docs/CODEMAPS の退役 — 構造は保存せずコードから導出する

## Status

accepted

## Date

2026-09-05

## Context

`docs/CODEMAPS/` は手で保守する Markdown 6 枚（205 KB）で、コードベースの file-level
構造 — 行数つきモジュール一覧、import グラフ、システム図、パイプラインごとの長い
「Data Flow」散文 — を記述していた。`architecture.md` 単体で 119 KB（約 30k token）、その
freshness header は 2,000 字の `Updated:` 変更履歴に育ち、`INDEX.md` は 9,000 字の
再走査履歴段落を抱えていた。CLAUDE.md はこのディレクトリをアーキテクチャの正本と呼び、
機構変更のたびに Data Flow 節を同じ PR で更新することを義務づけ、PostToolUse hook
（`codemap-freshness-check.sh`、Claude Code と Codex の両方に配線）が監視対象モジュールへの
commit で codemap が触られていないと催促していた。

2026-09-05 の実測:

- 2026-06-01 以降、`src/` を触った commit が 197、`docs/CODEMAPS/` を触った commit が 159。
  ほぼソース commit 1 件につき codemap commit 1 件。
- 唯一の人間の著者は codemap を読まない。想定読者は次セッションの LLM だったが、読まれた
  証拠は無い。CLAUDE.md と harness の約 44 箇所の参照は読者をそこへ*誘導*していたが、
  セッションは実際には language server・`grep`・docstring が引く ADR に手を伸ばす。
- ソースの 70 ファイルが ADR 番号を直接引用している（69 ADR）。codemap が再述していた
  設計理由は既に `docs/adr/` にある。
- Claude Code の LSP tool は pyright 経由でこの repo で動く。`workspaceSymbol`・
  `findReferences`・`incomingCalls` / `outgoingCalls` を実走した（`distill()` → 呼び出し元
  17 件、行番号まで正確）。`grimp` と import-linter は既に導入済みで層契約を強制している。
- 外部ツール調査（2026-09-05 時点）では、codemap の内容のうち 2 つを除く全部 — モジュール
  一覧、行数、import / call 構造、ADR↔モジュール対応 — がコードから都度導出できる。例外は
  ファイル横断のパイプライン段構成と、個々の guard の incident 理由。2026 年製の
  「code graph」MCP 群は不採用（若い・単独メンテ・常駐 index が新しい drift 源）。Archify は
  LLM が書いた図を検証するものでコードからの導出ではないため不採用。
- 独立の build-or-not レビューが Data Flow 3 節を全文読み、大半がコードの再述だと確認した。
  ゲート順は「コードの順どおり」と自認し、reason code 一覧は chaos test が pin し、weekly の
  段構成は `scripts/weekly-pipeline.sh` の冒頭（2〜17 行）に既にあり、wiki の 4 節は RFC-0025
  が退役させた機構を述べていた。Data Flow 散文中の日付つき括弧（ADR 番号・task id・incident
  日付）は本文に inline された変更履歴であり、肥大源は header でなく Data Flow そのもの。

本作業を開いた問いは「codemap を graph に再エンコードすべきか」だった。前提を検証すると
「そもそも残すべきか」に変わった。

## Decision

1. **`docs/CODEMAPS/` を削除する。** 鮮度を保つために存在した機構も全部: hook
   `codemap-freshness-check.sh` と 2 つの配線（`.claude/settings.json`、`.codex/hooks.json`）、
   `tests/test_doc_stats.py`（INDEX の統計表を読んでいた）、`tests/test_codemap_freshness_hook.py`、
   `scripts/docs_consistency_scan.py` の `codemaps_freshness` / `mechanism_freshness` 読み（残る
   `freshness` 読みは block 形 FRESHNESS header を今も持つ唯一のファイル `docs/CYCLES.md` だけを対象）。
2. **file-level 構造は導出層であって保存層ではない。**「どのファイルに X があるか」「誰が Y を
   呼ぶか」は LSP tool と `grimp` が問いごとに答える。checkout から再計算できるものは書き残さない。
   `graph.jsonld` は concept 層（コードノード 0）のまま無変更。
3. **導出できない 2 つの内容の置き場**: パイプラインの段構成は、それを走らせる script の冒頭
   コメント（weekly チェーンは既にそう）。guard の incident 理由は guard の隣の module docstring
   か機構を所有する ADR。削除前の bounded な監査で、他のどこにも無い理由だけを移した
   （Consequences 参照）。それ以外は移送していない。
4. **CLAUDE.md の鮮度規約を書き換える**: ゲート・式・閾値・段構成の変更は所有 ADR（新設か追補）
   と script header を同じ PR で更新する。機構散文を第 2 の文書に複製しない。
5. **global harness からも生産機構を撤去する**（`update-codemaps` skill、`codemap-writer` agent、
   context-sync Phase 0、release-doi の再生成手順）。harness ADR に記録し本 ADR とリンクする。
   独立レビューは per-repo opt-out を推した（1 repo の読みは 1 回の測定）が、著者は機構が
   再生産されないよう全面撤去を選んだ。sibling repo 9 つに `docs/CODEMAPS/` が残る。各 repo は
   次回接触時に本 ADR を引いて削除する。

## Review-when

- LSP tool がこの repo の Python で動かなくなり（pyright の除去、または Claude Code からの
  tool 撤去）、代わりの per-query 構造ソースが無い — 導出層の源が消える。
- パイプライン段構成の読み違いに起因する修理事故が 2 件 — 各件は修正 commit の message に `T-…` 行で
  記録し、土曜ゲート（`/weekly-gate`、当週の commit を読む場）で数える。直し方は script header か
  ADR の Mechanism 節であって codemap の復活ではないが、2 件は今の置き場が見つかっていない印。
- sibling repo 9 つが全部 codemap を削除した — harness ADR の transfer 証拠が揃い、本 ADR の
  Consequences を閉じられる。

## Alternatives Considered

**現状維持。** 却下: 読者が観測されない文書にソース commit 1 件あたり codemap commit 約 1 件を
払い続け、本文は第 2 の変更履歴になっていた。

**Data Flow 節だけに縮め、hook と `mechanism_freshness` を残す。** main loop の第一案で、著者も
最初はこれを選んだ。独立レビューが節を実読して却下: 肥大源は header でなく Data Flow 自体で、
hook がまさにその散文を求め続ける以上、1 ヶ月で再び育つ。hook + test + 読み + 導線書き換えを
残すコストは削除とほぼ同じで、節約が無い。

**graph に再エンコード（発端の問い）。** 却下: 導出可能な構造の graph は同じ保存鏡の別構文で、
drift も同じ。理由の散文は node 属性に入るだけで形式は変わらない。JSON-LD は Markdown の節が
持つ locality を失う（node の近傍がファイル中に散らばり query tool が要る）。graph が勝つ場面 —
多段 hop の波及問い、path 実在検査 — は LSP の call hierarchy と Markdown への path test で既に
足りる。

**導出型 repo-map ツールの採用**（Aider 型 tree-sitter + PageRank の署名一覧、または 2026 年製
code-graph MCP）。不採用で保留: 今は LSP tool と Glob で cold start の問いに足りる。MCP 群は
若く常駐 index を再導入する。具体的な cold start の失敗が観測されたら再評価。

**全削除して Data Flow 散文を全部 ADR に畳む。** 移送としては却下: 大半がコードの再述で、
ADR に無い incident 理由だけが移す価値を持つ。それは監査であって移送ではない。

## Consequences

- 機構変更のたびの codemap 同期コストが消える。機構変更の Doc Sync は所有 ADR と script header。
- 次セッションの LLM は、コードと一致するかわからない 30k token の文書を読む代わりに、コードに
  問う（`workspaceSymbol` / `incomingCalls` / `grimp`）。コストは毎 PR から毎問いへ移り、答えは常に
  現在のもの。
- weekly / wiki チェーンの段構成散文は 1 箇所に無くなる。weekly を修理するセッションは
  `scripts/weekly-pipeline.sh` の冒頭とそこが名指す script を読む。独立レビューの最強の反論で、
  鏡でなく正本を読むコストとして受け入れる。
- `scripts/docs_consistency_scan.py` の JSON 契約が変わる: `readings` は `freshness` だけ
  （`codemaps` と `mechanism` は消える）。`readings.mechanism` を読んでいた土曜ゲートの散文は
  同じ commit で更新。
- 生きた導線を約 20 箇所書き換えた（CLAUDE.md、README 両言語、CYCLES、CONFIGURATION、runbooks
  index、llms.txt、llms-full.txt、weekly-report の diagnosis 参照、docstring 1 件）。CODEMAPS に
  言及する ADR 38 ファイル（19 本、en + ja）・CHANGELOG・evidence は歴史記録として触っていない。
  例外は ADR-0014 と ADR-0093 で、本 ADR が Decision を一部反証するため Decision 直下に日付つき注記を置いた。
- 削除前監査の結果は `docs/evidence/adr-0102/` — LSP probe の出力と、incident 理由項目ごとの
  COVERED / 移送の処置一覧。
- harness 側の撤去と sibling repo 9 つは harness ADR が追跡する。本 ADR では追わない。

## References

- harness [ADR-0062](https://github.com/shimo4228/claude-harness/blob/main/docs/adr/0062-retire-codemap-machinery.md)
  — 生産機構（update-codemaps / codemap-writer / context-sync Phase 0）を撤去し、2026-09-01 に codemap の
  freshness gate を script 化した harness ADR-0060 を本判断の 4 日後に supersede
- [ADR-0014](./0014-retire-system-spec.ja.md) — system-spec 層を「CODEMAPS に譲って」退役させた。
  その後継が今回退役する（Decision 直下に日付つき注記）
- [ADR-0079](./0079-module-reorganization-package-splits.ja.md) — codemap が最も密に追っていた
  モジュール分割
- [ADR-0093](./0093-repo-plane-deterministic-intakes.ja.md) — 本 ADR が読みを削る
  docs-consistency intake
- [ADR-0095](./0095-retire-task-ledger-machinery.ja.md) — 保守コストが読み値を超えた機構を
  退役させた先例
- [ADR-0101](./0101-instrument-dissolution-mandate.ja.md) — `mechanism_freshness` 読みの消費者は
  著者だけで、著者は読まなかった
- Agent Knowledge Cycle `docs/scaffold-dissolution.md` — 本退役は platform absorption の一例
  として記録（LSP が codemap の構造機能を吸収）
