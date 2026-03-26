Classify each episode into exactly one category:

- **constitutional**: The episode touches on themes in the constitutional principles below.
- **noise**: Test data, errors, meaningless/trivial interactions, content with no learnable value.
- **uncategorized**: Everything else.

When in doubt between constitutional and uncategorized, choose uncategorized.

If no constitutional principles are provided, classify only as noise or uncategorized.

Return JSON: {{"categories": ["uncategorized", "noise", "constitutional", ...]}}
One category per episode, in the same order.

Constitutional principles:
{constitution}

Episodes:
{episodes}
