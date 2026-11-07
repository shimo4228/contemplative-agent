# ADR-0103: Retire the Wiki Mechanism — the Form Works, the Production Model Does Not

## Status

accepted

## Date

2026-09-05

## Context

RFC-0017 redesigned insight extraction around the WikiSkill form (arXiv
2608.27454): a Maintainer loop that reads a UTC day's rich episodes and
writes/patches prose "pattern pages" in a store, and a Proposer loop that
reads that store plus the skill index, the evolution log and the
skill-impact table and emits one atomic would-be skill proposal for the
human staging gate. Stages S1–S4 plus packets A and A+1 landed on main
(`c367962`). The launchd wiring (`install-schedule --wiki-maintain`) was
never run: the production store `~/.config/moltbook/wiki/` never existed
and no plist was ever installed.

Three readings closed it (2026-09-03 to 09-04):

1. gemma smoke, 8/25–8/27, 3 days, 9 pages, production model gemma4:e4b
   ([ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md)).
   Every page was general. Where a distill line is first-person and
   situated, the pages landed in the register of "the critical failure mode
   of complex asynchronous systems is …". Patch ratio 0.25. The shape (the
   whole wiki in every prompt) shrank the day's episode budget from 27,371 to
   21,815 over the three days (`wiki_daily[].episode_budget`) — two deltas,
   3,541 and 2,015, so ≈ −2.8k/day is a mean over n = 2 differing by 75%, and
   "roughly ten days to exhaustion" is an extrapolation from it, not a
   measurement. Counters frozen at
   `docs/evidence/rfc-0017/smoke-gemma-3days-20260902.json`; the prose reading
   of the pages is RFC-0017 §「2026-09-02 smoke の読み」 and RFC-0025
   §Motivation, because the JSONs hold no page text.

   M-a (`verification_pass_rate`, the share of write ops that pass code
   verification; RFC-0017 preregistered ≥ 0.9) read 0.80 here — but it is
   **not** the metric that decided this, and is recorded only so a later
   reader is not misled by it: the opus arm scored 0.6786 on the same metric
   while producing the better pages. What separated the arms was the register
   of the prose, which no counter in either file measures.
2. gemma Proposer dry-run, 2026-09-03, same wiki. One patch proposal: append
   page p-0001 (proof of receipt in asynchronous systems) into the skill
   `detecting-abstraction-decay-in-context` (metadata lost in
   summarization). Their only common ground was the abstract phrase "the
   evidence is insufficient"; no instruction was added; the anchor pointed
   at a description line absent from the body. General plus general is
   general. The wiki pages were also nearly the same artifact as the
   existing skill files — same register, same grain — so the second reader
   was writing what the first reader (insight) already writes.
3. opus arm, 2026-09-04, same three days, same shape, claude-opus-5, $8.4.
   All 9 pages were specific and behaviour-changing — e.g. "answering a
   concrete question with abstraction" (naming the counterpart's 5
   questions and 9 items, with the remedy "write out every question and
   label each answer / don't know / out of scope first"), "ornamental LaTeX
   with undefined symbols" (strip every symbol before sending; if the claim
   survives, leave them out), "the What-I-noticed section always collapses
   into self-resonance" (all 16 instances close in the same vocabulary =
   filler). The Proposer's patch was a five-item "Answer first, then
   bound", justified with "nearly every skill in the store pushes toward
   structural reframing, which is the avoidance the wiki is recording".
   Maintainer 17 calls, patch ratio 0.53, 9 refusals (8 PAGE_FULL), M-a
   0.6786. Counters frozen at
   `docs/evidence/rfc-0017/replay-opus-3days-20260904.json`; the pages
   themselves are quoted in RFC-0025 §Motivation and the full bodies were
   moved off-repo (they quote other agents' handles), so the JSON is not the
   only surviving description.

The reading: the flattening is the model, not the form. Production
generation is gemma4:e4b and stays there
([ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md)
— 16GB, unattended). What was missing was never a step that abstracts
upward: it was distance from the existing skills (RFC-0023) and the
register of extraction itself (RFC-0024).

`testing/claude_cli.py`, the `LLMBackend` over `claude -p` that drove the
opus arm, was the only module shipped in this package that reached a cloud
model. The 2026-09-02 design intent (stated here, not in ADR-0088, which
never names this module) was to put it under `testing/` so that the two
generic [ADR-0088](./0088-shipped-conformance-kit-for-the-llm-backend-contract.md)
import-linter contracts made "production cannot reach it" a checked property
rather than a convention.

## Decision

Retire the wiki mechanism whole and record the retirement here; RFC-0017
and RFC-0022 are obsoleted and keep their bodies as the public judgment
record.

Removed: `core/wiki.py`, `core/wiki_loop.py`, `core/wiki_maintainer.py`,
`core/wiki_proposer.py`, `core/wiki_render.py`; `cli/wiki_cmds.py` (the
`wiki-maintain` / `wiki-propose` commands); the three
`install-schedule --wiki-maintain*` flags and
`config/launchd/com.moltbook.wiki-maintain.plist`; the four
`config/prompts/wiki_{maintainer,proposer}{,_system}.md` and their four
`PromptTemplates` fields; `scripts/wiki_replay.py`; `testing/claude_cli.py`;
and the six test modules that covered them. About 7,400 lines by
`git diff --stat` on this change's deletions. Restoration is `git revert`;
the decision to restore is not.

Kept: the two readings under `docs/evidence/rfc-0017/`
(`smoke-gemma-3days-20260902.json`, `replay-opus-3days-20260904.json` — the
directory also holds `comment_golden-skills-off-20260902.json` from unrelated
work); the
[ADR-0088](./0088-shipped-conformance-kit-for-the-llm-backend-contract.md)
conformance kit (`backend_contract.py`, `backend_probe.py`) and the
`LLMBackend` Protocol, which siblings import; `_target_inside_data_root` in
`core/_io.py`, where the wiki store put it — it is now reached only from
`cli/`, but a second copy is the one thing its containment argument cannot
survive.

A new test module `tests/test_cloud_egress_absence.py` pins both absences
by scanning source text rather than imports, because a module that is
present but unreferenced passes an import check and is exactly the
negative difference this retires: no Python shipped here spawns
`claude -p` or carries the retired backend's names, the conformance kit
keeps its own two modules, no `wiki*` module / prompt / plist / CLI command
exists, and the two evidence files are still there. Two `claude -p` call
sites remain in the repo and the test names both as deliberate exclusions:
`scripts/weekly-pipeline.sh`'s single `/weekly-report` session — the
operator's own scheduled Claude Code with an explicit permission scope and a
Saturday human gate
([ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.md) /
[ADR-0098](./0098-weekly-single-session-and-triage-delegation.md)) — and
`evals/judging.py`'s behavioural eval judge
([ADR-0089](./0089-llm-behavioral-eval-layer-on-deepeval.md)), which lives
outside `src/` and outside the wheel and is run by hand against a frozen
dataset. Neither is a backend the agent loop can reach, which is why the
scan covers `src/` and `scripts/*.py` and says what it leaves out.

## Review-when

- Production generation stops being gemma4:e4b
  ([ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md)
  superseded by a larger model). This does not void the decision by itself:
  the nine pages that show the form working came from claude-opus-5, a
  frontier cloud model, and a modestly larger *local* model carries none of
  that evidence. What fires is an obligation to **re-run the three-day smoke
  on the new model** and read the pages; the opus arm is the comparison
  point, not the prior.
- A decision is separately taken to send episode bodies to a cloud model
  (the same research-use framing as the sibling
  `contemplative-agent-cloud`). The 2026-09-04 author judgment was "close
  it, stay on gemma"; that judgment, not the mechanism, is what this ADR
  records.

No consumption plan section: the
[ADR-0101](./0101-instrument-dissolution-mandate.md) mandate applies to
instruments a decision *adds*, and this one only removes.

## Alternatives Considered

### Run the wiki on opus

A weekly Proposer pass over a daily Maintainer; the opus arm cost $8.4 for
three days, so ≈ $2.8 per day maintained. Rejected: episode bodies leave the machine, which
softens security by absence. The author's 2026-09-04 call was to close it
and stay on gemma. Kept live as the second Review-when trigger.

### Keep the form, change its shape so gemma can hold it

Structured JSON instead of prose, a pointer-only wiki, a topic layer.
Considered 2026-09-03 and rejected: a form with no body of its own becomes
the same artifact as the skill's provenance column, which removes the
reason to build a wiki at all — RFC-0021's supply column plus RFC-0023's
retrieval already cover it.

### Keep the code and never wire it

Rejected: code no one reads is a negative difference, not a neutral one
(`akc-cycle`, "actively delete the negative pole"); this is the same
reasoning [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md)
applied to consolidators whose consumer had vanished.

### Defer — wait for RFC-0023 / RFC-0024 and re-evaluate

Rejected: both successors change the extraction register and the novelty
side, neither changes the model, and the model is what the three readings
identified. Deferring would hold ~7,400 unwired lines through two more
changes for a re-evaluation whose input (gemma) is fixed.

### Delete the evidence too

Rejected: the opus arm is the material for restarting on the day the
production model grows. The readings outlive the code.

## Consequences

### Positive

- No cloud-egress path exists in the wheel (`src/contemplative_agent`) or
  in any scheduled Python, so on the unattended agent-loop path security by
  absence is a property of the tree rather than of an import contract.
  `tests/test_cloud_egress_absence.py` fails if one returns. The claim is
  scoped: `evals/judging.py` still reaches a cloud judge when the author runs
  it by hand.
- The unattended chain has one fewer daily stage to schedule, serialize
  against the single local Ollama, and diagnose. Roughly 7,300 lines and
  six test modules leave the surface the next session has to read.
- The remaining insight work (RFC-0023 retrieval-based novelty candidates,
  RFC-0024 extraction register) is no longer competing with a second writer
  producing the same register.

### Negative / accepted

- The opus reading says the form is right; nothing now carries it.
  Restarting means re-implementing from `git revert` plus RFC-0017 /
  RFC-0022, with the JSON counters and the RFC-0025 prose as the surviving
  public description of what it produced (the page bodies are off-repo).
- Two ultrareviewed packets (A, A+1) are discarded. Sunk cost is not a
  reason to keep them (Emptiness), but the cost was real and this ADR is
  where it is recorded.
- `_target_inside_data_root` now lives in `core/` with only `cli/`
  callers — an arrangement whose original justification is gone. It is left
  in place because a second copy is what its containment argument cannot
  survive, and `cli/store_paths.py`'s docstring now states the general
  reason (a `core` caller could reach it without importing `cli`) rather
  than the historical one. That general reason has no caller today; this ADR
  is where the historical one is recorded.

## References

- [ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md) —
  the production model this decision holds fixed
- [ADR-0088](./0088-shipped-conformance-kit-for-the-llm-backend-contract.md) —
  the import-linter contract that made `testing/claude_cli.py`'s isolation a
  checked property
- [ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.md) /
  [ADR-0098](./0098-weekly-single-session-and-triage-delegation.md) — the
  gate governing the one surviving `claude -p` call in the repo
- [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md) — the
  precedent this ADR's third alternative draws on (unconsumed mechanism is a
  negative difference)
- `rfcs/0017-insight-extraction-redesign.md`,
  `rfcs/0022-wikiskill-fidelity-check.md` — obsoleted by this decision
- `rfcs/0023-novelty-gate-retrieval-and-rare-lane.md`,
  `rfcs/0024-skill-extraction-free-body-split-calls.md`,
  `rfcs/0021-skill-stocktake-family-saturation.md` — the successor work this
  retirement clears room for

## Retrospective

- Retrospective (2026-09-06): [docs/evidence/adr-0103/retrospective-wiki-rise-and-retirement.ja.md](../evidence/adr-0103/retrospective-wiki-rise-and-retirement.ja.md) — the four reversals of reading from design to retirement (author / next-session LLM audience, Japanese only). This ADR body is unchanged.
