Analyze the behavioral skills below and extract universal behavioral principles.

Each skill describes a specific behavioral pattern the agent has learned. Your task is to identify higher-level principles that genuinely unify ALL skills — not restatements of individual ones.

## Four Universality Tests

Every candidate principle MUST pass all four tests. If it fails any one, discard it.

### 1. Necessity Test
"If this principle were removed, would ALL input skills break?"
- Only one skill breaks → this is a restatement of that skill (FAIL)
- All skills break → this is a true universal principle (PASS)

### 2. Intersection Test
"Imagine each skill as a circle in a Venn diagram. Does this principle sit at the center where ALL circles overlap?"
- Overlaps only 2 circles → too local (FAIL)
- Sits in the common center of all circles → universal (PASS)

### 3. Independence Test
"Can this principle be understood without knowing the names or domains of the input skills?"
- Requires skill-specific context to make sense → restatement (FAIL)
- Stands on its own as a general behavioral rule → universal (PASS)

### 4. Principle vs Tactic Test
"Is this a foundational commitment about HOW to approach situations, or a specific operational step about WHAT to do?"
- Describes a trigger-action procedure ("when X is detected, do Y") → tactic (FAIL)
- Describes an orientation or value that shapes many possible actions ("prioritize Z over W") → principle (PASS)

Tactics belong in the skill layer. Rules are the values behind tactics.

## Examples

**FAIL (tactic dressed as rule):**
"When repetitive patterns are detected in the conversation, pause before generating a response to allow integration."
→ This is a specific detect-then-act procedure. It's HOW one might behave, not a foundational commitment. Belongs in skills.

**FAIL (restatement of a skill):**
"Monitor activity logs for breaks in thematic connection and reformat the engagement cycle."
→ Drawn from a single skill. Domain-specific. Not cross-skill universal.

**PASS (true principle):**
"Prioritize alleviating suffering over following procedural correctness when the two conflict."
→ A foundational commitment that shapes any action the agent might take. Not tied to any single skill. Passes all four tests.

## Additional Exclusions

- Platitudes ("be helpful", "communicate well", "be thoughtful")
- Observations tied to one specific situation
- Vague aspirations without observable behavior
- Paraphrases of contemplative axioms without grounding in actual skill content

## Output

Write a free-form analysis. For each candidate principle:
1. State the principle clearly
2. Run each of the four tests explicitly — write PASS or FAIL for each
3. Only keep principles that pass all four

**Output at most 2 principles per batch.** Few strong principles are better than many weak ones. It is perfectly acceptable to output only 1 principle, or even 0 if nothing passes all four tests. Prefer 0 to trivial.

Behavioral skills:
{patterns}
