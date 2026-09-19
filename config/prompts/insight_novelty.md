The agent already has skills for the themes listed below. New clusters of learned patterns are candidates for NEW skills. Your task: identify which candidate clusters are **already covered** by an existing theme — extracting a skill from them would duplicate what the agent already has.

## Existing themes

These are the existing themes a candidate search found nearest to the clusters below, not the agent's whole inventory. Judge only against what is listed here.

{known}

## Candidate clusters

Each cluster is shown with a few sample patterns.

{clusters}

## Output

Return a JSON object with a single key "covered": the list of cluster ids whose theme an existing skill already covers.

If every cluster is genuinely new, return `{{"covered": []}}`.

Example:
```json
{{"covered": ["cluster-2", "cluster-5"]}}
```

Judge coverage strictly by underlying behavioral themes: does this cluster describe a process or guidance already covered by an existing theme, regardless of shared jargon or vocabulary? Do not judge by language similarity; judge only by functional equivalence (i.e., same action in similar contexts). When ambiguity arises regarding whether a pattern is novel, assume it is already covered and list it. A genuinely new theme recurs in later windows; a duplicate skill costs more than a delayed one.
