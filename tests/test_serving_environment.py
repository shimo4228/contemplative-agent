"""``core.llm.serving_environment()`` — weight digests + Ollama build for the
session-start episode and the pivot-snapshot manifest (ADR-0069 addendum
2026-09-06). Model names are mutable tags; only the digest pins the weights."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from contemplative_agent.core import llm as llm_module
from contemplative_agent.core.llm import configure, reset_llm_config, serving_environment

GEN_DIGEST = "a1" * 32  # synthetic: shape of an Ollama sha256 digest
EMB_DIGEST = "b2" * 32

TAGS = {
    "models": [
        {"name": "gemma4:e4b", "digest": GEN_DIGEST},
        {"name": "nomic-embed-text:latest", "digest": EMB_DIGEST},
        {
            "name": "bge-m3:latest",
            "digest": "c3" * 32,
        },
    ]
}


def _resp(payload: object) -> MagicMock:
    m = MagicMock()
    m.json.return_value = payload
    return m


def _ollama_get(url: str, **_kw: object) -> MagicMock:
    if url.endswith("/api/version"):
        return _resp({"version": "0.30.11"})
    if url.endswith("/api/tags"):
        return _resp(TAGS)
    raise AssertionError(f"unexpected GET {url}")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:e4b")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    reset_llm_config()
    yield
    reset_llm_config()


class TestServingEnvironment:
    @patch("contemplative_agent.core.llm.requests.get", side_effect=_ollama_get)
    def test_records_version_and_12_hex_digests(self, _get):
        env = serving_environment()
        assert env == {
            "ollama_version": "0.30.11",
            "generation_model_digest": GEN_DIGEST[:12],
            "embedding_model_digest": EMB_DIGEST[:12],
            "serving_environment_reason": "ok",
        }

    @patch("contemplative_agent.core.llm.requests.get", side_effect=_ollama_get)
    def test_bare_embedding_name_matches_latest_tag(self, _get):
        # Config says ``nomic-embed-text``; /api/tags lists ``nomic-embed-text:latest``.
        assert serving_environment()["embedding_model_digest"] == EMB_DIGEST[:12]

    @patch(
        "contemplative_agent.core.llm.requests.get", side_effect=requests.ConnectionError("down")
    )
    def test_unreachable_gives_all_none_with_reason(self, _get):
        env = serving_environment()
        assert env["ollama_version"] is None
        assert env["generation_model_digest"] is None
        assert env["embedding_model_digest"] is None
        assert env["serving_environment_reason"] == "ollama_unreachable"

    @patch("contemplative_agent.core.llm.requests.get", side_effect=_ollama_get)
    def test_unlisted_model_is_named_in_reason(self, _get, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
        env = serving_environment()
        assert env["generation_model_digest"] is None
        assert env["serving_environment_reason"] == "model_not_listed:qwen3:4b"
        assert env["embedding_model_digest"] == EMB_DIGEST[:12]

    @patch("contemplative_agent.core.llm.requests.get", side_effect=_ollama_get)
    def test_injected_backend_skips_generation_digest_but_keeps_embedding(self, _get):
        backend = MagicMock()
        backend.model = "claude-opus-5"
        configure(backend=backend)
        env = serving_environment()
        assert env["generation_model_digest"] is None
        assert env["embedding_model_digest"] == EMB_DIGEST[:12]
        assert env["serving_environment_reason"] == "backend_injected"

    @patch("contemplative_agent.core.llm.requests.get", side_effect=_ollama_get)
    def test_asks_ollama_once_per_process_and_reset_clears(self, get):
        first = serving_environment()
        second = serving_environment()
        assert first == second
        assert get.call_count == 2  # version + tags, once
        second["ollama_version"] = "mutated"
        assert serving_environment()["ollama_version"] == "0.30.11"  # copy, not the cache
        reset_llm_config()
        assert llm_module._serving_env is None
        serving_environment()
        assert get.call_count == 4

    @patch("contemplative_agent.core.llm.requests.get")
    def test_malformed_body_is_its_own_reason_and_never_raises(self, get):
        # Reachable daemon, garbage bodies: not "unreachable", and the
        # non-iterable ``models`` (a TypeError path) must degrade, not raise.
        get.side_effect = lambda url, **kw: _resp("not-a-dict")
        assert serving_environment()["serving_environment_reason"] == "ollama_malformed_response"
        reset_llm_config()
        get.side_effect = lambda url, **kw: _resp({"models": 5, "version": 7})
        env = serving_environment()
        assert env["ollama_version"] is None
        assert env["serving_environment_reason"] == "ollama_malformed_response"

    @patch("contemplative_agent.core.llm.requests.get")
    def test_version_ok_but_tags_down_keeps_version_and_says_unreachable(self, get):
        def flaky(url, **kw):
            if url.endswith("/api/version"):
                return _resp({"version": "0.30.11"})
            raise requests.ConnectionError("tags down")

        get.side_effect = flaky
        env = serving_environment()
        # Two sequential calls: version cannot be trusted as "this run's" once
        # tags failed mid-way, so the whole read is reported unreachable.
        assert env["ollama_version"] is None
        assert env["generation_model_digest"] is None
        assert env["serving_environment_reason"] == "ollama_unreachable"

    @patch("contemplative_agent.core.llm.requests.get", side_effect=_ollama_get)
    def test_configure_invalidates_cache(self, _get):
        assert serving_environment()["generation_model_digest"] == GEN_DIGEST[:12]
        backend = MagicMock()
        backend.model = "claude-opus-5"
        configure(backend=backend)
        assert serving_environment()["serving_environment_reason"] == "backend_injected"

    @patch("contemplative_agent.core.llm.requests.get", side_effect=_ollama_get)
    def test_does_not_follow_redirects(self, get):
        serving_environment()
        for call in get.call_args_list:
            assert call.kwargs["allow_redirects"] is False
