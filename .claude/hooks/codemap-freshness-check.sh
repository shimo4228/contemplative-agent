#!/bin/bash
# PostToolUse(Bash) hook: codemap freshness check (CLAUDE.md 鮮度規約).
#
# Fires after a `git commit` lands. If the new HEAD touches a
# mechanism-bearing core module but NOT docs/CODEMAPS/architecture.md,
# inject additionalContext so the agent amends before pushing.
# Deterministic + precise: silent unless the mismatch actually exists.

INPUT=$(cat)

python3 - "$INPUT" << 'PYEOF'
import json
import subprocess
import sys
import time

try:
    data = json.loads(sys.argv[1])
except (IndexError, json.JSONDecodeError):
    sys.exit(0)

command = (data.get("tool_input") or {}).get("command", "")
if "git commit" not in command or "--dry-run" in command:
    sys.exit(0)

def git(*args):
    r = subprocess.run(
        ["git", *args], capture_output=True, text=True, timeout=10
    )
    return r.stdout.strip() if r.returncode == 0 else ""

# Only react to a commit created just now (guard against failed commits
# re-reporting an older HEAD).
head_ts = git("log", "-1", "--format=%ct")
if not head_ts or time.time() - int(head_ts) > 60:
    sys.exit(0)

files = git("show", "--name-only", "--format=", "HEAD").splitlines()
if not files:
    sys.exit(0)

MECHANISM = {
    "thresholds.py", "knowledge_store.py", "distill.py", "views.py",
    "insight.py", "rules_distill.py", "constitution.py", "clustering.py",
}
touched = sorted(
    f for f in files
    if f.startswith("src/contemplative_agent/core/")
    and f.rsplit("/", 1)[-1] in MECHANISM
)
codemap_updated = "docs/CODEMAPS/architecture.md" in files

if touched and not codemap_updated:
    msg = (
        "[Codemap 鮮度チェック] 直前の commit は機構系 core モジュール "
        f"({', '.join(f.rsplit('/', 1)[-1] for f in touched)}) を変更しましたが、"
        "docs/CODEMAPS/architecture.md は更新されていません。"
        "この変更がゲート・式・閾値・パイプライン段構成を変えたなら、"
        "push する前に Data Flow セクションを更新して `git commit --amend` するか"
        "追加 commit してください (CLAUDE.md 鮮度規約)。"
        "機構に触れない変更 (コメント・rename・docstring のみ) なら無視して進んでください。"
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg,
        }
    }))
PYEOF
exit 0
