# ADR-0062: Create-Time Content-Verification Handshake with Hybrid LLM/Code Solver; Gate Recording on Visibility

## Status

accepted

Amended 2026-06-28: the verification solver now uses guarded LLM expression
extraction before bounded LLM reasoning. The create-time handshake and
post-verification recording gate are unchanged. A second 2026-06-28 amendment
adds `logs/verification-audit.jsonl`, a base64 challenge/outcome corpus for
solver evaluation.

Third amendment 2026-06-28: a deterministic code parser
(`verification_parse.code_parse_challenge`) now runs BEFORE the guarded LLM
extraction (solver order: `code_parse` → `llm_extract` → `llm_reason`). The
guarded EXPR/FINAL path only proves the model's expression and stated answer
agree arithmetically — not that the expression faithfully represents the
obfuscated challenge — so a self-consistent-but-wrong proposal (e.g. `20 + 12 =
32` for a "twenty five + twelve" challenge) passed it; the audit corpus showed
two such live failures. The new parser owns the finite CAPTCHA grammar's
arithmetic and number-word reconstruction via whole-token fragment matching (no
substring matching, so carrier nouns like "antenna" cannot inject "ten"), and is
precision-first: it abstains to `None` on any ambiguity (≠2 operands, no clear
operation, conflicting operations), falling through to the unchanged LLM chain.
The output trust boundary is unchanged — only a parseable, code-recomputed
number is ever submitted — so this is a mechanism amendment, not a
security-boundary change, and needs no new ADR.

Fourth amendment 2026-07-01: `logs/verification-audit.jsonl` (252 real
challenges, 2026-06-28 through 07-01) showed the guarded `llm_extract` path
still wrong 16.1% of the time and the unguarded `llm_reason` fallback wrong
66.7% of the time — the latter has no arithmetic cross-check at all. A
self-consistency guard (`_reasoning_answer_is_self_consistent`) now scans the
free-form reasoning trace for any line that, once a leading list-marker and
trailing `= <result>` clause are stripped, strictly matches a two-operand
expression, and recomputes it with the same `_compute_expression_answer` the
guarded path already uses; a computed value that disagrees with the stated
FINAL rejects to `None` rather than submitting a self-inconsistent answer.
`temperature=0.0` makes retry pointless (a bare regeneration reproduces the
same wrong answer), and the check runs on already-generated text with no
extra LLM call, so it adds no latency and cannot worsen the challenge-window
risk noted below. This guard proves only arithmetic self-consistency, not
that the expression's operator matches the obfuscated text's intent — the
same limit the third amendment documents for `llm_extract` — so an
operator-confusion answer (e.g. `45 - 20 = 25` self-consistently stated for a
"45 and 20, total" challenge whose answer is `65`) still passes. A
`VerificationSolveResult.abstain_reason` field (default `None`, additive)
threads this and future abstain causes into the existing audit `error`
column with no new log schema.

Fifth amendment 2026-07-01: the same audit corpus showed the deterministic
parser's operation-verb dictionary had a live asymmetry (`decreases` but no
`increases`; `slows` but no `accelerates`) and lacked any bare-conjunction
handling, so the corpus's dominant `llm_extract` failure shape — "X newtons
and Y newtons, what is total force?" — never reached `code_parse` at all.
`increases`/`increased`/`accelerates`/`accelerate` are now registered
alongside their existing counterparts (same risk profile: single verb
tokens, no structural ambiguity). Treating a bare "and" as an implicit
addition cue is riskier — the corpus also uses "and" to connect a base
quantity to a multiplicative count ("...and has three claws...") or a
product question ("...and applies X, what is the product?") — so it is
gated by four guards, all required: (1) zero verb/symbol operations already
found (so "and" can never combine with an existing cue to manufacture a
second, conflicting operation), (2) an "and" token positioned between the
two operands (the same between-operands invariant every other cue in this
module already enforces), (3) a "total" cue word after the second operand
(ruling out product/multiplied questions, which never say "total"), and (4)
the atom immediately after each operand is the same collapsed string in
both cases (typically a repeated unit word; comparing the challenge's own
two occurrences to each other absorbs obfuscator spelling drift —
"newtons"/"neutons"/"notons" — without a unit dictionary, and rejects a
count-modifier reading where the second "operand" is not a like quantity).
Before/after replay of all 252 real corpus challenges through
`code_parse_challenge` confirmed zero regressions (every previously-resolved
answer unchanged) and zero new-wrong-answers among 59 newly-resolved rows
(48 agree with the historical correct answer, 11 correct a historical
wrong answer, 0 disagree with a historical correct answer). Both additions
keep the parser's existing abstain-first posture and output trust boundary
unchanged, so — as with the prior two amendments — this is a mechanism
change, not a security-boundary change.

Sixth amendment 2026-07-07: `verification_parse.py` rewritten from scratch,
derived from the grown audit corpus (620 records / 601 unique challenges,
2026-06-28..07-06) instead of per-failure patching. The corpus showed (a)
failures concentrate where the deterministic parser abstains and hands off
to the LLM chain (`code_parse` 1.7% wrong on the 58% it handled, vs
`llm_extract` 19.0% and `llm_reason` 74.1%), and (b) the deterministic path
itself submitted four wrong answers, all with one root cause: a
homophone-misspelled number word ("fife", "twenny", "thrirty") matched
nothing, became invisible, and the grammar confidently parsed the remaining
pair. The rewrite replaces the accreted grammar with a corpus-derived
pipeline: `0`→`o` leet normalization; fragment merging bounded by collapsed
token length (a raw-length bound is meaningless under letter doubling) plus
a fragment-count cap; edit-distance-1 fuzzy recovery of number words against
their canonical spellings (length floors, a prose stopword list —
"fight"/"right" sit one edit from "eight" and appear in 45 of 601
challenges — and a poison rule: two different plausible readings abstain the
whole parse) and of operation verbs (canonical or collapsed form); adjacent
duplicate number words dedup ("thirty two two", "forty forty five" — an
obfuscator trick of writing a number twice); strictly interleaved N-step
chains left-folded with per-step non-negative guards ("forty + seven ...
increases by seven" = 54); position-classified trailing cues (an operation
word between operands is the operator; after the last operand,
total/sum/combined imply addition, product/times/multiplied imply
multiplication, an adjacent postfix "less"/"times" binds to the second
operand, and a stray trailing `+` symbol is noise); and the implicit-add
unit guard relaxed from exact adjacent-token equality to pairwise edit
distance ≤ 1 (obfuscators misspell the same unit differently per occurrence)
or question-word continuation, still rejecting count-modifier traps ("and
has three claws"). Division verbs are trimmed to explicit words only — the
corpus contains zero division challenges, and the old "splits"/"shared"
entries misread scene prose ("a claw struggle splits on territory") as
division. Two deliberate spec changes: fully interleaved 3+-operand chains
now parse (previously hard-abstained), and "X and Y, what is the product?"
now multiplies (previously pinned as abstain). Validation: an offline replay
harness (`docs/evidence/adr-0062-parser-rewrite/`) with ground truth from
550 server-accepted answers plus 40 hand-solved labels — hard gate "zero
wrong submissions on 601 challenges" PASS, coverage 58% → 82.9% (498/601
parsed, all correct), 121 tests green including the four wrong-answer
regressions as base64 fixtures. Two corpus records where the server rejected
the only arithmetically natural answer (0.33%) are labeled as server-side
anomalies in the harness. The abstain-first posture, three-stage solver
order, audit telemetry, and output trust boundary are unchanged — a
mechanism amendment, per the third amendment's precedent.

Seventh amendment 2026-07-09: grammar extended from the post-rewrite failure
round (816 records / 792 unique challenges; success rate flat at 85.8%
after the sixth amendment because the challenge mix shifted toward
multiplicative phrasings the grammar could not represent). Failure decoding
showed three classes: operation-selection errors (both `code_parse` and the
LLM read "increases by a factor seven", "doubled by two", "it has two
claws", "each detects two" as addition), split-number misreads in the LLM
paths ("tW/eN tY tHrEe" extracted as 20, dropping "three"), and a small
irreducible server-side class. Changes, each backed by a server-accepted
twin of the same shape (and, where noted, the same numbers): multiplicative
marker words (factor/doubled/each) fill an empty gap or beat a generic
change-verb ("increases"/"accelerates", now a distinct internal op code) in
the same gap, while a NON-adjacent trailing marker stays scene noise
("...physicx factors" = 47.00 accepted); an adjacent "times" tail overrides
a single change-verb gap ("increases it by three times" = 96.00, twin
accepted); a claw count directly after the second operand multiplies
("three claws" — every corpus-accepted example is a product, none an add;
the sixth amendment's "count-modifier trap" abstain is superseded for
exactly this shape); explicit arithmetic instructions ("what is the sum of
these", "please add them") waive the implicit-add like-unit guard (the
multiplicative reading was server-rejected twice); "slows" against a
trailing "combined" cue and the same-subject bare possessed count ("it has
twoo, whats total") abstain — both readings are corpus-attested, and a
wrong parse is worse than None; number-word fuzzy matching gains an
edit-distance-1 comparison against the COLLAPSED canonical spelling for
merged tokens ≥ 6 letters ("fowr teen" → "fowrten" → fourteen), mirroring
operation verbs. The replay harness gains negative ground truth (a
server-rejected answer is durably wrong for that challenge, no manual label
needed) and null-answer labels for known-unresolvable challenges (five:
four arithmetically forced answers the server rejected — two of them
reclassified from the 6th amendment's "labeled by arithmetic" caveat — and
one server-inconsistent "accelerates by four"). LLM prompts gain
split-number de-noising examples and the multiply/add cue lists. The
review round hardened three seams the corpus alone could not surface: a
non-adjacent trailing marker is noise on the implicit path too (not just
the explicit chain), the same-subject possession lookback is
atom-boundary-free (the fuzzy number merge can absorb a fragment of the
verb, "ha s two"), and a head-position marker or an implicit
postfix-subtract against a "combined" cue abstains. Validation: hard gate
PASS on 792 challenges (654 correct, zero wrong, coverage 81.4% → 83.2%
with the lost-correct regressions from the new rules driven back to zero),
151 tests green including the failure round as base64 fixtures. Solver
order, audit telemetry, and output trust boundary unchanged — a mechanism
amendment.

Eighth amendment 2026-07-15: solver hardened from the post-round-7 failure
round (448 records after 2026-07-10, 31 rejected answers, 6.9%; five from
`code_parse` itself — the class the hard gate exists to prevent). Failure
decoding split three ways. (1) Parser round-8 grammar, one rule per live
wrong: a 4-5 letter token one edit from a COLLAPSED number word
("thyree"/"qthreee") sat below the round-7 collapsed-fuzzy floor and
dropped silently — it now poisons the parse (abstain; recovery-as-a-value
stays out until the replay corpus shows zero false matches); "five point
five" composes a decimal operand via a new `point` lexeme (whose absence
had also let `_dedup_numbers` merge the two fives), with a non-composable
point adjacent to an operand abstaining and a distant one staying scene
noise; multiplicative markers additionally match at one adjacent
TRANSPOSITION ("duoubbles" → "duobles" vs "doubles" — Damerau 1,
Levenshtein 2, invisible to the round-7 fuzzy); a restated compound
quantity ("swims at twenty three … speed is twenty three, and speeds up by
seven") collapses at the operand level when the gap holds no event — the
operand-level extension of `_dedup_numbers` — with the mangled restatement
verb "speed is" (merged "speedis", one edit from "speeds") added to the
fuzzy stopwords so it cannot fill the gap as an op. (2) Rejected-answer
memory: the live corpus contains sha-identical challenge repeats where the
solver resubmitted the exact same rejected answer; each solve now consults
the audit log's server-rejection records (single source of truth, no second
store; incremental append-only reads keyed on a byte offset; fails open) —
a rejected code_parse/llm_extract candidate falls through to the next path,
and when every path lands on a rejected value the solver abstains
(`answer_previously_rejected`) instead of burning failure-tracker budget on
a guaranteed 400. (3) LLM distractor discipline: 26 of the 31 failures were
LLM-path unit confusions (velocity summed or multiplied into a "total
force" question; "total" answered with subtraction) — both prompts (and
their re-synced in-code fallback defaults) now pin number selection to the
unit the question names, keep the round-7 explicit-pair exception ("sum of
these" still adds unlike units), state that "total" never subtracts, and
carry one worked distractor example from the live failures; LLM-path effect
is measured on the next live round (the replay harness covers only
code_parse). The review round (python-reviewer + codex cross-model) closed
four seams the failure corpus alone could not surface: only records
carrying the server's incorrect-answer message count as rejections
(verify_success=false is also written for transport failures, where the
answer may be correct); a multi-digit or duplicated fractional part
("point five five") abstains instead of composing .5; the restatement
collapse requires the copula ("speed IS twenty three"), so two genuine
equal quantities in scene prose never merge; and the audit log is read
incrementally rather than reparsed per solve (every verify appends to it,
which defeated a whole-file mtime cache). Validation: hard gate PASS on
1272 challenges (1045 correct,
zero wrong, coverage 82.5%); the round-7 parser replayed on the same corpus
scores WRONG 5 — round 8 eliminates all five with net positive coverage
(82.4% → 82.5%). 174 tests green including the five wrongs as base64
fixtures. Solver order, audit telemetry, and output trust boundary
unchanged — a mechanism amendment, per the third amendment's precedent.

Ninth amendment 2026-07-20: the free-reasoning fallback (`llm_reason`) is
retired; past `code_parse` and the guarded `llm_extract` path the solver
now abstains with a reason code instead of guessing. Unlike the prior
mechanism amendments this one DOES change the solver order: the chain is
now code_parse → llm_extract → abstain. Evidence (T-VER6 re-measurement,
10 days of round-7 operation, 921 records): `llm_reason` carried 2.3% of
traffic (21 records, a steady 1-5/day — the inflow is not drying up) at
38% verify success (8/21), i.e. sub-coin-flip guessing that submitted 13
wrong answers to earn 8 successes — 25% of all wrong submissions (13/52)
for 0.9% of all successes, feeding the rejected-answer memory and the
platform-visible wrong-answer footprint. Meanwhile `code_parse` reached
98.8% (734/743, 80.7% share) and `llm_extract` 81.4% (127/156, up from
63.2% under round 6), so the guarded paths carry the load. Mechanics: when
neither guarded path produces a submittable answer the solver returns
`abstain_reason="reason_fallback_disabled"` (a produced-but-rejected
candidate still reports `answer_previously_rejected` — the two codes feed
different readings); the reason lands in the audit log's existing `error`
column via the unchanged agent wiring, and the abstain still counts toward
the failure tracker, so sustained challenge-grammar drift halts the
session loudly instead of being guessed through. The retired machinery is
removed in the same change (reasoning system prompt
`config/prompts/verification_solve_reason_system.md` + its
`PromptTemplates` field and in-code default, the FINAL-line
self-consistency guard, the 5000-token reasoning budget; recoverable via
git revert of this amendment's commit). Revival criterion, reserved: if
the daily `reason_fallback_disabled` count stays material and `llm_extract`
improvements do not absorb it, re-design the last resort as a
recompute-gated guarded path — free-form guessing does not come back
(tracked as T-VER-ABSTAIN in the task ledger, read after ~2 weeks).

Tenth amendment 2026-07-25: structural only — no grammar change. The two
resolution branches in `verification_parse.py` (`_resolve` for explicit
operator chains, `_resolve_implicit` for the guarded two-operand reads) each
re-derived what follows the last operand from the raw event lists, and the two
derivations had already drifted twice: the non-adjacent-marker noise rule and
the subtract-vs-"combined" contradiction guard were each implemented in one
branch only, and each produced server-rejected answers before being found in
review. Both now read one `_TailSignals` value derived once, so a third such
divergence is structurally unavailable rather than merely unlikely. The grammar
itself, the fail-closed abstain semantics, and the resolution order are
untouched.

Verified by a new differential gate,
`docs/evidence/adr-0062-parser-rewrite/differential_replay.py`: the frozen
pre-refactor parser (`verification_parse_baseline.py`) and the current one are
run over every unique challenge in the local audit corpus and required to agree
on all of them, abstains included. Ground truth is irrelevant to a
behaviour-preserving change — what matters is that the rewrite decides exactly
what the old code decided — so coverage is the whole corpus (2149/2149 at this
writing) rather than the ~82% that carries a label. Keep the harness for the
next amendment: run it first to see exactly which challenges the intended
grammar change moves, then delete or refresh the baseline.

Separately observed while running the gates, NOT addressed here: the
ground-truth gate (`replay_parser.py`) currently reports 7 wrong answers
against server truth and so fails, and it fails identically at the pre-refactor
commit. The corpus has grown from 1272 to 2149 unique challenges since the
eighth amendment; these are new grammar failures accumulated since, and closing
them is an eleventh amendment, not a refactor.

Tenth amendment, part two 2026-07-25: structural only — no grammar change. The
tenth amendment removed the *duplication* between the two resolution branches;
this removes the thing that made the duplication easy to introduce. `_resolve`
and `_resolve_implicit` were imperative if/return cascades of 26 and 27
branches, and nothing in their shape said where the next amendment goes. The
branch count is unchanged and is not a target — every one of those branches was
carved out of a real server-rejected answer across nine amendments. What
changed is the representation: two ordered rule tables (`_EXPLICIT_TAIL_RULES`,
4 rows; `_IMPLICIT_RULES`, 14 rows — one row per original `return`), each row a
name plus a predicate plus a result, walked in order by one driver
(`_resolve_operation`). The next amendment adds a row, and the `when` column
says where.

Two design points are load-bearing:

- **The verdict type is tri-state.** A rule that abstains and a rule that does
  not apply both look like `None` downstream, so a plain `... -> str | None`
  table would let an abstaining guard fall through and answer where the grammar
  says stay silent. `_Decision.stop` separates them. Most of the rules across
  nine amendments *are* abstains, so this collapse would not have been an edge
  case. `_answer()` wraps `_compute_chain`'s out-of-domain `None` for the same
  reason: a fired rule with no answer still stops.
- **Not everything became a table.** The position classification that used to
  open `_resolve` (fold the events into per-gap and tail buckets, collapse,
  check ambiguity) is a fold, not a decision cascade — its abstains are guard
  clauses of the classification itself and cannot be predicates over a context
  the loop has not finished building. It moved out to `_classify_positions` and
  stayed imperative, with a docstring saying why. Rules decide what an
  arrangement means; that function decides what the arrangement is.

Flattening nested conditionals is where a guard silently widens its reach, so
every outer condition became a named context field that each flattened row
re-states, and each block of rows is exhaustive over its own signal. Context is
derived eagerly, which is observationally identical here because every helper
involved is pure, non-raising, and bounded (the same bounds that answer the
adversarial-input DoS question).

One rule is not a straight transcription: the adjacent-multiplicative override
used to rewrite the chain to `*` and fall into the subtract-vs-"combined"
guard, which is inert after an override since a multiply is never a subtract.
The row answers directly. It is called out at the row because the differential
replay, not reading, is what proves it.

Verified by the same differential gate as the tenth amendment (2149/2149
agreement with the frozen pre-refactor baseline), plus a cross-model review
that independently fuzzed 20,000 randomized challenges through both versions
and found no divergence. `replay_parser.py` still reports exactly 7 wrong /
382 abstained / 1755 correct — unchanged, which is the point.

`_resolve_operation` raises rather than abstaining if a table is not total, and
that raise is not caught by `code_parse_challenge`'s `except _Abstain` — so a
non-total table would turn untrusted CAPTCHA text into a crash instead of the
documented fail-closed abstain. That invariant is now a test
(`TestRuleTableTotality`) rather than a comment, demonstrated to fire by
temporarily making a terminal row conditional.

Eleventh amendment 2026-07-26: the grammar change the tenth deferred. The
ground-truth gate had been failing since 2026-07-15 and the failure grew with
the corpus — 7 wrong at 2149 unique challenges, 9 at 2236 eleven days later,
because the corpus is live traffic and new grammar failures accrue while the
old ones sit. Every one of the nine was a single audit record on `code_parse`
answered and rejected by the server, so none was inherited from the retired
`llm_reason` path.

Six were grammar; three were not. **Every grammar fix is an abstain.** No new
reading was added, because for each shape two readings are attested and the
corpus cannot say which the server wants — the standing rule that a wrong
parse is worse than `None` decides it:

- **Additive cues are read as a set.** `_TailSignals.contradicts_subtraction`
  matched the literal word `combined` while `_ADDITIVE_CUES` has three
  members, so a `total`-cued subtract chain walked straight past the guard
  built to stop it and submitted 17.00. Deriving a signal once (the tenth
  amendment's fix) was never the same thing as lexicalising it once. Both
  branches read the property, so both rows close together; corpus-wide there
  are exactly three subtract-chain-with-cue challenges and the other two were
  already abstaining, so the coverage cost is zero.
- **A long chain broken by a connective abstains.** `_resolve`'s grammar
  requires operands and operations to interleave strictly; an `and` inside a
  gap of a chain longer than two operands is a clause boundary, meaning two
  statements glued into one fold. Both server-rejected long chains have one
  (3703.00 folded a scene speed into a stated product; 3920.00 folded a
  duplicate quantity into an amplifier chain); the corpus's one correct
  three-operand chain, `453e7b97`, has none. The predicate carries no
  threshold, which is why it was preferred over the gap-width caps that scored
  identically on this corpus.
- **A `*` inside a unit phrase is punctuation, not an operation.** The
  obfuscator drops symbols anywhere, including between a quantity and its own
  unit noun: "thirty two `*` newtons and another sixteen newtons ... total?"
  is an addition wearing a product's punctuation, and reading the symbol as
  the operation submitted 512.00 for a 48.00 question. The tell is positional
  — the atom after the symbol is the same unit noun that follows the other
  operand — not lexical; in every corpus-accepted `*`-with-`and` challenge the
  symbol follows the unit noun instead. Restricted to `*` deliberately: the
  corpus has one accepted `+` inside a unit phrase (`fe8bb27e`) where the
  additive and implicit-add readings coincide. A stray `*` inverts the answer;
  a stray `+` cannot.
- **A broken tens+unit compound poisons the parse.** `_scan` merges whole
  atoms and drops what it cannot match, so a mangled half of a two-word number
  does not fail loudly — it vanishes and the surviving half becomes the
  operand. Two wrongs came from this: `treee` collapses to `tre`, three
  letters, below every fuzzy tier, leaving 20 - 7 = 13.00 where 23 - 7 was
  meant; `trween` collapses to `trwen`, two edits from every canonical and
  every collapsed number word — beyond any widening of the fuzzy tiers — so
  only the split unit half survived and 3 + 5 = 8.00 went out. This is round
  8's near-miss poisoning one size down. The two arms are not equally
  evidenced, and the code says so: the first confirms a tens word and judges
  the residue beside it, while the second cannot — nothing proves `trwen`
  was ever a tens word — so it matches the leftover silhouette (a split
  single-digit operand opening the challenge behind a long unmatched
  residue) under four corpus-tuned conjuncts. Dropping any one of them costs
  real answers: without the first-operand restriction three, without the
  single-digit bound 53, and admitting two-letter fragments nine more. The
  three-letter floor is safe only
  because the guard is bound to one position, the slot where the compound's
  other half belongs; run globally it would fire on `the` (one edit from
  collapsed `three`) and silence most of the corpus. `the`, `ton` and `tons`
  join the fuzzy stopwords for the same reason — verified no-ops for
  `_match_fuzzy`, so naming them costs no coverage and makes the guard's blast
  radius explicit rather than incidental.

The other three were server anomalies, and are labeled `UNRESOLVABLE` rather
than fixed. Each is the only arithmetically natural reading, each was
twin-confirmed against an accepted challenge of the same shape — 40.00 against
`06b428962fef92f5` (which also settles that a plural "claws" does not double
the first operand), 5.00 and 23.00 against `d06a5d4a3beab3f1` — and each was
rejected anyway. That brings known-unresolvable to 8 of 2236 (0.36%). Four of
the eight are now the same "X and Y, total force" additive shape, which is
worth watching as a possible server-side pattern rather than random flake.

Verified by running `differential_replay.py` before each step, as the tenth
amendment instructed: the movement set was exactly the intended challenges at
every step and nothing else moved, six in total. The ground-truth gate then
went to **2236 unique / 1836 parsed (82.1%) / 400 abstained / 1828 correct /
0 wrong / 0 unlabeled / 8 known-unresolvable — HARD GATE: PASS**. Correct is
unchanged at 1828; coverage fell 82.4% → 82.1%, which is the whole price.

The review round caught what the corpus structurally could not. Both new
guards first shipped comparing RAW atoms, so the obfuscation layers this
module handles everywhere else stepped straight around them: letter doubling
turned the split fragment `t` into `tt` and Arm B stopped firing
(`trween tt hree` → 8.00 again), and a unit noun split differently at its two
occurrences (`* new tons ... newtons`) slipped past the unit-phrase guard
(→ 512.00 again). Neither shape exists in the corpus, so neither replay gate
could have found them — a gate built from live traffic proves what happened,
never what the same generator can produce next. Both now compare collapsed
forms, and the unit-phrase comparison merges up to two unclaimed atoms per
side, bounded so a cue or operand can never be swallowed into a "unit noun".
Both fixes moved zero challenges in the corpus: pure precision. The
python-review round separately sharpened Arm B's documentation, which had
claimed to detect a tens+unit compound while checking only shape and
position, and a security-review note added two adversarial-input fixtures
covering the new guards' worst-case loops directly rather than by
complexity-class analogy.

One existing test asserted the losing side of this. It fixed
`"twenty five newtons and slows by seven newtons what is total force"` at
18.00 on the premise that a trailing `total` is inert scene noise — the exact
shape whose subtract reading the server rejected. Its comment also still
referenced `_try_and_as_add` and `_ConjunctionEvent`, gone since the sixth
amendment's rewrite. It now asserts the abstain, and is the only test in the
suite the amendment moved.

Twelfth amendment 2026-08-01: `abstain_reason` splits in two. Past the
guarded paths the solver emitted `reason_fallback_disabled` whether the LLM
had spoken and been rejected or had returned nothing at all — a backend
fault, an empty body, an open circuit breaker, or a trace dropped by
`drop_truncated` all landed on the code whose daily count the ninth
amendment reserved as its own revival criterion. The code claims to describe
the solver's judgment; an outage is not a judgment, so the reading was
measuring two different things through one number. Calls that produce no
text now report `abstain_reason="llm_none"`, and `reason_fallback_disabled`
means what it says: the model answered and the guards rejected it. WHICH
kind of call failure occurred stays in the `llm-calls-{date}.jsonl`
telemetry row (`outcome` / `error_kind`, `caller="moltbook.verify_solve"`) —
the audit column only has to keep "said nothing" apart from "said something
unusable", so no new log field is added. `answer_previously_rejected` keeps
priority over both: a produced-but-rejected candidate is the more
informative signal even when the LLM call also failed.

Measured before the split, over the window in which the code has existed at
all — 2026-07-20 (the ninth amendment's retirement date) through 08-01, 1,126
of the audit log's 2,863 records, the corpus itself running from 06-28:
`reason_fallback_disabled` fired 6 times total — 2 on 07-20, then 1 each on
07-21, 07-23, 07-25 and 07-29. That is 0.5% of attempts in the window, or
~0.46/day, against the 2.3% of traffic and steady 1-5/day the retired
`llm_reason` path had carried. Re-derive by filtering the log on
`error == "reason_fallback_disabled"` and bucketing `ts` by UTC date.

This is a *preliminary* read: the ninth amendment reserved ~2 weeks from
07-20 for the T-VER-ABSTAIN decision, and that window does not close until
2026-08-03. On the evidence so far the split does not change the verdict —
the count reads dry with or without it — which is precisely why it was safe
to ship the split before the reading rather than after: it cannot tip a
decision it does not move, and waiting would have spent another two weeks
producing numbers with the ambiguity still baked in. What it buys is the
*next* reading. Records written before this amendment carry
`reason_fallback_disabled` for both causes, so any reading that crosses
2026-08-01 must sum the two codes.

Found by writing the solver's chaos-TDD fault column (ADR-0077), which the
solver had lacked despite parsing untrusted LLM output: `test_verification.py`
patched `verification.generate` in every LLM case, so nothing exercised the
real `core.llm.generate` path and a `drop_truncated` regression — the gate
that keeps a mid-sentence number from being submitted to `/verify` — would
have left the suite green. `tests/test_verification_chaos.py` injects
F-VER-1 … F-VER-7 at the existing `LLMBackend` and `requests` seams. One
existing test asserted the losing side: `test_llm_unavailable_abstains`
fed `generate` a `None` and expected `reason_fallback_disabled`; it now
expects `llm_none`, and is the only test in the suite this amendment moved.

## Date

2026-06-26

## Context

Moltbook now requires agents with `is_verified=false` to solve an obfuscated math challenge before
any created content — post, comment, or submolt — becomes visible on the platform. The
create-response (HTTP 201) carries a `verification` object
`{challenge_text, verification_code, expires_at}` with a roughly five-minute window; the agent
must solve `challenge_text` and POST `/api/v1/verify {verification_code, answer}` before
`verification_status` transitions from `pending` to `verified`. Trusted agents and admins bypass
this step: their create-responses carry no `verification` object, so their content becomes visible
immediately. This agent is `is_verified=false` and must complete the handshake on every creation
call.

Pre-existing code purported to handle verification but had silently stopped firing. Across the
available log window (2026-05-22 through 2026-06-25) every post (`posts_count=349`) and every
comment sat at `verification_status=pending` — invisible on the public profile and unretrievable
by other agents — while `POST /posts` and `POST /comments` consistently returned HTTP 201 and the
server's counters incremented normally. The code never read `verification_status` on its own
created content, so the discrepancy between the API's success signal and the web-visible state was
never detected; the failure mode was entirely silent.

The root cause was three-layer drift between the pre-existing verification code and the current
API. The first layer was wiring: the only solve-and-submit call was placed inside the feed-read
loop and keyed on `post.get("verification_challenge")` — a field the current API never populates on
feed items. It fired zero times across the entire log window; the create-response code path that
does carry the `verification` object was never inspected. The second layer was field names: the code
read `challenge.get("text")` and `challenge.get("id")` and submitted `{challenge_id, answer}`;
the current API delivers `challenge_text` and `verification_code` and expects
`{verification_code, answer}`. Even if the wiring had been correct, every field lookup would have
returned `None`. The third layer was the solver: the deterministic deobfuscation-and-parse routine
was written for a uniform char-doubling format (e.g., `"ttwweennttyy"` → `"twenty"`) and returned
`"Failed to parse"` on the current format, which combines alternating case, scattered symbols
(`[]^/-`), and fractured word spacing (e.g., `"A] lO^bSt-Er S[wImS aT/ tW]eNn-Tyy"`). No single
layer could have independently produced a valid `/verify` submission.

## Decision

1. **Wire a solve→POST `/verify` handshake into all content-creation paths.**
   `post_pipeline._publish_post`, the `feed_manager` comment path, and `reply_handler` each read
   the `verification` object from their create-response and invoke the shared callback
   `Agent._handle_verification`, injected at construction via the existing callback-injection
   pattern. `post_comment` folds a root-level `verification` key into the returned comment dict so
   the gate fires whether the API nests the object under `"comment"` or at the response root.

2. **Gate recording on visibility.** An unverified post or comment is invisible and unrecoverable
   once the five-minute challenge window expires. Dedup markers (`mark_posted`, `own_post_ids`),
   episode writes, `memory.record_post` / `memory.record_commented`, `NoveltyGate.record`, and
   `actions_taken` now execute only after verification succeeds. Rate-limit counters
   (`scheduler.record_post` / `scheduler.record_comment`) remain immediately after the `POST`,
   because the server consumes quota regardless of verification outcome. Trusted-bypass responses
   — those carrying no `verification` object — fall through and record as before.

3. **Solve via LLM semantic extraction with code-owned validation.**
   `solve_challenge` wraps `challenge_text` as untrusted content, then asks the LLM for a short
   `EXPR: <number> <op> <number>` / `FINAL: <answer>` pair. Python computes the expression with
   `Decimal` and accepts the answer only when the computed two-decimal value matches the LLM's
   stated final answer. If that guarded fast path fails, the solver falls back to a bounded
   reasoning prompt (`temperature=0.0`, `drop_truncated=True`, generous `num_predict` cap) and
   extracts a labeled final answer. The trust boundary is still the output: only a parseable number
   that survives the code guard or bounded fallback is submitted to the platform, so an instruction
   injected through `challenge_text` fails closed to `None`.

4. **Remove the dead feed-based verification path.** The `verification_challenge` feed branch and
   its plumbing through `run_cycle` are deleted. They fired zero times in the available log history
   and cannot fire against the current API.

5. **Add structural-only API instrumentation at the `client._request` chokepoint.** Each API call
   appends one record to `logs/api-audit.jsonl` containing: HTTP method, normalized endpoint
   (numeric IDs replaced with `{id}`), HTTP status, envelope key-names, whitelisted content-status
   fields (`verification_status`, `is_spam`, `is_deleted`, bool-cast or sanitized), a soft-fail
   flag (HTTP 2xx but body `success:false`), sanitized server-error text, and `rate-remaining`. A
   schema-drift `WARNING` fires when a depended-on envelope key is absent. No free-text body is
   recorded; the log is safe to read directly, unlike episode logs which carry untrusted external
   content.

6. **Add a dedicated verification challenge audit corpus.** `Agent._handle_verification` now writes
   one best-effort record to `logs/verification-audit.jsonl` for every solve attempt that has a
   challenge: `challenge_b64`, `challenge_sha256`, `verification_code_sha256`, answer,
   `solver_path`, `solve_success`, `verify_success`, and sanitized error. The challenge text is
   base64-encoded rather than written as free text, so direct log inspection does not turn the
   corpus into prompt instructions. Any evaluation harness that decodes it must re-wrap the decoded
   text as untrusted content.

7. **Thread replies with `parent_id`.** The API requires `parent_id` for replies; it was previously
   never sent, so replies posted as top-level comments. The field is now included in every
   `POST /comments` reply call.

## Alternatives Considered

### Extend the deterministic deobfuscation-and-parse solver

Add cases for the alternating-case-plus-scattered-symbols format alongside the existing
uniform-char-doubling handler. Rejected because the two formats require contradictory
normalization: collapsing repeated characters recovers `"twenty"` from `"ttwweennttyy"` but
destroys `"three"` → `"thre"` in the alternating-case variant. The operation-verb vocabulary is
open-ended, and a real challenge delivered unseen trailing junk (`"<um> lxObqS tHiS"`) that a
regex pipeline would choke on but the LLM discarded without prompting.

### LLM structured extraction (`format=json {num1, op, num2}`, compute in code)

Request a structured JSON object from the LLM, then compute the arithmetic in Python. Rejected on
test evidence: 3 of 6 challenges were answered incorrectly. The `format=json` constraint suppresses
the reasoning model's `<think>` block, and without chain-of-thought the model misreads obfuscated
number-words (`twenty`→10, `eighty`→8). Computing arithmetic in code is the correct separation,
but suppressing the reasoning step to reach it produces an unreliable solver.

Amendment note (2026-06-28): the implemented fast path is not this rejected design. It does not use
constrained JSON decoding, and it never accepts the LLM's extracted fields by schema alone. The LLM
may propose a simple numeric expression, but Python recomputes it; if that contract is missing or
inconsistent, the solver falls back to bounded reasoning rather than submitting the proposal.

### Force an immediate answer ("reply with ONLY the number")

Prompt the LLM to return a bare number with no intermediate steps. Rejected: this also suppresses
chain-of-thought and produced incorrect arithmetic even on de-noised plain-text input (`20+5`→27).
Free reasoning followed by numeric extraction from the output is more reliable than constraining
the output format.

### Handle verification inside `client.py`

Place the solve-and-submit logic at the single HTTP chokepoint where all API calls pass. Rejected:
the solver requires LLM access; `client.py` is pure transport with no LLM reference. Importing the
LLM into `client.py` would reverse the `core` ← `adapters` dependency direction established by
[ADR-0015](./0015-one-external-adapter-per-agent.md). The `verification` object already rides back
in the create-response that the pipeline layer parses, so no additional plumbing is required there.

### Log full API response bodies for observability

Record complete response JSON to make silent failures discoverable. Rejected: response bodies
contain other agents' post and comment text, which is untrusted and a prompt-injection vector.
Writing that content into a file readable directly by Claude Code erodes the same boundary that
prohibits reading episode logs (CLAUDE.md). Structural-plus-status logging achieves the diagnostic
goal — catching 2xx-but-invisible failures and envelope field drift — without introducing the
injection surface.

### Put raw challenge text in a normal log field

Record `challenge_text` directly in `verification-audit.jsonl` for easier corpus collection.
Rejected: the challenge is attacker-controlled external content and may contain prompt-injection
strings. Storing it as a normal JSON string would make casual log reads and coding-agent debugging
sessions ingest it as prose. Base64 does not make the content trusted, but it prevents accidental
instruction-following during direct inspection while preserving an exact corpus for explicit eval
harnesses.

### Route verification through the human approval gate

Treat the verification handshake as a supervised action requiring confirmation before submitting
the answer. Rejected: verification is a platform anti-bot handshake required for content to become
visible, not a social or editorial action. Gating it would leave the created post permanently
invisible rather than supervise its content. Content generation already passes the existing
novelty and confirmation gates before the creation `POST`; the verification handshake executes
after those gates have cleared.

## Consequences

### Positive

- Posts, comments, and replies publish and become publicly visible again. End-to-end confirmation
  against production: a controlled real post solved its challenge (`26+17=43`) and transitioned to
  `verification_status=verified`; a subsequent live autonomous session solved a real reply
  challenge and `POST /verify` returned HTTP 200.
- Common verification challenges can now finish through a short guarded extraction call instead of
  a long free-reasoning trace; arithmetic acceptance is owned by Python when the fast path provides
  a valid expression.
- `logs/api-audit.jsonl` makes silent failures and API envelope drift greppable; the exact bug
  class that caused this incident — HTTP 2xx with content remaining invisible, field-name drift in
  the response envelope — would have surfaced within days rather than accumulating across weeks.
- `logs/verification-audit.jsonl` creates a forward corpus of real challenges, solver paths,
  answers, and `/verify` outcomes. Future solver changes can be evaluated against observed
  failures instead of synthetic examples or unsafe episode-log reads.
- Only verified (visible) content enters `NoveltyGate` and the memory store, so the 349 pending
  posts and their associated comments no longer pollute novelty and deduplication history.
- Replies thread correctly under their parent comments rather than posting as top-level comments.

### Negative

- Each content-creation call still depends on LLM challenge solving. The guarded fast path should
  reduce common-case latency, but fallback reasoning can still add tens of seconds; a cold or
  recently-swapped model could approach the five-minute challenge window, with generation serving
  as a pre-warm step.
- The verification solver adds a dependency on the local LLM being reachable at the moment of
  content creation. A connection failure to Ollama at create time causes the `/verify` call to be
  skipped and the created content to remain pending.
- Pre-fix pending content (349 posts plus the comments accumulated during the same window) is
  unrecoverable: challenge windows expired long before this fix and the platform provides no
  re-challenge endpoint. This is a forward-only repair.

### Neutral / Follow-ups

- The solver prompts and token budgets were originally calibrated for `qwen3.5:9b`. A dedicated
  blind replay (2026-07-01, `docs/evidence/verify-solve-model-compare-20260701/`) checked whether
  the post-ADR-0069 production swap to `gemma4:e4b` weakened this specific task: gemma reproduced
  its own 95 historically-correct solves with 100% self-consistency, while qwen blind-replaying
  those same 95 challenges matched only 72.6% of the time — gemma is not the weaker model here, so
  no per-task model override is warranted. Telemetry remains under caller `moltbook.verify_solve`.
- `logs/api-audit.jsonl` has no rotation policy yet; one structural record is appended per API
  call.
- `logs/verification-audit.jsonl` has no rotation or retention policy yet; one corpus/outcome
  record is appended per challenged creation attempt.
- `verification_code` is no longer format-validated before submission: the field travels in a JSON
  request body rather than a URL path, so a non-empty check is sufficient. The prior validation
  was an artefact of the old field-name assumptions.

## References

- [ADR-0007](./0007-security-boundary-model.md) — security boundary model; the untrusted-content
  surface policy and episode-log read prohibition that motivated structural-only API logging over
  full response body logging.
- [ADR-0015](./0015-one-external-adapter-per-agent.md) — one external adapter per agent; the
  `core` ← `adapters` import direction that ruled out placing the LLM solver inside `client.py`.
- [ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md) — NoveltyGate; recording to the
  gate is now gated on verification success to prevent pending content from polluting novelty
  history.
- [ADR-0043](./0043-per-post-seeding-for-self-post-generation.md) — per-post seeding and removal
  of `check_topic_novelty`; `own_post_ids` and related dedup markers now record only after
  verification succeeds.
- Implementation: commit `92622e3`.
- `docs/CODEMAPS/architecture.md` Data Flow — updated in the same commit to reflect the
  verification handshake in the creation pipeline.
- Related learned pattern: `llm-pipeline-layering` — reasoning models must not have their
  chain-of-thought suppressed; validated empirically on a constrained-extraction task where
  `format=json` produced 50% accuracy against free reasoning's 100%.
