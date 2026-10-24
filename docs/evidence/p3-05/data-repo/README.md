# Data-repo changes for the owner to apply (Mac side)

The data repository is an `rsync --delete` mirror of `MOLTBOOK_HOME`, except for the
files kept by hand: `DATACARD.md`, `NOTICE`, `README.md`, `README.ja.md`,
`llms.txt`, `graph.jsonld`, `CITATION.cff`, `.zenodo.json`. Nothing here was written
to that repository; the edits are prepared as text.

## Apply

1. Unload the sync job (the agent's launchd label for `sync-data`), so a run does
   not collide with the checkout.
2. In the data checkout: `git apply --check hand-kept-files.patch`, then
   `git apply hand-kept-files.patch`. It rewrites `DATACARD.md` (the 7 datasheet
   sections), adds the "Third-party content & takedown" section to `NOTICE`,
   lowercases the Hugging Face id in `README*.md`, `llms.txt`, `.zenodo.json` and
   `graph.jsonld`, and fixes the stale snapshot / embedding wording in `llms.txt`
   and `graph.jsonld`. (`DATACARD.md.draft` is the same DATACARD as a whole file.)
3. Replace the placeholders (`grep -rn '<OWNER-' .`):
   - `<OWNER-ALIAS>`: the contact address for takedown and correction requests (also
     in `.zenodo.json`, `NOTICE`, `DATACARD.md`; the Hugging Face card gets the same
     sentence, see below).
   - `<OWNER-CONFIRM: …>`: the Moltbook terms clause (from the dated re-reading
     entry), the governing law and exception relied on.
   - `<date>` in the reach table, and `<OWNER-RESULT>` for the `real_sample.jsonl`
     check on the earlier version DOIs.
4. Check: `python3 scripts/docs_consistency_scan.py --repo <framework> --data-repo .`
   (from the framework checkout) should report only the three licence-prose findings
   in `llms.txt` (roadmap P0-03.14) and **zero** `data_placeholder` findings (an
   unfilled `<OWNER-...>` or `<date>` must not be committed), and the `describe` block of the DATACARD must
   match `python3 -I scripts/export-patterns-jsonl.py --describe knowledge.json`
   (the command is in the DATACARD).
5. Commit, reload the sync job.

## Hugging Face cards (external, owner token)

- `shimo4228/contemplative-agent-data` card: frontmatter `size_categories` to the
  value the hub computes (`10K<n<100K` at the time of writing, not `n<1K`); add the
  sentence "Takedown / correction requests: `<OWNER-ALIAS>` or a GitHub security
  advisory on the data repository (either works). Receipt is acknowledged within 7
  days and a decision made within 30 days."; lowercase ids.
- `shimo4228/contemplative-agent` (graph mirror) card: version = the framework's
  `pyproject.toml` version, DOI, node count from the graph; the graph's root
  `version` / `dateModified` now carry the version.
- Upload with `hf upload` (the Mac's token).

## Left undecided here

- Variant A or B for `reports/analysis/patches/` (D-P3-05-4, decided as A, recommended:
  exclude from sync; the DATACARD row keeps both sentences until the sync exclude
  helper exists).
- The next dataset version (P3-05.12) is cut after the 2026-12-05 gate: the rule is
  written into the DATACARD ("Versioning rule"); the Zenodo-GitHub integration of the
  data repository must be switched off before it.
