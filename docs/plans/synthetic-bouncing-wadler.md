# コードダイエット計画 — 義務の再均衡 + 削除トランシェ

## Context

著者の観測「多重レビューの連鎖で行数が増えた」を実測で検証した結果、直接のレビュー修正は成長の 4.1% に過ぎず、実体は **(a) 機構層 ADR スライス（計器・週次機構・eval 層）の連打**（8 月 +35.5k 行、総量は 4 ヶ月で 29k→93.5k の 3.2 倍）と **(b) 建立側だけの義務**（ADR-0075 監査ログ + ADR-0077 fault column が全機能に適用され、テストが成長の 57%）だった。畳む側は任意（Review-when を持つ ADR は 99 本中 4 本）という非対称が在庫を構造的に単調増加させている。北極星（ADR-0080: 機構層は止まるのが完成）と逆行。

解は ADR-0095 の先例に従い**機構でなく整理**: 義務の再均衡（3 commit）→ 死物の削除（4 commit）→ 読み窓での計器退役（ゲート判断）→ 溶解義務の遡及棚卸し。

## 著者決定（2026-08-29）

1. **fault column 義務（ADR-0077）完全退役 + skill `chaos-tdd-fault-injection` 退場。既存 fault テストは維持**（削除コードと連動でのみ消える）
2. **監査ログ義務（ADR-0075）は常駐 production 経路（run/distill/insight/publish/verification）に限定**（dated amendment）。read-only 計器・一発測定は docs/evidence 凍結で代替
3. **溶解の義務化（新 ADR-0101）**: 新計器の ADR/RFC に消費計画（いつ・何回読む・満了時撤去）必須。既存計器へは遡及棚卸し（T4）

## 前提検証の結果（設計 agent、HEAD 64393cf で確認済み）

- `retrieval_recall_measure.py`（1,325 + tests 1,401）は **T0 から除外・延期**: ADR-0097 Review-when の recall@5 条件が「将来の手動測定」を読む未実施 arm（docs/evidence/adr-0097/ 不存在）+ RFC-0017（draft）が抽出側への転用を予約。RFC-0017 の設計決着時に再判断
- `coselection_families.py` は削除可: RFC-0013 は `withdrawn`（2026-08-26 終端）、正準数値は ADR-0097 Note に凍結済み。復元点は git 履歴（ADR-0097 に日付注記）
- worktree 3 本は消滅（RFC-0016/0018/0019 は本日 main 着地済み）— 衝突制約は解消
- coverage の機械 floor は存在しない（pytest -q のみ。80% は harness 方針）。削除は code+tests 同時なので中立
- `~/Library/LaunchAgents/` に weekly-analysis の legacy plist は**未インストール** — uninstall shim 不要
- `integrations/skills/rules-distill-ca/` は **untracked**（gitignored）— tracked 変更は install.sh の 1 行のみ

## 実装 — commit 順序（義務変更が先、削除が後）

理由: 義務変更前に削除 commit を積むと、CLAUDE.md がまだ義務を主張している状態でレビューされる。
全 commit: **pathspec 明示で stage**（`git add -A` 禁止 — working tree に土曜ゲート待ちの rfcs/*.md 17 本あり）、`.claude/verify.sh --staged` → full。git 操作は skill `git-workflow` 準拠。

### Commit 1 — ADR-0100: chaos-TDD by-default 義務の退役

- 新規 `docs/adr/0100-retire-chaos-tdd-by-default-mandate.md` + `.ja.md`（partially-supersedes ADR-0077）。Decision: 義務退役（fault column は TDD 時の opt-in 判断へ）/ skill 退場 / 既存 fault テスト維持 / tests/chaos.py は importer が居る間残置。Review-when: 既存 column が捕まえたはずの障害クラスが 2 回再発 → 再訪; chaos.py importer 0 → kit 削除
- `docs/adr/0077-*.md` + `.ja.md`: Status → `partially-superseded-by ADR-0100` + 存続範囲 1 文
- `docs/adr/README.md` + `README.ja.md` index 更新、`graph.jsonld` に 0100 node + 相互 partial edges（`test_partial_supersede_edges_are_reciprocal` が強制）
- `CLAUDE.md`: 開発原則の Chaos-TDD 項（~L88）削除 + skill 表の行（~L128）削除（AGENTS.md は symlink、編集不要）
- `.claude/skills/chaos-tdd-fault-injection/` 削除（tracked）。`.claude/skills/llm-pipeline-layering/SKILL.md:3` の参照 1 箇所修正
- 検証: `uv run pytest tests/test_adr_status_consistency.py -q`（en/ja/index×2/graph の 5 面一致）→ verify full
- 注: ADR 番号は commit 直前に `docs/adr/` を再列挙（並行採番の衝突回避。現在の次番は 0100/0101）

### Commit 2 — ADR-0075 dated amendment（新 ADR ではない）

- `docs/adr/0075-*.md` + `.ja.md` Status に追記: 「Amended 2026-08-29: 義務は常駐 production 経路（run/distill/insight/publish/verification）に限定。read-only 計器・一発測定スクリプトは対象外、docs/evidence への結果凍結で代替」。index の status セルは `accepted` のまま（0077 の amendment 前例に同じ）
- `CLAUDE.md` Observability 項（~L87）に同じ限定句を追記
- 実行時確認: `.claude/skills/replayable-audit-logs` / `read-only-instruments` が全機能義務を主張していれば 1 行の scope 注記

### Commit 3 — ADR-0101: 計器の溶解義務

- 新規 `docs/adr/0101-instrument-dissolution-mandate.md` + `.ja.md`。Decision: 新計器の ADR/RFC は (a) 誰が・いつ読むか (b) 何回の読みで何を決めるか (c) 満了時の撤去条件 を必須記載。書けない計器はゲートで不採択。Rollout 節が T4（週次機構 ~17.8k 行への遡及棚卸し手順）を定義。Review-when: 連続 2 回の棚卸しで退役候補ゼロかつ新計器ゼロ → ADR-0071 prose へ畳む
- `CLAUDE.md` 開発原則に溶解義務の 1 項追加。index + graph.jsonld 更新

### Commit 4 — T0-a: 消費者ゼロの計器・道具の退役（src/ 変更なし、~2.1k 行）

- 削除: `scripts/coselection_families.py`(912) / `tests/test_coselection_families.py`(726) / `scripts/offwindow-run.sh`(129) / `tests/sampling_probe.py`(296)
- `docs/adr/0097-*.md` + `.ja.md` unit-C Note（L85-93 付近）に日付注記: 計器は 2026-08-29 退役、数値はこの Note と RFC-0013 Status が正準、RFC-0013 再提起条件を試す時は削除 commit から git 復元
- `docs/adr/0047-*.md` + `.ja.md` に 1 行注記（probe 削除済み、結果は ADR 本文が保持）
- `docs/CODEMAPS/moltbook-agent.md:245` / `architecture.md:891` の operator-run instruments 記述を更新
- **残すもの**: `scripts/_scan.py` / `_stats.py` / `tests/test_stats.py`（dead_code_scan / docs_consistency_scan が import）

### Commit 5 — T0-b: `enrich` の除去（deprecated no-op、~40 行）

- `cli/memory_cmds.py`: `_handle_enrich`(214-222) / `_add_enrich_arguments`(536-537) / CommandSpec(578-586) / docstring(1)
- `core/distill.py::enrich`(210-221) — docstring が「CLI のために残す」と自己申告、CLI と共に死ぬ
- `tests/test_distill.py`: import(:18) と `test_enrich_returns_zero`(:402-404)
- `docs/CODEMAPS/moltbook-agent.md:183` の行削除。architecture.md Data Flow は変更不要（enrich は非掲載 — 実行時に再 grep）

### Commit 6 — T0-c: `--weekly-analysis` 単独 install 経路の除去（T0 最終、stats 同期）

- `cli/schedule.py`: 定数(:30/:57)、installer(:195-209)、dispatch(:460-465/:528-531)、排他 parser.error(:496-497)、flags(:595-609)、help(:632/:681)、`--uninstall` エントリ(:370)、stale-reconcile 分岐(:386/:404-407)。`--weekly-pipeline` の docstring/help を過去形へ
- 削除: `config/launchd/com.moltbook.weekly-analysis.plist`。**`scripts/weekly-analysis.sh` は残す**（weekly-pipeline.sh:270 が stage 1a で呼ぶ）
- `tests/test_cli_schedule.py`: 該当スライス除去（tests :321-356, :395-416, :623-634 / kwargs・fixture :435, :454-456, :479-487, :664, :687, :753, :769 / import :23）
- 同 commit doc-sync: `CLAUDE.md:58` / `docs/CODEMAPS/moltbook-agent.md:203-204,218-219` / `docs/CONFIGURATION.md:61,387,392-393` / ADR-0085 Status に 1 行日付注記（en+ja）
- `docs/CODEMAPS/INDEX.md` Statistics を**トランシェ全体分まとめて live 再計測**（節内のコマンドで）
- commit message に記録: 「legacy plist は本番機で不在確認済み。他所で見つけたら launchctl unload + rm」

### Commit 7 — T0-d: rules-distill-ca の鏡の除去

- `integrations/claude-code/install.sh:23` から `/rules-distill-ca` を削除（tracked はこれだけ）
- commit 外のローカル作業: `integrations/skills/rules-distill-ca/` 削除、`skill-stocktake-ca` / `distill-identity-ca` の SKILL.md:18 相互参照を修正（untracked）

### Push

全 commit green 後に main へ直 push（push-workflow: branch/PR なし、sandbox 無効化）。

## 後続トランシェ（このプランでは実行しない — 各ゲートで判断、削除リストだけ事前確定）

- **T2a（読み窓 2026-09-03、RFC-0011）**: 退役なら `adapters/moltbook/submolt_scope.py`(819) + `tests/test_submolt_scope.py`(1,173) + cli 4 ファイルの参照(12/3/12/31) + plist（**本番機にロード済み → launchctl uninstall 手順必須**）+ ADR-0086 / CLAUDE.md:54-55 / codemaps
- **T2b（読み窓 2026-09-05、RFC-0014/0015）**: 退役なら `core/selection_metrics.py`(1,059) + `never_selected_metrics.py`(808) + `selection_window.py`(170) + 5 テストファイルのスライス + `report --skill-selection` 配線。**窓まで selector 系ファイルは凍結（T0 は非接触を確認済み）**
- **T3（~2026-11、RFC-0012）**: shadow-constitution 消費後、`core/constitution_shadow.py`(278) + tests(470) + CLI + CLAUDE.md:49。skill `shadow-mode-validation` は汎用ノウハウとして残す
- **T4（ADR-0101 rollout）**: 週次機構 ~17.8k 行の遡及棚卸し — 消費計画を書けない計器は土曜ゲートで退役候補化。判定は所有 ADR への日付注記で記録
- **RFC-0017 決着時**: `retrieval_recall_measure.py` + test（2.7k）の去就を再判断（ADR-0097 Review-when arm の書き換えと同時）

## 期待効果

- 即時（T0）: 約 **−2.5k 行** + 規約 2 本の退役/限定 + skill 1 本退場
- 窓判断で最大: T2 −5.3k / T3 −0.75k / 延期分 −2.7k
- 構造効果: テスト複利（成長の 57%）の元栓と、建立/溶解の非対称の是正 — 以後の在庫増加が止まる

## スコープ外（触らない）

既存 fault テスト全部 / `tests/chaos.py` / `src/contemplative_agent/testing/`（ADR-0088）/ `verification_parse.py` / `docs/evidence/**`（凍結）/ `scripts/weekly-analysis.sh` / 既存 `rfcs/*.md` の内容（本日ゲート所有。新規 RFC も不要）/ selector 系 3 ファイル（9/5 まで）/ 本日着地した RFC-0016/0018/0019 のファイル / 公開 fork repo（chaos-tdd-fault-injection の GitHub repo 等）

## 検証（各 commit）

1. `.claude/verify.sh --staged`（pre-commit hook でも発火）
2. ADR/graph commit: `uv run pytest tests/test_adr_status_consistency.py -q`
3. テスト変更 commit: `.claude/verify.sh`（full = ruff / pyright / lint-imports / bandit / pip-audit / pytest 全 ~3.7k）
4. Commit 6 後: `uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing` で coverage を commit message に記録 + `contemplative-agent install-schedule --help` smoke + INDEX.md Statistics と live 再計測の一致確認

## Critical files

- `CLAUDE.md`（開発原則 2 項変更 + 1 項追加 + skill 表 + :58）
- `docs/adr/0100-*.md`(新) / `0101-*.md`(新) / `0077-*.md` / `0075-*.md` / `0097-*.md` / `0085-*.md` / `0047-*.md`（+ 各 .ja.md）/ `README.md` index ×2 / `graph.jsonld`
- `src/contemplative_agent/cli/schedule.py` / `cli/memory_cmds.py` / `core/distill.py`
- `tests/test_cli_schedule.py` / `tests/test_distill.py`
- 削除: `scripts/coselection_families.py` / `tests/test_coselection_families.py` / `scripts/offwindow-run.sh` / `tests/sampling_probe.py` / `config/launchd/com.moltbook.weekly-analysis.plist` / `.claude/skills/chaos-tdd-fault-injection/`
- `docs/CODEMAPS/INDEX.md`(Statistics) / `moltbook-agent.md` / `architecture.md` / `docs/CONFIGURATION.md`
