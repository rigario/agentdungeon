"""Tests for the DM profile wrapper module."""

import sys
import os
import json
import asyncio

# Add project roots to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dm-runtime"))

from app.services.dm_profile import get_status, narrate_via_direct


class TestDMProfileStatus:
    """Test the DM profile status reporting."""

    def test_status_returns_expected_keys(self):
        """Status dict should contain all expected keys."""
        status = get_status()
        assert "mode" in status
        assert "hermes_profile" in status
        assert "api_key_set" in status
        assert "base_url" in status
        assert "model" in status
        assert "timeout" in status
        assert "max_tokens" in status

    def test_status_mode_is_string(self):
        """Mode should be a string (direct or hermes)."""
        status = get_status()
        assert isinstance(status["mode"], str)
        assert status["mode"] in ("direct", "hermes")

    def test_status_hermes_profile_name(self):
        """Hermes profile should be d20-dm."""
        status = get_status()
        assert status["hermes_profile"] == "d20-dm"

    def test_status_model_is_kimi(self):
        """Default model should be kimi-k2.5."""
        status = get_status()
        assert "kimi" in status["model"].lower()


class TestDMProfileNarration:
    """Test the narration wrapper (no live API calls)."""

    def test_direct_returns_none_without_key(self):
        """Without API key, direct mode should return None."""
        # Temporarily unset key
        old_key = os.environ.get("KIMI_API_KEY", "")
        os.environ["KIMI_API_KEY"] = ""

        try:
            result = asyncio.run(narrate_via_direct(
                system_prompt="You are a DM.",
                user_prompt="A cave entrance.",
            ))
            assert result is None
        finally:
            os.environ["KIMI_API_KEY"] = old_key


class TestDMProfileHermesProfileConfig:
    """Test that the d20-dm Hermes profile exists and has correct config."""

    def test_d20_dm_profile_exists(self):
        """The d20-dm profile directory should exist."""
        profile_dir = os.path.expanduser("~/.hermes/profiles/d20-dm")
        assert os.path.isdir(profile_dir), f"Profile dir not found: {profile_dir}"

    def test_d20_dm_config_yaml_exists(self):
        """config.yaml should exist in the profile directory."""
        config_path = os.path.expanduser("~/.hermes/profiles/d20-dm/config.yaml")
        assert os.path.isfile(config_path), f"Config not found: {config_path}"

    def test_d20_dm_config_has_kimi_provider(self):
        """Config should reference kimi-coding as provider."""
        import yaml
        config_path = os.path.expanduser("~/.hermes/profiles/d20-dm/config.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert config["model"]["provider"] == "kimi-coding"
        assert "kimi" in config["model"]["default"].lower()

    def test_d20_dm_config_minimal_tools(self):
        """DM profile should have minimal toolsets (no terminals/browsers)."""
        import yaml
        config_path = os.path.expanduser("~/.hermes/profiles/d20-dm/config.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert config.get("browser", {}).get("enabled", True) is False
        assert config.get("checkpoints", {}).get("enabled", True) is False
        assert config.get("memory", {}).get("memory_enabled", True) is False

    def test_d20_dm_env_file_exists(self):
        """Environment file should exist."""
        env_path = os.path.expanduser("~/.hermes/profiles/d20-dm/.env")
        assert os.path.isfile(env_path), f"Env not found: {env_path}"
