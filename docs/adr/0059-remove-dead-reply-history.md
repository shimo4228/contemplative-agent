# ADR-0059: Remove the Dead Reply-History Mechanism

## Status

accepted

## Date

2026-06-22

## Context

The reply path included a conversational-memory mechanism: `MemoryStore.get_history_with(replier_id)`
fetched past interactions with the counterparty, passed the result as `conversation_history` into
`generate_reply` in `adapters/moltbook/llm_functions.py`, and `_build_context_section` rendered it
into the `{history_section}` placeholder in `config/prompts/reply.md`. The intent was to ground
each reply in the prior exchange with that counterparty.

The mechanism has been silently non-functional since [ADR-0055](./0055-counterparty-identity-by-author-name.md)
(commit 6c20032). Live Moltbook feed posts carry `author.name` but not `author.id`: the
representative-week audit underlying ADR-0055 found 271/271 comment interaction records with
`agent_name` populated and `agent_id` set to `"unknown"`. The `replier_id` resolved from the live
feed is therefore always `"unknown"`. `get_history_with` filters its history table on
`i.agent_id == replier_id`, so it compares `"unknown"` against the stored records — which were
written with the real agent name rather than an id. The filter never matched. The history list was
always empty; `{history_section}` in the reply prompt was always blank.

[ADR-0055](./0055-counterparty-identity-by-author-name.md) diagnosed this same id-key failure and
re-keyed the sibling functions `count_recent_comments_by_author` and `get_prior_comment_targets`
onto `agent_name`. `get_history_with` was not carried along — the re-key was scoped to the rate-limit
and repeat-topic guards that ADR-0055 was fixing, leaving the reply-history function on the dead key.
The present ADR was surfaced during a subsequent code audit and is independent of the concurrent
distill clustering redesign.

Two structural considerations prevent simply re-keying `get_history_with` onto `agent_name`. First,
the mechanism demonstrated zero production value across its entire operational lifetime: the filter
failure means no version of the reply path ever ran with a non-empty history section, and there is no
baseline of working behavior to restore. Second, [ADR-0052](./0052-retire-session-insight.md)
established identity distillation as the single approved channel for cross-session continuity; a
conversational reply-history capability — carrying prior exchanges into each reply generation — would
be an unapproved parallel continuity path, and reviving it conflicts with that design principle.

## Decision

Remove the dead reply-history mechanism end-to-end:

1. **Delete `MemoryStore.get_history_with`** (`core/memory.py`). This is the storage function the
   mechanism depends on; no other caller uses it.

2. **Delete `_build_context_section` and the `conversation_history` parameter of `generate_reply`**
   (`adapters/moltbook/llm_functions.py`). The parameter accepted the empty list from the history
   fetch and passed it into `_build_context_section`; both are inert.

3. **Delete the history fetch, `history_summaries` construction, and the `conversation_history=`
   keyword argument** in the reply handler (`adapters/moltbook/reply_handler.py`). This is the call
   site that orchestrated the fetch and supplied the always-empty result to `generate_reply`.

4. **Remove the `{history_section}` placeholder** from `config/prompts/reply.md`. The prompt
   template implied a conversational-memory capability that never fired; removing it makes the
   prompt match the actual inputs.

5. **Remove the corresponding tests**: `test_get_history_with` and `test_get_history_with_limit` in
   `tests/test_memory.py`; `test_reply_with_history` and `test_reply_without_history` in
   `tests/test_llm.py`. These tests exercised the dead path in isolation and carry no behavioral
   coverage of working production behavior.

Reply generation now grounds solely on the original post and the other agent's comment — the inputs
that were always the effective content of the reply prompt.

The dialogue adapter (`adapters/dialogue/peer.py`) has its own independent `_build_history_section`
and `{history_section}` in its own prompt template, serving the local two-peer dialogue experiment
(`contemplative-agent dialogue HOME_A HOME_B`). It is not touched by this change.

## Alternatives Considered

### Re-key `get_history_with` onto `agent_name`

Apply the same fix ADR-0055 made for the sibling functions: replace the `i.agent_id == replier_id`
filter with a name-keyed equivalent. Rejected on two grounds. The mechanism demonstrated zero value
over its entire production lifetime — the filter failure meant no reply was ever generated with a
non-empty history section, so re-keying would introduce a new behavior rather than restore a
known-working one. That new behavior conflicts with [ADR-0052](./0052-retire-session-insight.md):
conversational reply memory is a cross-session continuity path, and ADR-0052 established identity
distillation as the sole approved continuity channel.

### Leave the dead code in place

Retain `get_history_with`, `_build_context_section`, the fetch logic in the reply handler, and the
`{history_section}` placeholder without fixing or removing them. Rejected: dead code that implies a
capability the codebase does not have is actively misleading. A reader encountering `{history_section}`
in the reply prompt or `get_history_with` in the memory module would reasonably conclude that reply
generation is informed by conversational history — a false inference. The prompt placeholder and the
function signature are implicit documentation; they should describe the actual mechanism.

## Consequences

### Positive

- Reply generation is grounded on real present-turn material only — the original post and the other
  agent's comment — with no silently-empty fake-history section polluting the prompt context.
- The codebase no longer implies a conversational-memory capability that never worked; the prompt,
  the function interface, and the actual behavior now agree.
- Net code reduction across `core/memory.py`, `adapters/moltbook/llm_functions.py`,
  `adapters/moltbook/reply_handler.py`, `config/prompts/reply.md`, and four test functions.

### Negative

- Four tests are removed. This is a reduction in test count, not in behavioral coverage: the removed
  tests exercised a code path that was never reached in production and whose net effect was always
  a no-op.

### Neutral / Follow-ups

- The dialogue adapter's `_build_history_section` and its `{history_section}` placeholder are a
  separate mechanism for the local two-peer dialogue experiment. They are not affected by this change
  and should not be confused with the Moltbook reply path removed here.
- This removal is independent of the concurrent distill clustering redesign. The two changes touch
  separate parts of the codebase and were surfaced by the same code audit; they are tracked and
  landed separately.

## References

- [ADR-0055](./0055-counterparty-identity-by-author-name.md) — precedes. This ADR removes the
  function ADR-0055 left on the dead `agent_id` key when it re-keyed only the sibling rate-limit
  and repeat-topic guards onto `agent_name`.
- [ADR-0052](./0052-retire-session-insight.md) — design constraint. Established identity distillation
  as the single approved cross-session continuity channel; that principle is the structural reason
  reviving the reply-history mechanism is undesirable, not merely unnecessary.
