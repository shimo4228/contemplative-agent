# ADR-0109: The Dependency Floor Is the Wheel's, Not the Repo's — Runtime Stays requests + numpy, Everything Outside Follows search-first

## Status

accepted

## Date

2026-09-12

## Context

"requests + numpy only" is applied across the repo as a policy, but no ADR
owns it as a decision, and no text says what it applies to. The fact is
`pyproject.toml`'s `[project].dependencies = ["requests>=2.33.0",
"numpy>=1.24.0"]`. The renderings of that fact, all verified 2026-09-12:

- `README.md` line 108 (mirrored in `README.ja.md`): the "Security by
  absence" bullet lists "two runtime dependencies (requests, numpy)" as part
  of the public security claim, alongside "talks only to moltbook.com and
  localhost Ollama". `docs/security/2026-04-01-security-scan.md` line 69 is a
  dated snapshot of the same claim.
- `CLAUDE.md` line 32 states it as a bare fact (`依存: requests, numpy`), not
  a prohibition.
- `src/contemplative_agent/core/llm/prompting.py` line 345 uses it as a
  production premise ("ships only requests+numpy, so no real tokenizer is
  available").
- [ADR-0075](0075-observability-by-default.md) (§Alternatives, OpenTelemetry)
  and [ADR-0078](0078-otel-connection-via-vocabulary-and-offline-export.md)
  (Context, line 16) cite "a deliberately minimal dependency floor (requests +
  numpy)" as a premise for rejecting a runtime observability framework.
- [ADR-0077](0077-chaos-tdd-fault-injection.md) (§Alternatives, "Place
  ChaosBackend in src/") states: "Runtime dependencies stay requests + numpy
  only, and test-only code must not enter production import paths." Three
  of its other alternatives (chaostoolkit / toxiproxy, agent-chaos,
  requests-mock) are dev-tier and weigh dependency footprint alongside
  altitude or redundancy.
- [ADR-0071](0071-read-only-pattern-composition-instruments.md)
  (§Alternatives, "Adopt an embedding-drift monitoring stack (evidently,
  whylogs)") rejects the stack because "the pandas/scikit-learn dependency
  footprint conflicts with the requests+numpy-only policy". Its instrument is
  `core/view_metrics.py`, imported by `distill.py` and `insight.py` — inside
  the wheel.
- `.claude/verify.md` line 158 (git-tracked) rejects `typing_extensions` for
  `Unpack[TypedDict]` as "新依存（requests+numpy のみ方針に抵触）". The
  annotation was for `adapters/moltbook/client.py` — inside the wheel.
- [ADR-0007](0007-security-boundary-model.md) (§Alternatives, "External
  security scanner"): "Adds a dependency. At the current scale, built-in
  pattern matching suffices" — the earliest use of a dependency as a
  rejection reason, paired with a scale argument.
- [ADR-0011](0011-knowledge-injection-to-skills.md) line 92 uses the phrase
  "Minimal Dependency principle" for something unrelated: the orchestrator's
  independence from Claude Code ("anything that can invoke the CLI
  suffices"). Same words, different claim.

Every recorded application of the rule as a veto is to wheel code. The rule itself is
sound there. What is missing is the scope statement: nothing says the rule
stops at the wheel boundary, so an agent reading "requests+numpy-only
policy" in ADR-0071 or `verify.md` reads a repo-wide rule. On 2026-09-12
that reading produced a draft that was about to hand-write groupby / pivot
aggregation in stdlib + sqlite3 for an instrument script under `scripts/`.
The author corrected it: basic libraries such as pandas and scipy may be
added; avoiding them forces reinvention; the exception is not adding a
library for a single function ("過剰なのなら入れなくていい"). That is the one
instance of the rule reaching outside the wheel, and it was caught by the
author, not by any text.

The global harness routes the other way. `~/.claude/rules/common/planning.md`
sends every dependency addition and self-built utility through skill
`search-first` first. `search-first` treats dependency footprint as one
evaluation axis among several (Step 2) and names exactly one anti-pattern
about dependencies — "dependency bloat: installing a massive package for one
small feature" — landing on Adopt / Extend / Compose / Build. Skill
`implementation-chain` routes a plan that adds a dependency through the
Build-or-not four questions (at build tier, agent `architect`), which ask
whether a thing should exist, not whether dependencies are forbidden. No
global rule says "do not add dependencies".

Two further facts constrain the decision. `uv.lock` is gitignored; the
durable pin record is `pyproject.toml` — version floors in
`[dependency-groups]` and transitive security floors in
`[tool.uv].constraint-dependencies` (the 2026-07-31 pip-audit drain). The
groups are `dev` (auto-synced by `uv run`) and `eval` (opt-in,
[ADR-0089](0089-llm-behavioral-eval-layer-on-deepeval.md)). And several
`scripts/` are stdlib-only on purpose because their launcher is bare
`python3` under the weekly chain / launchd, not the venv — e.g.
`scripts/weekly-pipeline.sh` line 799 ("stdlib-only → python3, no uv") and
[ADR-0105](0105-skill-store-exit-confusion-pairs.md)'s "stdlib-only so it can
run outside the venv". The precedent for a script that does need venv
packages is the skill-selection stage of `scripts/weekly-analysis.sh`,
launched by the unattended weekly chain as `uv run --no-sync python`.

## Decision

1. **The floor is the wheel's runtime dependency set, and it stays
   `requests` + `numpy`.** The reason is the README's security-by-absence claim: the
   wheel is what a user installs, and every runtime dependency is executable
   code inside the production process that claim describes. Adding a runtime
   dependency requires an ADR (a new one, or an amendment of this one) that
   also updates the gate: `tests/test_dependency_floor.py` asserts that the
   distribution names in `[project].dependencies` equal the floor (version
   specifiers are free to move) and that `[project.optional-dependencies]`
   is absent — an extra is runtime code a user installs, so it is inside
   D1, not a way around it. A bare pyproject edit fails the suite. This is the only scope where "it adds a dependency" is a
   sufficient rejection reason by itself.
2. **Outside the wheel — `[dependency-groups]` dev and eval, `scripts/`,
   `tests/`, `evals/` — dependency weight is not a veto.** The decision is
   the search-first verdict, and the question that decides it is "is this
   the tool's main job, or one function?" A basic library (pandas, scipy, and
   the like) is adopted when the task is its main job; a single-function need
   stays on numpy or stdlib. "It conflicts with the requests+numpy policy" is
   not a valid rejection reason in this scope. The existing gates stay in
   front of the verdict: a plan that adds a dependency still answers
   `implementation-chain`'s Build-or-not questions, and `verify.sh`'s
   dependency audit still runs over the groups.
3. **A script that takes a dev-group dependency declares its launcher.** The
   dependency goes in `[dependency-groups] dev`, and the script is started as
   `uv run --no-sync python` (precedent: the skill-selection stage of
   `scripts/weekly-analysis.sh`), never bare `python3`. Conversely,
   "stdlib-only" remains a legitimate per-script property when the script's
   launcher is bare `python3` outside the venv; that constraint is stated in
   the script's header comment as the launcher's requirement, not cited as
   repo policy.
4. **Naming.** This ADR calls the D1 set the "runtime dependency floor".
   ADR-0011's "Minimal Dependency principle" (orchestrator independence from
   Claude Code) is a different statement and is not affected.

Doc sync in the same change: `CLAUDE.md` line 32 gains the scope (runtime
floor with its gate; dev / scripts follow the search-first verdict). No prior
ADR receives a note. ADR-0071's rejection is wheel-scope and is exactly D1.
`verify.md`'s rejection is D1 as recorded; had the import been guarded by
`TYPE_CHECKING` (a pyright-only import is not a runtime dependency), it
would have fallen under D2 — the D1/D2 line runs exactly there. ADR-0075 / 0078 and ADR-0077's `src/` rejection are D1;
ADR-0077's dev-tier rejections weigh footprint as one reason among others,
which is D2's axis-not-veto reading; ADR-0007's rejection concerns `core/`
sanitization and is D1. README is unchanged because its claim (two runtime
dependencies) stays true.

## Review-when

- The README stops claiming the two-dependency runtime floor as part of
  security by absence → D1 loses its reason and this ADR is superseded on
  that half. (A runtime dependency added *through* an ADR is an amendment of
  D1, not its expiry; a runtime dependency that lands *without* one means
  the gate was bypassed and D1 is dead in practice.)
- The repo splits `scripts/` or `evals/` into a separately packaged project →
  the D2/D3 boundary must be redrawn against the new wheel boundary.
- `search-first`'s verdict rules change so that dependency footprint becomes
  a veto axis rather than one evaluation axis → D2 must be re-derived. The
  skill lives in the harness, outside this repo, so this trigger is checked
  by the author at harness skill-stocktake time, not by any repo scan.
- A `verify.sh` gate or a `scripts/weekly-pipeline.sh` stage fails because a
  package in the `dev` group as it stands on this ADR's date resolved to a
  version that broke it (`uv.lock` is gitignored, so pins are pyproject
  floors) → the first such failure is repaired; a second one while the `dev`
  group's membership is unchanged since the first is this trigger, and
  reopens whether lock tracking or narrower pins belong in D3.

## Alternatives Considered

- **Keep "requests + numpy only" as an implicit repo-wide policy (status
  quo).** Rejected: no ADR owns it and no text bounds it, so an agent reads
  it as repo-wide and hand-writes groupby / pivot / diff with `Counter` for
  a `scripts/` instrument, increasing lines and bug surface (author
  correction, 2026-09-12). The rule was only ever applied to wheel code; the
  status quo leaves that scope unwritten.
- **Write the scope sentence into `CLAUDE.md` and stop — no ADR, no gate.**
  Rejected: a sentence bounds the reading but does not stop a runtime
  dependency landing without a decision (D1's gate does), and it cannot
  carry the launcher rule (D3) or the audit trail a later reader needs to
  see why the floor is the wheel's and not the repo's. The sentence is
  written anyway; this ADR is what it points to.
- **Drop the floor entirely and let search-first decide runtime dependencies
  too.** Rejected: the README makes the runtime dependency count part of the
  public security-by-absence claim, and the wheel's import surface is what
  that claim is about. search-first's footprint axis is a cost estimate, not
  a security boundary.
- **Vendor or copy small functions instead of adding a dependency.** Rejected
  as a general rule — it is reinvention with worse maintenance. It survives
  as the D2 exception for a single-function need, where numpy or stdlib
  already suffices.
- **Make `scripts/` a separate uv sub-project with its own dependency set.**
  Undecided — revisit if the dev group grows until `uv run` sync time or
  conflicting pins become a felt cost, or if the D2/D3 Review-when trigger
  fires.

## Consequences

**What gets easier.** search-first verdicts in `scripts/` / `evals/` /
`tests/` are honest: dependency footprint is an axis, not a veto, so the
Build verdict is no longer forced by an unbounded rule. Less hand-written
aggregation code in instruments; fewer lines to review. The floor has an
owner, a scope, and a machine gate; future ADRs cite this one instead of
restating the policy as a premise. The two meanings of "dependency" (wheel
vs. outside) are named, so a reviewer can say which one an objection is
about.

**What gets harder.** More third-party code executes unattended: the weekly
chain already runs `uv run --no-sync python` stages against
`$MOLTBOOK_HOME`, and D2 enlarges exactly the set of packages those stages
can import. D1 protects the wheel a user installs, not the whole unattended
process — that boundary is the README's claim, and this ADR does not widen
it. The dev group grows, and with `uv.lock` gitignored, version drift risk
grows with it; pins are floors in `pyproject.toml`. A script that takes a
dev dependency cannot be launched by bare `python3`; each such script must
carry its launcher, and the weekly chain's launcher lines must match.
Runtime dependency additions now have an explicit ADR cost and a failing
test, which is intended.

## References

- `pyproject.toml` — `[project].dependencies` (the D1 floor),
  `[dependency-groups]` (the D2/D3 scope), and `[tool.uv].constraint-dependencies`
  (the durable pin record while `uv.lock` is gitignored)
- `tests/test_dependency_floor.py` — the D1 gate
- `~/.claude/rules/common/planning.md`, skill `search-first` (Step 2 verdicts;
  "dependency bloat" anti-pattern), skill `implementation-chain` (Build-or-not) —
  the harness wiring D2 defers to
- `scripts/weekly-analysis.sh` skill-selection stage — the
  `uv run --no-sync python` launcher precedent for D3
- `README.md` §"Security by absence" — the public claim D1 keeps true
