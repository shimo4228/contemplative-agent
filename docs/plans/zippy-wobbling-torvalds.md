# T-VERIFY-WORKTREE-PLIST — worktree でパス由来の `claude` 一致が test を落とす

## Context

2026-08-16 から `.claude/worktrees/*` の git worktree で並行セッションを走らせている。
その全セッションで `bash .claude/verify.sh` が赤くなる。原因は 1 件のテストで、
**worktree の repo root パスが `.claude` を含む**ことだけが理由。機械ゲートが worktree で
使えないと、毎回「既知の 1 件」を目視で除外することになり本物の回帰を見落とす。

受け入れ条件は「この worktree で `bash .claude/verify.sh` が緑」。

---

## Phase 0: 前提の照合（結果）

**全 6 件とも検証済み。反証なし。** 実行はすべて cwd（worktree、base commit `7cfbf31`、
working tree clean）で行った。

| # | 前提 | 判定 | 根拠 |
|---|---|---|---|
| 1 | producer が `{{PROJECT_ROOT}}` を repo root 絶対パスへ置換し plist の `<string>` に入れる | 検証済み | `src/contemplative_agent/cli/schedule.py:119`（行ずれなし）。root は `cli/runtime.py:40` の `Path(__file__).resolve().parents[3]` = **cwd でなくソース位置**由来 → worktree の src を使えば worktree root。`config/launchd/com.moltbook.watchdog.plist` の `WorkingDirectory` と script path の 2 箇所に入る |
| 2 | その `<string>` が部分文字列 `claude` を含む | 検証済み | worktree root = `…/contemplative-agent/.claude/worktrees/verify-worktree` → `claude` を含む（`.claude` 由来） |
| 3 | sink がパス由来の `claude` と実行対象の `claude` を区別していない | 検証済み | `tests/test_cli_schedule.py:495-496`（行ずれなし）。`content.splitlines()` から `<string>` を含む**行**を集めて部分文字列検査するだけ |
| 4 | この diff と無関係（base commit でも再現） | 検証済み（実行） | 何も変更していない `7cfbf31` の worktree で `uv run pytest -q` → **`1 failed, 3272 passed, 82 skipped`**。落ちるのは `TestWeeklyPipelineSchedule::test_install_watchdog_creates_plist` の `assert not True` 1 件だけ |
| 5 | main チェックアウトでは通る | 検証済み（パス形状） | main root `~/MyAI_Lab/contemplative-agent` は `claude` も `uv ` も含まない（`contemplative-agent` に `claude` は現れない）。main 側では何も実行・書き込みしていない |
| 6 | 同型の脆いアサーションが他に無いか | 検証済み | `tests/` 全体で `<string>` 行を集める部分文字列検査は :495 の 1 箇所のみ。同ファイル :261-264 と :700 は既に**要素値**を取り出す形（下記） |

### 副次の観測（今回は直さない）

- `tests/test_cli_schedule.py:61` `assert "/contemplative-agent" in content` は
  `WorkingDirectory` のパスにも一致するため、`ProgramArguments` から binary が消えても
  通る **false-PASS** の余地がある。同じ欠陥クラスだが赤の原因ではなく HIGH でもないので、
  台帳の規約どおり**起票せず commit message に 1 行残す**。
- `scripts/pipeline_watchdog.sh:13-16` の HARD CONSTRAINT（no claude / no uv / no python）は
  **script 本体に対する機械ゲートが存在しない**。:496 は plist しか読んでおらず、
  今回の変更で失われるものではない（前も無かった）。同じく commit message に 1 行。

### 既存の手本（新規発明ではない）

同ファイルに「行でなく要素として読む」形が 2 つある。今回はその系列に乗せる。

- `:261-264` — PATH の `<string>` を正規表現で取り出し `:` 分割して**要素の完全一致**
- `:700` — `ProgramArguments` の array を切り出して `<string>` の**要素値**を集合比較

さらに、**レンダリング済み** plist は `plistlib.loads()` で構造として読めることを実測で確認した
（`ProgramArguments: ['bash', '…/scripts/pipeline_watchdog.sh']`、prose コメントは消える）。
テンプレート側（`:700`）が正規表現なのは `{{CALENDAR_INTERVALS}}` 等の placeholder で
XML として不正だからで、レンダリング後にはこの制約が無い。

---

## 実装案（テストのみ。production コードは 1 行も変えない）

### 1. `tests/test_cli_schedule.py` にモジュール階層のヘルパを 2 つ足す

```python
def _program_arguments(content: str) -> list[str]:
    """launchd が実行する argv を、レンダリング済み plist の要素として読む。"""
    return plistlib.loads(content.encode("utf-8"))["ProgramArguments"]


def _invoked_commands(argv: list[str]) -> set[str]:
    """argv が起動しうるコマンド名（basename）。inline shell の語も展開する。"""
```

- `_invoked_commands` は各要素を `shlex.split()` してから `PurePosixPath(token).name` を取る。
  - パス `…/.claude/worktrees/wt/scripts/pipeline_watchdog.sh` → basename は
    `pipeline_watchdog.sh` なので**パスに何が含まれていても一致しない**
  - `["claude", "-p", …]` → `claude` を捕らえる
  - `["bash", "-c", "claude -p x"]` → shlex 展開で `claude` を捕らえる

### 2. `test_install_watchdog_creates_plist`（:485-498）の主張を構造で言い直す

```python
argv = _program_arguments(content)
assert PurePosixPath(argv[0]).name == "bash"          # pure bash entrypoint（正の pin）
assert not {"claude", "uv"} & _invoked_commands(argv)  # 起動対象に claude / uv が無い
```

元の主張（「watchdog が claude / uv CLI を起動しない」）を弱めない。むしろ
`argv[0]` が bash であることを新たに pin するので**厳しくなる**。`<string>` 行の網は
「値なら何でも引っかかる」偶然の広さで、実行対象という主張の外側（`WorkingDirectory`・
ログパス・Label）まで巻き込んでいたもの。launchd が実行するのは `ProgramArguments` だけなので、
そこに絞ることは主張の精密化であって縮小ではない。

### 3. 回帰テストを 2 本足す（両方向を主張する）

- **通ること**: `tmp_path` に `…/.claude/worktrees/wt/` 形の偽 repo root を作り
  （`.venv/bin/` と実テンプレートを置く）、`contemplative_agent.cli.runtime._repo_root` を
  patch して**本物の producer**に plist を書かせ、上の検査が通ることを主張する。
  読解でなく producer を通した再現なので、パス形状の回帰を実際に捕らえる。
- **捕らえること**: `plistlib.dumps` で作った plist を parametrize で 2 形
  （`["claude", "-p", …]` 直接起動 / `["bash", "-c", "claude -p …"]` inline shell）与え、
  検査が発火することを主張する。前者だけだと「弱めただけ」になるので必須。

### やらない直し方（制約の再掲）

assert の削除 / skip、`if "worktree" not in path` 型の環境分岐、
`"/claude" in line` のような今のパスだけを避ける部分文字列いじり。

---

## 変更するファイル

- `tests/test_cli_schedule.py` — ヘルパ 2 つ追加、:495-496 の書き換え、回帰テスト 2 本追加、
  `plistlib` / `shlex` / `PurePosixPath` の import 追加
- **production コードは変更なし**

---

## 検証

1. `uv run pytest tests/test_cli_schedule.py -v` — 全 PASS（現在は 1 failed / 40 passed）
2. `uv run pytest -q` — `0 failed`（現在は 1 failed / 3272 passed）
3. **`bash .claude/verify.sh` を worktree で実行 → 緑**（これが受け入れ条件そのもの）
4. Review agent 群（決定論 Verify 全 PASS でも省略しない）+ `/implementation-chain` の
   種別判定（fix）に従う chain

## 手順（承認後）

1. `claims.py claim T-VERIFY-WORKTREE-PLIST`（`CLAUDE_PROJECT_DIR` をメイン側に固定）
2. `.notes/premise-check-T-VERIFY-WORKTREE-PLIST.md` に上記 Phase 0 を書く（30 行以内）
3. `/implementation-chain` → TDD で実装
4. Review agent 群 → `bash .claude/verify.sh`
5. commit（**push しない・main へ merge しない**。branch `task/verify-worktree` に置く）
6. `claims.py release … --outcome done --commit <SHA>` → 台帳 frontmatter を `state: done`
