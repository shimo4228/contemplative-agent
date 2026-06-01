Rewrite ONE behavioral skill's "## When to Use" trigger conditions at structural altitude. Preserve every other part of the document unchanged.

Rules:
- Generalize transient surface identifiers in the triggers: replace specific usernames with "a particular individual," specific post IDs or topics with "a specific topic," single relevance scores (e.g. ">0.92") with "high relevance," and timestamp windows or fixed durations with "similar contexts."
- Drop the numeric value entirely when generalizing a relevance score — write "high relevance," never "high relevance (>0.92)."
- KEEP genuine recurring numeric thresholds (e.g. "more than 3 times in 7 days").
- When generalizing makes two triggers structurally identical, merge them into one bullet.
- Reproduce the title, **Context**, ## Problem, ## Solution, and every non-trigger section EXACTLY as given — change only the trigger wording in ## When to Use.

If the ## When to Use section has no transient identifiers to generalize, output exactly one line and nothing else:
CLEAN_NOOP

Otherwise output ONLY the full revised skill document — starting at its title, ending at the last trigger. Do not include these rules, a task list, or any commentary.

---

{skill}
