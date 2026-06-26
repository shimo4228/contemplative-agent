# ADR-0062: Create-Time Content-Verification Handshake via LLM Reasoning; Gate Recording on Visibility

## Status

accepted

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

3. **Solve via LLM reasoning — not deterministic parsing, not constrained extraction.**
   `solve_challenge` passes the raw `challenge_text` to the LLM with a reason-step-by-step prompt
   (`num_predict=3000` as a generous budget cap, not a target; `drop_truncated=True` to fail
   closed on a truncated response). The solution is extracted by locating the final numeric token
   in the generated output, formatted to two decimal places. The trust boundary is the output:
   only a float-parseable number is ever submitted to the platform, so an instruction injected
   through the untrusted `challenge_text` fails closed to `None` rather than executing.

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

6. **Thread replies with `parent_id`.** The API requires `parent_id` for replies; it was previously
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
- `logs/api-audit.jsonl` makes silent failures and API envelope drift greppable; the exact bug
  class that caused this incident — HTTP 2xx with content remaining invisible, field-name drift in
  the response envelope — would have surfaced within days rather than accumulating across weeks.
- Only verified (visible) content enters `NoveltyGate` and the memory store, so the 349 pending
  posts and their associated comments no longer pollute novelty and deduplication history.
- Replies thread correctly under their parent comments rather than posting as top-level comments.

### Negative

- Each content-creation call now carries approximately 30–90 seconds of additional latency while
  the LLM solves the challenge. The same model just generated the content, so it is warm at solve
  time; a cold or recently-swapped model could approach the five-minute challenge window, with
  generation serving as a pre-warm step.
- The verification solver adds a dependency on the local LLM being reachable at the moment of
  content creation. A connection failure to Ollama at create time causes the `/verify` call to be
  skipped and the created content to remain pending.
- Pre-fix pending content (349 posts plus the comments accumulated during the same window) is
  unrecoverable: challenge windows expired long before this fix and the platform provides no
  re-challenge endpoint. This is a forward-only repair.

### Neutral / Follow-ups

- The solver prompt and `num_predict=3000` budget are calibrated for `qwen3.5:9b`; a weaker or
  swapped model may require prompt or budget adjustment.
- `logs/api-audit.jsonl` has no rotation policy yet; one structural record is appended per API
  call.
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
