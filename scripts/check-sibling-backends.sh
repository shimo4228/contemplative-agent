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
# There is no `--decision` target below on purpose: no DecisionBackend
# implementation exists outside this repository (ADR-0112), so the kit's decision
# contract has nothing to measure here. Add a target when one appears.
#
# Output (P1-11.13): each present sibling prints one line carrying the facts a
# release note / sibling README "Verified" line needs, copied verbatim:
#   [sibling] ok <target> sha=<sibling short sha[-dirty]> main=<git describe> level=<..> kit=<..> state=<active|frozen>
# `kit=` changing between releases means the kit added checks; `sha=` unchanged
# while the check fails means main's Protocol moved. The line is meant to be
# pasted into the sibling README and the CHANGELOG by hand (no auto-append).
# Consumption plan (ADR-0101): (a) whoever runs the release gate reads it each
# release; (b) kit= differing => kit grew, sha= same + failing => Protocol
# changed; (c) if every sibling is frozen and the line is identical for two
# releases in a row, shrink it to a fixed string in the Frozen status line.
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

# state | repo-directory | import target | constructor kwargs (space separated, may be empty)
#
# state is `active` or `frozen` (D-P1-11-1/-2, owner 2026-10-24; ADR-0070 /
# ADR-0067 addenda). A frozen target is still measured and its line is printed
# (marked FROZEN), but a failure there is reported, never a release blocker:
# exit 1 is reserved for active targets. UNUSABLE (exit 2) is not softened —
# a kit or import error means no verdict, frozen or not. Runtime-level checks
# and `--decision` targets do not exist (D-P1-11-5 = B, ADR-0088 addendum):
# this gate is static only, and no decision backend has an implementation.
#
# Kwargs exist only to reach the constructor; nothing here contacts a provider.
# The static checks never call generate(), so the values are placeholders and
# no credential is needed or read.
TARGETS=(
  "frozen|contemplative-agent-mlx|contemplative_agent_mlx.backends.mlx:MlxLmBackend|base_url=http://localhost:8080 model=conformance-probe"
  "frozen|contemplative-agent-cloud|contemplative_agent_cloud.backends.anthropic:AnthropicBackend|"
  "frozen|contemplative-agent-cloud|contemplative_agent_cloud.backends.openai:OpenAIBackend|"
)

FAIL=0
FROZEN_FAIL=0
UNUSABLE=0
checked=0
absent=0

# Identity of main, printed on every line so a pasted line stands alone.
MAIN_REF=$(git -C "$ROOT" describe --tags --always --dirty 2>/dev/null || echo unknown)

# sibling_sha <repo-dir> — short sha, "-dirty" suffix when the working tree
# differs (the script imports the working tree, not a commit).
sibling_sha() {
  local sha
  sha=$(git -C "$1" rev-parse --short HEAD 2>/dev/null) || { echo unknown; return; }
  if [[ -n $(git -C "$1" status --porcelain 2>/dev/null) ]]; then
    sha="${sha}-dirty"
  fi
  echo "$sha"
}

# report_field <key> <first line of kit output> — value of "key=value".
report_field() {
  local m
  m=$(sed -n "s/.*[ <]$1=\\([^ >]*\\).*/\\1/p" <<<"$2" | head -n 1)
  echo "${m:-unknown}"
}

for entry in "${TARGETS[@]}"; do
  IFS='|' read -r state repo target kwargs <<<"$entry"
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
    head_line=$(head -n 1 <<<"$out")
    printf '[sibling] ok      %s sha=%s main=%s level=%s kit=%s state=%s\n' "$target" \
      "$(sibling_sha "$SIBLING_ROOT/$repo")" "$MAIN_REF" \
      "$(report_field level "$head_line")" "$(report_field kit "$head_line")" "$state"
    # The kit's first line is the one-liner a release records (level, kit
    # version, capabilities — docs/runbooks/release.md step 2). It used to be
    # discarded, which left the CHANGELOG's conformance line unreproducible.
    printf '[sibling]           %s\n' "$head_line"
  else
    status=$?
    if [[ $status -eq 1 ]]; then
      if [[ $state == frozen ]]; then
        printf '[sibling] FAILED (FROZEN, not a release blocker)  %s (exit %d)\n%s\n' "$target" "$status" "$out"
        FROZEN_FAIL=$((FROZEN_FAIL + 1))
      else
        printf '[sibling] FAILED    %s (exit %d)\n%s\n' "$target" "$status" "$out"
        FAIL=1
      fi
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

printf '[sibling] %d checked, %d absent, %s%s\n' \
  "$checked" "$absent" "$([[ $FAIL -eq 0 ]] && echo 'all conforming' || echo 'NON-CONFORMING')" \
  "$([[ $FROZEN_FAIL -eq 0 ]] || echo " ($FROZEN_FAIL frozen target(s) failing — reported, not blocking)")"
exit $FAIL
