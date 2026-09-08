"""The app should start safely, not refuse to start.

`APP_SECRET_KEY` signs the JWT that says somebody is logged in, and the default
value `change-me` is in this repository. An installation that never set it
therefore runs on a key anybody can look up, and whoever holds the key writes
themselves a valid admin token.

From v1.25.0 to v1.29.2 EMCargo solved that by refusing to start. That was
wrong, and the proof is in the application's own defaults: `APP_SECRET_KEY=
change-me` and `CORS_ALLOWED_ORIGINS=*`, plus an Unraid template that leaves the
key blank. Every installation that had not filled in those two by itself crashed
on startup, in a container that exited too fast for the message to be readable.
Nothing became safer — the app was gone.

These tests record the behaviour that *should* be there: an app with its own data
folder makes a key itself, stores it, and starts. And it keeps its hands off a
key the administrator set themselves.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.core.security_checks import (
    MINIMUM_SECRET_LENGTH,
    PUBLISHED_SECRETS,
    SECRET_KEY_FILENAME,
    apply_security_configuration,
    configuration_warnings,
    ensure_secret_key,
    is_production,
    is_usable_secret,
    suggested_secret,
)


@dataclass
class FakeSettings:
    """Enough of Settings to feed the check, without .env or the environment."""

    data_dir: Path = Path("/nonexistent")
    app_env: str = "production"
    app_secret_key: str = field(default_factory=suggested_secret)
    cors_allowed_origins: str = "https://emcargo.example.com"
    admin_password: str | None = None


@pytest.fixture
def settings(tmp_path):
    return FakeSettings(data_dir=tmp_path)


# --- Where it went wrong: the app has to start ----------------------------


def test_the_shipped_defaults_start_instead_of_crashing(tmp_path):
    """Exactly the configuration EMCargo comes out of the box with, and the
    one every Unraid installation fell over on since v1.25.0."""
    out_of_the_box = FakeSettings(
        data_dir=tmp_path, app_secret_key="change-me", cors_allowed_origins="*"
    )
    apply_security_configuration(out_of_the_box)  # no exception
    assert is_usable_secret(out_of_the_box.app_secret_key)


def test_an_empty_secret_starts_too(tmp_path):
    """The Unraid template passes APP_SECRET_KEY with an empty value."""
    blank = FakeSettings(data_dir=tmp_path, app_secret_key="")
    apply_security_configuration(blank)
    assert is_usable_secret(blank.app_secret_key)


def test_the_generated_key_is_stored_next_to_the_database(tmp_path):
    settings = FakeSettings(data_dir=tmp_path, app_secret_key="change-me")
    key = ensure_secret_key(settings)
    stored = (tmp_path / SECRET_KEY_FILENAME).read_text(encoding="utf-8").strip()
    assert stored == key


def test_the_same_key_comes_back_after_a_restart(tmp_path):
    """Otherwise everybody was logged out after every restart of the container."""
    first = ensure_secret_key(FakeSettings(data_dir=tmp_path, app_secret_key="change-me"))
    second = ensure_secret_key(FakeSettings(data_dir=tmp_path, app_secret_key="change-me"))
    assert first == second


def test_the_stored_key_is_not_readable_for_others(tmp_path):
    ensure_secret_key(FakeSettings(data_dir=tmp_path, app_secret_key="change-me"))
    mode = (tmp_path / SECRET_KEY_FILENAME).stat().st_mode
    assert mode & 0o077 == 0, oct(mode)


def test_a_data_directory_that_cannot_be_written_still_starts(tmp_path, caplog):
    """On Unraid /data is occasionally not writable. That must not hold up
    startup; it only costs the key its survival across a restart.

    The folder is made unusable here by putting a file where the parent folder
    should be. Taking permissions away does not work: the tests often run as
    root, and then a folder without write permission is still writable.
    """
    blocked = tmp_path / "afile" / "data"
    (tmp_path / "afile").write_text("geen map", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        key = ensure_secret_key(FakeSettings(data_dir=blocked, app_secret_key=""))

    assert is_usable_secret(key), "the app should simply keep running"
    assert "log in again after a restart" in caplog.text


# --- And it keeps its hands off a key of your own -------------------------


def test_a_key_the_administrator_set_is_left_alone(tmp_path):
    own = suggested_secret()
    settings = FakeSettings(data_dir=tmp_path, app_secret_key=own)
    apply_security_configuration(settings)
    assert settings.app_secret_key == own
    assert not (tmp_path / SECRET_KEY_FILENAME).exists(), "niets te bewaren"


def test_a_configured_key_wins_over_a_stored_one(tmp_path):
    """Whoever deliberately puts their key in the environment wants it to apply —
    including when one was made earlier."""
    ensure_secret_key(FakeSettings(data_dir=tmp_path, app_secret_key=""))
    own = suggested_secret()
    assert ensure_secret_key(FakeSettings(data_dir=tmp_path, app_secret_key=own)) == own


@pytest.mark.parametrize("published", sorted(PUBLISHED_SECRETS))
def test_no_published_value_survives_as_a_key(published, tmp_path):
    """The long one from .env.example too, which slips past a pure length check."""
    settings = FakeSettings(data_dir=tmp_path, app_secret_key=published)
    apply_security_configuration(settings)
    assert settings.app_secret_key != published


def test_a_key_that_is_too_short_is_replaced(tmp_path):
    settings = FakeSettings(data_dir=tmp_path, app_secret_key="kort")
    apply_security_configuration(settings)
    assert len(settings.app_secret_key) >= MINIMUM_SECRET_LENGTH


def test_a_generated_key_is_long_enough_and_different_every_time():
    first, second = suggested_secret(), suggested_secret()
    assert first != second
    assert len(first) >= MINIMUM_SECRET_LENGTH


@pytest.mark.parametrize("value,usable", [
    (suggested_secret(), True),
    ("change-me", False),
    ("CHANGE-ME", False),
    ("  change-me  ", False),
    ("change-me-to-a-long-random-string", False),
    ("", False),
    (None, False),
    ("x" * (MINIMUM_SECRET_LENGTH - 1), False),
    ("x" * MINIMUM_SECRET_LENGTH, True),
])
def test_what_counts_as_a_usable_key(value, usable):
    assert is_usable_secret(value) is usable


# --- What is still reported -----------------------------------------------


def test_a_wildcard_origin_is_answered_without_credentials(tmp_path, monkeypatch):
    """"*" with credentials made Starlette reflect whatever origin asked,
    cookie and all — the one combination CORS exists to forbid. Since
    v1.190.0 the wildcard is anonymous and a named origin keeps the cookie."""
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{data_dir / 'test.db'}")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CATALOG_AUTO_SYNC", "false")
    preflight = {"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    try:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
        get_settings.cache_clear()
        with TestClient(create_app()) as client:
            answer = client.options("/api/auth/me", headers=preflight)
        assert answer.headers.get("access-control-allow-origin") == "*"
        assert "access-control-allow-credentials" not in answer.headers

        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://emcargo.example.com")
        get_settings.cache_clear()
        with TestClient(create_app()) as client:
            stranger = client.options("/api/auth/me", headers=preflight)
            friend = client.options("/api/auth/me", headers={
                **preflight, "Origin": "https://emcargo.example.com"})
        assert "access-control-allow-origin" not in stranger.headers
        assert friend.headers.get("access-control-allow-origin") == "https://emcargo.example.com"
        assert friend.headers.get("access-control-allow-credentials") == "true"
    finally:
        get_settings.cache_clear()


def test_wide_open_cors_is_reported_but_does_not_stop_anything(settings):
    settings.cors_allowed_origins = "*"
    warnings = apply_security_configuration(settings)
    assert any("CORS_ALLOWED_ORIGINS" in w for w in warnings)


def test_a_documented_admin_password_is_reported(settings):
    settings.admin_password = "emcargo123"
    assert any("ADMIN_PASSWORD" in w for w in configuration_warnings(settings))


def test_a_password_of_your_own_is_not_reported(settings):
    settings.admin_password = "een-eigen-wachtwoord-dat-nergens-staat"
    assert configuration_warnings(settings) == []


def test_the_warnings_reach_the_log(settings, caplog):
    settings.cors_allowed_origins = "*"
    with caplog.at_level(logging.WARNING):
        apply_security_configuration(settings)
    assert "CORS_ALLOWED_ORIGINS" in caplog.text


def test_a_warning_says_what_to_do_about_it(settings):
    settings.cors_allowed_origins = "*"
    assert "CORS_ALLOWED_ORIGINS=https://" in configuration_warnings(settings)[0]


# --- In production only ---------------------------------------------------


@pytest.mark.parametrize("env", ["development", "dev", "local", "test", "testing", "DEV"])
def test_development_is_not_nagged(env, settings):
    settings.app_env = env
    settings.cors_allowed_origins = "*"
    settings.admin_password = "emcargo123"
    assert configuration_warnings(settings) == []
    assert not is_production(env)


@pytest.mark.parametrize("env", ["production", "prod", "", None, "staging"])
def test_anything_that_is_not_clearly_development_counts_as_production(env):
    assert is_production(env)


def test_development_still_gets_a_usable_key(tmp_path):
    """In development the app must not sign on a published key either; there it
    is simply no reason to report anything."""
    settings = FakeSettings(data_dir=tmp_path, app_env="development", app_secret_key="change-me")
    apply_security_configuration(settings)
    assert is_usable_secret(settings.app_secret_key)
