# ADR-0112: A Decision Backend Seam — Typed Probabilistic Judgments Behind a Protocol, Observed in Shadow on Skill Selection

## Status

accepted

## Date

2026-09-22

## Context

Six of the agent's LLM calls ask for a judgment, not text: skill selection,
relevance scoring, submolt selection, the distill post-gate, the insight
novelty gate and the insight duplicate judge. All six run on the production
generation model (gemma4:e4b, [ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md))
as constrained text generation — the model writes names, numbers or JSON and
code parses and validates the answer.

[RFC-0043](../../rfcs/0043-skillsel-offline-arm-replay.md) replayed 150
production skill-selection rows through eight gemma arms and a frontier
ceiling ([docs/evidence/rfc-0043/](../evidence/rfc-0043/README.md)). Changing
the interface — temperature 0, enum constraint, or reading the option logits
instead of sampling — did not move gemma's agreement with the ceiling
(Jaccard 0.143–0.162 against opus-5's self-agreement of 0.678). A hosted
decision model (TypeSafe Jev) was measured once on the same 150 rows; that
reading, written up by the owner on 2026-09-21
([Zenn](https://zenn.dev/shimo4228/articles/jev-vs-opus-skill-selection)),
is what started this work. Its figures are not reproduced in this repository:
[RFC-0040](../../rfcs/0040-jev-system-one-local-decision-backend.md) records
the vendor's Master Customer Agreement clause 2.3(f) on publishing performance
information, the owner's 2026-09-20 decision to keep such readings out of
tracked files, and clause 2.3(b) that bars distilling from Jev's output.
Jev's weights are closed, and the owner does not send production traffic off
the machine.

In the week after Jev's launch, more than thirty open reimplementations
appeared (catalogued at systemonemodels.org, read 2026-09-22). They converge
on one contract — three typed questions, `noul` (yes/no), `choice` and
`score`, answered with probabilities — and several serve the same HTTP shape.
None of the trained ones (kev, von, Laya, openJev-verdict) run under Ollama:
each carries a custom head. The ones that do run under Ollama are logit
readouts of a frozen LLM, which is the family RFC-0043 already measured on
gemma.

Three facts about the machine shape the design:

- Two models do not share the 16 GB unified memory well. Running gemma beside
  a 1.6 GB GLiClass checkpoint during RFC-0043 pushed swap to 17 GB and
  slowed each row by about 1.8× (evidence §8). On 2026-09-22, during an
  interactive session, swap was already at 5.2 GB with no model loaded and
  6.1 GB with gemma loaded (`vm.swapusage`).
- Ollama 0.34.2 on this machine has `OLLAMA_MAX_LOADED_MODELS` unset, so it
  loads a second model beside the first whenever it judges both fit. A
  no-co-residence guarantee therefore has to be explicit: a
  `{"model": …, "keep_alive": 0}` request evicts a model, and gemma's cold
  reload measured about 7 s (a 23-token prompt returned in 8.0 s total,
  2026-09-22).
- Ollama's `/api/generate` returns `logprobs` with `top_logprobs` capped at
  20 (21 returns HTTP 400, evidence §5). One skill-selection prompt is about
  12,000 characters — roughly 3,000 tokens at four characters per token,
  which is the conversion used throughout this ADR: the catalog about 9,600
  characters and the situation 1,500 at the median and 7,100 at the maximum
  (September 2026 audit rows whose `prompt_b64` round-trips through the
  production template splitter, decoded for length only on 2026-09-22 with
  the harness's own `split_prompt`). The situations are English — the CJK
  share is 0 at the 90th percentile.

The seam that exists today, `LLMBackend`
([ADR-0088](./0088-shipped-conformance-kit-for-the-llm-backend-contract.md)), carries text
generation. A decision model does not fit it: it returns a distribution, not
a string, and the harness that measured the readout
(`scripts/skillsel_arm_replay.py`) had to post to Ollama directly because
`core.llm` does not expose `logprobs`.

## Decision

1. **Add a `DecisionBackend` protocol next to `LLMBackend`**, in
   `core/llm/decision.py`, re-exported from `core.llm`. Its contract is the
   converged three-question shape: `NoulQuestion`, `ChoiceQuestion`,
   `ScoreQuestion` in, `DecisionResult` out — per-question probabilities over
   the options, the served model id, latency, and a closed reason vocabulary
   for every way the call can abstain (`unconfigured`, `circuit_open`,
   `http_error`, `bad_json`, `logprobs_unavailable`, `no_option_observed`,
   `label_alphabet_exceeded`, `budget_exceeded`, `backend_exception`). Every type is a frozen
   dataclass holding tuples. The backend returns probabilities; thresholds,
   set sizes and any normalisation across questions are decided in the
   calling code, where they are visible ([ADR-0071](./0071-read-only-pattern-composition-instruments.md)).
2. **Inject it the way `LLMBackend` is injected**:
   `configure(decision_backend=…)`, a module global, cleared by
   `reset_llm_config()`. **The default is `None`, which disables the path**:
   no call, no record, no telemetry. A default-on backend would attach one
   call per catalog entry to every CLI tier that configures the LLM, and
   configuration absence would stop being the kill switch
   ([ADR-0076](./0076-skill-selection-shadow-instrument.md)). The CLI constructs a
   backend only when `DECISION_MODEL` is set.
3. **Ship one implementation in the wheel, with no new dependency**:
   `OllamaLogprobsDecisionBackend` reads the first-token `top_logprobs` of a
   `num_predict: 1`, temperature 0 request to the existing Ollama allow-listed
   URL. A `noul` reads the yes/no pair; a `choice` or `score` with at most 20
   options labels them A–T and reads the label tokens, marking unobserved
   options as truncated; a `choice` with more than 20 options abstains with
   `label_alphabet_exceeded` rather than being decomposed inside the backend
   — a choice promises one distribution, and splitting it into independent
   yes/no questions is a caller's decision. `num_ctx` is always sent (Ollama's documented default of
   2,048 truncates silently — the trap recorded in RFC-0043's replay notes). The state is the prompt
   prefix and the question the suffix so Ollama's prefix cache carries the
   ~3,000-token state across the per-entry calls. Trained decision models
   that need torch are injected from a sibling repository through the same
   `configure` call, as `contemplative-agent-cloud` injects its generation
   backend; the wheel's dependency floor ([ADR-0109](./0109-dependency-floor-scoped-to-the-wheel.md))
   does not move.
4. **Never hold the decision model and the generation model in memory at
   once.** When the backend's model differs from the served generation model
   (`exclusive=True`), it evicts the generation model with
   `keep_alive: 0` before its batch and evicts itself with `keep_alive: 0`
   on the batch's last call; the next generation call reloads gemma. When
   the two models are the same, nothing is sent. The backend posts its own
   requests and never touches the shared circuit breaker's counters; it
   only reads `is_open`. Each `decide()` batch runs under a wall-clock
   budget (`batch_budget_s`, default 120 s): RFC-0043's arm `C/logits`, the
   same per-entry shape on gemma, took 51.0 s per row at the median and
   820 s at the maximum over 150 rows (evidence JSON
   `arms["C/logits"].latency_ms`). When the budget is spent the remaining
   questions are not sent and are reported as `budget_exceeded`.
   ADR-0076's rule carries forward: a decision-path failure or timeout never
   suppresses or aborts the publish it precedes — the hook degrades to null
   fields and the generation proceeds; the budget bounds the delay the
   shadow can add. Restructuring a cycle into a judge-everything phase
   followed by a generate-everything phase is deferred to the enforcement
   ADR (Alternatives).
5. **Observe it first on skill selection, in the existing record.**
   `observe_skill_selection_recorded` asks the decision backend one `noul`
   per catalog entry after the live selection has run — the decomposed
   shape is the one that covers the whole catalog (AUC 0.728 at 100%
   coverage against 0.642 at 37% for the one-pass readout, evidence §5) —
   and writes
   `decision_backend`, `decision_model`, `decision_latency_ms`,
   `decision_reason`, `decision_p` (per entry) and `decision_topk` (the
   top entries by probability, as many as the live path selected — the
   size rule baked in at record time) into the same
   `skill-selection-*.jsonl` row. The live `selected` is not touched, the
   hook returns nothing the caller can inject, and when the backend is
   unconfigured every field is null with `decision_reason: "unconfigured"`.
   A row's `decision_reason` is `answered` only when every entry answered;
   otherwise it is the first non-answered reason in catalog order, and
   `decision_answered_count` carries how many entries did answer.
   `decision_reason` joins the weekly census enum fields. One telemetry row
   per `decide()` batch — not per entry — goes to `llm-calls-*.jsonl` with
   `kind: "decision"`; it is removed under the same condition as the fields.
6. **Ship the conformance check in the wheel**, `testing/decision_contract.py`,
   deriving the canonical call from `DecisionBackend.decide`'s own signature
   as `backend_contract.py` does for generation, so a sibling backend is
   checked against the protocol rather than a hand-copied signature.

The wheel's I/O surface does not change: the only new outbound request is to
the Ollama URL that already passes `validate_trusted_url`. One new side
effect is named here because it crosses a process boundary: `keep_alive: 0`
evicts a model from the shared Ollama daemon, which anything else using that
daemon will feel as a reload.

## Review-when

- **The shadow reading is due after four Saturday readings** once at least
  200 rows carry `decision_reason: "answered"` (cumulative, counted from the
  first Saturday after this ADR lands on main; the owner enables
  `DECISION_MODEL=gemma4:e4b` in the scheduled sessions' environment in that
  first week — a launchd change the owner makes, not the chain). The reading
  puts three numbers side by side over the same four-week window: the
  answered share of the rows on which a backend was configured, the live
  path's `judged` share of those same rows, and the decision latency p95
  against the cycle wait. The owner decides enforce (a further ADR: phase
  separation, `decision_topk` feeding injection) or retire at that reading.
  These are readings, not auto-firing triggers; any threshold is set from
  the first two readings, not before them (one run is not evidence).
- **Eight Saturday gates from that start** without 200 answered rows is a
  quiet instrument: remove the hook, the fields and the census enum in one
  commit.
- **The offline round 3** of RFC-0043 (a second frozen LLM's logits, kev,
  Laya on the same 150 rows) finds no local candidate whose bootstrap CI of
  (candidate − `C/logits`) on Jaccard@topk excludes zero on the positive
  side (the paired-difference reading of evidence §2), with the precision
  of its p ≥ 0.5 set against the ceiling reported with its denominator: the
  seam is kept for the readout only and no sibling backend is built.
- Ollama gains the ability to serve custom-head decision models, or Jev's
  weights are released: the sibling-injection half of Decision 3 is
  reconsidered and the comparison table in RFC-0040 redone.
- The Ollama daemon is started with `OLLAMA_MAX_LOADED_MODELS=1`: the
  explicit eviction in Decision 4 becomes redundant and is removed.
- The production generation model stops being gemma4:e4b: the readout was
  measured on gemma; the "same model, zero swaps" first week has to be rerun.

### Consumption plan

The new fields ride the existing `skill-selection-*.jsonl` census row
([ADR-0107](./0107-instrument-census-and-episode-log-folder.md) /
[ADR-0110](./0110-instrument-series-projection.md)) as a `decision_reason`
enum count, and the Saturday gate reads one `DecisionReading` added to the
skill-selection instrument: answered rate, Jaccard between `decision_topk`
and the live `selected`, per-entry mean probability, calibration against the
`judged` selection as a stand-in truth, latency p50/p95, and the reload cost
read as the `duration_ms` delta on the generation row that follows. Exactly
two decisions consume it: the enforce-or-retire reading above and the
quiet-instrument reading. When both have been answered the fields, the hook,
the enum entry and the reading are removed together with whichever decision
they served. This section is the canonical statement; the summary in
RFC-0040 points here.

## Alternatives Considered

- **A default-on backend with gemma as the decision model.** Rejected: it
  would add one call per catalog entry to every generation on every tier
  that configures the LLM (stocktake, evals, dialogue), and would remove
  configuration absence as the kill switch. Setting `DECISION_MODEL=gemma4:e4b`
  gives the same zero-swap readout for the first shadow week, opt-in.
- **Decompose an over-20-option choice into per-option yes/no inside the
  backend.** Rejected: the backend would be returning a set of unrelated
  conditionals labelled as one distribution. Skill selection is
  multi-label and asks per-entry `noul` from the caller, which is the shape
  the AUC 0.728 evidence measured; the calibration problem of that shape
  (ECE 0.766, "almost all yes") is then visible in `decision_p` rather than
  hidden behind a softmax.
- **Phase separation now** (judge every candidate in a cycle, evict once,
  generate everything). Deferred — 未決, revisit at the enforcement reading.
  In shadow the backend-internal swap costs two reloads per selection batch
  and no adapter changes; phase separation only pays once relevance scoring
  and note generation also move behind the seam, which is enforcement work.
- **Rely on Ollama's own eviction for the no-co-residence guarantee.**
  Rejected: with `OLLAMA_MAX_LOADED_MODELS` unset, 0.34.2 co-loads whenever
  it judges both models fit, and gemma4:e4b at 3.4 GB resident (`ollama ps`
  at `num_ctx` 32768) beside qwen3.5:9b at 6.6 GB (`ollama list`, both
  2026-09-22) may pass that judgment on a 16 GB machine.
- **Put torch-based decision models in the wheel as an optional extra.**
  Rejected by ADR-0109: `test_no_optional_dependency_extras` treats an
  extra as wheel runtime code, and the floor is requests + numpy.
- **A separate `decision-shadow-*.jsonl` log.** Rejected: the comparison
  the gate reads is row-for-row against `selected`, and a second log would
  need a join on `selection_id`. RFC-0044 added `temperature` to the same
  record for the same reason.
- **Measure offline only and build no seam until a model wins.** Rejected by
  the owner on 2026-09-22: the contract is the same whichever model wins,
  and the shadow reading is the only way to price the reload in production
  traffic.

## Consequences

### Positive

- Any model that speaks the three-question contract — a hosted one, a
  sibling-injected one, or the Ollama readout — plugs into the same seam and
  is compared in the same record fields.
- Nothing is added to the wheel's dependencies or its outbound surface.
- The path is off by default; a production run without `DECISION_MODEL`
  is byte-for-byte the current behaviour.
- The reload cost, which decides whether the swap design is viable, is
  measured in production rows rather than estimated.

### Negative

- With the backend configured, each skill selection makes one Ollama call
  per catalog entry (53–57 today). The same shape on gemma took 51.0 s per
  row at the median in RFC-0043 (arm `C/logits`, 150 rows, arms interleaved
  so the prefix cache was colder than production's back-to-back calls);
  the production selection call itself takes 19.1 s at the median (evidence
  §7). The batch budget caps what the shadow can add to a cycle;
  `decision_latency_ms` measures what it does add.
- The shipped per-entry shape is the worst-calibrated arm RFC-0043 measured
  (ECE 0.766, against 0.116 for the one-pass readout that covers only 37%
  of the catalog). Calibration is read in `decision_p`, not assumed.
- `keep_alive: 0` is a side effect on a shared daemon. In the swap
  configuration every selection batch costs two reloads, about 10 s on the
  gemma side alone.
- The readout helpers (`binary_softmax`, the label alphabet, the yes/no
  token surfaces) exist in the harness script and are now shipped in
  `core.llm.decision`; the script keeps its copies until the round-3 arms
  land and a follow-up chore switches it to the shipped ones. Until then
  the two copies can drift.
- The skill-selection record gains seven fields; readers that count keys
  must tolerate nulls.

### Reversal cost

Deleting `core/llm/decision.py`, `testing/decision_contract.py`, the
`configure` parameter, the hook and the seven fields returns the tree to
today. Rows already written keep the fields as data; the census tolerates
unknown keys. Nothing outside git is created.

### Neutral

- The harness's arm C and arm F remain the reference implementation the
  backend was lifted from; the evidence README is the record of what the
  readout measures on gemma.
- The remaining five judgment faces (relevance, submolt, post-gate,
  novelty, duplicate) are not moved by this ADR. Each is a later, separate
  change behind the same seam.

## References

- [RFC-0040](../../rfcs/0040-jev-system-one-local-decision-backend.md) —
  the task, the candidate table, the design premises of 2026-09-22 and the
  round-3 reading order
- [RFC-0043](../../rfcs/0043-skillsel-offline-arm-replay.md) and
  [docs/evidence/rfc-0043/](../evidence/rfc-0043/README.md) — the offline
  measurement the readout and the no-co-residence rule come from
- [ADR-0076](./0076-skill-selection-shadow-instrument.md) — the shadow-mode
  pattern and its kill switch; [ADR-0081](./0081-skill-selection-two-pass-injection-enforcement.md)
  — the live selection this ADR observes beside
- [ADR-0088](./0088-shipped-conformance-kit-for-the-llm-backend-contract.md) — the
  generation seam and conformance kit this one mirrors
- [ADR-0101](./0101-instrument-dissolution-mandate.md) — the consumption
  plan above; [ADR-0109](./0109-dependency-floor-scoped-to-the-wheel.md) —
  why torch stays outside the wheel
- Skill `shadow-mode-validation` (repo-local) — the observe-only discipline
