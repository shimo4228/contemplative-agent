"""Surface snapshot: the externally visible names, pinned as literals (P1-06.2).

The project is heading for a long stop (ADR-0080: the mechanism layer is
finished when it stops). What a stopped mechanism owes its readers and its
unattended schedule is a surface that does not change by accident: the CLI
commands and the tier each one runs at, the launchd labels, the environment
keys, the prompt files, the conformance-kit version, the two outbound hosts,
and where the production model literal lives. Each is a literal below, and each
test fails when exactly one of them moves.

Changing any of these is allowed only together with an ADR addendum in the
same change (the freshness rule in CLAUDE.md). A PR that predates this file
does not retroactively owe it: the literals are the values on 2026-10-24, and
a branch that adds a command (P0-05.1 adds ``doctor``) or removes a prompt
(P1-07.14 drops ``stocktake_merge_rules``) re-pins its own line here.

The CI configuration literals live in ``tests/test_ci_config.py`` (P1-08.25);
this file does not duplicate them.
"""

from __future__ import annotations

import ast
from pathlib import Path
from urllib.parse import urlparse

from contemplative_agent.adapters.moltbook.config import ALLOWED_DOMAIN
from contemplative_agent.cli import COMMANDS, schedule
from contemplative_agent.core.env import ENV_KEYS
from contemplative_agent.core.llm import DEFAULT_OLLAMA_MODEL, DEFAULT_OLLAMA_URL, LOCALHOST_HOSTS
from contemplative_agent.testing import KIT_VERSION

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "contemplative_agent"

EXPECTED_COMMANDS: frozenset[tuple[str, str]] = frozenset(
    {
        ('adopt-staged', 'no_llm'),
        ('amend-constitution', 'llm_full'),
        ('dialogue', 'no_llm'),
        ('dialogue-peer', 'llm_full'),
        ('distill', 'llm_full'),
        ('distill-identity', 'llm_full'),
        ('generate-report', 'llm_full'),
        ('init', 'llm_full'),
        ('insight', 'llm_full'),
        ('install-schedule', 'no_llm'),
        ('meditate', 'llm_full'),
        ('register', 'agent'),
        ('remove-skill', 'no_llm'),
        ('report', 'llm_full'),
        ('run', 'agent'),
        ('shadow-constitution', 'llm_full'),
        ('skill-stocktake', 'llm_runtime_only'),
        ('solve', 'agent'),
        ('status', 'agent'),
        ('submolt-scan', 'agent'),
        ('sync-data', 'no_llm'),
    }
)
EXPECTED_ENV_KEYS: frozenset[str] = frozenset(
    {
        'AUDIT_CHECK_BYPASS',
        'BENCH_DIR',
        'CONTEMPLATIVE_CONFIG_DIR',
        'CONTEMPLATIVE_DIALOGUE_PEER_MODULE',
        'DECISION_BUDGET_S',
        'DECISION_ENFORCE',
        'DECISION_FACES',
        'DECISION_MODEL',
        'MOLTBOOK_API_KEY',
        'MOLTBOOK_BACKUP_REPO',
        'MOLTBOOK_DISTILL_POSTGATE',
        'MOLTBOOK_HF_DATASET',
        'MOLTBOOK_HOME',
        'MOLTBOOK_INSIGHT_FAILOPEN_CAP',
        'MOLTBOOK_PIPELINE_STAGES',
        'MOLTBOOK_SUBMOLT_SCOPE_DISABLE',
        'N_SIMS',
        'OLLAMA_BASE_URL',
        'OLLAMA_EMBEDDING_MODEL',
        'OLLAMA_MODEL',
        'OLLAMA_TRUSTED_HOSTS',
        'PIPELINE_CLAIMS_PY',
        'PIPELINE_COMMENT_OUTCOMES_TIMEOUT',
        'PIPELINE_CONFUSION_TIMEOUT',
        'PIPELINE_DEADCODE_TIMEOUT',
        'PIPELINE_DEADLINE_SECONDS',
        'PIPELINE_DOCSCAN_TIMEOUT',
        'PIPELINE_IDENTITY_TIMEOUT',
        'PIPELINE_INSIGHT_MARKER_MAX_AGE',
        'PIPELINE_NEVER_SELECTED_TIMEOUT',
        'PIPELINE_TASKS_DIR',
        'PIPELINE_WEEKLY_TIMEOUT',
        'SKIP_WINDOW_GUARD',
        'VERIFY_REPO_ROOT',
        'WEEKLY_PREV_COUNT',
    }
)
EXPECTED_PROMPT_STEMS: frozenset[str] = frozenset(
    {
        'comment',
        'constitution_amend',
        'constitution_synthesize',
        'cooperation_post',
        'dialogue',
        'distill_episode',
        'distill_postgate',
        'identity_distill',
        'insight_description',
        'insight_duplicate',
        'insight_duplicate_system',
        'insight_extraction',
        'insight_name',
        'insight_naming',
        'insight_naming_system',
        'insight_novelty',
        'insight_novelty_system',
        'internal_note',
        'learned_rules_framing',
        'learned_skills_framing',
        'meditation_interpret',
        'post_title',
        'principles',
        'relevance_score4',
        'reply',
        'reply_post_block',
        'skill_selection',
        'stocktake_description',
        'stocktake_description_system',
        'stocktake_merge_rules',
        'submolt_selection',
        'system',
        'topic_summary',
        'untrusted_marker_complete',
        'untrusted_marker_truncated',
        'untrusted_wrapper',
        'verification_solve_extract_system',
        'weekly-analysis',
    }
)

EXPECTED_LAUNCHD_LABELS: frozenset[str] = frozenset(
    {
        "com.moltbook.agent",
        "com.moltbook.backup",
        "com.moltbook.distill",
        "com.moltbook.insight",
        "com.moltbook.submolt-scan",
        "com.moltbook.watchdog",
        "com.moltbook.weekly-pipeline",
    }
)
EXPECTED_KIT_VERSION = "2"
# Exactly two outbound hosts: the platform and the local model server.
EXPECTED_PLATFORM_HOST = "www.moltbook.com"
EXPECTED_LOCAL_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})
# Files whose code holds the production model literal. env.py is the env
# registry's documentation of the default (its value is asserted equal below).
EXPECTED_MODEL_LITERAL_FILES: frozenset[str] = frozenset(
    {"core/env.py", "core/llm/backend.py"}
)
MODEL_LITERAL = "gemma4:e4b"


def test_cli_commands_and_tiers() -> None:
    assert frozenset((c.name, c.tier.value) for c in COMMANDS) == EXPECTED_COMMANDS


def test_launchd_labels() -> None:
    labels = frozenset(
        value
        for name, value in vars(schedule).items()
        if name.startswith("LAUNCHD_") and name.endswith("_LABEL")
    )
    assert labels == EXPECTED_LAUNCHD_LABELS


def test_env_keys() -> None:
    assert frozenset(n for key in ENV_KEYS for n in key.names) == EXPECTED_ENV_KEYS


def test_prompt_stems() -> None:
    stems = frozenset(p.stem for p in (ROOT / "config" / "prompts").glob("*.md"))
    assert stems == EXPECTED_PROMPT_STEMS


def test_kit_version() -> None:
    assert KIT_VERSION == EXPECTED_KIT_VERSION


def test_outbound_hosts_are_two() -> None:
    assert ALLOWED_DOMAIN == EXPECTED_PLATFORM_HOST
    assert urlparse(DEFAULT_OLLAMA_URL).hostname in EXPECTED_LOCAL_HOSTS
    assert frozenset(LOCALHOST_HOSTS) == EXPECTED_LOCAL_HOSTS


def test_model_literal_lives_in_the_expected_files() -> None:
    holders: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(n, ast.Constant) and n.value == MODEL_LITERAL for n in ast.walk(tree)
        ):
            holders.add(path.relative_to(SRC).as_posix())
    assert holders == EXPECTED_MODEL_LITERAL_FILES
    assert DEFAULT_OLLAMA_MODEL == MODEL_LITERAL
    registry = {k.name: k for k in ENV_KEYS}["OLLAMA_MODEL"]
    assert registry.example == MODEL_LITERAL
