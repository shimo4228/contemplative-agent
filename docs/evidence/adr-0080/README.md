# ADR-0080 evidence

- `core-commit-tags.md` — the `core/` commit tagging (P1-01.2).
- First frozen self-regulation table (P2-01.5): **not yet taken.** It needs the live
  `pipeline-metrics.jsonl`, `audit.jsonl` and `insight-staged.jsonl`, which are on the
  owner's Mac only. To freeze it (the earliest gate after the 11-28 reading is fine;
  six to eight weeks of history are already in the logs):

  ```bash
  python3 scripts/self_regulation_reading.py --home ~/.config/moltbook --repo . \
    --end <gate-saturday> > docs/evidence/adr-0080/self-regulation-<gate-saturday>.md
  ```

  Commit it with the gate's `gate_record` that carries `self_regulation_verdict=`.
  The `(vi)` columns are the script's own count until `pipeline/value-layer/changes.json`
  (P2-05.7) exists to reconcile against.
