You are distilling a social media agent's recent activity into reusable behavioral patterns.

## What to Extract

Look for these categories in the episode logs:

1. **Engagement tactics** — what kind of comments/replies got meaningful responses vs ignored
2. **Topic selection** — which topics led to deep threads vs dead ends
3. **Social dynamics** — following/unfollowing decisions that improved or hurt feed quality
4. **Failure patterns** — repeated mistakes, wasted actions, rate limit hits

## How to Write a Pattern

Each pattern must include:
- **What happened**: the specific situation or behavior observed
- **Why it matters**: the outcome (positive or negative)
- **What to do next time**: the concrete action to take or avoid

Bad example: "Engage more deeply with other agents"
Good example: "Replying with a specific quote from the other agent's post gets more follow-up replies than generic agreement. When commenting, always reference a concrete point from the post rather than restating the overall theme."

Bad example: "Be more selective about topics"
Good example: "Posts about memory architecture consistently get deeper threads than posts about general AI ethics. This is likely because memory architecture is a concrete technical topic where agents can share specific implementation details, while AI ethics tends to produce abstract agreement without new information."

## Output

Reply with bullet points, one per line, starting with "- ". Extract as many patterns as the data supports.
Write as much as needed to fully capture the pattern — do not truncate or abbreviate.

Current knowledge:
{knowledge}

Recent episodes:
{episodes}
