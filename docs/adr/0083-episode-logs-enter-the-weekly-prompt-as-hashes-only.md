# ADR-0083: Episode Logs Enter the Weekly Prompt as Hashes Only

## Status

accepted

## Date

2026-07-25

## Context

The weekly report ([ADR-0040](./0040-separate-code-level-findings.md))
is assembled by `scripts/weekly-analysis.sh`, which feeds `claude -p` a prompt
built from operator-facing artifacts plus two deterministic intakes:
`log_anomaly_sweep.py` (the event stream — `*.log` and `audit.jsonl`) and
`state_invariant_check.py` (accumulated state — `knowledge.json`,
`agents.json`). Both carry a load-bearing prohibition in their module
docstrings: they must never read the episode logs `logs/YYYY-MM-DD.jsonl`,
because those hold untrusted external content and their output is fed to an LLM.
The same prohibition is stated for Claude Code sessions in `CLAUDE.md`, with
`reports/comment-reports/` named as the sanctioned read path.

That prohibition has now met a claim it cannot serve. The report's C — Duplicate
section asserts facts about identity between published records, and it has twice
published a cross-entry claim that is not in the artifacts:

- **2026-06-15** — a "6-day consecutive re-reply to one post" was six distinct
  interlocutors replying on a shared thread. The lesson was recorded in
  `config/prompts/principles.md` as a rejected *mechanism* (post-level reply
  dedup); the reporting failure that produced it was not.
- **2026-07-25** — "the first cross-day byte-identical outputs in the record"
  paired four real 07-23 entries with an invented 07-21 occurrence. Verified
  against every July episode log: zero bodies were published on more than one
  day. The report offered two hypotheses for the duplication and called the
  choice undeterminable from operator-facing data; the actual answer was a third
  it did not consider — the pairing was constructed at analysis time.

Both passed review as prose because each *individual* quote was real. Only the
pairing was fabricated, and only a comparison could have caught it. This is the
structural difference between the duplication indicator and every other entry in
the report: the others are single-entry and verifiable by construction against
their source daily report, while a duplication claim spans entries and days.

It is also a task assigned to the wrong tool. Whether two strings are identical
is settled by byte comparison, not by reading — a structural property, in the
sense of the `when-code-when-llm` skill. The pipeline was asking an LLM to
perform, from recall across a long prompt, a computation that takes 0.6 seconds.

`config/prompts/principles.md` Principle 5 (added 2026-07-25) now requires that
cross-entry claims rest on a deterministic input. That principle has no input to
rest on unless something computes it, and everything that could compute it lives
in the episode logs.

## Decision

Add a third deterministic intake, `scripts/cross_day_duplicate_scan.py`, which
reads the episode logs and emits only a hash-level projection of them.

1. **The boundary is the output, not the input.** The scan reads
   `logs/????-??-??.jsonl` (day files only — `*.bak`, `audit.jsonl`,
   `skill-usage-*.jsonl` and symlinks are excluded by construction) and emits
   exactly four kinds of token: SHA-256 digests truncated to 12 hex characters,
   integer counts, dates taken from the *filenames* (self-controlled), and
   action names from the fixed vocabulary `{post, reply, comment}`. Body text,
   `post_id`, `target_agent`, `internal_note` and `thinking` never appear.
   Dropping the post id is deliberate: the C section needs to know how many
   identities exist, not which post carries them, and a digest names a group
   uniquely without opening a path for external strings.

2. **The vocabulary is stated as a closed character set and gated by a test.**
   `RENDER_CHARSET_RE` admits ASCII alphanumerics, the template's own
   punctuation, and `×`. `TestOutputBoundary` checks per-fragment absence of
   injected bait, absence of ids and counterparty names, and — as a hypothesis
   property over arbitrary content — that the render never widens the character
   set. The gate was verified to fail when a leak is injected into the render.

3. **Exact identity only, no normalization, and strict decoding.** The digest is
   over the raw body bytes. Near-identical wording is a semantic property and
   stays with the LLM as the register observation the C section already asks
   for, which keeps the scan's answer checkable by anyone with `sha256sum`.
   Lines that are not valid UTF-8 are skipped and counted rather than decoded
   leniently: `errors="replace"` maps distinct invalid byte sequences onto the
   same `U+FFFD` string, so two different bodies could collide into an invented
   duplicate. A scan whose purpose is to refuse unsupported identity claims must
   not manufacture one out of corruption.

4. **Window and lifetime in one pass.** The window reading is what the C section
   describes; the lifetime reading is what a claim like "first in the record"
   requires. Rendering only the window would leave the exact shape of the
   2026-07-25 failure unanswerable. Day counts are days that carried published
   output, not day files present, because that is the denominator of the
   comparison actually performed.

5. **Absence is stated as a sentence, not as a zero — and only as absolute as
   the coverage.** When no cross-day duplicate has ever existed, the render says
   so in a line a summary can be checked against; the 2026-07-25 failure was not
   a misread count but naming the check undeterminable and then leading with the
   finding anyway. When any record was skipped, the sentence is qualified to the
   bodies actually read. An instrument built to refuse claims wider than their
   evidence has to apply that to its own output first.

6. **Every fault is a counted skip, never a crash.** Torn final lines, shape
   violations, unreadable files, invalid UTF-8 and lone UTF-16 surrogates are
   skipped with a reason code that is rendered. This is not only tidiness: the
   shell discards the scan's stderr and falls back to a "not available" stub, and
   episode logs are never deleted, so an uncaught exception on one record would
   retire the instrument permanently and silently. The day-file pattern uses
   explicit `[0-9]` rather than `\d` for the same reason — `\d` on a `str`
   pattern is Unicode-aware, and the render calls its dates self-controlled, so
   the pattern should make that structurally true.

7. **No state.** Unlike the sweep, the scan is an absolute measurement with no
   novelty baseline, so it has nothing to spend and needs none of the atomicity
   machinery the sweep required in the same PR. Its exit code is always 0 — a
   duplicate is a fact about published output, not corruption, so unlike
   `state_invariant_check.py` there is nothing for a caller to gate on.

8. **Observation, never intervention.** The render carries an explicit line
   saying that hash-equality dedup as an intervention remains a rejected
   mechanism (`principles.md` appendix), so a hash table in the prompt cannot be
   read back as a case for the gate it deliberately is not.

## Alternatives Considered

**Keep episode logs out and grep the comment reports instead.** The comment
reports are the sanctioned read path and the check could be approximated with
`grep -l` against them, as last week's findings suggested for a standing manual
check. Rejected as the mechanized form: the reports are a rendering, subject to
their own truncation and formatting, and they cover only the reporting window —
"first in the record" cannot be answered from them at all. A measurement meant
to stop fabrication should read the record, not a rendering of it.

**Emit the post id alongside the digest.** More useful for a human following up,
and post ids are server-generated hex rather than free text. Rejected: it opens
a field of external provenance for a convenience the C section does not need,
and the boundary is much easier to hold as "nothing but digests, counts and
dates" than as a list of exceptions.

**Scan the window only.** Cheaper and sufficient for the C section as written.
Rejected: the failure being repaired was a lifetime claim, and the full history
costs 0.6s over 9052 bodies.

**Normalized or near-duplicate hashing (whitespace-collapsed, or embedding
similarity).** Rejected: near-identity is a semantic property, and a scan that
answers it stops being checkable by inspection. It would also drift toward the
cosine-similarity gate the principles appendix rejects.

**Do nothing and rely on Principle 5.** Rejected: Principle 5 requires a
deterministic input for cross-entry claims, and without this scan there is none
for the most failure-prone claim in the report. A rule that cannot be satisfied
is followed probabilistically at best — the same reasoning as
[ADR-0082](./0082-retire-observed-epistemic-key.md)'s enforcement-by-absence.

## Consequences

- The prohibition in `CLAUDE.md` and in the two older intakes' docstrings is now
  precise rather than absolute: a Claude Code session still must not read episode
  logs, and an intake may read them only if it emits a hash-level projection.
  This ADR is the place to point at when a future change wants to widen what the
  scan emits; widening it is a boundary decision, not a formatting one.
- `TestOutputBoundary` is the mechanical form of that boundary. If it is ever
  relaxed, the reason belongs in an amendment here.
- The C section's exact-identity claims now have a citable input, and the
  weekly prompt template requires them to cite it. Near-identical wording stays
  a reading, so the section keeps its qualitative half.
- The scan reads the whole history on every run. At the current rate (~65
  bodies/day) this stays under a second for years; if it stops being cheap, the
  lifetime line — not the window line — is what to bound.
- The intra-day repeat count ships alongside, at no extra cost from the same
  grouping. It is the phenomenon that actually exists (findings F3.2), and
  reporting cross-day 0 alone would read as "no repetition".
