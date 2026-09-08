"""The open application: anyone may use it, nothing is kept about anyone.

``CARGOPILOT_MODE=open`` is not a switch inside the organisation application;
it is a second application in the same image. The difference is enforced by
what is *mounted*, not by what is refused: the sign-in, the users page, the
settings screen, the equipment library, mail and the administrator's
maintenance do not exist there and answer 404 like any other address that
does not exist. These tests pin that route by route, because a promise made
in a README and kept by nothing is the kind that quietly stops being true.

Two things the tests check that are easy to get wrong:

- **A saved administrator overlay is ignored.** A database that used to serve
  the organisation application may hold a settings row with a mail server in
  it. The open application has no screen that could ever change that row, so
  honouring it would let a setting nobody can see govern a public site.
- **A typo is the closed application.** ``CARGOPILOT_MODE=opne`` must not open
  anything. It runs as the organisation application and says so.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tests import route_table
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import deps
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.startup import bootstrap_admin
from app.main import create_app
from app.models.user import User
from app.schemas.settings import InstanceSettings
from app.services import settings_store

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """A database of its own, and the settings cache cleared on both sides."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{data_dir / 'test.db'}")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CATALOG_AUTO_SYNC", "false")
    engine = create_engine(f"sqlite:///{data_dir / 'test.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    get_settings.cache_clear()
    yield session
    session.close()
    get_settings.cache_clear()


def application(mode: str | None, monkeypatch, db) -> TestClient:
    if mode is None:
        monkeypatch.delenv("CARGOPILOT_MODE", raising=False)
    else:
        monkeypatch.setenv("CARGOPILOT_MODE", mode)
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


@pytest.fixture
def open_client(fresh, monkeypatch):
    with application("open", monkeypatch, fresh) as client:
        yield client


@pytest.fixture
def organisation_client(fresh, monkeypatch):
    with application(None, monkeypatch, fresh) as client:
        yield client


#: The addresses that presume an account. Every one of them must be absent
#: from the open application — not forbidden, absent.
ACCOUNT_ROUTES = [
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/forgot-password"),
    ("GET", "/api/auth/two-factor"),
    ("GET", "/api/users"),
    ("GET", "/api/audit"),
    ("GET", "/api/audit/actions"),
    ("GET", "/api/audit/export.csv"),
    ("GET", "/api/settings/me"),
    ("GET", "/api/settings/instance"),
    ("POST", "/api/settings/instance/mail-test"),
    ("GET", "/api/equipment"),
    ("POST", "/api/documents/export/bundle/mail"),
    ("GET", "/api/un-cards/status"),
    ("POST", "/api/assistant/model"),
    ("GET", "/api/changelog"),
    ("GET", "/api/update-status"),
    ("POST", "/api/update-apply"),
]


# --- what does not exist ----------------------------------------------------


@pytest.mark.parametrize("method,path", ACCOUNT_ROUTES)
def test_the_open_application_has_no_account_routes(open_client, method, path):
    response = open_client.request(method, path, json={})
    assert response.status_code == 404, (method, path, response.status_code)


@pytest.mark.parametrize("method,path", ACCOUNT_ROUTES)
def test_the_organisation_application_still_has_them(organisation_client, method, path):
    """The other direction: nothing from the account side went missing in
    the split. Unauthenticated, so 401 or 422 — anything but 404."""
    response = organisation_client.request(method, path, json={})
    assert response.status_code != 404, (method, path)


def test_the_route_table_itself_carries_nothing_account_bound(fresh, monkeypatch):
    """Structural, so it does not depend on which addresses the list above
    happens to name: no mounted path may start with an account prefix."""
    monkeypatch.setenv("CARGOPILOT_MODE", "open")
    get_settings.cache_clear()
    app = create_app()
    paths = route_table.paths(app)
    forbidden = ("/api/auth", "/api/users", "/api/equipment", "/api/settings/me",
                 "/api/settings/instance", "/api/un-cards", "/api/changelog",
                 "/api/update", "/api/assistant/model",
                 "/api/documents/export/bundle/mail")
    leaked = sorted(p for p in paths if p.startswith(forbidden))
    assert leaked == []


# --- what does exist, and for whom ------------------------------------------


def test_the_work_needs_no_cookie_in_the_open_application(open_client):
    response = open_client.post("/api/calculate", json={
        "lines": [{"quantity": 2, "weight_total_kg": 10.0}]})
    assert response.status_code == 200
    assert response.json()["totals"]["total_weight_kg"] == 10.0


def test_the_same_call_still_wants_a_cookie_in_the_organisation_application(
        organisation_client):
    response = organisation_client.post("/api/calculate", json={
        "lines": [{"quantity": 2, "weight_total_kg": 10.0}]})
    assert response.status_code == 401


def test_the_interface_can_still_draw_itself(open_client):
    """The public facts and the option lists answer a visitor: the settings
    screen needs the language list, the wizard needs to know whether address
    lookup will answer and whether UN cards are on."""
    assert open_client.get("/api/settings/options").status_code == 200
    public = open_client.get("/api/settings/public")
    assert public.status_code == 200
    assert "address_lookup_enabled" in public.json()


def test_health_says_which_application_this_is(open_client, organisation_client):
    assert open_client.get("/api/health").json()["mode"] == "open"
    assert organisation_client.get("/api/health").json()["mode"] == "organisation"


def test_the_visitor_is_nobody_and_never_an_administrator():
    somebody = deps.visitor()
    assert somebody.username == ""
    assert somebody.role == "user"
    with pytest.raises(Exception):
        deps.require_admin(somebody)


# --- mail: not guarded, absent ----------------------------------------------


def test_no_mail_whatever_the_environment_says(fresh, monkeypatch):
    """``SMTP_*`` in the environment of an open installation configures
    nothing. The send action does not exist, so the public facts say mail is
    off and the effective settings carry no server at all."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "cargopilot@example.com")
    with application("open", monkeypatch, fresh) as client:
        assert client.get("/api/settings/public").json()["mail_enabled"] is False
        effective = settings_store.instance_settings(fresh)
        assert effective.mail_enabled is False
        assert effective.mail_host == ""


def test_the_same_environment_does_configure_the_organisation_application(
        fresh, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "cargopilot@example.com")
    with application(None, monkeypatch, fresh):
        effective = settings_store.instance_settings(fresh)
        assert effective.mail_enabled is True
        assert effective.mail_host == "smtp.example.com"


# --- the environment is the whole configuration -----------------------------


def test_a_saved_administrator_overlay_is_ignored(fresh, monkeypatch):
    """A row left by the organisation application: a mail server and the QR
    door open. The open application reads neither."""
    settings_store.save_instance_settings(fresh, InstanceSettings(
        card_links_enabled=True, mail_enabled=True,
        mail_host="smtp.example.com", mail_from="x@example.com"))
    with application("open", monkeypatch, fresh) as client:
        effective = settings_store.instance_settings(fresh)
        assert effective.card_links_enabled is False
        assert effective.mail_enabled is False
        # And the door really is shut: 404, as for any installation that has
        # not opened it.
        assert client.get("/api/cards/lookup?un=1203").status_code == 404


def test_the_environment_opens_the_qr_door(fresh, monkeypatch):
    monkeypatch.setenv("CARD_LINKS_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_URL", "https://cargopilot.example.org/")
    with application("open", monkeypatch, fresh) as client:
        response = client.get("/api/cards/lookup?un=1203")
        assert response.status_code == 200
        assert response.json()["cards"][0]["un_number"] == "1203"
        assert settings_store.instance_settings(fresh).public_url == \
            "https://cargopilot.example.org"


@pytest.mark.parametrize("variable,value,field,expected", [
    ("DEFAULT_LANGUAGE", "de", "default_language", "de"),
    ("DEFAULT_LANGUAGE", "klingon", "default_language", "nl"),
    ("DEFAULT_THEME", "dark", "default_theme", "dark"),
    ("DEFAULT_THEME", "sepia", "default_theme", "system"),
    ("ADDRESS_LOOKUP_ENABLED", "false", "address_lookup_enabled", False),
    ("UN_CARDS_ENABLED", "false", "un_cards_enabled", False),
    ("PUBLIC_URL", "not-an-address", "public_url", ""),
])
def test_the_screen_switches_have_environment_names(
        fresh, monkeypatch, variable, value, field, expected):
    """And a typo in any of them falls back rather than failing: these are
    read on every request, and a raise would take the application down."""
    monkeypatch.setenv(variable, value)
    with application("open", monkeypatch, fresh):
        assert getattr(settings_store.instance_settings(fresh), field) == expected


def test_the_environment_is_also_the_starting_point_for_the_organisation(
        fresh, monkeypatch):
    """Same variables, same meaning, in the closed application — where a
    saved setting still wins over them, as it always has."""
    monkeypatch.setenv("UN_CARDS_ENABLED", "false")
    with application(None, monkeypatch, fresh):
        assert settings_store.instance_settings(fresh).un_cards_enabled is False
        settings_store.save_instance_settings(fresh, InstanceSettings(un_cards_enabled=True))
        assert settings_store.instance_settings(fresh).un_cards_enabled is True


# --- starting up ------------------------------------------------------------


def test_no_administrator_is_made_and_none_is_missed(fresh, monkeypatch, caplog):
    monkeypatch.setenv("CARGOPILOT_MODE", "open")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-perfectly-good-password")
    get_settings.cache_clear()
    with caplog.at_level(logging.WARNING):
        assert bootstrap_admin(fresh) is False
    assert fresh.query(User).count() == 0
    assert "No admin exists" not in caplog.text


def test_accounts_left_behind_are_reported_but_not_deleted(fresh, monkeypatch, caplog):
    fresh.add(User(username="ada", email="ada@example.com", password_hash="x",
                   role="admin", active=True))
    fresh.commit()
    monkeypatch.setenv("CARGOPILOT_MODE", "open")
    get_settings.cache_clear()
    with caplog.at_level(logging.WARNING):
        bootstrap_admin(fresh)
    assert "1 account(s)" in caplog.text
    assert fresh.query(User).count() == 1


def test_a_typo_is_the_closed_application(fresh, monkeypatch):
    with application("opne", monkeypatch, fresh) as client:
        assert client.get("/api/health").json()["mode"] == "organisation"
        assert client.get("/api/auth/me").status_code == 401


def test_unset_is_the_closed_application(organisation_client):
    assert organisation_client.get("/api/health").json()["mode"] == "organisation"


# --- what the documentation promises ----------------------------------------


def test_the_privacy_page_says_what_open_means():
    """The promise has to be checkable. The health line says which
    application answers; this is the paragraph a visitor reads to know what
    that means, and it has to exist and name the variable."""
    text = (ROOT / "docs" / "privacy.md").read_text(encoding="utf-8")
    assert "EMCARGO_MODE" in text
    assert "## Two applications" in text


def test_the_configuration_page_lists_the_mode():
    text = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    assert "`EMCARGO_MODE`" in text
