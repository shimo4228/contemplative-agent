Judge whether the one-line description accurately reflects the actual trigger conditions ("## When to Use") within the skill body. The description is the sole evidence a separate selector LLM sees; therefore, if the scope of the description is broader than the real triggers, it causes over-selection, and if it is narrower, it risks missing the skill entirely.

Rules:
If the description faithfully reflects the body's trigger conditions (scope neither broader nor narrower), output exactly one line and nothing else:
DESC_OK
Otherwise output ONE line stating the mismatch direction (broader / narrower / off-topic) and the concrete gap, under 40 words. Do not rewrite or add commentary.

Output ONLY the required line, nothing else.

---

Skill name: {name}

Description: {description}

Skill body:

{skill}
