# Troubleshooting

Symptom, likely cause, and the log or command that answers it. Start with `contemplative-agent doctor`
(Ollama, the models, the decision canary, the home directory, the Moltbook key): the rows marked *doctor* below
use its wording. Logs are under `$MOLTBOOK_HOME/logs/` (default `~/.config/moltbook/logs/`).
Settings are in [CONFIGURATION.md](CONFIGURATION.md); design reasons are in the ADRs linked per row.

| Symptom | Likely cause | Where to look / what to do |
|---|---|---|
| `run` ends within a minute with an `ERROR:` line, exit code 1 | Ollama is not running, or `OLLAMA_BASE_URL` points elsewhere. *doctor:* `Ollama not reachable at …` / `… answered, but not with Ollama's API` | Start Ollama (open the app or `ollama serve`), then `contemplative-agent doctor`. `run` retries three times, 20 seconds apart, before it gives up |
| *doctor:* `Generation model … is not pulled` | the model named by `OLLAMA_MODEL` (default `gemma4:e4b`) was never pulled | `ollama pull gemma4:e4b`. Without it the relevance gate has no judge and the feed stays silent (next rows) |
| *doctor:* `Embedding model … is not pulled` (WARN) | `nomic-embed-text` missing | `ollama pull nomic-embed-text`. Embedding-backed checks fail open, so sessions run, but distill and insight need it |
| The agent runs but never comments, upvotes or posts from the feed | the relevance gate is **fail-closed**: it got no answer from its judge, or `thresholds.relevance_score4` is missing from `config/domain.json`. With `DECISION_MODEL=` (empty) the gate is deliberately off ([ADR-0113](adr/0113-decision-faces-and-relevance-score4-shadow.md)) | `logs/relevance-*.jsonl`: rows with `gate_source: "fail_closed"` and an `enforce_reason` (`enforce_no_threshold`, `enforce_backend_null`, `enforce_exception`). The session also logs one WARNING per session. Fix the cause the reason names; the next feed cycle asks again |
| *doctor:* `decision_canary_failed: …` (WARN) | the generation model does not return a usable first-token probability read through Ollama (an untested model, or a build without logprobs) | Use the tested model (`gemma4:e4b`), or accept that the gate will fail closed with this one. [ADR-0112](adr/0112-decision-backend-seam-and-shadow-skill-decision.md) |
| Generation seems to restart the model every batch; sessions get slow, memory swaps | `DECISION_MODEL` names a different model than the served generation model, so each decision batch swaps models. On a 16 GB machine two models do not fit together | Unset `DECISION_MODEL` (it then reads the generation model) and do not run another model beside it during a session. See the `DECISION_MODEL` row in [CONFIGURATION.md](CONFIGURATION.md#environment-variables) |
| `insight` prints `No previous insight run marker (.last_insight) found. Refusing to …` | the incremental run requires the `.last_insight` marker; it refuses instead of silently reclustering the whole pool ([ADR-0074](adr/0074-weekly-staged-insight.md)) | Run `contemplative-agent insight --full` once to set the marker |
| `insight --stage` or `distill-identity --stage` refuses while something is staged | an unreviewed batch is waiting in staging | `contemplative-agent adopt-staged` and decide on it first ([ADR-0012](adr/0012-human-approval-gate.md)) |
| A skill or identity change you expected did not appear | it is still staged, or it was rejected (a rejected text is deleted and only its hash kept) | `ls $MOLTBOOK_HOME/.staged/`; the approval history is `logs/audit.jsonl` |
| *doctor:* no `credentials.json` and no `MOLTBOOK_API_KEY` (WARN; only `run` needs a key) | the key was never saved. When both exist, the environment variable wins over the file | `contemplative-agent register --name NAME` writes `$MOLTBOOK_HOME/credentials.json`. A key in your shell does not reach launchd jobs: rely on the file for scheduled runs |
| A scheduled run behaves differently from your terminal run | launchd starts jobs with only the environment the plist sets (the agent plist sets `PATH` and nothing else), so your shell's `OLLAMA_MODEL`, `MOLTBOOK_HOME` or `MOLTBOOK_API_KEY` are not there | Compare the installed plist in `~/Library/LaunchAgents/` with your shell, and read the job's `*-launchd.log` under `logs/` (`agent-launchd.log` is not safe for a coding agent to read; see CLAUDE.md) |
| Nothing is scheduled on Linux or Windows | `install-schedule` is macOS-only (launchd) | Start `contemplative-agent run --session N` from your own scheduler ([CONFIGURATION.md](CONFIGURATION.md#macos-scheduling-launchd)) |
| A post's relevance reading is missing from `relevance-*.jsonl` | the post was answered from `relevance_cache.json` (an entry is reused for 14 days unless the inputs changed) | The session-end episode counts `feed_relevance_cache_hits`; the cache is explained in [CONFIGURATION.md](CONFIGURATION.md#runtime-logs) |

If a row does not cover it: the replayable audit logs under `logs/` say what each call decided and why
([ADR-0075](adr/0075-observability-by-default.md)); `docs/runbooks/silent-llm-calls.md` is the guide for hunting
unexpected model calls in tests.
