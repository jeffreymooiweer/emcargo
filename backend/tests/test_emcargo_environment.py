"""Documented EMCargo variables must select the intended privacy mode."""
from app.core.config import Settings


def test_emcargo_environment_selects_open_mode(monkeypatch):
    monkeypatch.setenv("EMCARGO_MODE", "open")
    monkeypatch.setenv("EMCARGO_HISTORY", "true")
    settings = Settings(_env_file=None)
    assert settings.is_open
    assert settings.emcargo_history is True


def test_constructor_configuration_still_works(monkeypatch):
    monkeypatch.delenv("EMCARGO_MODE", raising=False)
    monkeypatch.delenv("EMCARGO_HISTORY", raising=False)
    assert Settings(_env_file=None, emcargo_mode="open").is_open
    assert Settings(_env_file=None).mode == "organisation"
