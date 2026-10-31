"""Environment-variable registry: the one place that names every key (P1-06.4).

``ENV_KEYS`` is the source of truth for every environment variable the product
or its scripts read — name, default, owning ADR, where it is read, what the
empty string means. Three things follow from it and are checked in
``tests/test_configuration_doc.py``:

* every read under ``src/`` goes through :func:`env_get` / :func:`env_is_set` /
  :func:`environ_copy` (the only ``os.environ`` access in ``src/`` is this
  module), so a key cannot be read without being registered — an unregistered
  name raises ``KeyError`` here, not silently ``None`` there;
* the environment-variable table in ``docs/CONFIGURATION.md`` and the whole of
  ``.env.example`` are generated from this registry
  (``python scripts/render_env_docs.py``), and the test asserts they are
  byte-equal to :func:`render_config_table` / :func:`render_env_example`;
* the script-side knobs (``${NAME:-default}`` in ``scripts/*.sh``) are listed
  with the files that read them, and the test checks both directions.

Thresholds (score4 / novelty / circuit) are NOT here: their table is the
threshold table of P1-04.8. This module registers environment keys only.

Stdlib only; imports nothing from the package, so ``core.domain`` and the
adapter ``config`` module can read keys at import time without a cycle.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import overload

# Group order is the order of sections in ``.env.example``.
GROUPS: tuple[tuple[str, str], ...] = (
    ("moltbook", "Moltbook key"),
    ("ollama", "Ollama (defaults shown)"),
    ("storage", "Storage (default: ~/.config/moltbook)"),
    ("decision", "Decision backend (the relevance gate, ADR-0113)"),
    ("tuning", "Tuning and switches"),
    ("jobs", "Scheduled jobs and scripts (read by scripts/ and the schedule installer)"),
)


@dataclass(frozen=True)
class EnvKey:
    """One registered environment variable.

    ``read_by`` lists repo-relative paths; a path under ``scripts/`` or
    ``.claude/`` means a shell script reads it (``${NAME:-default}``), a path
    under ``src/`` means Python does. ``also`` are further names that share this
    row (the retired pair). ``example`` is the value shown commented-out in
    ``.env.example`` (``None`` = bare ``NAME=``).
    """

    name: str
    default: str
    description: str
    group: str
    owner: str
    read_by: tuple[str, ...]
    empty_means: str
    example: str | None = None
    short: str = ""
    also: tuple[str, ...] = ()
    retired: bool = False

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name, *self.also)


_PIPELINE_SH = "scripts/weekly-pipeline.sh"
_PIPELINE_EMPTY = "treated as unset (the default applies)"

ENV_KEYS: tuple[EnvKey, ...] = (
    EnvKey(
        name="MOLTBOOK_API_KEY",
        default="(unset)",
        description=(
            "Moltbook API key. Optional: `register` saves the key to "
            "`$MOLTBOOK_HOME/credentials.json`, which is read when this is unset; when "
            "set, it takes priority"
        ),
        group="moltbook",
        owner="ADR-0007",
        read_by=(
            "src/contemplative_agent/adapters/moltbook/auth.py",
            "src/contemplative_agent/cli/doctor.py",
        ),
        empty_means="treated as unset (the credentials file is read)",
        short=(
            "`contemplative-agent register --name NAME` saves the new agent's key to\n"
            "$MOLTBOOK_HOME/credentials.json, which every command (scheduled runs too)\n"
            "reads on its own. Set this only to use a key you already have in commands you\n"
            "run yourself; it takes priority over the file. For scheduled runs, write an\n"
            'existing key to ~/.config/moltbook/credentials.json as {"api_key": "..."}.'
        ),
    ),
    EnvKey(
        name="OLLAMA_BASE_URL",
        default="`http://localhost:11434`",
        description=(
            "Ollama endpoint for generation and embeddings. Must name a trusted host "
            "(localhost, or one listed in `OLLAMA_TRUSTED_HOSTS`); anything else is rejected"
        ),
        group="ollama",
        owner="ADR-0007",
        read_by=("src/contemplative_agent/core/llm/__init__.py",),
        empty_means="rejected (an empty URL names no trusted host)",
        example="http://localhost:11434",
    ),
    EnvKey(
        name="OLLAMA_MODEL",
        default="`gemma4:e4b`",
        description=(
            "Ollama model name. The relevance gate reads first-token logprobs, so the "
            "model must answer in one token and Ollama must return them: validated with "
            "Gemma 4 E4B on Ollama 0.34.2 (the author's environment; a tested version, "
            "not a measured minimum). For any other model run `contemplative-agent "
            "doctor` and read the canary line"
        ),
        group="ollama",
        owner="ADR-0069",
        read_by=("src/contemplative_agent/core/llm/__init__.py",),
        empty_means="an empty model name (the request fails; it is not a fallback to the default)",
        example="gemma4:e4b",
    ),
    EnvKey(
        name="OLLAMA_EMBEDDING_MODEL",
        default="`nomic-embed-text`",
        description="Ollama embedding model name (embeddings always stay on Ollama)",
        group="ollama",
        owner="ADR-0069",
        read_by=("src/contemplative_agent/core/embeddings.py",),
        empty_means="an empty model name (embedding requests fail; it is not a fallback)",
        example="nomic-embed-text",
    ),
    EnvKey(
        name="OLLAMA_TRUSTED_HOSTS",
        default="(none)",
        description="Additional trusted Ollama hosts (comma-separated)",
        group="ollama",
        owner="ADR-0007",
        read_by=("src/contemplative_agent/core/llm/guard.py",),
        empty_means="no extra hosts",
        short="extend trust beyond localhost (e.g. a remote Ollama on the LAN)",
    ),
    EnvKey(
        name="MOLTBOOK_HOME",
        default="`~/.config/moltbook/`",
        description="Runtime data directory",
        group="storage",
        owner="ADR-0003",
        read_by=(
            "src/contemplative_agent/adapters/moltbook/config.py",
            "src/contemplative_agent/core/domain.py",
            "src/contemplative_agent/core/takedown.py",
            "scripts/backup-runtime.sh",
            "scripts/pipeline_watchdog.sh",
            "scripts/sync-research-data.sh",
            "scripts/weekly-analysis.sh",
            _PIPELINE_SH,
        ),
        empty_means=(
            "the data-directory default reads it as the current directory (`Path('')`); "
            "the prompt-override lookup and the shell scripts treat it as unset"
        ),
        example="/custom/path",
    ),
    EnvKey(
        name="CONTEMPLATIVE_CONFIG_DIR",
        default="`{project}/config/`",
        description=(
            "Config templates directory. The default resolves relative to the source "
            "checkout, so outside a checkout (a wheel or `uv tool` install has no "
            "`config/` beside it) it must be set — the project is installed from a clone "
            "with `pip install -e .`. `--help` and `--version` work without any "
            "`config/`; prompts load on first use, so `init` and every command that "
            "renders a prompt need the directory"
        ),
        group="storage",
        owner="ADR-0003",
        read_by=("src/contemplative_agent/core/domain.py",),
        empty_means="treated as unset",
    ),
    EnvKey(
        name="CONTEMPLATIVE_DIALOGUE_PEER_MODULE",
        default="`contemplative_agent.cli`",
        description=(
            "Python module each `dialogue` peer process runs, so an outer wrapper "
            "(e.g. a managed-LLM shim) can route peers through its own entry point and "
            "have its setup (such as a configured LLM backend) run in every peer"
        ),
        group="tuning",
        owner="ADR-0015",
        read_by=("src/contemplative_agent/cli/session_cmds.py",),
        empty_means="an empty module name (the peer fails to start)",
        example="contemplative_agent.cli",
    ),
    EnvKey(
        name="DECISION_MODEL",
        default="(unset = `OLLAMA_MODEL`)",
        description=(
            "Ollama model name for the decision backend "
            "([ADR-0112](adr/0112-decision-backend-seam-and-shadow-skill-decision.md)), "
            "whose one caller is the relevance gate "
            "([ADR-0113](adr/0113-decision-faces-and-relevance-score4-shadow.md)). "
            "Unset reads the Ollama generation model, so on the default Ollama path no "
            "model is swapped (ADR-0113 amendment 2, 2026-10-09; before that, unset "
            "was off); with a sibling cloud / MLX generation backend injected it is "
            "still the Ollama model, run exclusive (the decision model is reloaded once per batch — "
            "accepted, ADR-0112 addendum 2026-10-24). The gate is always on and has no "
            "other switch (amendment 3): with an answered read and "
            "`thresholds.relevance_score4` set, the gate is `P(directly on-topic) >= "
            "relevance_score4`, and it alone decides the upvote, the note, the "
            "full-body fetch and the comment, and which peer posts may seed a "
            'self-post (its rows say `source: "seed"`; the feed\'s say `"feed"`). When '
            "the gate has no answer it fails closed: no engagement and no memo, the "
            "feed cycle ends there and the next cycle asks again (a failure tied to "
            "one post's text, `no_option_observed`, skips that post instead); the row "
            'says why (`gate_source: "fail_closed"`, `enforce_reason`: '
            "`enforce_no_threshold` / `enforce_backend_null` / `enforce_exception`; "
            "rows from before amendment 3 may say `enforce_unconfigured`), and a "
            "missing threshold also logs one ERROR per session. Empty constructs no "
            "backend: no call, no telemetry, every read records `unconfigured` and "
            "fails closed (`enforce_backend_null`) — no feed engagement and no seed "
            "selection — with one WARNING at startup. A value other than the served "
            "generation model makes every batch swap models — the generation model is "
            "evicted before the batch and the decision model after it, and the next "
            "generation reloads"
        ),
        group="decision",
        owner="ADR-0113",
        read_by=("src/contemplative_agent/cli/runtime.py",),
        empty_means="constructs no decision backend: every relevance read is `unconfigured` and the gate fails closed",
        short="empty disables the relevance gate's backend (the gate then fails closed)",
    ),
    EnvKey(
        name="DECISION_BUDGET_S",
        default="`120`",
        description=(
            "Wall-clock seconds one decision batch may spend. Questions the budget "
            "does not reach are reported as `budget_exceeded` rather than delaying the "
            "generation behind them. Unreadable or non-positive values fall back to "
            "the default with a WARNING"
        ),
        group="decision",
        owner="ADR-0113",
        read_by=("src/contemplative_agent/cli/runtime.py",),
        empty_means="unreadable: falls back to the default with a WARNING",
        example="120",
    ),
    EnvKey(
        name="DECISION_FACES",
        also=("DECISION_ENFORCE",),
        default="(retired)",
        description=(
            "Removed in ADR-0113 amendment 3 with the skill-selection decision shadow "
            "(ADR-0112 D5) and the relevance gate's enforce switch. Set to anything "
            "(empty included), each is ignored with one WARNING per session; it no "
            "longer turns the gate or any face on or off"
        ),
        group="decision",
        owner="ADR-0113",
        read_by=("src/contemplative_agent/cli/runtime.py",),
        empty_means="ignored with one WARNING per session (set or empty alike)",
        retired=True,
    ),
    EnvKey(
        name="MOLTBOOK_DISTILL_POSTGATE",
        default="on",
        description=(
            "The distill post-extraction gate is on by default; the exact value `0` "
            "opts out. Any other value, empty included, leaves it on"
        ),
        group="tuning",
        owner="ADR-0081",
        read_by=("src/contemplative_agent/core/distill.py",),
        empty_means="leaves the gate on (only `0` opts out)",
        example="0",
    ),
    EnvKey(
        name="MOLTBOOK_INSIGHT_FAILOPEN_CAP",
        default="`20`",
        description=(
            "Maximum clusters the fail-open `insight` stage extracts per run; the rest "
            "are deferred to a later window (a review-budget circuit breaker, not a "
            "quality filter). An unreadable or non-positive value logs a WARNING and "
            "uses the default"
        ),
        group="tuning",
        owner="ADR-0074",
        read_by=("src/contemplative_agent/core/insight.py",),
        empty_means="unreadable: logs a WARNING and uses the default",
        example="20",
    ),
    EnvKey(
        name="MOLTBOOK_SUBMOLT_SCOPE_DISABLE",
        default="(unset = enabled)",
        description=(
            "The exact value `1` disables the submolt-scope instrument's sweep "
            "(read-only; the session itself is unaffected). Re-running `install-schedule` "
            "does not carry this variable into the plist"
        ),
        group="tuning",
        owner="ADR-0086",
        read_by=("src/contemplative_agent/adapters/moltbook/submolt_scope.py",),
        empty_means="leaves the sweep enabled (only `1` disables it)",
        example="1",
    ),
    EnvKey(
        name="MOLTBOOK_OPERATOR",
        default="(unset)",
        description=(
            "An approver name recorded as `approver` on gate decisions when neither "
            "`--approver` nor a names-file `# approver:` line says "
            "([ADR-0116](adr/0116-approval-gate-records-as-acts-of-responsibility.md)). "
            "An override for a second named human, not a default: the registered names "
            "are in `docs/GOVERNANCE.md`"
        ),
        group="tuning",
        owner="ADR-0116",
        read_by=("src/contemplative_agent/cli/approval.py",),
        empty_means="treated as unset (no approver from the environment)",
    ),
    EnvKey(
        name="MOLTBOOK_GATE_SESSION",
        default="(unset)",
        description=(
            "Session id recorded as `session` on gate decisions, when "
            "`CLAUDE_CODE_SESSION_ID` is not exported by the host (`--session` wins over both)"
        ),
        group="tuning",
        owner="ADR-0116",
        read_by=("src/contemplative_agent/cli/approval.py",),
        empty_means="treated as unset (no session id from the environment)",
    ),
    EnvKey(
        name="CLAUDE_CODE_SESSION_ID",
        default="(set by the host, if at all)",
        description=(
            "Read, never set by this project: when the Claude Code host exports it, it is "
            "recorded as `session` on gate decisions (best effort; `--session` and "
            "`MOLTBOOK_GATE_SESSION` are the fallbacks)"
        ),
        group="tuning",
        owner="ADR-0116",
        read_by=("src/contemplative_agent/cli/approval.py",),
        empty_means="treated as unset (`MOLTBOOK_GATE_SESSION` is read next)",
    ),
    EnvKey(
        name="MOLTBOOK_PIPELINE_STAGES",
        default="`report,valuelayer,deadcode,docsscan`",
        description=(
            "Comma-separated stages of the weekly chain (`scripts/weekly-pipeline.sh`). "
            "Exporting it in the shell that runs `install-schedule --weekly-pipeline` bakes "
            "it into the plist (shadow rollout); a later re-install without the export "
            "reverts to the full chain"
        ),
        group="jobs",
        owner="ADR-0085",
        read_by=("src/contemplative_agent/cli/schedule.py", _PIPELINE_SH),
        empty_means=_PIPELINE_EMPTY,
        example="report",
    ),
    EnvKey(
        name="MOLTBOOK_BACKUP_REPO",
        default="`$HOME/MyAI_Lab/contemplative-agent-runtime-backup`",
        description="Private disaster-recovery repo that `scripts/backup-runtime.sh` mirrors MOLTBOOK_HOME into",
        group="jobs",
        owner="(none)",
        read_by=("scripts/backup-runtime.sh",),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="MOLTBOOK_DATA_REPO",
        default="`$HOME/MyAI_Lab/contemplative-agent-data`",
        description="The git clone `sync-data` mirrors the public data into, that the weekly collector reads the State Diff from, and the watchdog's `sync-data` row reads the reflog of. Owner-operated: a third party points it at their own data repo",
        group="jobs",
        owner="ADR-0010",
        read_by=(
            "scripts/pipeline_watchdog.sh",
            "scripts/sync-research-data.sh",
            "scripts/weekly-analysis.sh",
        ),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="RSYNC_BIN",
        default="(first rsync 3.x found on PATH / Homebrew)",
        description=(
            "rsync binary that `scripts/lib-rsync.sh` uses for the data sync and the "
            "runtime backup. Must be executable; the disclosure boundary's matching "
            "rules are tested against rsync 3.x only"
        ),
        group="jobs",
        owner="ADR-0010",
        read_by=("scripts/lib-rsync.sh",),
        empty_means="treated as unset (the search applies)",
    ),
    EnvKey(
        name="MOLTBOOK_HF_DATASET",
        default="`Shimo4228/contemplative-agent-data`",
        description=(
            "Hugging Face dataset that `scripts/sync-research-data.sh` mirrors the "
            "knowledge projection to (best-effort after the git push)"
        ),
        group="jobs",
        owner="ADR-0010",
        read_by=("scripts/sync-research-data.sh",),
        empty_means="disables the upload (set empty for network-isolated runs)",
        example="Shimo4228/contemplative-agent-data",
    ),
    EnvKey(
        name="PIPELINE_TASKS_DIR",
        default="`{project}/rfcs`",
        description="The RFC ledger the weekly chain reads; its drafts go to `PIPELINE_INBOX_DIR` under it (written, never committed by the chain)",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="PIPELINE_INBOX_DIR",
        default="`$PIPELINE_TASKS_DIR/.inbox`",
        description="Untracked, unnumbered directory the weekly chain files its drafts into; the Saturday gate numbers and publishes them (`scripts/rfc_inbox.py adopt`)",
        group="jobs",
        owner="ADR-0098",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="PIPELINE_CLAUDE_ENV_PASSTHROUGH",
        default="(none)",
        description="Space-separated names of extra variables passed through `env -i` to the headless weekly report session (e.g. token-based auth such as `CLAUDE_CODE_OAUTH_TOKEN`); keychain login needs none",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means="no extra variables (only the fixed allowlist)",
    ),
    EnvKey(
        name="PIPELINE_WEEKLY_MODEL",
        default="(unset = the CLI's default)",
        description="Model the headless weekly report session is pinned to; unset is recorded as `model=default` in chain_start. A change is a regime boundary for the longitudinal readings",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means="treated as unset (the CLI's default model)",
    ),
    EnvKey(
        name="PIPELINE_WEEKLY_TIMEOUT",
        default="`5400`",
        description="Seconds before the single weekly report session is killed (a hang detector, not a budget)",
        group="jobs",
        owner="ADR-0098",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
        example="5400",
    ),
    EnvKey(
        name="PIPELINE_DEADCODE_TIMEOUT",
        default="`300`",
        description="Seconds before the dead-code scan stage is killed",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
        example="300",
    ),
    EnvKey(
        name="PIPELINE_DOCSCAN_TIMEOUT",
        default="`180`",
        description="Seconds before the docs-consistency scan stage is killed",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
        example="180",
    ),
    EnvKey(
        name="PIPELINE_IDENTITY_TIMEOUT",
        default="`900`",
        description="Seconds before the monthly identity-distill staging step is killed",
        group="jobs",
        owner="ADR-0091",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
        example="900",
    ),
    EnvKey(
        name="PIPELINE_LAUNCH_AGENTS_DIR",
        default="`~/Library/LaunchAgents`",
        description="Directory the weekly chain reads launchd plists from to find the next agent session (the identity-window guard); a test seam",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="PIPELINE_WATCHDOG_STATUS",
        default="`$MOLTBOOK_HOME/reports/PIPELINE-STATUS.md`",
        description="Watchdog status file whose age the chain records as `watchdog_age_h=` (`WATCHDOG_STALE` over 72 h or missing)",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="PIPELINE_KEEP_RUNS",
        default="`12`",
        description="Run-directory generations under `logs/weekly-pipeline/` kept when the chain ends",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
        example="12",
    ),
    EnvKey(
        name="TIMEOUT_BIN",
        default="unset",
        description="Executable used as the stage hang detector when neither `timeout` nor `gtimeout` is on PATH (the chain records `timeout_bin=`; none at all is `NO_TIMEOUT_BIN`)",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH, "scripts/host_check.sh"),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="WATCHDOG_MIN_FREE_KB",
        default="`10485760`",
        description="Free-disk floor in KB for the watchdog's `disk` row (10 GB)",
        group="jobs",
        owner="ADR-0085",
        read_by=("scripts/pipeline_watchdog.sh",),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="PIPELINE_DEADLINE_SECONDS",
        default="`10800`",
        description="Seconds after the chain starts by which it must be finished (09:00 to 12:00)",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
        example="10800",
    ),
    EnvKey(
        name="PIPELINE_INSIGHT_MARKER_MAX_AGE",
        default="`21600`",
        description="Maximum age in seconds of the last-insight marker for the value-layer stage to treat the weekly insight as current",
        group="jobs",
        owner="ADR-0091",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
        example="21600",
    ),
    EnvKey(
        name="PIPELINE_NEVER_SELECTED_TIMEOUT",
        default="`300`",
        description="Seconds before the never-selected reading stage is killed",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
        example="300",
    ),
    EnvKey(
        name="PIPELINE_CONFUSION_TIMEOUT",
        default="`300`",
        description="Seconds before the skill-confusion reading stage is killed",
        group="jobs",
        owner="ADR-0085",
        read_by=(_PIPELINE_SH,),
        empty_means=_PIPELINE_EMPTY,
        example="300",
    ),
    EnvKey(
        name="WEEKLY_PREV_COUNT",
        default="`1`",
        description="How many previous weekly reports `scripts/weekly-analysis.sh` puts into the materials (the observation ledger carries the continuation; raise it per run)",
        group="jobs",
        owner="ADR-0085",
        read_by=("scripts/weekly-analysis.sh",),
        empty_means=_PIPELINE_EMPTY,
        example="1",
    ),
    EnvKey(
        name="N_SIMS",
        default="`10`",
        description="Simulations per arm in `scripts/ipd-two-arm.sh`",
        group="jobs",
        owner="ADR-0090",
        read_by=("scripts/ipd-two-arm.sh", "scripts/ipd-series.sh"),
        empty_means=_PIPELINE_EMPTY,
        example="10",
    ),
    EnvKey(
        name="BENCH_DIR",
        default="`../contemplative-agent-rules/benchmarks/prisoners-dilemma`",
        description="Checkout of the IPD benchmark that `scripts/ipd-two-arm.sh` runs",
        group="jobs",
        owner="ADR-0090",
        read_by=("scripts/ipd-two-arm.sh", "scripts/ipd-series.sh"),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="BENCH_REF",
        default="`v0.2.0`",
        description="Rules-repo tag the IPD calibration contract is pinned to (D-P1-11-6 = A). `scripts/ipd-two-arm.sh` records the checkout's `git describe` in provenance.txt and only warns when the checkout is not at this ref",
        group="jobs",
        owner="ADR-0090",
        read_by=("scripts/ipd-two-arm.sh",),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="SKIP_WINDOW_GUARD",
        default="`0`",
        description="The exact value `1` skips the wait for a clear window between scheduled sessions in `scripts/ipd-two-arm.sh` and `scripts/ipd-series.sh` (16 GB: concurrent heavy Ollama runs have caused OOM)",
        group="jobs",
        owner="ADR-0090",
        read_by=("scripts/_ipd_common.sh",),
        empty_means="the guard stays on (only `1` skips it)",
        example="1",
    ),
    EnvKey(
        name="ARM_A_FILE",
        default="unset",
        description="Arm A text for `scripts/ipd-two-arm.sh` in `--files` mode (any two texts, no audit-hash check); same as the first `--files` argument and needs `ARM_B_FILE`",
        group="jobs",
        owner="ADR-0090",
        read_by=("scripts/ipd-two-arm.sh",),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="ARM_B_FILE",
        default="unset",
        description="Arm B text for `scripts/ipd-two-arm.sh` in `--files` mode; needs `ARM_A_FILE`",
        group="jobs",
        owner="ADR-0090",
        read_by=("scripts/ipd-two-arm.sh",),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="DATA_REPO",
        default="`../contemplative-agent-data` beside the repo",
        description="Checkout of the public data repo whose constitution versions `scripts/ipd-series.sh` runs through the bench (P3-03)",
        group="jobs",
        owner="ADR-0090",
        read_by=("scripts/ipd-series.sh",),
        empty_means=_PIPELINE_EMPTY,
    ),
    EnvKey(
        name="AUDIT_CHECK_BYPASS",
        default="`0`",
        description="The exact value `1` skips the check that arm A's constitution is the last-approved one in `scripts/ipd-two-arm.sh`; for non-production homes only",
        group="jobs",
        owner="ADR-0090",
        read_by=("scripts/ipd-two-arm.sh",),
        empty_means="the check stays on (only `1` bypasses it)",
        example="1",
    ),
    EnvKey(
        name="VERIFY_OFFLINE",
        default="(unset = probe)",
        description="Overrides `.claude/verify.sh`'s network probe before pip-audit: `1` treats the run as offline (pip-audit is inconclusive, exit 2), `0` as online. Unset, a probe of the package index decides",
        group="jobs",
        owner="ADR-0062",
        read_by=(".claude/verify.sh",),
        empty_means="treated as unset (the probe decides)",
    ),
    EnvKey(
        name="VERIFY_REPO_ROOT",
        default="(the script's own repo)",
        description="Repo root `.claude/verify.sh` checks when invoked through the approval mechanism, which runs a verified copy of the script from a temporary file",
        group="jobs",
        owner="ADR-0062",
        read_by=(".claude/verify.sh",),
        empty_means="treated as unset (the script's own location decides)",
    ),
)

_BY_NAME: dict[str, EnvKey] = {name: key for key in ENV_KEYS for name in key.names}

# Names that are listed only so a stale setting can be flagged; no code reads
# them for a value.
RETIRED_NAMES: tuple[str, ...] = tuple(
    name for key in ENV_KEYS if key.retired for name in key.names
)


def _registered(name: str) -> EnvKey:
    try:
        return _BY_NAME[name]
    except KeyError:
        raise KeyError(
            f"{name!r} is not a registered environment key — add it to ENV_KEYS "
            "in core/env.py (and run scripts/render_env_docs.py)"
        ) from None


@overload
def env_get(name: str) -> str | None: ...
@overload
def env_get(name: str, default: str) -> str: ...
def env_get(name: str, default: str | None = None) -> str | None:
    """Read the registered key *name* (``default`` when it is not set).

    An unset variable returns *default*; an empty one returns ``""`` — what the
    empty string means is per key, in ``EnvKey.empty_means``.
    """
    _registered(name)
    return os.environ.get(name, default)


def env_is_set(name: str) -> bool:
    """True when *name* is present in the environment, empty included."""
    _registered(name)
    return name in os.environ


def environ_copy() -> dict[str, str]:
    """A copy of the whole environment, for building a child-process env."""
    return dict(os.environ)


# --- generated artifacts ----------------------------------------------------

TABLE_BEGIN = "<!-- env-table:begin (generated from src/contemplative_agent/core/env.py by scripts/render_env_docs.py; do not edit by hand) -->"
TABLE_END = "<!-- env-table:end -->"

_ENV_EXAMPLE_HEADER = """\
# Environment variables Contemplative Agent reads. Every one is optional.
# Generated from src/contemplative_agent/core/env.py by scripts/render_env_docs.py
# (docs/CONFIGURATION.md#environment-variables has the full table).
#
# The CLI does not load this file by itself. Copy it to .env, edit it, and
# load it into your shell before running a command:
#   set -a; . ./.env; set +a
# Scheduled runs (install-schedule) start from launchd and see none of these:
# no shell exports and no custom MOLTBOOK_HOME. They always use
# ~/.config/moltbook and the defaults shown below.
"""


def render_config_table() -> str:
    """The Markdown table that lives between the markers in CONFIGURATION.md."""
    lines = [
        "| Variable | Default | Description | Owner | Read by | Empty string |",
        "|----------|---------|-------------|-------|---------|--------------|",
    ]
    for key in ENV_KEYS:
        label = " / ".join(f"`{n}`" for n in key.names)
        read_by = ", ".join(f"`{p}`" for p in key.read_by)
        lines.append(
            f"| {label} | {key.default} | {key.description} | {key.owner} | "
            f"{read_by} | {key.empty_means} |"
        )
    return "\n".join(lines) + "\n"


def render_env_example() -> str:
    """The whole of ``.env.example``."""
    out = [_ENV_EXAMPLE_HEADER.rstrip("\n")]
    for group, title in GROUPS:
        keys = [k for k in ENV_KEYS if k.group == group and not k.retired]
        if not keys:
            continue
        out.append("")
        out.append(f"# --- {title} ---")
        for key in keys:
            if key.short:
                out.extend(f"# {line}" for line in key.short.split("\n"))
            value = "" if key.example is None else key.example
            out.append(f"# {key.name}={value}")
    return "\n".join(out) + "\n"
