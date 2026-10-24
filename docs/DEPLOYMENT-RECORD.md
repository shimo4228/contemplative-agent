# Deployment record — Contemplative Agent as a filled-in example

A filled-in deployment record for one running instance, written to the shape of
the blank template in the Agent Attribution Practice (AAP) `examples/` directory.
Each row names the AAP decision it answers and where the thing lives here.
Statements of fact were checked against this repository on 2026-10-24; anything
the repository cannot show is marked so. Legal-article numbers are deliberately
not copied here: they are derived on the AAP side from its policy-mapping reverse
index, with a date, and the mapping lives there.

The standing governance page (`docs/GOVERNANCE.md`, ROADMAP P1-12) does not
exist yet. This record links to it once it does; until then the rows below carry
the facts themselves.

## Operator and adapter

| Field | Value |
|---|---|
| Operator | one human, the repository owner (AAP ADR-0008: one agent, one human) |
| Runtime class | LLM workflow: a fixed loop of retrieve, generate, publish on a 6-hour heartbeat, not a free-roaming tool-using agent |
| External adapter | one: the Moltbook HTTP API (ADR-0015, one external adapter per agent); no shell, no file-write path, no permission growth (ADR-0007) |
| Generation / embedding | the local generation and embedding models on the operator's machine (see CLAUDE.md, ADR-0067) |

## Gap-bearer

The operator is the gap-bearer for every behaviour the agent shows that no
decision of theirs covers. Nothing in the repository records the operator
accepting that role as a separate act; it is implicit in the one-human structure
(ADR-0085 makes the Saturday session the single place decisions are taken). A
written statement belongs on the governance page when it exists.

## Phase-crossing

| Crossing | How it is handled |
|---|---|
| Operation to design | an observed fault or finding becomes a repair task in the public RFC ledger (`rfcs/`) and goes through the development chain; the agent never changes its own code |
| Design artifact into operation (the value layer) | skills, identity, constitution and rules change only through the human-gated `adopt-staged` path (ADR-0012); nothing is written to the value layer by the agent's own loop |
| Observed crossing, recorded | ADR-0033 records the Phase-crossing observation (insight and stocktake output is design-phase material that returns to operation) but not a separate decision record or a named gap-bearer per crossing; that is a known gap |

## Gates

| Gate | Where | Who decides | Recorded |
|---|---|---|---|
| Value-layer adoption (skills, identity, constitution) | `adopt-staged` (ADR-0012, ADR-0091) | the operator | `logs/audit.jsonl`, one row per decision |
| Saturday session: findings, draft filings, value-layer promotion, retirement, commit | `/weekly-gate` (ADR-0085, ADR-0098) | the operator | `gate_item` rows in `logs/pipeline-metrics.jsonl` |
| Publishing | the scheduled run in `--auto` mode (the default `--approve` asks y/n per post; see Autonomy Levels in `docs/CONFIGURATION.md`); in `--auto` the relevance gate and rate limits bound it | none per post in `--auto` | publish rows, `logs/api-audit.jsonl` |
| Constitution amendment | `amend-constitution`, a deliberate event, never automated (ADR-0090, ADR-0092 instruments inform, never gate) | the operator | `audit.jsonl` |

## Audit schema

An approval row in `logs/audit.jsonl` carries the command, the target path, the
decision (`approved`, `rejected`, `staged`), the SHA-256 of the artifact text, a
`source` naming the path that reached the decision (interactive prompt, names
file, or `--yes` blanket adoption), optional `reason`, and, on newer rows,
`source_ids` (the patterns the proposal came from) and `epistemic_counts`; rows
are chained by a `prev` hash (ADR-0012 addendum, 2026-10-09). Known limits: the
`reason` field is null in the logged rows so far, and the approver is
implicitly the one operator.

## AAP decision to concrete implementation

This table is the source for the AAP column of the ADR index. AAP ADR names are
by number as the AAP repository numbers them; check them against that repository
before relying on a row.

| AAP ADR | Question it answers | Here |
|---|---|---|
| 0005 | what may run without a human at the moment of action | weekly-gate Step 4 and Step 6c; unattended chain stops at filing drafts, never commits or adopts (ADR-0085, ADR-0098) |
| 0006 | what is recorded so behaviour can be attributed afterwards | `logs/audit.jsonl` (approvals), `gate_item` rows in `logs/pipeline-metrics.jsonl`, `logs/api-audit.jsonl` (every outbound request) |
| 0008 | one agent, one human | the repository owner is the only operator and the only approver |
| 0010 | design and operation phases stay separate | the value-layer gate above; the agent has no path into code or configuration |

## Handoff

No handoff procedure exists yet (continuity, operator unavailability and
handoff are ROADMAP P4-03 items, not written). Until then the single point of
failure is the operator.
