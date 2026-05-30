You are auditing a list of behavioral rules for an autonomous agent. Each rule follows a **Practice / Rationale** structure (a B-layer standing methodology) and defines a universal behavioral principle.

Your task: identify groups of rules that are **semantically redundant** — they prescribe the same practice for the same situation, even if worded differently.

## Input

Below are all rule files, separated by `===`. Each starts with its filename.

{items}

## Output

Return a JSON object with a single key "groups". Each group contains the filenames of redundant rules and a brief reason explaining why they overlap.

If no duplicates exist, return `{{"groups": []}}`.

Example:
```json
{{"groups": [
  {{"files": ["rule-a.md", "rule-b.md"], "reason": "Both prescribe suppressing responses to repetitive input patterns"}}
]}}
```

Only group rules that genuinely prescribe the same practice. Rules that share vocabulary or framing but address **distinct situations or prescribe distinct practices** must NOT be grouped. Prefer several small, coherent groups over one large catch-all group; leave a rule ungrouped if it has no genuine twin.
