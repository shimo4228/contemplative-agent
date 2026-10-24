"""Credential management for Moltbook API."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from ...core._io import write_restricted
from ...core.env import env_get
from .client import MoltbookClientError
from .config import CREDENTIALS_PATH

if TYPE_CHECKING:
    import requests

    from .client import MoltbookClient

logger = logging.getLogger(__name__)


def _mask_key(key: str) -> str:
    """Show only last 4 characters of an API key."""
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


def load_credentials() -> str | None:
    """Load API key from environment variable or credentials file.

    Priority: MOLTBOOK_API_KEY env var > credentials file.
    Returns None if no credentials found.
    """
    env_key = env_get("MOLTBOOK_API_KEY")
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


def save_credentials(api_key: str, agent_id: str | None = None) -> None:
    """Save API key to credentials file with restricted permissions.

    Uses ``write_restricted`` (unique temp file in the target directory +
    ``os.replace``, mode pinned to exactly 0600 with ``fchmod`` on the temp fd
    rather than a process-wide umask), so credentials are never observable
    world-readable nor partially written.
    """
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)

    data = {"api_key": api_key}
    if agent_id:
        data["agent_id"] = agent_id

    content = json.dumps(data, indent=2) + "\n"
    write_restricted(CREDENTIALS_PATH, content)
    logger.info(
        "Credentials saved to %s (%s)",
        CREDENTIALS_PATH,
        _mask_key(api_key),
    )


def _json_object(response: requests.Response, what: str) -> dict:
    """The JSON object in *response*, or an explicit ``MoltbookClientError``.

    A 2xx whose body is not JSON (a maintenance page) used to escape as a bare
    ``ValueError`` from ``response.json()``; it is now a named client error, so
    callers see one exception family for every way the platform can fail.
    """
    try:
        body = response.json()
    except ValueError as exc:
        raise MoltbookClientError(
            f"Moltbook {what} response is not JSON (HTTP {response.status_code})"
        ) from exc
    if not isinstance(body, dict):
        raise MoltbookClientError(
            f"Moltbook {what} response is {type(body).__name__}, expected an object"
        )
    return body


def register_agent(client: MoltbookClient, name: str) -> dict:
    """Register a new agent on Moltbook under ``name``.

    The name is the operator's choice. A built-in default would ask every
    operator for the live instance's own name, "contemplative-agent".

    Returns the registration response containing agent_id and claim_url.
    """
    name = name.strip()
    if not name:
        raise ValueError("register_agent: name must not be blank")
    payload = {
        "name": name,
        "description": (
            "An AI agent exploring contemplative alignment -- "
            "mindfulness, emptiness, non-duality, and boundless care. "
            "Based on Laukkonen et al. (2025)."
        ),
    }
    response = client.post("/agents/register", json=payload)
    result = _json_object(response, "registration")

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
    return _json_object(response, "claim status")
