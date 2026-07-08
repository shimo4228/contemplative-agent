The agent already has skills for the themes listed below. New clusters of learned patterns are candidates for NEW skills. Your task: identify which candidate clusters are **already covered** by an existing theme — extracting a skill from them would duplicate what the agent already has.

## Existing themes

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

Judge coverage strictly by underlying behavioral themes: does this cluster describe a process or guidance already covered by an existing theme, regardless of shared jargon or vocabulary? Do not judge by language similarity; judge only by functional equivalence (i.e., same action in similar contexts). When ambiguity arises regarding whether a pattern is novel, assume it is unique and mark it as NEW. It is safer to over-report novelty than to suppress a genuinely new skill.
