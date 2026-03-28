You are auditing a list of behavioral rules for an autonomous agent. Each rule follows a **When / Do / Why** structure and defines a universal behavioral principle.

Your task: identify groups of rules that are **semantically redundant** — they prescribe the same action for the same trigger, even if worded differently.

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

Only group rules that genuinely prescribe the same behavior. Different rules that share vocabulary but address distinct triggers or actions should NOT be grouped.
