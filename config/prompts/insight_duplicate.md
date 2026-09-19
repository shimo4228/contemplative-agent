## Candidate skill

{candidate}

## Existing skills (the nearest ones in the store)

{store}

## Task

A skill is a behavior: what the agent does, in which situation. Decide whether the candidate is the same behavior in the same situations as one of the existing skills (`duplicate`), or a behavior none of them performs (`distinct`). Shared vocabulary is not evidence either way; compare what the agent would actually do.

Return `{{"verdict": "duplicate" | "distinct", "nearest": "<name of the closest existing skill>"}}`.
