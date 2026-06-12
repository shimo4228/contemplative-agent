---
name: when-code-when-llm
description: Decision framework for choosing between deterministic code (regex, keyword match, AST parse, schema validation) and LLM-based processing (classification, semantic similarity, judge) for a single task. Use when you catch yourself writing a regex for a task that keeps producing false positives or negatives, or when you are about to call an LLM for something a three-line code check would handle. Covers the structural-vs-semantic axis, the false-positive test, worked examples of both directions, and the enumerate/decide split for tasks where detection is structural but resolution needs judgment.
compatibility: Developed and tested on Claude Code; portable to other Agent Skills-compatible agents.
user-invocable: true
origin: shimo4228
---

# When Code, When LLM

Code and LLMs are not in opposition. They are different tools for different kinds of work, and the failure mode is not "picking the wrong side of a debate" — it is **forcing one tool to do the other's job.**

Two symmetric failure modes to watch for:

- **Code-where-LLM-belongs.** You write a regex to classify whether a paragraph is a test or a bug report. You add patterns. You add exceptions. The regex grows and still misclassifies. The task is semantic; no amount of pattern polish will fix it.
- **LLM-where-code-belongs.** You call an LLM to "check if this filename ends in `.py`" or "validate this JSON." You pay latency, tokens, and nondeterminism for a check `str.endswith` would do in a nanosecond.

This skill is the decision rule for telling them apart, plus examples of each kind going right and wrong.

---

## The judgment axis: structural vs semantic

The question is not "is this task hard?" It is **"what kind of property am I checking?"**

### Structural properties — use code

A property is structural when it depends only on the literal shape of the input: characters, tokens, delimiters, syntax, format. A machine reading the bytes can decide it without knowing what the text "means."

Tools for structural work:

- **Regex** — pattern presence, tag stripping, token replacement, format matching
- **Keyword / substring match** — `in`, `startswith`, `endswith`
- **AST / parser** — "does this Python file define a class named `Foo`?"
- **Schema validation** — JSON Schema, Pydantic, dataclass with strict types
- **Format check** — is this a valid UUID, ISO 8601 timestamp, URL with pinned host

### Semantic properties — use LLM

A property is semantic when deciding it requires understanding what the text *means*: intent, topic, tone, category, equivalence across wording. Two inputs that differ structurally may be semantically identical, and two structurally similar inputs may mean opposite things.

Tools for semantic work:

- **LLM classification** — "is this a bug report or a feature request?"
- **Embedding similarity** — "are these two questions asking the same thing?"
- **LLM judge** — "does this response actually answer the user's question?"
- **LLM extraction** — "pull the key decisions from this meeting transcript"

---

## The false-positive test

When you are about to write a regex (or reach for an LLM), ask:

> **"Can I imagine two inputs where the same rule is right for one and wrong for the other, and the difference is about meaning — not about characters?"**

- **No** — the property is structural. Use code.
- **Yes** — the property is semantic. Use an LLM (or a classifier trained for it).

Concrete check: write the regex and think of three counter-examples in 60 seconds. If you can, the pattern is semantic. Every further regex tweak will trade one false positive for a new false negative. Stop patching and switch tools.

---

## Worked examples — code going right

These are cases where the job is structural, and code is the correct answer. LLMs would be slower, nondeterministic, and no more accurate.

### Stripping reasoning tags from LLM output

```python
def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
```

The tag is a literal delimiter. There is no "what if `<think>` metaphorically means something" case. Regex is correct.

### Removing forbidden substrings from LLM output

```python
def redact(text: str, patterns: tuple[str, ...]) -> str:
    for pat in patterns:
        text = re.sub(re.escape(pat), "[REDACTED]", text, flags=re.IGNORECASE)
    return text
```

"Does this exact string appear, case-insensitively?" is a byte-level question. Code is correct.

### Validating a config file shape

```python
schema = {"type": "object", "required": ["domain", "max_requests"]}
jsonschema.validate(config, schema)
```

Shape is structural. An LLM check ("does this config look valid?") would be both slower and less reliable.

### Routing by file extension or HTTP status code

```python
if path.suffix == ".py": run_python_handler()
if 500 <= response.status < 600: retry()
```

Byte-level, deterministic, trivially testable. Do not call an LLM for this.

---

## Worked examples — code going wrong

These are cases where code was picked for a semantic job. The symptom is always the same: the pattern grows, the exceptions multiply, and accuracy stays stuck.

### "Is this a test file or a production file?"

Tempting: `if "test" in path: ...`. Reality: `test_utils.py` is a test, `pytest_plugin.py` is a test, `testing.py` is a utility, `contest.py` is neither. The category is semantic (role in the project), not structural. An LLM or a project-specific classifier is the right tool.

### "Is this commit message a bug fix or a refactor?"

Conventional commit prefixes help (`fix:` vs `refactor:`) — that is a deliberate structural encoding of the semantic category. But if the project does not use them, scanning the message body with regex is a losing game. Ask an LLM.

### "Does this user message contain a complaint?"

Sentiment is semantic. Keyword lists ("angry", "bad", "broken") miss sarcasm, indirect complaints, and polite escalations, while firing on benign sentences that happen to contain the words.

### "Are these two error reports duplicates?"

Structural similarity (Levenshtein, shingle overlap) catches identical reports. It misses two reports of the same underlying bug with different wording. Embeddings or an LLM judge are the right tool.

---

## Worked examples — LLM going wrong

The opposite failure mode is just as common and more expensive.

### "Check if this string is a valid UUID"

`uuid.UUID(s)` in a try/except is one line and always correct. An LLM call is 200ms, costs tokens, and can hallucinate.

### "Decide if a number is even"

Yes, people write this. `n % 2 == 0`.

### "Parse JSON"

`json.loads(s)`. Do not ask an LLM to parse JSON unless the JSON is malformed and you need semantic recovery — and even then, try `json-repair` first.

### "Check that a URL is under `example.com`"

Parse with `urllib.parse.urlparse`, compare the host. Do not ask the LLM "is this URL safe" — the answer is nondeterministic and the check is trivial.

---

## Worked examples — splitting one task between both

The axis does not always cut between tasks. Sometimes it cuts **through the middle of a single task**: one stage is structural, the next is semantic. The failure mode here is treating the task as a unit — either building a heuristic that tries to *resolve* what only judgment can resolve, or asking an LLM to *enumerate* what code enumerates exactly.

### Canonical-label drift across data files

Several data files describe the same entity (same ID), and over time their display labels diverge — one file says `six-phase loop`, another says `AKC six-phase loop`.

- **Detection is structural**: "the same ID carries ≥2 distinct label values across files" is decidable from the bytes. A linter enumerates every case, deterministically, with zero false negatives. Put it in CI.
- **Resolution is semantic**: *which* label is canonical requires judgment — majority usage? the file with definitional authority? the more precise wording? No regex answers that.

The working split: **the linter reports, never auto-fixes; the review conversation decides; variants demoted to an alias field.** A lint that auto-picked (say) the longest label would be code-where-LLM-belongs; an LLM asked to re-scan all files for duplicates every time would be LLM-where-code-belongs. Each tool does exactly half.

### The same split, generalized

The pattern recurs wherever a check has an *enumerate* stage and a *decide* stage:

- **Duplicate candidate detection** (exact/near-exact match → code) vs **merge decision** (same underlying thing? → judgment)
- **Broken-link enumeration** (HTTP status → code) vs **replacement target** (what should it point to now? → judgment)
- **Style violation flagging** (line length, naming pattern → code) vs **rename choice** (what is a *better* name? → judgment)

Checklist addition for this shape: when a task resists classification, ask **"is there an enumerate/decide seam inside it?"** If yes, split at the seam instead of forcing the whole task to one side.

---

## Why naive rules push people the wrong direction

Several well-meaning rules compose into a regex-first bias that overshoots into semantic territory:

- "Deterministic beats probabilistic." True for structural checks; wrong framing for semantic tasks where the ground truth is itself probabilistic.
- "Code graders beat model graders." True for byte-level equality; wrong when the correct answer is "yes, these two sentences mean the same thing."
- "Start simple — try a regex first." Good heuristic, but only if you actually stop and switch tools when the regex starts sprouting exceptions.

The failure mode is not any single rule; it is **applying structural rules to semantic tasks** and refusing to switch when the evidence accumulates. When a regex hits its third exception, that is the signal — not to add a fourth, but to reclassify the task.

Symmetrically: do not reach for an LLM because it feels modern. If `str.endswith(".py")` answers the question, that is the correct, boring, nanosecond-fast answer.

---

## The decision checklist

Before committing to an approach:

1. **Can I decide this from the bytes alone, without understanding meaning?** → code
2. **Do two inputs with the same bytes mean different things in different contexts?** → LLM
3. **Does my regex already have exceptions, and did the last fix create a new failure?** → stop, switch to LLM
4. **Does my LLM call answer a question `str.endswith` or a JSON schema would answer?** → stop, switch to code
5. **Is the ground truth itself fuzzy (judgment, intent, topic)?** → LLM, and accept that "correct" means "agrees with a human rater above some threshold"
6. **Is the ground truth exact (format, syntax, presence)?** → code, and expect 100% accuracy

If you are unsure after this checklist, write two small prototypes — one of each — and compare on ten hand-labeled examples. The winner is obvious within fifteen minutes.

---

## Related

- Companion principle: **AKC ADR-0008 "Code-LLM Layering"** — [agent-knowledge-cycle/docs/adr/0008-code-and-llm-collaboration.md](https://github.com/shimo4228/agent-knowledge-cycle/blob/main/docs/adr/0008-code-and-llm-collaboration.md) (Agent Knowledge Cycle research line, concept DOI [10.5281/zenodo.19200726](https://doi.org/10.5281/zenodo.19200726)). Code owns determinism / auditability / control flow + termination; LLM owns meaning; never let the LLM own durable state or termination. Scoring by an LLM is justified only as input to a code-owned decision (judge + enforce); a score nothing downstream consumes is scaffolding.
- Source: this decision framework is distilled in the same AKC research line — [agent-knowledge-cycle/docs/skills/when-code-when-llm.md](https://github.com/shimo4228/agent-knowledge-cycle/blob/main/docs/skills/when-code-when-llm.md).
