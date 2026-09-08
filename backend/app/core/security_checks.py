"""Making sure the app starts safely — not making sure it does not start.

`APP_SECRET_KEY` signs the JWT that says a user is logged in. Its default value
is in this repository, so an installation that never set it runs on a key
anybody can look up, and whoever holds that key writes themselves a valid admin
token. That is an open front door, not a blemish.

**What used to be here, and why that was wrong.** From v1.25.0 EMCargo
refused to start in that case. The reasoning — nobody reads a warning in a log
— was sound; the execution was not. This application's own defaults *are*
`APP_SECRET_KEY=change-me` and `CORS_ALLOWED_ORIGINS=*`, and the Unraid
template leaves the key blank. So every installation that had not filled in
those two by itself crashed on startup, in a container that exited too fast for
the message to be read. Security gained nothing: the app was simply gone.

A self-hosted application with its own data folder does not need to ask the
user about this either. It makes a key itself, keeps it next to its database
and uses it from then on. That is safer than what was there (random rather than
published), it costs the user nothing, and the key survives a restart because
it lives on the mounted volume.

What remains is reporting. CORS wide open, or an admin password taken from the
documentation, is worth saying out loud — but not worth bolting the door with
the user on the outside.
"""
from __future__ import annotations

import logging
import secrets
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

# Values that appear in this repository, in the documentation or in the
# examples. Everything in here is public and therefore not a secret.
PUBLISHED_SECRETS = {
    "change-me",
    "changeme",
    "dev-secret",
    "ci-secret",
    "secret",
    "cargopilot",
    "please-change",
    "your-secret-key",
    # Appears verbatim in .env.example and is long enough to slip past the
    # length check; whoever copies that file is not safe.
    "change-me-to-a-long-random-string",
}

# The same for the first admin password: this appears in docs/development.md
# and in AGENTS.md as an example.
PUBLISHED_ADMIN_PASSWORDS = {
    "cargopilot123",
    "admin",
    "password",
    "changeme",
    "change-me",
}

# Below this length an HS256 key is too short to be meaningful.
MINIMUM_SECRET_LENGTH = 32

DEVELOPMENT_ENVIRONMENTS = {"dev", "develop", "development", "local", "test", "testing"}

#: Next to the database, on the mounted data folder, so the key survives a
#: restart and a re-created container.
SECRET_KEY_FILENAME = "secret_key"


def is_production(app_env: str) -> bool:
    return str(app_env or "").strip().lower() not in DEVELOPMENT_ENVIRONMENTS


def suggested_secret() -> str:
    return secrets.token_urlsafe(48)


def is_usable_secret(secret: str) -> bool:
    """Can this sign a token that cannot be guessed or looked up?"""
    value = str(secret or "").strip()
    if value.lower() in PUBLISHED_SECRETS:
        return False
    return len(value) >= MINIMUM_SECRET_LENGTH


def _read_stored_secret(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _store_secret(path: Path, secret: str) -> bool:
    """Store the key, readable by the owner only. True when that worked."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secret + "\n", encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return True
    except OSError as error:
        # On Unraid /data is occasionally not writable. That must not hold up
        # startup; it only costs the key its durability.
        logger.warning("Could not store the key in %s: %s", path, error)
        return False


def ensure_secret_key(settings) -> str:
    """Supply a usable signing key, making one if that is what it takes.

    In order: what was configured, otherwise what was stored earlier, otherwise
    a new one. A configured value always wins when it is sound, so whoever
    manages their key deliberately stays in charge of it.
    """
    configured = str(settings.app_secret_key or "").strip()
    if is_usable_secret(configured):
        return configured

    path = Path(settings.data_dir) / SECRET_KEY_FILENAME
    stored = _read_stored_secret(path)
    if is_usable_secret(stored):
        logger.info(
            "APP_SECRET_KEY is not set; using the key stored in %s.", path
        )
        return stored

    generated = suggested_secret()
    if _store_secret(path, generated):
        logger.warning(
            "APP_SECRET_KEY was not set, or too short. A key has been generated "
            "and stored in %s. To manage it yourself, set APP_SECRET_KEY in the "
            "environment; that value takes precedence.",
            path,
        )
    else:
        logger.warning(
            "APP_SECRET_KEY was not set, or too short, and the generated key "
            "could not be stored. The app runs safely, but everybody has to log "
            "in again after a restart. Set APP_SECRET_KEY in the environment, or "
            "make %s writable.",
            path.parent,
        )
    return generated


def configuration_warnings(settings) -> list[str]:
    """What deserves attention apart from the key, in plain words.

    These are reports, not refusals. They say what is open and what can be done
    about it; the user decides whether that matters in their setup — behind a
    reverse proxy on a single domain, CORS is not in the picture.
    """
    if not is_production(settings.app_env):
        return []

    warnings: list[str] = []

    if settings.cors_allowed_origins.strip() == "*":
        warnings.append(
            "CORS_ALLOWED_ORIGINS is set to '*'. A wildcard is answered without "
            "credentials, so a call from another website cannot carry the login "
            "cookie — the interface served by this application is unaffected. "
            "Better to name the addresses you reach EMCargo on:"
            "\n    CORS_ALLOWED_ORIGINS=https://cargopilot.example.com"
        )

    password = str(settings.admin_password or "")
    if password and password.strip().lower() in PUBLISHED_ADMIN_PASSWORDS:
        warnings.append(
            "ADMIN_PASSWORD is set to a password that appears in this project's "
            "documentation. Pick one of your own, and change it after the first "
            "login."
        )

    return warnings


def apply_security_configuration(settings) -> list[str]:
    """Make the configuration safe enough to start with, and report the rest.

    Called while the application is being built, so before a single request can
    be answered. Returns the reports, so a test can read them without having to
    look in the log.
    """
    settings.app_secret_key = ensure_secret_key(settings)

    warnings = configuration_warnings(settings)
    for warning in warnings:
        logger.warning("Aandachtspunt in de configuratie: %s", warning)
    return warnings
