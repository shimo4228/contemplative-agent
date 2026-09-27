# T-GUARD — Phase 0 前提照合の結果（実装案なし・停止）

## Context

T-GUARD は「staging pending ガードの fast-fail を insight 以外の producer にも hoist する」タスク。
Phase 0 で台帳の前提を実コードで照合したところ、**前提 3 が反証された**。指示の規約に従い、
実装案は書かず、台帳の直し方の提案だけを出して止まる。

作業は worktree `~/MyAI_Lab/contemplative-agent/.claude/worktrees/staging-guard`
（branch `task/staging-guard`）で行い、ファイルは 1 つも編集していない。

**claim は未実行**（plan mode が非 read-only 操作を禁じているため）。承認後すぐ
`claims.py claim T-GUARD --label "staging pending ガードの fast-fail を全 producer へ"` を打つ。

## Phase 0 結果

| # | 前提 | 判定 | 根拠 |
|---|---|---|---|
| 1 | `_stage_results` の呼び出し口は 4 つ | **検証済み（表は不完全）** | `staging.py:131` / 呼び出しは `memory_cmds.py:247, 373, 426` と `stocktake_cmd.py:620` の 4 つ。新規 producer なし |
| 2 | fast-fail を持つのは insight だけ | **検証済み** | `memory_cmds.py:336-346` のみ。:247 / :426 / stocktake:620 の手前に検査なし |
| 3 | `_run_stocktake_phases` に fast-fail を置けば grouping を節約できる | **反証** | 下記 |
| 4 | pending 時に batch は捨てられる（＝効率の改善であって正しさの改善ではない） | **検証済み** | `staging.py:162-174` が `return False`、wipe/write は :176 以降。前倒ししても捨てられること自体は変わらない |

台帳が引用する行番号（`memory_cmds.py:247/336-346/339/364-370/373/426`、`staging.py:162-174`、
`stocktake_cmd.py:620`）は**全部ずれていない**。台帳は鮮度としては新しく、壊れているのは 1 箇所の構造理解だけ。

## 反証の中身（前提 3）

grouping の LLM コールは `_run_stocktake_phases` の**外で既に終わっている**:

```
_handle_skill_stocktake       stocktake_cmd.py:777  run_skill_stocktake(...)   ← LLM grouping はここ
  └ core/stocktake.py:582       _find_duplicate_groups(...)  （generate_full、think-ON、全コーパス 1 コール）
_handle_stocktake_result      stocktake_cmd.py:553  → _run_stocktake_phases(run, result)
  └ stocktake_cmd.py:614-617    merge / drop / clean / describe   ← 残るのはここだけ
  └ stocktake_cmd.py:620        staging._stage_results(...)
```

`:614` の前に置いたガードが節約するのは merge / clean / describe だけで、これらは
`merge_groups` / `quality_issues` / `clean_prompt` が無ければそもそも発火しない条件付きコール
（`:599-603` の early return）。**stocktake で一番高い grouping コールは救えない。**

### 同じ誤りが単発系にもある

台帳 第一手 2 は `_handle_single_result` も挿入先に挙げているが、この関数にも LLM 処理は無い。
LLM は呼び出し元で済んでいる（`_handle_distill_identity:289` の `distill_identity(...)`、
`_handle_amend_constitution:460` の `amend_constitution(...)`）。

つまり**単一の系統的な誤り**: 台帳の表は `_stage_results` の**呼び出し口**を列挙していて、
第一手 2 がそれを**挿入点**と取り違えている。全ケースで LLM コールは 1 段上の呼び出し元にあるので、
この 2 つは構造的に別物。

## 副次：表が取りこぼしている producer

`--stage` を持つコマンドは 6 つあり（`_add_stage_argument` の登録先: distill-identity /
rules-distill / amend-constitution / insight / skill-stocktake / rules-stocktake）、
4 つの呼び出し口を共有している。台帳の表は `amend-constitution` を「等の単発系」に畳み、
**`rules-stocktake` を 1 行も書いていない**（`_handle_rules_stocktake:806` が `run_rules_stocktake`
→ 同じ :620 の call site へ合流）。

結果、第一手 1 の「4 箇所で同じ文言・同じ判定を再実装しない」は数を取り違えている。
実際の挿入点は **5 箇所**（insight の既存分を除く）:

| 挿入点 | LLM コール |
|---|---|
| `memory_cmds.py:_handle_distill_identity` :288 の直前 | `distill_identity` :289 |
| `memory_cmds.py:_handle_amend_constitution` :459 の直前 | `amend_constitution` :460 |
| `memory_cmds.py:_handle_rules_distill` :415 の直前 | `distill_rules` :416 |
| `stocktake_cmd.py:_handle_skill_stocktake` :776 の直前 | `run_skill_stocktake` :777 |
| `stocktake_cmd.py:_handle_rules_stocktake` :805 の直前 | `run_rules_stocktake` :806 |

## 台帳の直し方（提案・オーナー判断）

**推奨: `state: ready` のまま、第一手 2 と表を差し替える。** `candidate` 戻しも `dropped` も要らない
— タスクの目的（高価な処理の前に fast-fail を hoist する）は生きていて、反証されたのは挿入点の
特定だけ。修正内容は上の 2 つの表で確定している。具体的には:

1. 表の見出しを「呼び出し口」から**「staging call site」と「挿入点（＝ LLM コールの直前）」の 2 列**に
   分ける。取り違えの再発をここで塞ぐ
2. `rules-stocktake` の行を足し、`amend-constitution` を「等の単発系」から独立させる（4 → 5 挿入点）
3. 第一手 2 の「`_handle_single_result` / `_run_stocktake_phases` の LLM 処理の前に置く」を
   「5 つの**ハンドラ**の LLM コールの直前に置く（この 2 関数には LLM 処理が無い）」に直す
4. 第一手 3 の回帰テストも 4 → 5 producer に増える

分割は要らないと見ている（1 つの機械的パターンが 2 ファイル 5 箇所に出るだけ）。ただし
`rules-stocktake` は台帳が一度も検討していない producer なので、オーナーが「スコープ外」と
判断するなら 4 箇所に留める選択もある — **これは私の判断ではなく確認したい点**。

## 承認後にすぐやること

1. `claims.py claim T-GUARD`（上記の形）
2. `.notes/premise-check-T-GUARD.md` に本 Phase 0 結果を 30 行以内で書く
3. 台帳 `.notes/tasks/T-GUARD.md` の修正（上記 1-4）— **修正して止まるのか、続けて実装まで行くのかは
   承認時に指示がほしい**

実装には入らない。前提が 1 つ反証されている状態で書いた実装案は、起票より証拠が少ないコード変更になる。

## 確認したこと（読んだだけ・変更なし）

- `staging.py:66-128, 131-199`、`memory_cmds.py:223-470, 535-600`
- `stocktake_cmd.py:502-628, 771-830`、`core/stocktake.py:554-643`
- `tests/test_cli_memory.py:93-107`（`TestInsightStagePathADR0074`、helper `_run(..., prefill_staging=)` は
  台帳の記述どおり実在）、`tests/chaos.py:98-110`（`ChaosBackend.calls` list があるので
  「LLM backend が一度も呼ばれない」を呼び出し回数で主張できる）
