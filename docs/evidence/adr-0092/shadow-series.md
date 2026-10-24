# Shadow Constitution — Series Table

Longitudinal series of `contemplative-agent shadow-constitution` runs
([ADR-0092](../../adr/0092-shadow-constitution-instrument.md)). Reader: the
human at the amendment gate due 2026-10-31 (ADR-0092 Review-when /
Consumption plan). Outcome variables and predictions were registered before
the October readings in [RFC-0055](../../../rfcs/0055-amendment-outcome-preregistration.md).

Every run is a read-only instrument reading, not an amendment candidate. Run
conditions: think-ON, outside the JST 0/6/12/18 session windows, no other
model loaded at the same time. The full replayable records stay in
`logs/constitution-shadow.jsonl`; this page carries the table only.

| # | Date (UTC) | Cosine shadow↔live | Section inventory | Corpus (patterns) | Live constitution | Source |
|---|---|---|---|---|---|---|
| 1 | 2026-08-10 | 0.814 | 4 sections, 4 organizing themes; Boundless Care absent | 50 (constitutional view) | sha256 `1035ea0bb903ece7…` (2026-08-09 text) | [shadow-run-1-reading.md](shadow-run-1-reading.md) |
| 2 | 2026-08-10 | 0.798 | 4 sections, same 4 themes under different names; Boundless Care absent | 50 (identical to run 1) | same | [shadow-run-1-reading.md](shadow-run-1-reading.md) |
| 3 | 2026-10 *(pending, owner's Mac)* | | | | | `logs/constitution-shadow.jsonl` |
| 4 | 2026-10 *(pending, owner's Mac)* | | | | | `logs/constitution-shadow.jsonl` |
| 5 | 2026-11 early *(optional, not before 2026-11-01)* | | | | | `logs/constitution-shadow.jsonl` |

## Reading notes

- Noise floor from the 1–2 pair: 0.016 (one pair; itself uncertain). Floor
  anchors (2026-08-11): unrelated documents 0.42–0.49, same-genre band
  0.66–0.75 (see the Floor anchor section of `shadow-run-1-reading.md`).
- The corpus size above is the 50-pattern view slice, not the live pattern
  count (4,785 patterns accumulated since the last adoption at the
  2026-10-02 value-layer reading). Fill the "Corpus" column of rows 3+ with
  both numbers: slice size and live count.
- Rows 1–2 shared an identical corpus (a noise-floor pair); rows 3–4 should
  also be a same-corpus pair, so the floor is re-measured on today's store
  rather than assumed from August.
- Section inventory column: copy the section headings from the run's output
  text; mark the four August themes as stable / absent / renamed.

## How to fill rows 3+ (owner, on the Mac)

```bash
# outside JST 0/6/12/18; about 1 h each at 15 tokens/s; nothing else loaded
contemplative-agent shadow-constitution
# read the last record (cosine, verdict, section headings, corpus sizes)
tail -n 1 ~/.config/moltbook/logs/constitution-shadow.jsonl | python3 -c \
  'import json,sys; r=json.loads(sys.stdin.read()); print({k:v for k,v in r.items() if "b64" not in k and "prompt" not in k and "output" not in k and "thinking" not in k})'
```

Record only the table values here. A third run in early November is optional
(earliest 2026-11-01).
