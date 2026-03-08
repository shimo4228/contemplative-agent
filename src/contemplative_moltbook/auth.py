"""Credential management for Moltbook API."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Optional

from .config import CREDENTIALS_PATH

if TYPE_CHECKING:
    from .client import MoltbookClient

logger = logging.getLogger(__name__)


def _mask_key(key: str) -> str:
    """Show only last 4 characters of an API key."""
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


def load_credentials() -> Optional[str]:
    """Load API key from environment variable or credentials file.

    Priority: MOLTBOOK_API_KEY env var > credentials file.
    Returns None if no credentials found.
    """
    env_key = os.environ.get("MOLTBOOK_API_KEY")
    if env_key:
        logger.info("Using API key from environment (%s)", _mask_key(env_key))
        return env_key

    if CREDENTIALS_PATH.exists():
        try:
            data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
            file_key = data.get("api_key", "")
            if file_key:
                logger.info(
                    "Using API key from %s (%s)",
                    CREDENTIALS_PATH,
                    _mask_key(file_key),
                )
                return file_key
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to read credentials file: %s", exc)

    return None


def save_credentials(api_key: str, agent_id: Optional[str] = None) -> None:
    """Save API key to credentials file with restricted permissions."""
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)

    data = {"api_key": api_key}
    if agent_id:
        data["agent_id"] = agent_id

    CREDENTIALS_PATH.write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    CREDENTIALS_PATH.chmod(0o600)
    logger.info(
        "Credentials saved to %s (%s)",
        CREDENTIALS_PATH,
        _mask_key(api_key),
    )


def register_agent(client: MoltbookClient) -> dict:
    """Register a new agent on Moltbook.

    Returns the registration response containing agent_id and claim_url.
    """
    payload = {
        "name": "contemplative-agent",
        "description": (
            "An AI agent exploring contemplative alignment -- "
            "mindfulness, emptiness, non-duality, and boundless care. "
            "Based on Laukkonen et al. (2025)."
        ),
    }
    response = client.post("/agents/register", json=payload)
    result = response.json()

    # API may return keys at top level or nested under "agent"
    agent_data = result.get("agent", result)
    api_key = agent_data.get("api_key")
    agent_id = agent_data.get("id") or agent_data.get("agent_id")

    if api_key:
        save_credentials(api_key, agent_id=agent_id)
        logger.info("Agent registered. ID: %s", agent_id)

    return result


def check_claim_status(client: MoltbookClient) -> dict:
    """Check the current agent's claim/verification status."""
    response = client.get("/agents/status")
    return response.json()
