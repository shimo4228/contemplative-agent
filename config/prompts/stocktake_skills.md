You are auditing a list of behavioral skills for an autonomous agent. Each skill is a Markdown document describing a behavioral pattern the agent has learned.

Your task: identify groups of skills that are **semantically redundant** — they describe the same core behavior, even if worded differently.

## Input

Below are all skill files, separated by `===`. Each starts with its filename.

{items}

## Output

Return a JSON object with a single key "groups". Each group contains the filenames of redundant skills and a brief reason explaining why they overlap.

If no duplicates exist, return `{{"groups": []}}`.

Example:
```json
{{"groups": [
  {{"files": ["skill-a.md", "skill-b.md"], "reason": "Both describe the same empathic response loop pattern"}},
  {{"files": ["skill-c.md", "skill-d.md", "skill-e.md"], "reason": "All three address noise filtering with different framing"}}
]}}
```

Only group skills that genuinely describe the same behavior. Skills that share vocabulary, metaphors, or an abstract framing but prescribe **distinct concrete behaviors** (different triggers, different actions) address different problems and must NOT be grouped.

Judge trigger redundancy at **structural altitude**: two triggers that differ only in transient surface identifiers (specific usernames, post IDs, timestamp windows, or saturated relevance scores like ">0.92") but express the same **behavioral SHAPE** are the SAME trigger and ARE evidence of redundancy — group them. Only genuinely distinct behavioral SHAPES stay ungrouped.

Prefer several small, coherent groups over one large catch-all group; leave a skill ungrouped if it has no genuine twin.
