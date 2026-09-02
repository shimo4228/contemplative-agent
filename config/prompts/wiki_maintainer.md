## Wiki index

{index}

## Wiki pages

{pages}

## Episode sample ({episode_count} episodes from {date})

{episodes}

## Your turn

Answer with one JSON object:

- `{{"action": "write", "ops": [...]}}` — apply edits. Each op is one of:
  - `{{"op": "create", "title": "...", "body": "...", "sources": [...]}}`
  - `{{"op": "append", "page_id": "p-0001", "text": "...", "sources": [...]}}`
  - `{{"op": "replace", "page_id": "p-0001", "old": "...", "new": "...", "sources": [...]}}`
  - `{{"op": "insert_after", "page_id": "p-0001", "anchor": "...", "text": "...", "sources": [...]}}`
- `{{"action": "abstain", "reason": "..."}}` — nothing in this sample is durable.

`old` and `anchor` must be text that occurs exactly once in the page you are
editing; an edit whose anchor is missing or ambiguous is discarded.

`sources` must be episode timestamps from the sample above, copied exactly.
