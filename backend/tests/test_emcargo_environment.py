"""The renamed environment variables must preserve the open-mode privacy boundary.

An operator following the EMCargo documentation must actually get open mode;
legacy deployment variables and constructor calls must keep working as well.
"""
from app.core.config import Settings


def test_new_environment_names_take_precedence(monkeypatch):
    monkeypatch.setenv("EMCARGO_MODE", "open")
    monkeypatch.setenv("CARGOPILOT_MODE", "organisation")
    monkeypatch.setenv("EMCARGO_HISTORY", "true")
    monkeypatch.setenv("CARGOPILOT_HISTORY", "false")
    settings = Settings(_env_file=None)
    assert settings.is_open
    assert settings.cargopilot_history is True


def test_existing_deployments_keep_their_configuration(monkeypatch):
    monkeypatch.delenv("EMCARGO_MODE", raising=False)
    monkeypatch.delenv("EMCARGO_HISTORY", raising=False)
    monkeypatch.setenv("CARGOPILOT_MODE", "open")
    settings = Settings(_env_file=None)
    assert settings.is_open
    monkeypatch.delenv("CARGOPILOT_MODE")
    assert Settings(_env_file=None, cargopilot_mode="organisation").mode == "organisation"
