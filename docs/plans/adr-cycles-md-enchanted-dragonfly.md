# Plan: verification solver の llm_reason 経路を abstain 化（ADR-0062 第 9 amendment）

## Context

T-VER6 再計測（第 7 amendment 運用 10 日 / 921 件）で、最終フォールバック `llm_reason` 経路が
**流入 2.3%（21 件、毎日 1〜5 件で枯れていない）・verify 成功率 38%（8/21）** と判明。
コイントス未満の推測で 10 日あたり誤答 13 件をサーバへ送信しており（全誤答 52 件の 25%）、
`answer_previously_rejected` の蓄積・platform footprint リスクに対し得られる成功は全体の 0.9%。
ユーザー承認済みの方針: **llm_reason を廃し、理由コード付き abstain に置換**（推測せずスキップ、
audit に流入痕跡を残して将来の復活/確定判断を可能にする）。dead になる機構一式は**同 PR で撤去**
（ユーザー選択済み。復元は git revert、所在は amendment に記録）。

- タスク種別: **fix**（chain: Plan → TDD → Review 並列 → Doc Sync → Verify）
- 根本原因確認: 済（audit ログ集計が証拠。debugging.md の確認待ちはこの会話で完了）

## 実装

### 1. `src/contemplative_agent/adapters/moltbook/verification.py`

- `solve_challenge_result()` (285-397): llm_reason 段（359-397 の LLM 呼び出し〜自己整合性チェック〜返却）を撤去し、
  code_parse / llm_extract の両方が答えを出せなかった時点で
  `VerificationSolveResult(answer=None, solver_path="none", abstain_reason="reason_fallback_disabled")` を返す。
  **LLM は呼ばない**（流入計測に would-be 答えは不要 — 38% は測定済み。shadow 化はしない）
- 既存の abstain 分岐は維持: 空 challenge (296-301)、全候補 rejected → `answer_previously_rejected`
  （rejected fall-through は llm_extract で終端するようになる）
- 新理由コードは `_REJECTED_ERROR_MARKER` 付近に module 定数として追加（既存語彙は bare string のまま触らない）
- dead 撤去: `_reason_system_prompt()` / `_DEFAULT_REASON_SYSTEM` / `_extract_answer()` /
  `_reasoning_answer_is_self_consistent()` / `_SOLVER_NUM_PREDICT`
- 変更なし: audit writer (`record_verification_audit`)、`agent.py` 側（`abstain_reason` は既存配線
  `agent.py:516` で audit の `error` 列に乗る）、`VerificationTracker`（abstain は従来通り failure 扱い →
  7 連続失敗 auto-stop が grammar drift の loud な警報として機能する。意図的挙動として amendment に明記）

### 2. パッケージ資産

- `config/prompts/verification_solve_reason_system.md` を削除（唯一の消費者が撤去対象）
- `docs/CONFIGURATION.md` の canonical プロンプト一覧から該当行を削除
- `tests/test_packaged_assets.py` の期待リストを追従

### 3. テスト（TDD — 先に書く。`tests/test_verification.py`）

新規（RED → GREEN）:
- 文法外 challenge + llm_extract 失敗 → `solver_path=="none"`、`abstain_reason=="reason_fallback_disabled"`、
  **LLM 呼び出しが 1 回だけ**（extract のみ。reason プロンプトで 2 回目が飛ばない regression pin)
- llm_extract 候補が全て rejected → `answer_previously_rejected` が引き続き返る（終端の移動を固定）
- audit 統合: abstain 時の record に `error="reason_fallback_disabled"` が乗る（agent 経由）

更新/削除（dead 機構向けテストの整理）:
- 削除: `test_falls_back_to_reasoning_path` / `test_result_records_reasoning_solver_path` /
  `test_reasoning_fallback_rejects_self_inconsistent_trace` / `test_reasoning_fallback_accepts_self_consistent_trace`
- 書き換え: `test_unparseable_output_returns_none` / `test_llm_unavailable_returns_none` /
  `test_solver_uses_bounded_fast_path_and_fails_closed_fallback` / `test_code_parse_rejected_falls_through_to_llm` /
  `test_all_paths_rejected_abstains` → 2 段チェーン + abstain 前提の主張に更新

chaos-TDD 注記（Verify での問いに先回り）: 本 PR は LLM 呼び出しを**除去**する変更で、新規 fault column は
不要。望ましいガード挙動（fall-through → 理由コード付き abstain）は上記新規テストが仕様として主張する。
verification 全体の chaos column 未整備は既知のギャップのまま（スコープ外、台帳に残さない — 発火条件は
「verification に LLM 面を足す次の機会」）。

### 4. Doc Sync（同 PR）

- **ADR-0062 第 9 amendment**（`docs/adr/0062-create-time-verification-handshake.md` + `.ja.md`）:
  既存パターン踏襲（Status 節内の段落 `Ninth amendment 2026-07-20: ...`）。内容 = T-VER6 の計測値
  （21 件 / 38% / 誤答 13 件）、決定（チェーンは code_parse → llm_extract → abstain。solver order を
  **変更する** amendment であることを明記 — 過去の "solver order unchanged" 型とは異なる）、撤去資産の所在、
  abstain が failure tracker に乗る意図、復活基準（`error=reason_fallback_disabled` の流入が高止まりし
  llm_extract 改善で吸収できない場合、recompute ゲート付きの guarded reasoning として再設計 — 素の推測は復活させない）
- **CODEMAPS 3 面**（鮮度規約: 段構成の変更）:
  `architecture.md` Data Flow の verification 節 (117-147, 特に 136 の solver order)、
  `adapters-moltbook.md` §Verification (101-116) + モジュール表 20 行目、
  `moltbook-agent.md` 186 行目の solver order + 232 行目 audit 行
- **graph.jsonld**: ADR-0062 ノードの description が 3 経路 order を記述していれば更新（実装時に確認）
- **`.notes/TASKS.md`**: T-VER6 → Done（読み結果 + 本 fix へのリンク）。新規 observing 行
  `T-VER-ABSTAIN`: 流入再読（`error=reason_fallback_disabled` の日次件数、〜2 週間後）→ 復活/確定判断

### 5. Review（実装後、並列起動）

Parallel Group: **python-reviewer + security-reviewer + codex-review**
（fix × 非自明 diff → codex-review Y。verification は untrusted 入力境界 → security-reviewer Y）
いずれか CRITICAL で停止・報告。

### 6. Verify → commit

1. `uv run pytest tests/ -q`（全件 + coverage 感覚は test_verification 中心に確認）
2. `uv run pyright`（型エラー 0 維持）/ ruff は PostToolUse hook で自動
3. `uv run lint-imports`
4. secret scan は pre-commit hook
5. doc sync 確認（上記 4 の全ファイルが同 diff に居るか）
6. `git status` → diff 提示（人間ゲート）→ 承認後 main 直 commit → push
   （コミット: `fix: retire llm_reason guessing — verification solver abstains past llm_extract (ADR-0062 9th amendment)` 系）

### 7. Post-commit

- graph.jsonld を触った場合のみ HF mirror sync（/hf-sync、実行前にひと言）
- harness memory `project_moltbook_verification_handshake.md` の solver 記述を確認し、
  3 経路記述があれば 2 段 + abstain に更新

## Verification（end-to-end）

- 全テスト PASS + 新規 abstain テストが RED→GREEN を経ること（one-run-not-evidence: RED 確認を必ず挟む）
- `python3 -c "from contemplative_agent.adapters.moltbook import verification"` 相当の import 健全性は pytest が担保
- デプロイ後の実測は T-VER-ABSTAIN（台帳）で追跡: verification-audit.jsonl に
  `error="reason_fallback_disabled"` が記録され、`llm_reason` の新規レコードがゼロになること
