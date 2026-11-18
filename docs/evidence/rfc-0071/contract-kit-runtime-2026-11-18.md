# Conformance kit against the built-in Ollama backend — reading 2026-11-18 (RFC-0071 P1-06.1)

reanalysis: public — the kit and the backend are in this repository; anyone with
a clone and `uv sync` can re-run the commands below. No Ollama call is involved
(see "What the runtime level contains").

Target: `contemplative_agent.core.llm.ollama:OllamaBackend`
(`src/contemplative_agent/core/llm/ollama.py:166`, a frozen dataclass whose
`model` resolves through the facade on every call). Kit:
`src/contemplative_agent/testing/`, `KIT_VERSION = "2"`. This file records the
reading; it states no verdict.

## Environment

| item | value |
|---|---|
| run | 2026-11-18 19:06:33 JST (10:06 UTC), production machine |
| tree | branch from `main` at `32299fca` + the plan commit `2c426c41` (`git describe`: `v2.14.0-80-g2c426c41`) |
| Python | 3.13.5 (worktree `.venv`, `uv sync`) |
| Ollama | 0.34.2 (`ollama --version`, `/api/version`) |
| model the backend resolves | `gemma4:e4b` (`OllamaBackend().model`), `context_window` 32768 |
| before the run | `pgrep -fl "contemplative-agent run"` empty (exit 1); `ollama ps` listed no loaded model |

## Commands and exit codes

The command in the roadmap STATUS note, then the two neighbouring levels:

```sh
uv run --no-sync python -m contemplative_agent.testing \
  --backend contemplative_agent.core.llm.ollama:OllamaBackend --require runtime   # exit 1
uv run --no-sync python -m contemplative_agent.testing \
  --backend contemplative_agent.core.llm.ollama:OllamaBackend --require static    # exit 0
uv run --no-sync python -m contemplative_agent.testing \
  --backend contemplative_agent.core.llm.ollama:OllamaBackend --require full      # exit 1
```

Report line for each: `level=static kit=2 capabilities=[]`.

## Per-check results (`--require runtime`)

The CLI prints only failed and skipped checks; the full list was read through
`check_backend(OllamaBackend(), require="runtime")`.

| check id | status | detail |
|---|---|---|
| `meta.level_reached` | FAILED | caller declared require='runtime', but the kit currently implements checks through 'static' |
| `meta.declared_capabilities_present` | PASSED | |
| `protocol.members` | PASSED | |
| `model.type` | PASSED | |
| `context_window.positive_int` | PASSED | |
| `generate.binds_canonical_call` | PASSED | |
| `generate.kwonly_defaults` | PASSED | |
| `count_tokens.signature` | SKIPPED (`capability_absent`) | backend does not present capability 'counts_tokens' |

Counts: 6 PASSED, 1 FAILED, 1 SKIPPED. With `--require static` the same eight
rows come out with `meta.level_reached` PASSED (7 PASSED, 1 SKIPPED, exit 0).
`--require full` gives the same FAILED row as runtime.

## What the runtime level contains

Nothing yet. Every entry of the kit's check registry
(`src/contemplative_agent/testing/backend_contract.py:470-480`) is
`LEVEL_STATIC`, so `_MAX_IMPLEMENTED_LEVEL` (`:483-486`) is `static`, and
`_reachable_level` (`:514-529`) returns `min(probe level, static)`. A
`BackendProbe` therefore cannot raise the reached level.

This was checked directly with a minimal probe that has both `responding` and
`make_backend` (so its own level is `full`). Run from the repository root:

```sh
uv run --no-sync python - <<'PY'
from contextlib import contextmanager
from contemplative_agent.testing import check_backend
from contemplative_agent.core.llm.ollama import OllamaBackend

class P:
    def make_backend(self, **overrides):
        raise NotImplementedError

    @contextmanager
    def responding(self, *responses):
        calls = []
        yield calls

for probe in (None, P()):
    r = check_backend(OllamaBackend(), probe=probe, require="runtime")
    print("probe=", type(probe).__name__, "ok=", r.ok, "level_reached=", r.level_reached)
    for c in r.results:
        print("  ", c.status, c.check_id, "|", c.detail)
PY
```

Output on 2026-11-18: for both `probe=NoneType` and `probe=P` the header is
`ok= False level_reached= static`, followed by the same eight rows as the table
above (`failed meta.level_reached | caller declared require='runtime', but the
kit currently implements checks through 'static'`, six `passed`, and
`skipped count_tokens.signature | backend does not present capability
'counts_tokens'`). The probe was run inline as above; no probe file was added
to the repository. The block was re-run verbatim after it was written into
this note and printed the same output.

No check calls `generate()`, so this reading never sent a request to Ollama; the Ollama version and model
above describe the machine, not traffic the kit produced.

The `--help` text "Levels above 'static' need a probe, which the CLI cannot
supply — use a test file" (`__main__.py`) describes the design; in kit version
2 a test file with a probe reaches the same `static` ceiling. The
`meta.level_reached` detail names that case separately from "no probe
supplied" (`backend_contract.py:649-666`).

## Input to the decision

- The static contract holds for the built-in backend (exit 0 at `static`).
- The STATUS command (`--require runtime`) cannot exit 0 against any backend
  until runtime-level checks are added to the kit; its one FAILED row is the
  kit's ceiling, not a property of `OllamaBackend`.
- Capabilities detected: none. `count_tokens` is absent on `OllamaBackend`;
  the behavioural capabilities (`reports_eval_count`, `reports_prefill`,
  `reports_finish_reason`, `produces_thinking`) are detectable only at
  runtime, which does not exist yet.
