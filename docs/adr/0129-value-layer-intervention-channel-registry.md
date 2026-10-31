# ADR-0129: A Registry of the Channels Through Which the Owner's Intent Reaches the Value Layer

## Status

accepted (note)

## Date

2026-10-24

## Decided by

proposed-by: Claude Code session (roadmap P3-07.1)
decided-by: repository owner (2026-10 roadmap batch)
date: 2026-10-24

The table lists channels that already exist; no channel is added, removed, or changed by this ADR. The classification column is the author's reading (the roadmap marks it as a candidate), and the owner may reclassify a row at a Saturday gate by amending this ADR in place with a dated note.

## Layer

governance

## Context

[ADR-0050](0050-epistemic-taxonomy-and-approval-lineage.md) defined the approval gate as **containment** (what gets deployed) rather than a **training signal** (the owner's corrections are not written back into the learning loop), and `docs/glossary.md` narrows "steering" to exactly that: reflecting the owner's corrections or rejections into the loop. That definition is correct but narrow. It does not classify the other ways the owner's intent reaches the value layer: a sentence in a prompt, an exemplar chosen by hand, a numeric threshold, a vocabulary ban, a bulk rewrite, a recommendation read in a chat. Each of those is either part of the apparatus that makes observation possible, or a quiet way of steering the observed thing. Without one list, "the project observes rather than steers" cannot be checked; it can only be asserted.

This ADR writes the list. It is a register, not a verdict: every row says where the channel lives, where its use is recorded, whether the record is public, and into which of three classes it falls.

Layer note: this is a governance ADR over the value layer (constitution / identity / skills / rules), documentation only. No mechanism-layer change: no code, prompt, threshold, or stored value moves with this ADR. It is the register that the value-layer interventions in [ADR-0050](0050-epistemic-taxonomy-and-approval-lineage.md), [ADR-0051](0051-retire-trust-weighting.md) and [ADR-0052](0052-retire-session-insight.md) (observation over steering) are checked against.

Classes:

- **gate authority** — the owner's explicit, recorded power over what is deployed (ADR-0012, ADR-0050). Using it is not steering.
- **observation design** — a choice that fixes what the instrument sees or how it reads (a threshold, a top-k, a floor). It is a policy choice, not an observed optimum ([ADR-0091](0091-value-layer-cadence-in-the-weekly-chain.md)), and changing it is a change of instrument that must be dated.
- **steering suspicion** — a channel through which the owner's preference could shape generated value-layer text without passing the gate's record. Listed so it can be watched, not because a use is known to be wrong.

## Decision

Adopt the table below as the registry. Row IDs (`C1` … `C14`, with `C4a` / `C4b`; C13 / C14 added 2026-10-24) are stable and are what any load instrument (P2-01) cites. Public means: the record is visible in this repository or the public data repository. `logs/` is excluded from the data sync (`scripts/sync-research-data.sh`), so `audit.jsonl` and the other `logs/` files are private.

| ID | Channel | Class | Recorded in | Public |
|----|---------|-------|-------------|--------|
| C1 | Gate `y/N` and `--yes` on `distill-identity`, `amend-constitution`, `adopt-staged` (`cli/approval.py`: audit sources `stage-adopted` vs `stage-adopted-auto`) | gate authority | `logs/audit.jsonl` (source name), pivot snapshots (ADR-0020) | the snapshots and the adopted artifact: yes; the audit row: no |
| C2 | Hand edit of a Markdown value-layer file (bypasses the gate; README states this) | gate authority | git history of the data repo (`constitution/`, `skills/`, `rules/`, `identity.md`); no audit row unless a `command: correction` row is written by hand | git history: yes |
| C3 | Prompt text that shapes a value-layer generator: the discretion clause in `config/prompts/constitution_amend.md` ("Integrate them boldly … merge or split sections, rename them", "update that attribution to reflect revision"), "Keep it brief" in `config/prompts/identity_distill.md`, the register instruction of ADR-0072 D1 | steering suspicion | git history of `config/prompts/` (this repository); structural-constraint removal: see C3 dated rows | yes |
| C4a | View seed text and threshold (`config/views/*.md`: `threshold`, `top_k`, seed prose) | observation design | git history of `config/views/`; ADR-0072 D3 | yes |
| C4b | The four exemplars appended to `config/views/self_reflection.md` — chosen by hand (ADR-0072 D3; rollback is one deleted line) | steering suspicion | git history; ADR-0072 | yes |
| C5 | Retrieval parameters: view `top_k` (50) and `MIN_PATTERNS_REQUIRED = 3` (`core/insight.py`, `core/constitution.py`) | observation design | git history; ADR-0050 (bounded, deterministic lineage) | yes |
| C6 | Extraction guard phrases `_EXTRACTION_FAILURE_PHRASES` (`core/distill.py`) | observation design | git history | yes |
| C7 | Vocabulary discipline in extraction (`insight_extraction.md` "Naming and vocabulary", ADR-0074 item 8) | observation design | git history; ADR-0074 | yes |
| C8 | Novelty gate's known ledger (what counts as "already skilled", ADR-0111 stages) | observation design | stage audit rows and ADR-0111 | ADR: yes; rows: no |
| C9 | Exit rules for the skill store: the 600-judged-exposure floor (ADR-0097), confusion pairs (ADR-0105), `adopt-staged --archive-names` | observation design | ADR-0097 / ADR-0105; `logs/audit.jsonl` for archives; `skills/.archive/` is excluded from the sync | ADRs: yes; archive moves: no |
| C10 | Bulk rewrite outside the gate (the owner or an assistant rewrites several store files in one pass) | steering suspicion | git history of the data repo, `_gc_trash/<date>-<name>/` for originals; nothing in `audit.jsonl` | the rewritten files: yes (git); the trash: no |
| C11 | An assistant's recommendation read before a gate decision (the eli5 recommendation, agreement 45/45 per RFC-0010) | steering suspicion | the weekly gate record; RFC-0010 | RFC: yes |
| C12 | Cadence: the 27-day identity and 83-day constitution due intervals (ADR-0091) | observation design | ADR-0091 ("policy choices, not observed optima"); the `--as-of` anchoring is in the chain script header | yes |
| C13 | Unattended layer-1 exit of the skill store (RFC-0048 / [ADR-0122](0122-skill-store-layer1-unattended-exit.md)): a deterministic rule archives a skill with no human word at the moment of the move; halted by `scripts/layer1_exit_guard.py` when two of its archives are restored within 28 days. Extends C9 | observation design | `logs/audit.jsonl` (source `archive-l1-unattended`); ADR-0122; `skills/.archive/` is excluded from the sync | ADR: yes; archive moves: no |
| C14 | `restore-skill` — the human's right of return for an archived skill ([ADR-0122](0122-skill-store-layer1-unattended-exit.md)). Counterpart of C9 / C13 | gate authority | `logs/audit.jsonl` (source `direct-restore`, with `--reason`); the restored file reappears in `skills/` | the restored skill: yes (git); the audit row: no |

Classes in the table are a reading, not a measurement. The boundary rows are C3 (an instruction in a prompt is apparatus, but an instruction that states a preferred register is a preference), C4b (hand-chosen exemplars are a seed, but the seed is the owner's selection), and C11 (reading a recommendation is not itself a write, but 45/45 agreement is a fact a reader should be able to see).

### Dated rows (worked examples)

**C2, 2026-08-09, constitution twin.** An approved amendment was written to `contemplative-axioms-2.md` beside the live `contemplative-axioms.md` by the collision guard (`approval._collision_free_path`). The runtime concatenates every `*.md` in the directory, so both texts were injected at once. It was repaired by hand within minutes and the sha verified ([ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.md), "Remediated by hand"). The docstring in `cli/adopt.py` records the mechanism.

**C2, 2026-08-15, identity twin.** The same guard wrote `identity-2.md`. `IDENTITY_PATH` is a fixed single path, so the twin was never read: the value layer did not change while `audit.jsonl` said `approved`. It was repaired by hand between 04:02Z and 04:17Z. There is no audit row for the repair. The record is the `command: correction` row planned in P1-12.4 (who, when, the `mv` source and destination, the sha checked) and the dated note planned in P3-04.2; until those exist the only record is the `cli/adopt.py` docstring and this row.

**C3, planned and conditional: deletion of L11 of `config/prompts/constitution_amend.md`.** The line "If the input claims a verbatim source, update that attribution to reflect revision." is still present in the prompt at the time of writing. P0-07.8 proposes deleting it as neutral with respect to the generated constitution, after the readings P0-07.1 / P0-07.2 of the 2026-10-31 amendment gate have been taken. If it is deleted, this row gains the prompt's sha12 after the deletion and the commit; the same sha is to be written into the fourth constitution-version row (P3-04.3), the boundary table (P3-02.1) and the input bundle of the amendment (the pattern set and the prompt of that day). Nothing is deleted by this ADR.

**C3, structural constraints removed at an unrecorded date.** The amend prompt once fixed four sections that could not be added, removed or renamed, with at most four clauses each; today it allows merge, split, rename, 1–4 clauses per section, and a rewrite of the Source line. The old constraint survives only in a quotation in the data repository's amendment report. The window is between the first amendment (2026-03-27, fixed sections) and the second (2026-05-05, renamed sections), estimated. Pinning the commit needs the full history (the clone used for this ADR is shallow, and the earlier text lived in `prompts.py` before the 2026-08-16 externalization): this is P3-07.5, an open item for the owner's machine. Because the removal is what made section renaming, Source-line rewriting and the widening of what the directives refer to possible, it is a research condition and C3 points here until a sha and a reason exist.

**C5, 2026-10-31, identity input pool aligned with the constitution (D-P3-04-3 = B).** The owner chose to make `distill_identity` route the `self_reflection` view over the live pool (`get_live_patterns()`), as `amend-constitution` does, instead of `get_raw_patterns()`. First affected staging: the weekly chain of 2026-11-07 (09:00 JST). The pattern set reaching the identity prompt does not change, because `ViewRegistry._rank` already skips closed rows (ADR-0021); the change aligns the call site, so `top_k` and the view threshold keep selecting from the same rows. Record: [ADR-0057](0057-identity-from-self-reflection-corpus-alone.md) amendment of 2026-10-31 and `closed_input_count` (0 by construction) in the identity `.meta.json` and audit row.

**C10, 2026-07-10, skill clean rewrite (10 files).** Ten skill files in the data repository were rewritten in one pass, outside the gate: when (2026-07-10), by whom (the owner's side, not an agent run), what (ten skills), originals kept in `_gc_trash/2026-07-10-clean-rewrite-originals/`, and the rewritten files are the current `skills/*.md` of the same stems. This row is the record place for that event (P3-04.11 uses it and writes no separate ADR amendment). If the owner later chooses to keep two-generation templates as an exception (D-P3-05-6 = B), the four such templates are to be listed here as exception rows; that is not decided in this ADR.

## Rule for future changes

An ADR that adds, removes or materially changes a channel to the value layer **must update this table in the same change** (a new row with a class, a record place and a public flag, or a dated note on an existing one). The ADR template in `docs/adr/README.md` carries a one-line reminder to that effect.

## Review-when

- A row is used in a way that no row describes (a new channel): add the row first.
- A Saturday gate reclassifies a row: amend in place with a dated note, do not rewrite the history.
- The 2026-10-31 amendment gate has taken its readings and L11 is deleted or kept: update the planned row.
- P3-07.5 identifies the commit that removed the structural constraints: replace the "unrecorded date" paragraph with the sha, date and reason.

### Consumption plan

(a) The owner at each Saturday gate, only when a change touches one of the files named in a row, and the P2-01 load instrument, which cites row IDs. (b) One reading decides one thing: is the use of the channel recorded where the row says it is. (c) Retire the table when a row-level audit makes it redundant, or at the wind-down review ([ADR-0080](0080-north-star-layered-end-state.md)); a row is struck, not deleted.

## Alternatives Considered

- **Widen the definition of steering in ADR-0050 instead.** Rejected: ADR-0050 is a decision; the list of channels is a fact that grows. A register can be corrected by a dated note without reopening the decision.
- **One class, "intervention".** Rejected: it would call the gate itself an intervention and make the register useless for telling the gate from a prompt sentence.
- **Classify as final.** Rejected: C3, C4b and C11 are judgment calls; claiming certainty would be the kind of target-state definition the observation stance avoids.

## Consequences

- "Observation over steering" becomes checkable row by row. Disagreements become a reclassification, not an argument about the definition.
- Nothing about the running agent changes.
- Two rows depend on work not done here: the C2 identity-twin repair record (P1-12.4, P3-04.2) and the C3 constraint-removal commit (P3-07.5).

## References

- [ADR-0012](0012-human-approval-gate.md) — the gate (C1).
- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — snapshots recorded at the gate.
- [ADR-0050](0050-epistemic-taxonomy-and-approval-lineage.md), [ADR-0051](0051-retire-trust-weighting.md), [ADR-0052](0052-retire-session-insight.md) — observation over steering; the gate as containment.
- [ADR-0072](0072-echo-chamber-interventions.md) — D1 register instruction (C3), D3 exemplars (C4b).
- [ADR-0074](0074-weekly-staged-insight.md), [ADR-0097](0097-consolidator-dissolution-and-skill-store-exit.md), [ADR-0105](0105-skill-store-exit-confusion-pairs.md), [ADR-0111](0111-insight-entrance-stages.md) — C7, C9, C8.
- [ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.md) — the 2026-08-09 twin repair (C2).
- [ADR-0091](0091-value-layer-cadence-in-the-weekly-chain.md) — cadence (C12).
- `src/contemplative_agent/cli/approval.py`, `src/contemplative_agent/cli/adopt.py` — audit sources and the twin-file docstring.
