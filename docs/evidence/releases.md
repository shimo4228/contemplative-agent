# Release ledger

One row per version identifier the project has published. The release procedure
([docs/runbooks/release.md](../runbooks/release.md), last step) appends the new
row; `scripts/release_consistency_check.py` reads this file and fails when a
CHANGELOG heading, the README BibTeX or a SWHID cell disagrees with it.

Written 2026-10-24 (P0-06.6 / P0-06.11), from `git ls-remote --tags origin`, the
GitHub releases list and the repository text. Nothing in this file was read from
Zenodo or Software Heritage: both were unreachable from the drafting session, so
those cells say `owner` (the owner reads them, once, and replaces the word).

## Columns

| Column | Meaning |
|---|---|
| tag | the git tag |
| commit | the commit the tag points at (the peeled commit for an annotated tag) |
| annotated? | `yes` = a tag object exists (`^{}` line in `git ls-remote`); `no` = lightweight |
| Release URL | the GitHub Release page, or `none` |
| version DOI | the Zenodo version DOI of that tag, bare (`10.5281/zenodo.N`); `owner` = not yet read from Zenodo; `none` = checked, no deposit |
| SWHID | **`swh:1:rel:<id>`** for an annotated tag, or **`swh:1:dir:<id>;origin=…;visit=…;anchor=swh:1:rev:<commit>`** for a lightweight tag; a bare `swh:1:snp:` is not allowed (a snapshot names the whole repository at visit time, not one version). `owner` = no resolved identifier recorded yet |
| HF revision | the Hugging Face dataset revision that mirrored this version, `n/a`, or `owner` |
| notes | free text; `candidate` ids are derived from git alone and have not been resolved against the Software Heritage API |

`owner` cells are the standing to-do list of this ledger. Resolution record for
a SWHID (date and HTTP status of `https://archive.softwareheritage.org/api/1/resolve/<swhid>/`)
goes in notes, per row, when the owner has done it.

## contemplative-agent

| tag | commit | annotated? | Release URL | version DOI | SWHID | HF revision | notes |
|---|---|---|---|---|---|---|---|
| v2.14.0 | dc02cbeba64344c41524748bf8abd76acf00dc16 | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.14.0 | 10.5281/zenodo.23837915 | owner | owner | cut 2026-10-31; Zenodo record created 2026-10-31T13:48Z; Software Heritage save request 2599267 accepted 2026-10-31T14:04Z (visit pending; SWHID owner until it resolves); Wayback snapshot 2026-10-31 |
| v2.13.0 | a2fe2693beea90827032e4e23f1a8b879f9dddba | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.13.0 | 10.5281/zenodo.23340441 | swh:1:rel:2c0c1f752051fe468076370fed93fb16d632b224 | owner | resolved 2026-10-31: `api/1/resolve/swh:1:rel:2c0c1f75…/` → 200, and `api/1/release/…` names v2.13.0 with target revision a2fe2693 (the tag's commit); the CITATION.cff snapshot swh:1:snp:70665478e21d8e2a80030f89256c7da56b507362 → 200, and its branch `refs/tags/v2.13.0` targets this release; DOI read from README / CITATION.cff / codemeta.json (682de21) |
| v2.12.0 | 950f190c1f8735926bc42310b804f3b31a8debce | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.12.0 | 10.5281/zenodo.22724623 | owner | owner | candidate swh:1:rel:11777165f1b7364ca8b191213ec5fe4bc216139c (tag object); DOI read from the README at the v2.13.0 tag ("version DOI for v2.12.0") |
| v2.11.0 | 78491f64802e2c745bd194d29409c338c1b363d8 | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.11.0 | 10.5281/zenodo.22028295 | owner | owner | candidate swh:1:rel:85f19fdba88839a94fadc4935d40b52f2e4a5b50 (tag object); DOI read from CITATION.cff inside the v2.12.0 tag (950f190), which cited the previous version; unconfirmed on Zenodo |
| v2.10.0 | f8b7f5dde48ce1d3fb62d9db94be06d83913c38b | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.10.0 | owner | owner | owner | candidate swh:1:rel:cfa6d39bfb5b4ddd818be86a74fb4f913c77ddab (tag object); the v2.11.0 tag's CITATION.cff cites 10.5281/zenodo.21861966, probably this version's (the self-citation drift), unconfirmed |
| v2.9.0 | 0b8a7903d0b4f8f8c60858d13af7797abc8b5985 | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.9.0 | owner | owner | owner | candidate swh:1:rel:6893db984a0e76524fa70183e135500bfd130228 (tag object) |
| v2.8.0 | 161224b87814d3c45d9a388a3c40168afe6c10f3 | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.8.0 | owner | owner | owner | candidate swh:1:rel:540271746e221838bf221a1c004756b572d048d1 (tag object) |
| v2.7.0 | 3e0fa686748809813a0dce946f54f4f90afa0ee5 | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.7.0 | owner | owner | owner | candidate swh:1:rel:38b51e1c748b03058f407b35885378f9aa8546b0 (tag object) |
| v2.6.0 | b845e81516637a13b306243bdeb981f7815dc5bd | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.6.0 | owner | owner | owner | candidate swh:1:rel:9288d142530117a17624850178e6d90be1217d5c (tag object) |
| v2.5.0 | 7ba699652c0a5dc86e70c95942afd87827bf49bc | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.5.0 | owner | owner | owner | candidate swh:1:rel:053868fc5c8ae54300eed94ddaa9decbe3f3260d (tag object) |
| v2.4.0 | 821fcbc1760a1201cb9e837500b5c03402b5d5b0 | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.4.0 | owner | owner | owner | candidate swh:1:rel:a57c984a8881bd7e1699c887d3af6dfa9bfa62ce (tag object) |
| v2.3.0 | a80134e5d337b7a8ab7312435b717f8d98bd868c | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.3.0 | 10.5281/zenodo.19212119 | owner | owner | candidate swh:1:rel:00d9e071d50dc853cf19fc06a69b9badea98b1fa (tag object); DOI read from the Hugging Face dataset card ("Per-version DOI (v2.3.0)"); unconfirmed on Zenodo |
| v2.2.1 | 3cee749388031e2405673c39a6d9a53cd380cbc2 | no | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.2.1 | owner | owner | owner | candidate swh:1:dir:e2c1972dfa746d0fa8fa6c2366a1547a28ce1c59 anchored at swh:1:rev:3cee749388031e2405673c39a6d9a53cd380cbc2 (tree of the commit) |
| v2.2.0 | b7db2153073db35ef1e1eb62e0a3363117b799e2 | no | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.2.0 | owner | owner | owner | candidate swh:1:dir:41c351ada1711d91a160dd4439c55a613992c766 anchored at swh:1:rev:b7db2153073db35ef1e1eb62e0a3363117b799e2 (tree of the commit) |
| v2.1.0 | 963f93e5148395a69dbcd02375c29317a3f73af3 | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.1.0 | owner | owner | owner | candidate swh:1:rel:d2b15307c7b719b402a949b47e08998b64851529 (tag object) |
| v2.0.0 | ed9236b83c732a4165e45b2d109eef8995a4bfed | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v2.0.0 | owner | owner | owner | candidate swh:1:rel:5e62850a1687c5e590106281344479519dad1689 (tag object) |
| v1.3.1 | 0b1cce5f32f254d899300ad1a79539f573069130 | no | https://github.com/shimo4228/contemplative-agent/releases/tag/v1.3.1 | owner | owner | owner | candidate swh:1:dir:4341d2785014053a5ec2cdc978cc023bd71ab151 anchored at swh:1:rev:0b1cce5f32f254d899300ad1a79539f573069130 (tree of the commit) |
| v1.3.0 | 4c1e3ef874cac9d910cf1422f93a18f900f3c7d1 | yes | https://github.com/shimo4228/contemplative-agent/releases/tag/v1.3.0 | owner | owner | owner | candidate swh:1:rel:7a7c64343b62277276212dab59fc5abf246a17d4 (tag object) |
| v1.2.0 | c10940985b07a9856213d5096e78eb907eba46a0 | no | https://github.com/shimo4228/contemplative-agent/releases/tag/v1.2.0 | owner | owner | owner | candidate swh:1:dir:0a7e38ab6dedb169df416c25543a8ed76e2dfbe4 anchored at swh:1:rev:c10940985b07a9856213d5096e78eb907eba46a0 (tree of the commit) |
| v1.1.0 | 650589f3ef713aefaeecf23c34a554f19c037b07 | no | https://github.com/shimo4228/contemplative-agent/releases/tag/v1.1.0 | owner | owner | owner | candidate swh:1:dir:9a378c7af4260dbf797f4e86cb3caab985585c1e anchored at swh:1:rev:650589f3ef713aefaeecf23c34a554f19c037b07 (tree of the commit) |
| v1.0.0 | 855899a28e1402f34130204fc243feddd1366fcc | no | https://github.com/shimo4228/contemplative-agent/releases/tag/v1.0.0 | owner | owner | owner | candidate swh:1:dir:227d4527c78db0f8f657a3cb8928a9e9f3c254b9 anchored at swh:1:rev:855899a28e1402f34130204fc243feddd1366fcc (tree of the commit) |
| v0.3.0 | a0d47ec08318a1fff7e04040ced8c2b17ce7193c | no | https://github.com/shimo4228/contemplative-agent/releases/tag/v0.3.0 | owner | owner | owner | candidate swh:1:dir:efdfd377593c997d08c8e1f45432cc6efe246cc0 anchored at swh:1:rev:a0d47ec08318a1fff7e04040ced8c2b17ce7193c (tree of the commit) |
| v0.2.0 | 671698739cfdb9b7252ec2ef653012bdba711f87 | no | https://github.com/shimo4228/contemplative-agent/releases/tag/v0.2.0 | owner | owner | owner | candidate swh:1:dir:b7b4ae5f15b513ccf3e11e237b3ec884865f6ae5 anchored at swh:1:rev:671698739cfdb9b7252ec2ef653012bdba711f87 (tree of the commit) |

CITATION.cff lists a `swh:1:snp:` identifier for v2.6.0 through v2.13.0. Those are
snapshot ids: valid, but they do not single out one version, so they stay in
CITATION.cff only until the `rel` / `dir` forms above are resolved and replace them
(P0-06.11, owner step).

## contemplative-agent-data

| tag | commit | annotated? | Release URL | version DOI | SWHID | HF revision | notes |
|---|---|---|---|---|---|---|---|
| v1.1.0 | c9100c4c217bb0f71da71d76d5cff85773ff239e | yes | https://github.com/shimo4228/contemplative-agent-data/releases/tag/v1.1.0 | 10.5281/zenodo.23837886 | owner | owner | pairs with v2.14.0; the tagged tree is the deposit (D-P3-05-11); Zenodo record created 2026-10-31T13:46Z; Software Heritage save request 2599268 accepted 2026-10-31T14:05Z; Wayback snapshot 2026-10-31 |
| v1.0.0 | acc3ad961fe942c6d41aefa183f9b5a84de436eb | no | none | owner | owner | owner | lightweight tag on the data repo; its CITATION.cff carries the concept DOI and version 1.0.0 only; `candidate` dir id not derived (data repo is overwritten daily by the sync) |
