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

Only group skills that genuinely describe the same behavior. Different skills that share some vocabulary but address distinct problems should NOT be grouped.
