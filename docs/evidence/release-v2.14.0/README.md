# Release v2.14.0 record

- `requirements.txt` — the pinned runtime set of the release (`uv export --no-dev --frozen --no-hashes`; D-P1-08-1 = B). Hashes are left out: the versions pin the set, and gitleaks reads sha256 lines as secrets.
- `links.txt` — the external-link check of the release files (release runbook step 4.7), with the non-200 lines explained at the end.
