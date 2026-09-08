"""The app has to start with the settings it is shipped with.

This is the test that was missing. From v1.25.0 to v1.29.2 CargoPilot refused to
start as soon as `APP_SECRET_KEY` was at its default value or empty, and as soon
as `CORS_ALLOWED_ORIGINS` was `*` — and those *are* this application's defaults,
plus what the Unraid template passes. Every installation that had not filled in
those two by itself fell over on startup.

The 500 tests that already existed did not find it. They all ran with
`APP_ENV=test`, which skips the check precisely, and not one of them built the
application the way a user starts it.

Hence this one: a genuinely separate process, with a clean environment, without
`.env`, and without a single setting a user would not also have. It deliberately
does not run inside the test process, because the environment is the subject here.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

BUILD_THE_APP = """
from app.main import create_app
from app.core.config import get_settings

create_app()
print("STARTED", get_settings().app_secret_key[:8])
"""


def start_with(env_dir: Path, **overrides) -> subprocess.CompletedProcess:
    """Build the application in a separate process, in an environment we know."""
    env_dir.mkdir(parents=True, exist_ok=True)
    env = {
        # A clean environment: only what a container has too. PATH and HOME stay
        # from the system — HOME points here at the user site where some of the
        # packages live, and taking that away would wreck Python itself instead
        # of putting the configuration to the test.
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(BACKEND),
        "DATA_DIR": str(env_dir),
        "DATABASE_URL": f"sqlite:///{env_dir}/cargopilot.db",
        # Without this, startup tries to fetch catalogues from the internet.
        "CATALOG_AUTO_SYNC": "false",
    }
    env.update({k: v for k, v in overrides.items() if v is not None})
    return subprocess.run(
        [sys.executable, "-c", BUILD_THE_APP],
        cwd=env_dir,  # not in the repo, so no .env comes along
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_the_app_starts_with_nothing_configured(tmp_path):
    """No APP_ENV, no APP_SECRET_KEY, no CORS — like somebody who switches the
    container on and fills in nothing further."""
    result = start_with(tmp_path)
    assert "STARTED" in result.stdout, result.stderr[-3000:]


def test_the_app_starts_the_way_the_unraid_template_configures_it(tmp_path):
    """The template in unraid/EMCargo.xml passes APP_SECRET_KEY empty."""
    result = start_with(tmp_path, APP_SECRET_KEY="")
    assert "STARTED" in result.stdout, result.stderr[-3000:]


def test_the_app_starts_on_the_published_default_secret(tmp_path):
    result = start_with(tmp_path, APP_SECRET_KEY="change-me")
    assert "STARTED" in result.stdout, result.stderr[-3000:]


def test_it_does_not_sign_with_the_published_key_it_was_given(tmp_path):
    """Starting is not enough — it had to be safe as well."""
    result = start_with(tmp_path, APP_SECRET_KEY="change-me")
    assert "STARTED" in result.stdout, result.stderr[-3000:]
    assert "STARTED change-me" not in result.stdout
    assert (tmp_path / "secret_key").exists()


def test_a_restart_keeps_everyone_logged_in(tmp_path):
    """A new key on every restart would throw everybody out."""
    first = start_with(tmp_path)
    second = start_with(tmp_path)
    assert "STARTED" in first.stdout and "STARTED" in second.stdout
    assert first.stdout.strip() == second.stdout.strip()


def test_a_key_of_your_own_is_the_one_that_is_used(tmp_path):
    own = "x" * 40
    result = start_with(tmp_path, APP_SECRET_KEY=own)
    assert f"STARTED {own[:8]}" in result.stdout, result.stderr[-3000:]


@pytest.mark.parametrize("app_env", ["production", "staging", "development"])
def test_it_starts_in_every_environment(app_env, tmp_path):
    result = start_with(tmp_path / app_env, APP_ENV=app_env)
    assert "STARTED" in result.stdout, result.stderr[-3000:]
