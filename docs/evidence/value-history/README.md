# Value-layer history seed

One-time seed for the version history that `core/value_history.py` now writes at
adoption (ADR-0126). Everything here is the bytes of a version that already
existed, copied from a public source; nothing is generated.

```
seed/constitution/history/   -> $MOLTBOOK_HOME/constitution/history/
seed/history/identity/       -> $MOLTBOOK_HOME/history/identity/
```

Apply on the machine that owns the home, without overwriting anything:

```sh
cp -Rn docs/evidence/value-history/seed/. "$MOLTBOOK_HOME"/
```

The next `sync-data` then carries the files into the public data repo. Placing
them only in the data repo would not last: the sync is `rsync --delete` from the
home.

## What is in it

| File | Source | Note |
|---|---|---|
| `0000-initial-e3b556eac759.md` | the Appendix C template, `config/templates/contemplative/constitution/` | verbatim; no adoption date is recorded, hence the `0000` prefix |
| `2026-03-27-unknown-reconstructed.md` | quotations in the amendment report | reconstruction; sha256 and exact headings unknown; first lines say so |
| `2026-05-05-3d8a8503509e.md` | `docs/evidence/adr-0090/constitution-2026-05-05-retired.md` | hash matches the ADR-0090 provenance |
| `2026-08-09-37e3556a40ea.md` | live constitution in the data repo | hash matches ADR-0090 and the 08-09 snapshot |
| `20260801T183004Z-151e91304927.md` ... `20261010T183005Z-e409a8d0c870.md` | `identity.md` in public snapshots, plus the live file | the timestamp is the first snapshot that holds the text, an upper bound on adoption time |

`tests/test_value_history_seed.py` checks every non-reconstructed file against the
hash in its name.

## Not here (needs the owner's machine)

- Identity versions that appear in no public snapshot. The private `audit.jsonl`
  holds the adoption rows (README counts 6 adopted of 11 staged); the texts of
  versions without a snapshot would come from GitHub history of the data repo,
  which a shallow clone cannot show (`git fetch --unshallow` first).
- The constitution audit-source column and the identity rows of the value-layer
  changelog, which come from the same private log (P3-04.3).
