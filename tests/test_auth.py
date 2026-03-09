"""Tests for credential management."""

import json
from unittest.mock import patch

from contemplative_moltbook.adapters.moltbook.auth import (
    _mask_key,
    load_credentials,
    save_credentials,
)


class TestMaskKey:
    def test_long_key(self):
        assert _mask_key("abcdefghij") == "******ghij"

    def test_short_key(self):
        assert _mask_key("abc") == "****"

    def test_four_char_key(self):
        assert _mask_key("abcd") == "****"


class TestLoadCredentials:
    def test_env_var_priority(self, monkeypatch):
        monkeypatch.setenv("MOLTBOOK_API_KEY", "env-key-1234")
        result = load_credentials()
        assert result == "env-key-1234"

    def test_no_credentials(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MOLTBOOK_API_KEY", raising=False)
        with patch("contemplative_moltbook.adapters.moltbook.auth.CREDENTIALS_PATH", tmp_path / "nope.json"):
            result = load_credentials()
            assert result is None

    def test_file_credentials(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MOLTBOOK_API_KEY", raising=False)
        cred_file = tmp_path / "credentials.json"
        cred_file.write_text(json.dumps({"api_key": "file-key-5678"}))
        with patch("contemplative_moltbook.adapters.moltbook.auth.CREDENTIALS_PATH", cred_file):
            result = load_credentials()
            assert result == "file-key-5678"

    def test_malformed_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MOLTBOOK_API_KEY", raising=False)
        cred_file = tmp_path / "credentials.json"
        cred_file.write_text("not json")
        with patch("contemplative_moltbook.adapters.moltbook.auth.CREDENTIALS_PATH", cred_file):
            result = load_credentials()
            assert result is None


class TestSaveCredentials:
    def test_saves_with_permissions(self, tmp_path):
        cred_file = tmp_path / "config" / "moltbook" / "credentials.json"
        with patch("contemplative_moltbook.adapters.moltbook.auth.CREDENTIALS_PATH", cred_file):
            save_credentials("test-key-abcd", agent_id="agent-123")

        assert cred_file.exists()
        data = json.loads(cred_file.read_text())
        assert data["api_key"] == "test-key-abcd"
        assert data["agent_id"] == "agent-123"
        assert oct(cred_file.stat().st_mode)[-3:] == "600"

    def test_saves_without_agent_id(self, tmp_path):
        cred_file = tmp_path / "credentials.json"
        with patch("contemplative_moltbook.adapters.moltbook.auth.CREDENTIALS_PATH", cred_file):
            save_credentials("test-key-only")

        data = json.loads(cred_file.read_text())
        assert data["api_key"] == "test-key-only"
        assert "agent_id" not in data
