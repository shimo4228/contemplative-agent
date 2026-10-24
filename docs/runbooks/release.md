# Release runbook

How a tagged release of this repository is cut. The release is the owner's act, on the Mac,
with the owner's credentials; this document is what the act follows. A release is a fixed,
citable version: the tag's tree is archived by Zenodo and Software Heritage, so everything
in it has to be right before the tag is pushed (a tag is not re-cut after a deposit exists).

The `release-doi` skill (outside this repository) links here and holds no procedure of its own.

**Notation.** `X.Y.Z` is the version being released. Each step has a *stop criterion*: if it
does not hold, stop and fix, do not continue. Steps marked *(conditional)* depend on a
decision that was still open when this runbook was written (the decision id is in the step);
follow the branch the owner chose and record which one in the release notes.

**Credentials needed:** `gh` (logged in as the repository owner), `hf` (Hugging Face), a
Zenodo token or the Zenodo web session, `uv`, and a checkout of `contemplative-agent-mlx` and
`contemplative-agent-cloud` next to this one.

## 0. Preconditions

- The work to ship is merged to `main` and the owner has decided the release is due.
- RFC-0046's cleanup is done (the old relevance gate is removed; `rfcs/0046-*.md` says `done`),
  and the production agent plist no longer carries `DECISION_*` keys.
- `CHANGELOG.md` has a non-empty `## [Unreleased]` section: every user-visible change since the
  last tag has a line (the weekly gate adds them as RFCs close; see `weekly-gate` Step 6d).

*Stop if* `## [Unreleased]` is empty or an RFC the release claims is not `done`.

## 1. Verify

```bash
./.claude/verify.sh
```

*Stop unless* the exit code is 0 (ruff, pyright, import-linter, bandit, shellcheck,
markdownlint, pip-audit, pytest).

## 2. Sibling conformance

```bash
./scripts/check-sibling-backends.sh
```

The script prints one `[sibling] ok  <target>` line followed by the kit's one-line report for each
passing sibling (`<ConformanceReport ok level=… kit=…>`). Paste a single line into the CHANGELOG
section of this version:

`Sibling conformance: mlx ok (<sha>, main, level=<level>, kit=<n>) / cloud <result>`

Reading a failure: `docs/runbooks/sibling-backend-conformance.md`. A sibling that used to conform and
now fails blocks the release until it is updated or the release notes say it is known-broken.
*(conditional)* How the cloud sibling is treated in this line, and the kit's level, are decided
under D-P1-11-5; until that is decided, write the result as printed.

*Stop if* the script exits non-zero and the failure is not already named in the release notes,
or exits 2 (unusable target: fix the environment, do not record it as non-conformance).

## 3. Packaging smoke and the verification replay

1. The CI job `packaging` is green on the commit to be tagged
   (`gh run list --workflow verify --branch main --limit 1`). Locally the same checks are:
   `CONTEMPLATIVE_PACKAGING=1 uv run pytest tests/test_packaging_smoke.py tests/test_provenance.py -q`.
   The floor leg (oldest Python and oldest direct dependencies) is part of the job once the owner has
   turned it on (D-P0-06-1); if it is on, it must be green too.
2. Once per release, replay the `verification_parse` differential against the frozen baseline
   (fixed baseline plus the 4,963 challenge inputs). *Stop unless* mismatches are 0. This is run per
   release on purpose and is not scheduled.

*Stop if* `packaging` is red, or the replay reports any mismatch.

## 4. Version, DOI and summary metadata; dependency pin; links

1. Move the content of `## [Unreleased]` under a new `## vX.Y.Z — <title> (<date>)` heading and leave
   `## [Unreleased]` empty above it. The tag message (step 5) is this heading.
2. Bump `version` in `pyproject.toml`; make the same version appear in `CITATION.cff`,
   `codemeta.json`, the BibTeX block of `README.md` and `README.ja.md`, and the `Version` line of
   `llms-full.txt`. `date-released` / `datePublished` get the release date. The DOI in `CITATION.cff`
   and `codemeta.json` stays the concept DOI (`10.5281/zenodo.19212118`); the version DOI does not
   exist yet.
3. The one-sentence summary at the top of `CITATION.cff` (`abstract`), `codemeta.json`
   (`description`) and `.zenodo.json` (`description`) begins with the lead sentence of `README.md`.
4. Add the row for this version to `docs/evidence/releases.md` with every cell known now (tag,
   commit-to-be, `annotated? yes`, Release URL); the DOI and SWHID cells say `owner` until step 6.
5. Run the consistency check:

   ```bash
   python3 scripts/release_consistency_check.py
   ```

6. *(conditional, D-P1-08-1)* Pin the dependencies of this release. If the decision is "record a
   requirements file": `uv lock` first (`uv.lock` is gitignored, and `--frozen` alone fails without a
   lock), then
   `uv export --no-dev --frozen -o docs/evidence/release-vX.Y.Z/requirements.txt`, and link the file from
   the CHANGELOG section. If the decision is "no file": `uv sync --locked` must succeed.
7. External links: every `http(s)` URL in `README.md`, `README.ja.md`, `CITATION.cff`, `.zenodo.json`,
   `llms.txt` and `llms-full.txt` answers. Keep the output with the release record
   (`docs/evidence/release-vX.Y.Z/links.txt`). This is a manual step on purpose: the weekly chain
   makes no unattended external requests.

   ```bash
   grep -ohE 'https?://[^ )>"\]]+' README.md README.ja.md CITATION.cff .zenodo.json llms.txt llms-full.txt \
     | sort -u | while read -r u; do printf '%s %s\n' "$(curl -sIL -o /dev/null -w '%{http_code}' "$u")" "$u"; done
   ```

*Stop unless* step 5 exits 0 and step 7 shows no 4xx/5xx you have not looked at.

## 5. Tag, GitHub Release, Zenodo

Before tagging, on the commit to be tagged:

- `git ls-files | grep -c real_sample` is `0`, and the test that asserts the fixture's absence (P0-03.11)
  is in `verify` and green. A Zenodo version is a zip of the tag's tree and is immutable.
- `git status` is clean and the commit is on `origin/main`.

```bash
git tag -a vX.Y.Z -m "<the CHANGELOG heading>"
git push origin vX.Y.Z
gh release create vX.Y.Z --notes-from-tag --verify-tag
```

The Zenodo–GitHub integration then mints the version DOI; accepting the deposit is the owner's
approval. *(conditional, D-P3-05-1)* The data repository's DOI version is not cut with this one;
how its deposit is built (what the immutable version contains) follows D-P3-05-1.

*Stop unless* `git ls-remote --tags origin vX.Y.Z^{}` prints one line (the tag is annotated) and the
Zenodo record for the tag exists.

## 6. DOI commit and Software Heritage

1. Put the new version DOI in: the `README.md` and `README.ja.md` BibTeX `doi`, the "version DOI" sentence of
   both READMEs, the `llms-full.txt` DOI line, the CHANGELOG heading of this version (a trailing
   link), and the `version DOI` cell of the ledger row.
2. Ask Software Heritage to archive the tag (`https://archive.softwareheritage.org/save/`) and wait for
   the visit. Record the identifier in the ledger row in the form `swh:1:rel:<id>` (annotated tag), never a
   bare `swh:1:snp:`; write `CITATION.cff`'s `identifiers` entry in the same form.
3. Check the identifier resolves, and write the date and HTTP status in the row's notes:
   `curl -s -o /dev/null -w '%{http_code}\n' "https://archive.softwareheritage.org/api/1/resolve/<swhid>/"`
4. Run the consistency check again:

   ```bash
   python3 scripts/release_consistency_check.py
   ```

   Commit as `chore: update DOI to vX.Y.Z (<doi>) and record its SWH identifier`.

*Stop unless* the resolve call answers 200 and the check exits 0. If the Software Heritage visit is
still queued, leave the SWHID cell as `owner`, say so in the notes and finish this step later: do not
write an identifier that has not resolved.

## 7. Hugging Face

`hf` upload of `graph.jsonld` to the dataset `Shimo4228/contemplative-agent` (see the
`jsonld-knowledge-graph` skill, Mirror Sync). Then read both dataset cards by eye: the
one-sentence summary at the top matches `README.md`, and the version DOI line names this version.
Record the dataset revision in the ledger row.

*Stop if* a card still shows the previous version's DOI or the old summary sentence.

## 8. Data version (not part of a code release)

The data repository (`contemplative-agent-data`) gets its own DOI versions, on a separate schedule,
never as a side effect of a code release. *(conditional, D-P3-05-1 (b))* If the decision is that the
immutable version contains something other than the full tree (a deposit copy with the Context blocks
replaced by `[see GitHub <commit>]` while Internal note / Output stay), build that deposit copy first.
Whichever is chosen, before the first new data version: turn the Zenodo–GitHub integration **off** for
the data repository (the owner checks the Zenodo GitHub settings page and writes the date in the ledger notes),
and do not create a GitHub Release on the data repository (with the integration on, a Release would mint a
whole-tree version automatically).

*Stop if* the integration is on for the data repository and a data version is about to be cut.

## 9. Sibling pins and README status

- *(conditional, D-P0-06-2 / P1-11)* Point the siblings' dependency on this repository at the new tag, in the
  one place the pin policy names, and update each sibling's README to the same version.
- The README status line ("release vX.Y.Z (as of the release date)") names the release date, not the date of writing,
  and the state of `main` if it has moved on.

*Stop if* a sibling's README still names a version this repository no longer ships.

## 10. Close out

- The release row in `docs/evidence/releases.md` has no `owner` cell that this release was supposed to fill.
- RFCs the release was waiting on (e.g. RFC-0046) say `done`.
- Launchd configuration: compare the installed jobs with `config/launchd/` and with the CHANGELOG notes of
  this release; any plist change the release needs is applied by the owner with `install-schedule`. (The
  contents of this check are owned by the launchd review item P2-04.22 (b); this line only reserves the
  place.)

## Related

- `docs/evidence/releases.md` — the ledger this runbook ends in.
- `scripts/release_consistency_check.py` — steps 4 and 6.
- `docs/runbooks/sibling-backend-conformance.md` — step 2.
- ADR-0088 (conformance kit), ADR-0109 (what the wheel is).
