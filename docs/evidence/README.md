# Evidence

ADR の決定を裏付ける測定・監査・実験の成果物。

## 配置ルール

- **1 ADR = 1 サブフォルダ**: `adr-XXXX/` にまとめる
- **サブフォルダ名**: `adr-XXXX/`（ADR の決定根拠）、`rfc-NNNN/`（ADR を持たない RFC の読み）、`<slug>-YYYYMMDD/`（どちらにも属さない一回限りの測定）。RFC の変更点を記録する横断メモは単一ファイル（例 `rfc-0051-path-rewrites.md`）でもよい
- **ファイル名**: 日付スタンプ付き (`<slug>-YYYYMMDD.md` / `.py` / `.json`)
- **ADR 本文からリンク**: evidence は「その決定をした根拠」なので、対応する ADR からリンク参照可能にする

## サブフォルダ

<!-- 表は `python3 scripts/gen_evidence_index.py` が `ls docs/evidence` から生成する（手書きの Scope 列は再生成で保たれる）。実体と表の不一致は tests/test_doc_links.py が落とす -->

<!-- evidence-index:begin -->
| Dir | Scope | 主要 ADR / RFC |
|---|---|---|
| `adr-0009/` | Importance scoring + embedding dedup calibration | ADR-0009 |
| `adr-0021/` | Pattern schema extension phases + post-landing audit | ADR-0021 / 0028 / 0029 |
| `adr-0029/` | Smoke-test derived observations | ADR-0029 |
| `adr-0030/` | Withdrawn approach handoff (archived) | ADR-0030 |
| `adr-0049/` | Beautiful Loop Fidelity Audit — Meditation Adapter | ADR-0049 |
| `adr-0053/` | Importance Ablation — Does the LLM Rating Earn Its Keep Beyond Decay? | ADR-0053 |
| `adr-0056/` | §B1 relevance-retune effect measurement (the first gate condition) | ADR-0056 |
| `adr-0060/` | ADR-0060 measurement evidence — per-episode grounded distill | ADR-0060 |
| `adr-0062-parser-rewrite/` | ADR-0062 parser evidence (6th-11th amendments) | ADR-0062 |
| `adr-0064/` | Ollama vs MLX A/B benchmark (speed/memory) + distill pattern-yield comparison | ADR-0064 |
| `adr-0067/` | MLX vs Ollama production A/B telemetry + prefill degradation + upstream failure-mode survey | ADR-0067 / 0065 |
| `adr-0068/` | gemma4:e4b think-on/off vs qwen3.5:9b comment-generation A/B (latency + codex blind judge) | ADR-0068 |
| `adr-0074/` | Incremental-window simulations + novelty calibration; the 2026-07-18 staged-candidate adoption review | ADR-0074 |
| `adr-0080/` | Core commit tags: repair / instrument / capability-growth (P1-01.2) | ADR-0080 |
| `adr-0081/` | T-SKILLSEL-CACHE-COST — プレフィックスキャッシュ仮説の統制 A/B（2026-08-05） | ADR-0081 |
| `adr-0084/` | Offline A/B replay script for the post-distill durability gate | ADR-0084 |
| `adr-0086/` | ADR-0086 evidence — submolt scope, 2026-08-01 | ADR-0086 |
| `adr-0088/` | Sibling conformance gate run — 2026-10-24 | ADR-0088 |
| `adr-0089/` | ADR-0089 evidence — run-to-run stability measurement (2026-08-06) | ADR-0089 |
| `adr-0090/` | IPD null pair (noise floor) + amendment two-arm run + retired 2026-05-05 constitution + AILuminate exploratory report | ADR-0090 |
| `adr-0091/` | 2026-08-15 の identity twin（`identity-2.md`）の dated note — 手当ての経緯と前後の公開 snapshot の対応 | ADR-0091 / 0126 |
| `adr-0092/` | Interpretation Notes — What the Shadow Readings Say About Boundless Care | ADR-0092 |
| `adr-0093/` | Cloud routines（claude.ai/code/routines）の CA への導入検討 | ADR-0093 |
| `adr-0094/` | Reading a ledger rendered before the 2026-08-15 escape change | ADR-0094 |
| `adr-0096/` | Worth-gate offline replay (log + script) and surprise calibration script, 2026-08-17 | ADR-0096 |
| `adr-0102/` | Pre-deletion audit — incident rationale in architecture.md, 2026-09-05 | ADR-0102 |
| `adr-0103/` | wiki 機構（RFC-0017 → 0022 → 0025）の導入から退役までの振り返り — 読みが反転した 4 点（著者と次セッションの LLM 向け、日本語のみ） | ADR-0103 |
| `adr-0105/` | 混同対の読みを本番の selection log に当てた 2026-09-07 の read-only dry run — 14 日 / 7 日 2 窓の読み値、候補ファイルの中身、core と手動計器の一致測定（機構 0 不一致 / 最近傍 5 件差）。skill 名のみ、rejected 名の生文字列は転記しない | ADR-0105 |
| `adr-0106/` | ADR-0106 two-window comment-outcomes reading (P1-04.5) | ADR-0106 |
| `adr-0111/` | ADR-0111 revise table (2026-10-24) | ADR-0111 |
| `adr-0124/` | Q2 compounding axes — first public reading (2026-10-24) | ADR-0124 |
| `constitution-lineage.md` | Constitution lineage — 8 clauses across 4 versions | — |
| `four-principles-coverage.md` | Four principles — mechanism coverage | — |
| `identity-drift/` | identity 版間距離の遡及表（公開木の 4 版、cosine は Ollama 待ち）と Mac で埋める手順 | ADR-0091 amendment |
| `moltbook-platform-readings.md` | Moltbook platform readings | — |
| `p3-05/` | Reproduction run, 2026-10-24 | — |
| `regimes/` | Apparatus boundaries and the longitudinal record (P3-02) | — |
| `releases.md` | Release ledger | — |
| `reproduction-scope.md` | Reproduction scope — what the paper reported, what was checked, and what this project measures itself | — |
| `research-questions.md` | Research questions — evidence table | — |
| `rfc-0011/` | RFC-0011 — submolt スコープ sweep 3 本の読み（2026-09-05） | RFC-0011 |
| `rfc-0014/` | skill 選択計器 第 4 読み（2026-09-05）— RFC-0014 / RFC-0015 | RFC-0014 |
| `rfc-0017/` | skills-on/off baseline の 1 回読み（Face A comment eval、off アームの run.json 凍結。RFC 単位のサブフォルダは初例 — 読みが決定でなく設計セッションの前提を決めるため ADR が無い） | RFC-0017 |
| `rfc-0023/` | Novelty gate: 485 本 vs top-k の差分リプレイ（2026-09-05） | RFC-0023 |
| `rfc-0027/` | 変更理由先行 arm と現行抽出 arm の一回限りの固定セット比較（本番記録から選んだ 12 ケース + 合成 4 件の smoke、軸別の事実のみ。判定はオーナーが読む） | RFC-0027 |
| `rfc-0041/` | RFC-0041 evidence — insight の入口で何が件数を決めているか（2026-09-19） | RFC-0041 |
| `rfc-0043/` | RFC-0043 evidence — skill selection の学習なし 5 arm offline 再生（2026-09-19〜20） | RFC-0043 |
| `rfc-0044/` | RFC-0044 第 2 段 — enum 拘束の受入測定（2026-09-26） | RFC-0044 |
| `rfc-0045/` | RFC-0045 evidence — relevance 判定を Jev との近さで読む（2026-09-24〜25） | RFC-0045 |
| `rfc-0046/` | RFC-0046 evidence — relevance gate の lab ratchet（S35 label set の凍結、2026-10-07） | RFC-0046 |
| `rfc-0047/` | RFC-0047 evidence — face 改善ループの型と face 台帳（2026-09-26 snapshot の凍結） | RFC-0047 |
| `rfc-0051-path-rewrites.md` | RFC-0051 path rewrites in frozen evidence | RFC-0051 |
| `rfc-0054/` | Injection-ablation summary (2026-10-22): the injection changes the output, the content is not carried | RFC-0054 |
| `serving-changes.md` | Serving changes | — |
| `third-party-overlap/` | Third-party word overlap in the public data (P0-03.9) | — |
| `value-history/` | 価値層の版履歴（憲法・identity）の種まきファイルと適用手順 | ADR-0126 |
| `verify-solve-model-compare-20260701/` | qwen3.5:9b vs gemma4:e4b — verify_solve-specific blind replay | — |
| `weekly-gate-step4-comply-20260808/` | weekly-gate Step 4 — skill-comply measurement (2026-08-08) | — |
<!-- evidence-index:end -->

## 昇格ワークフロー

1. 実験スクリプト・1 回限りの調査は `.reports/` で実行 (gitignored、scratch)
2. 成果が ADR の決定根拠になったら `docs/evidence/adr-XXXX/` に `git mv` で昇格
3. 対応する ADR 本文から相対リンクで参照 (`../evidence/adr-XXXX/<file>.md`)

## 書くべきでないもの

- 外部向けリリースノート → `CHANGELOG.md`
- 運用手順（migration, recovery）→ `docs/runbooks/`
- Session checkpoint / cold-start handoff → `.notes/` (gitignored)
- 議論・計画の中間草稿 → `.notes/` (gitignored)
