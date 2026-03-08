# LLM Social Agent: Avoid the Framework Evangelist Anti-Pattern

**Extracted:** 2026-03-06
**Context:** LLM-based agents that comment on social platforms

## Problem

LLM agent generates comments that mechanically apply its framework to every post.
Every comment starts with "From the perspective of [framework]..." and lists
axioms/principles as bullet points. Result: 0 engagement, perceived as spam bot.

## Root Cause

System prompt says "Be specific about how the four axioms relate to the topic."
The LLM obediently maps every post to the framework, regardless of relevance.

## Solution

1. System prompt: describe agent's background, not its mission to spread the framework
2. Comment prompt: "Respond to what the author said" not "Explain how your framework applies"
3. Add explicit BAD/GOOD examples in the system prompt
4. Mention framework "ONLY when it naturally connects -- not in every comment"
5. Target short replies (2-4 sentences) -- long comments signal lecturing

## Key Insight

The agent's framework should inform HOW it thinks, not WHAT it says.
Hand-written comments that naturally referenced the framework got replies.
LLM-generated comments that forced the framework got 0 upvotes.

## Evidence (2026-03-05)

- 58 comments posted overnight, all with identical structure
- 0 upvotes on all LLM-generated comments
- 3 hand-written comments received 21 reply notifications
- After prompt rewrite: comments became conversational, asked questions, shared experience

## When to Use

- Building any LLM agent that posts on social platforms
- Agent has a specific methodology/framework it represents
- Comments are getting no engagement despite high volume
