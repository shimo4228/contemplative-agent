# 週次レポート以降の diff を simplify する

## Context

2026-08-14 週次レポート（生成 8/15 09:14–10:30）以降、main に 22 commit・11,435 行追加が
積まれた。台帳 3 層化（ADR-0094）、weekly pipeline の権限境界締め、ADR Status 整合の
ゲート化。その大半が review 指摘を 1 件ずつ閉じる形で着地しているので、同じ問題の解が
複数ファイルに独立に生えている可能性がある。quality 軸で 1 回通す。

**レビュー群は回さない。** この 22 commit は既に code-reviewer / security-reviewer /
codex-review を通した後のもの。ADR-0039 の順序（Simplify → Review）は同一 chain 内の話で、
レビュー済みの commit に対して再度回すと終わらない。

## Step 1 — `/simplify` を範囲指定で実行

```
/simplify 0cfe6f2..HEAD
```

- `0cfe6f2` = 週次レポート生成直前の最後の commit
- working tree は clean で変更は既に main 上の commit なので、**範囲の明示が必須**。
  既定 target（現在の diff）のままだと対象ゼロになる
- target 引数が効かない場合は `git diff 0cfe6f2..HEAD` を対象として明示的に渡す

**何を冗長と見るかは skill に任せる。** コード・コメント・docstring の切り分けも事前には
しない。参考として測っておいた密度（判断の材料であって、指示ではない）:

| ファイル | 現状 | comment + docstring |
|---|---|---|
| `scripts/tasks.py` | 1204 行 | 555 行 (46%) |
| `scripts/ledger_condition_scan.py` | 664 行 | 363 行 (54%) |
| repo `src/` 中央値 | — | 30% |

## Step 2 — Verify

```bash
cd ~/MyAI_Lab/contemplative-agent
uv run ruff check src/ tests/ scripts/
uv run lint-imports
uv run pytest tests/ -q
```

範囲固有の確認: `python3 scripts/tasks.py render` が `.notes/TASKS.md` と byte 一致すること
（store は gitignored なので、この経路が唯一の災害復旧）。

`.claude/verify.sh` は eval baseline の staleness で exit 1 のまま（d190f4f 由来の既知の失敗、
本変更とは無関係）。他のゲートは全て通ること。

## Step 3 — commit

`/simplify` の出力を確認してから single commit。
