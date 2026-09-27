# モジュール再編計画（アーキテクチャ整理）

## Context

コードベースが約 19,850 行 / 54 ファイルまで成長し、規約上限 800 行を超えるファイルが 7 件に達した（cli.py は 3,037 行で規約の 3.8 倍）。import 方向規約（core ← adapters ← cli）は完全遵守で違反ゼロだが、単一ファイル内の責務同居が進行している。振る舞いを変えない refactor として段階的に再編し、併せて 1 週間分 stale な CODEMAPS を更新する。

## 現状の事実（baseline: commit `a1dd402`、2026-07-18 再検証済み）

- 800 行超: cli.py 3037 / core/llm.py 1507 / moltbook/verification_parse.py 1132 / core/insight.py 1041 / core/distill.py 1013 / moltbook/agent.py 853 / moltbook/client.py 844
- import 規約違反ゼロ。cli.py が唯一の composition root。core 内循環 import なし
- fan-in 上位: `_io` 23（設計意図どおり）、prompts 14、memory 13、llm 13
- テスト patch 集中: `contemplative_agent.cli.*` への patch 254 箇所（全て test_cli.py 内、最多はパス定数の tmp 差し替え）。`core.llm.requests` patch 72 箇所
- sibling repo (cloud / mlx) が `core.llm` の `LLMBackend, BackendResult, configure` と `cli.main` を import
- CODEMAPS stale: INDEX.md 統計乖離（cli 2817L 記載 vs 実 3037L、テスト数・LOC・モジュール数）、ADR-0076/0078 の新モジュール未反映

## 分割要否の判定

| ファイル | 判定 | 根拠 |
|---|---|---|
| cli.py (3037) | 分割（package 化） | 8 責務同居。テスト影響は test_cli.py に閉じる |
| core/llm.py (1507) | 分割（package 化 + 恒久 facade） | 4 系統同居 + fan-in 13 + sibling 依存。facade で import パス完全維持 |
| verification_parse.py (1132) | 現状維持 | 単一責務の決定論パーサ。分割は人工的 seam を作るだけ。ADR に例外記録 |
| core/insight.py (1041) | 分割（novelty フィルタ抽出） | novelty は別 LLM 呼び出し + 独自監査ログ + 独自予算の明確な副責務（~400 行） |
| core/distill.py (1013) | 分割（2 小抽出） | embedding dedup (~180 行) とエピソード描画 (~160 行) が純粋関数群として自己完結 |
| moltbook/client.py (844) | 現状維持 | 超過 44 行。churn に見合わない。例外記録、成長したら再訪 |
| moltbook/agent.py (853) | 現状維持 | 単一 Agent クラス。mixin 分割は可読性を損なう。例外記録 |

**shim の二択原則**: 「恒久 facade（= それが公開 API）」か「作らない（clean break + 同一 commit でテスト更新）」。時限 shim は作らない。理由: mock.patch は存在しない属性への patch で AttributeError を出す = shim なしなら移動漏れが loud に落ちる。shim ありだと patch が silent no-op 化し、cli のパス定数 patch では実データ書き込み事故につながる。

## 新モジュール構成

### Phase 1: `core/llm.py` → `core/llm/` package（テスト churn 最小 — ゼロではない）

```
core/llm/
  __init__.py   (~650) configure/reset、generate 系本体、_post_ollama、import requests、
                       トークン推計・予算 + 全公開シンボル re-export（恒久 facade）
  backend.py    (~250) BackendResult, GenerationOutput, LLMBackend, _CircuitBreaker, circuit_shield
  prompting.py  (~400) システムプロンプト構築、identity 検証、_load_md_files、budget reading、
                       mutable 状態 (_identity_path, _skills_dir, _MD_CACHE) の単一 owner
  guard.py      (~350) validate_trusted_url, _scrub_secrets, sanitize 系, wrap_untrusted_content
```

- transport と `import requests` を `__init__.py` に残す → `patch("...core.llm.requests.post")` 72 箇所が機能的にそのまま生きる
- sibling 2 repo + 内部 13 importer の import パス完全維持
- **facade は source 互換であって patch 互換ではない**（Codex 指摘・確認済み）: `_build_system_prompt` を patch するテスト（test_llm.py:932/947/960 + test_cli.py の adoption-budget 系 ~3 箇所）は、呼び出し元 `system_prompt_budget_reading` が prompting.py 内部参照を解決するため facade 越し patch が効かなくなる → **同一 commit で `core.llm.prompting._build_system_prompt` へ patch パス更新**（~6 箇所の churn）
- mutable なモジュール状態（`_identity_path`, `_skills_dir`, `_MD_CACHE`）は prompting.py を単一 owner とし、facade からは関数のみ re-export（状態のコピー re-export 禁止 — 二重状態化防止）

### Phase 2: `cli.py` → `cli/` package（re-export は `main` のみ）

```
cli/
  __init__.py      (~450) main(), argparse 構築, dispatch, _handle_agent_command
  runtime.py       (~200) logging / LLM runtime 設定
  schedule.py      (~330) launchd 系一式
  approval.py      (~200) 承認・監査ループ
  staging.py       (~180) StageItem, _stage_results
  adopt.py         (~350) _StagedItem, adopt-staged 系
  stocktake_cmd.py (~520) stocktake merge/drop/clean 描画 + handlers
  memory_cmds.py   (~500) distill / insight / rules_distill / amend_constitution handlers
  session_cmds.py  (~350) init / meditate / report / dialogue / sync handlers
```

- 内部シンボル・定数の `__init__` re-export は禁止（silent no-op patch 防止）
- **`cli/__main__.py` を追加**（現 cli.py:3036 の `if __name__ == "__main__"` 相当。`python -m contemplative_agent.cli` の挙動維持 — Codex 指摘）
- **リポジトリルート解決の修正**（Codex 指摘・確認済み）: `Path(__file__).resolve().parents[2]` が cli.py:109 (`_do_init`), :690 (`_run_sync`), :1883 (`_resolve_views_dir`) に 3 箇所。package 化で深さが 1 増えるため、そのまま移すと `src/` を指して schedule install 失敗・sync-data silent no-op・views fallback ミスになる → 共通 `_repo_root()` ヘルパーに集約して移行し、3 箇所それぞれの回帰テストを追加
- **テスト移行インベントリは patch 文字列だけでは不足**（Codex 指摘・確認済み）: 実数は `patch("contemplative_agent.cli.` 275 箇所 + `monkeypatch.setattr(cli_mod, ...)`（plist_sandbox fixture, test_cli.py:534-552）+ `from contemplative_agent.cli import ...` 文。同一 commit で全て機械的書き換え。完了検証 grep は patch 文字列 / patch.object / monkeypatch.setattr / import 文の 4 形態をカバーする
- **plist_sandbox fixture の移行が安全上最重要**（Codex 指摘・確認済み）: 現 fixture は `dir(cli_mod)` で `LAUNCHD_*_PLIST_PATH` を動的発見して tmp に差し替える。定数が cli/schedule.py へ移った後も旧モジュールを走査すると発見ゼロ → `_do_uninstall_schedule` が**ユーザーの実 launchd plist を削除**しうる。fixture を schedule モジュール走査に移行し、「登録済み全 plist パスが差し替え済みであること」を assert するガードテストを追加してから uninstall 系テストを流す
- test_cli.py (3,585 行) も新構成にミラーして分割（同 commit か直後）

### Phase 3a: `core/insight.py` → `core/insight_novelty.py` 抽出（フラット分割）

- novelty フィルタ一式 (~420 行) を移動。insight.py は ~650 行に
- 唯一の silent 化リスク: `generate_full` が両モジュールに存在し patch が成功してしまう → 移行後 grep で novelty テストに旧 patch パスが残っていないことを機械検証（完了条件）
- 前提再確認済み（2026-07-18、commit `6b47e60` のテストリファクタ後）: test_insight.py の patch は `insight.generate_full` 30 箇所 + `insight._extract_skill` 9 箇所に統一済み。novelty 系テストの `generate_full` patch を `insight_novelty.generate_full` へ書き換え、非 novelty 系は据え置き

### Phase 3b: `core/distill.py` → `core/pattern_dedup.py` + `core/episode_render.py` 抽出

- distill.py は ~690 行に。`render_episode` / `summarize_record` は公開名のため 1 行 re-export（恒久扱い）
- テスト更新 4-5 箇所の小規模 churn

## フェーズ構成（各フェーズ独立 commit・独立 green）

| Phase | 内容 | リスク | テスト churn |
|---|---|---|---|
| 0 | ADR 起草（分割方針 + 800 規約例外 3 件 + shim 二択原則） | ゼロ | 0 |
| 1 | core/llm package 化（恒久 facade + prompting patch パス更新） | 低 | ~6 箇所（test_llm 3 + test_cli 3） |
| 2 | cli package 化 + `__main__.py` + `_repo_root()` + test_cli 全面書き換え・分割 | 中 | test_cli.py のみ（275 patch + fixture + import） |
| 3 | 3a insight novelty 抽出 → 3b distill 2 抽出（別 commit 可） | 中 | test_insight ~30, test_distill ~5 |
| 4 | CODEMAPS 全面更新（/update-codemaps、統計再計測込み） | ゼロ | 0 |

- 各フェーズ commit に影響 CODEMAP セクションの最小更新を同梱（CLAUDE.md 鮮度規約）。**全面 refresh は最終 Phase 4 に置く**（Phase 0 で全面更新すると直後の分割で即 stale になる — Codex 指摘を採用）
- Phase 1-3 は各々独立 commit・独立 green。順序は 1→2→3 推奨だが相互依存なし

## 検証

全フェーズ共通:
1. pytest 全件 green + collected 件数が前後一致（テスト消失検出）
2. import 方向 grep 検証（cli submodule → core/adapters 可、逆不可）
3. ruff / pyright（型エラー 0 維持）

フェーズ固有:
- Phase 1: 公開シンボル一括 import smoke + sibling 2 repo（cloud / mlx）のテストをローカル本体に対して実行 + `_build_system_prompt` patch パスの旧形態残存ゼロを grep 確認
- Phase 2: `contemplative-agent --help` + 全サブコマンド `--help` smoke + `python -m contemplative_agent.cli --help` smoke（`__main__.py` 確認）+ 完了検証 grep 4 形態（`patch("contemplative_agent.cli.` が main 以外ゼロ / patch.object / monkeypatch.setattr / import 文）+ plist_sandbox ガードテスト green + `_repo_root()` 3 箇所の回帰テスト green
- Phase 3a: `grep 'insight\.generate_full' tests/` の残存が非 novelty テストのみ

## やらないこと

- verification_parse.py / agent.py / client.py の分割（ADR に例外記録。800 は上限であって目標ではない）
- 400-800 行帯 9 ファイルへの手入れ
- `_io` / prompts / memory のリネーム・移動
- 新抽象の導入（純粋なファイル移動 + import 書き換えのみ）
- 時限 re-export shim

## Cross-model review (Codex) 所見

```
Agent: codex-review（prompt-driven、設計ドキュメントレビュー — ユーザー明示指示）
Verdict: HIGH（設計骨格は妥当、実行計画に具体的な欠落 6 件 → 全件裏取りの上で本計画に編入済み）
Findings (top 3):
  1. [P1] cli package 化で parents[2] ルート解決が壊れる（cli.py:109/690/1883）→ _repo_root() 集約 + 回帰テストで対応
  2. [P1] plist_sandbox fixture (test_cli.py:534) の dir() 動的発見が定数移動後に空振り → 実 launchd plist 削除リスク。fixture 移行 + ガードテストで対応
  3. [P2] llm facade は source 互換であって patch 互換ではない（_build_system_prompt patch 6 箇所は churn 必須）→ Phase 1「churn ゼロ」を撤回し ~6 箇所更新に修正
Files touched: src/contemplative_agent/cli.py:109,690,1883,3036 / tests/test_cli.py:534-552 / tests/test_llm.py:932,947,960
Next action: continue（全指摘を計画に反映済み。総合評価は「boundaries と facade/clean-break の非対称は defensible」）
```

Codex の総評: 分割境界と「llm は恒久 facade / cli は clean break」の非対称は妥当。verification_parse.py / agent.py / client.py を分割しない判断にも同意。欠落していたのは filesystem ルート解決・`__main__` 実行・patch 互換の過大評価・テスト移行インベントリの不足・CODEMAPS 更新タイミングの 6 点で、全件を実コードで確認の上、本計画に反映した。
