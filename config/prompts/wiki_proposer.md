## Wiki index

{wiki_index}

## Skills the store already holds

{skill_index}

## Evolution log — every candidate ever proposed, and how it ended

{evolution}

## Skill impact — how often each skill was selected (last {impact_days} days)

{impact}

## Pages and skills you have opened

{opened}

## Your turn

You may still open {opens_left} more page(s) or skill(s).

Answer with one JSON object:

- `{{"action": "open_page", "page_ids": ["p-0001"]}}` — read the pages behind those index lines.
- `{{"action": "open_skill", "skill_names": ["some-skill"]}}` — read what those skills already say.
- `{{"action": "propose", "proposal": {{...}}}}` — exactly one change, either:
  - `{{"kind": "create", "name": "...", "description": "...", "body": "...", "cited_pages": [...]}}`
  - `{{"kind": "patch", "target": "<skill name>", "op": "append" | "replace" | "insert_after",
     "anchor": "...", "text": "...", "cited_pages": [...]}}`
- `{{"action": "abstain", "reason": "..."}}` — nothing here warrants a change.

For `replace` and `insert_after`, `anchor` must be text that occurs exactly once
in the target skill's file; a proposal whose anchor is missing or ambiguous is
discarded. `append` needs no anchor.

`cited_pages` must be wiki page ids you opened in this iteration.
