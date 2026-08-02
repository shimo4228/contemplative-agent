#!/usr/bin/env bash
# scripts/check-sibling-backends.sh — run the ADR-0088 conformance kit against
# every known sibling backend, from main.
#
# Why this lives in main rather than as CI in each sibling: the failure being
# addressed is that contemplative-agent-cloud drifted for three months WHILE
# HOLDING its own conformance test. Anything that depends on the sibling
# staying maintained inherits that failure. Running from main means a sibling
# can be untouched for a year and still be measured — the sibling side needs
# no test file, no workflow, and no maintenance.
#
# Exit: 0 = every present sibling conforms, 1 = at least one does not,
#       2 = a target or the kit could not be used.
#
# Siblings that are not checked out are reported as absent and do NOT fail the
# run — a clone of main alone has none of them. What is never allowed is
# silence: every entry prints a line saying which of the three it was.

set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P) || exit 2
SIBLING_ROOT=$(dirname "$ROOT")

command -v uv >/dev/null 2>&1 || { echo "[sibling] uv が無いため実行できません"; exit 2; }

# repo-directory | import target | constructor kwargs (space separated, may be empty)
#
# Kwargs exist only to reach the constructor; nothing here contacts a provider.
# The static checks never call generate(), so the values are placeholders and
# no credential is needed or read.
TARGETS=(
  "contemplative-agent-mlx|contemplative_agent_mlx.backends.mlx:MlxLmBackend|base_url=http://localhost:8080 model=conformance-probe"
  "contemplative-agent-cloud|contemplative_agent_cloud.backends.anthropic:AnthropicBackend|"
  "contemplative-agent-cloud|contemplative_agent_cloud.backends.openai:OpenAIBackend|"
)

FAIL=0
UNUSABLE=0
checked=0
absent=0

for entry in "${TARGETS[@]}"; do
  IFS='|' read -r repo target kwargs <<<"$entry"
  src="$SIBLING_ROOT/$repo/src"

  if [[ ! -d "$src" ]]; then
    printf '[sibling] absent  %-28s %s\n' "$repo" "(not checked out — skipped)"
    absent=$((absent + 1))
    continue
  fi

  args=()
  for pair in $kwargs; do
    args+=(--kwarg "$pair")
  done

  checked=$((checked + 1))
  # "${args[@]+...}" guards the empty-array case: under `set -u`, bash 3.2
  # (the macOS system bash) treats a bare "${args[@]}" on an empty array as an
  # unbound variable and aborts. That aborted the RUN rather than the check,
  # so a conforming backend would have been reported FAILED — a gate that
  # convicts on a shell error is worse than no gate.
  if out=$(PYTHONPATH="$src" uv run --project "$ROOT" --quiet \
      python -m contemplative_agent.testing --backend "$target" \
      "${args[@]+${args[@]}}" 2>&1); then
    printf '[sibling] ok      %s\n' "$target"
  else
    status=$?
    if [[ $status -eq 1 ]]; then
      printf '[sibling] FAILED    %s (exit %d)\n%s\n' "$target" "$status" "$out"
      FAIL=1
    else
      printf '[sibling] UNUSABLE  %s (exit %d)\n%s\n' "$target" "$status" "$out"
      UNUSABLE=1
    fi
  fi
done

if [[ $UNUSABLE -ne 0 ]]; then
  printf '[sibling] %d checked, %d absent, UNUSABLE TARGET OR KIT\n' "$checked" "$absent"
  exit 2
fi

printf '[sibling] %d checked, %d absent, %s\n' \
  "$checked" "$absent" "$([[ $FAIL -eq 0 ]] && echo 'all conforming' || echo 'NON-CONFORMING')"
exit $FAIL
