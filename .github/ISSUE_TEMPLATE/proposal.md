---
name: Proposal
about: A change that needs a decision first (a gate, threshold, stage, dependency, flag, or a change to the value layer)
labels: proposal
---

Changes of this kind go through an RFC (`rfcs/NNNN-slug.md`) or an ADR (`docs/adr/`) before a pull request. This issue is the way in: the maintainer decides whether it becomes an RFC. See CONTRIBUTING.md, "Where the line is".

**The problem** — what is wrong or missing today, and how you saw it (a log line, a test, a reading).

**What you would change** — the smallest version.

**What it would cost** — a new dependency, a new external call, a new flag, more state to keep. The project prefers removing to adding (ADR-0101).

**How we would know it worked, and when to take it out again.**
