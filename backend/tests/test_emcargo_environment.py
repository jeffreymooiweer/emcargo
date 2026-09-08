"""Retired deployment flags cannot restore anonymous application access."""
from app.core.config import Settings


def test_history_configuration_survives_a_retired_mode_variable(monkeypatch):
    monkeypatch.setenv("EMCARGO_MODE", "open")
    monkeypatch.setenv("EMCARGO_HISTORY", "true")
    settings = Settings(_env_file=None)
    assert settings.emcargo_history is True
    assert "emcargo_mode" not in Settings.model_fields


def test_constructor_does_not_accept_a_guest_access_switch():
    settings = Settings(_env_file=None, emcargo_mode="open")
    assert not hasattr(settings, "is_open")
