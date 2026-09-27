# README.md 全面書き直し — Constitution-first / value-layer 前面化

## Context

README.md（英語正本）は 2026-06-30 `3934b08` を最後に実質凍結（v2.6→v2.7 境界）。以降コードは v2.8.0 まで進み、v2.7→v2.8 を定義する「instrument before intervene → observability by default」系譜（ADR-0071〜0076）が README に**丸ごと欠落**。並行して、owner の research hub（shimo4228/shimo4228）が "Value-Layer Harness Engineering" / "human-gated cycle" に再フレーミングされ、本 repo も **constitution を明示的ハーネスとして持つ**点を前面化する方針がユーザー決定済み。外部 discourse（code/LLM 責務分離の記事波）がゲート層の手前まで収束しつつあり、価値層の語彙が検索され始める前に facing doc を揃える。

**規律**: 全フレーミングは記述的事実の並置（ADR-0032/0033: usage description over category claim）。Hub の "Value-Layer Harness Engineering" というラベル自体は README に**書かない**（category claim になる）。語彙（value layer / human-gated）の共有で整合する。

## ユーザー確定事項

1. **Lead は Constitution-first**（確定テキスト、para 1-2）:
   > Contemplative Agent is a CLI agent that carries an explicit, human-editable constitution — and amends it. The agent distills its own episode logs into patterns and proposes promotions into its value layer (constitution, identity, skills, rules); nothing lands there without passing a human approval gate. The whole loop runs on a single Apple Silicon Mac (M1+, 16 GB) with a local Gemma 4 model — no cloud, no API keys in transit, no shell execution.
2. **Entry-point 表を lead 直後に置く**（4行、多面性→ナビゲーション変換）:
   | If you came for… | Start at |
   |---|---|
   | An agent with an explicit, amendable constitution | How It Works |
   | A fully local agent with structural security | Security Model |
   | Agent memory & self-improvement research | Key Features / Related Work |
   | Instrument-first operational discipline | Observability by Default |

## 検証済みの現状事実（2026-07-11 実測）

v2.8.0 / tests 1783 / ADR 76 本（最高 0076）/ templates 11 / prompts 37 / views 2 / deps 2（requests, numpy）/ ~18.9k LOC。**README に volatile な数値（test 数・LOC・ADR 数）を書かない** — CODEMAPS INDEX.md へのポインタ 1 文のみ（INDEX.md は 2 日 stale → 実装前に `/update-codemaps` で refresh）。

## 新 README 構成（~200 行、上限 210。現 239 行）

1. **Header** — badge 5→3（DOI / License / Python）。DeepWiki + GitMCP は AI-facing reading order details 内の plain link へ移動
2. **Lead**（4 段落）— para 1-2: 確定 lead。para 3: 対句文 “The preset is swappable; the value-layer machinery is not: the human approval gate ([ADR-0012]), approval lineage on every promotion ([ADR-0050]), replayable pivot snapshots ([ADR-0020]), and value injection at action time rather than distillation time ([ADR-0058]) operate identically under any preset.” para 4: AKC/AAP companion + Moltbook + 「axioms は 11 preset の 1 つ」を 2 文に圧縮。AI-facing details block は現状維持
3. **Entry-point 表**（確定 4 行）
4. **How It Works** — Mermaid **再描画**: 承認ゲートを明示ノード `G{{"Human approval gate — ADR-0012"}}` に、value layer を labeled subgraph に（caption: "Value layer — every write passes the gate"）。`distill (ungated)` エッジをラベル付きで残す（ゲートの境界を可視化 — 現 lead の「全 promotion がゲート通過」は過大主張だったので修正）。**text equivalent 1 文必須**: "In short: `distill` turns raw actions into one pattern store without a gate; every arrow crossing into the value layer — skills via `insight`, rules via `rules-distill`, identity via `distill-identity`, constitution via `amend-constitution` — is a human-approved promotion; nothing lands in the value layer automatically." AKC 位相マッピングは 2 文 + CODEMAPS link に圧縮。末尾に Live Agent への teaser 1 文
5. **Quick Start** — 実質変更なし（11 templates 行は維持）
6. **Live Agent** — 位置維持。intro を「evolving **value layer** を公開 — 以下の各ファイルは承認ゲートを通って現在の状態に至った」に書き換え。リンク順を Identity / Constitution / Skills / Rules 先頭、reports 後ろに
7. **Key Features**（6 bullets — MINJA/provenance bullet はユーザー判断で削除。source_type は生きているが MINJA 検出器としては実質定数（view_metrics.py コメント + ADR-0029「防御の正本は quarantine」）で headline に不適。ADR-0051 の規律は llms-full.txt / ADR に既在）:
   1. Human-gated value layer（lead para 3 に ADR ID があるので本 bullet は機構名のみ）
   2. Grounded distill（ADR-0060）
   3. Embedding + views（ADR-0019/0026）+ v2.8 で 7→2 seeds prune（ADR-0073、計器が orphan を示した事実込み）
   4. Weekly staged insight（ADR-0074、~90–115 patterns/day、~1800 patterns で tractable な exact clustering）
   5. Markdown all the way down（37 prompts 含む）
   6. Backend-aware budget guard（ADR-0066）
8. **Observability by Default**（新設 ~10 行）— framing 1 文 “Since v2.7 the project's operating discipline is *instrument before intervene*…” + 4 bullets: read-only instruments（0071）/ echo-chamber を計測→修理（0072）+ orphan prune（0073）/ observability by default（0075: replayable JSONL audit log を同一 PR で出荷）/ skill-selection shadow instrument — observed, not enforced（0076）
9. **Security Model** — 現状維持（既に tight、独立セクションのまま）
10. **Adapters** — 現状維持
11. **Architecture** — AAP quadrant 段落を 1 文に圧縮（詳細は ADR-0033 / CODEMAPS へ）。core/adapters invariant + Yogācāra 1 行 + CODEMAPS ポインタ維持
12. **Using inside other agents** — 軽く圧縮（AGENTS.md 例パス削除、one-adapter-per-process と not-an-MCP-server は維持）
13. **Details blocks**（cloud / MLX / everyday CLI）— cloud と MLX の本文を各 ~2 文 + repo link + 警告 1 文に圧縮（“no cloud property preserved/relaxed” 文は必ず残す）
14. **Citation** — 現状維持（plain citation は details 外、BibTeX は details 内）
15. **Related Work** — AKC / AAP 段落 + 理論 3 引用（CCAI / Beautiful Loop / Vasubandhu）+ Acknowledgments は inline 維持（citation floor）。末尾に relocate 先へのポインタ行

## Cut / Relocate

| 対象 | 処置 | 行き先 |
|---|---|---|
| Development Records（16 記事 details） | relocate | 新規 `docs/DEVELOPMENT-RECORDS.md`（README 作成前に必ず作る — link 切れ防止） |
| Memory-systems bibliography details | relocate | 新規 `docs/BIBLIOGRAPHY.md`（全引用は ADR + graph.jsonld に既在 → citation-sync 4 層は無傷） |
| AAP quadrant 段落の機構詳細 | 1 文に圧縮 | 既に ADR-0033 / CODEMAPS にある |
| cloud / MLX details 本文 | ~50% 圧縮 | 各 sibling repo README |
| DeepWiki / GitMCP badge | 移動 | AI-facing reading order details 内 |

## LLM-read floor（prose に必ず置く 6 概念）

value layer（lead）/ human approval gate（lead + diagram text-equivalent）/ security by absence（Security Model）/ views（Key Features 3）/ grounded distill（Key Features 2）/ observability by default（新セクション）。constitution の「明示的・改正可能」性は lead 第 1 文が担う。

## 同一 PR の companion 更新（doc-sync 規約）

- **README.ja.md** — 同内容ミラー（value layer（価値層）bilingual first-use）
- **docs/glossary.md** — Project-coined phrases に **value layer（価値層）** を正式登録（ADR-0058/0069 アンカー、既存 "values at action time" と相互参照）
- **llms.txt** — 冒頭 blockquote に human-gated value layer の 1 文
- **llms-full.txt** — Q&A 追加: "What is the value layer, and what governs changes to it?" + Last updated 更新
- **graph.jsonld + CODEMAPS 言及** — `Value Layer` Concept ノード追加（CLAUDE.md 両面更新規約。`tests/test_graph_integrity.py` が guard）
- **新規 docs/DEVELOPMENT-RECORDS.md / docs/BIBLIOGRAPHY.md**

## 実装順序と Chain（writing 種別）

1. `/update-codemaps`（INDEX.md stats refresh — README のポインタ先を先に直す）
2. relocate 先 2 ファイル作成 → README.md 本文書き直し → companion 更新（ja / glossary / llms / graph）
3. **Parallel Group 1（レビュー）**: readme-reviewer agent + codex-review（prompt-driven モード — 公開 repo README = 高 stakes 文書）
4. **Verify（writing 版）**: readme-writer skill の readme_lint（構造 lint: H1/badge 数/local link 解決 — 新規 docs 2 ファイルの存在確認含む）/ ADR 番号・事実アンカー照合 / `uv run pytest tests/test_graph_integrity.py`（graph 変更分）/ `git status`
5. **人間 gate**: diff 承認 → commit（main 直 commit、PR なし — push-workflow feedback）

Verdict マッピング: readme-reviewer MAJOR ISSUES → 停止 / NEEDS REVISION → 修正して継続 / readme_lint exit 1 → 停止。

## リスクと緩和

- **Lead 密度**: 確定 lead は ADR ID ゼロ。対句文（para 3）が ID 4 個の上限 — これ以上足さない
- **Category claim 混入**: 最終 grep で "Value-Layer Harness Engineering" が README に無いこと確認
- **日付表現**: "since 2026-06-30" 型の文言は使わず "since v2.7" 型のバージョンアンカーで書く
- **数値 drift**: volatile counts は CODEMAPS ポインタのみ
