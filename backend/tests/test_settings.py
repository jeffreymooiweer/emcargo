"""Settings that are actually settings, and not just a screen full of switches.

Three defects are pinned here, each of which this feature could plausibly have
shipped with.

1. **A column-per-setting schema.** This application has no migration runner:
   ``init_app`` calls ``Base.metadata.create_all``, which creates missing tables
   but never adds a column to an existing one. A settings model with a column per
   preference works perfectly on a fresh install and breaks every upgrade with
   "no such column". The JSON payload is the fix, and the test below reads a
   payload written by a hypothetical older version to prove an unknown-to-old /
   missing-in-new key is survivable in both directions.

2. **Environment variables silently overruled.** ``GEO_ADDRESS_API_URL`` and
   friends were the only way to configure EMCargo until v1.45.0 and are
   documented as such. If the stored settings had simply carried their own
   hard-coded defaults, upgrading would have changed the behaviour of every
   installation that had configured them. A stored setting is an overlay.

3. **Decorative switches.** A toggle that saves but changes nothing is worse
   than no toggle: the administrator believes address lookups are off. Every
   instance setting is therefore checked through the endpoint it governs, not
   only through the store.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.deps import get_current_user, require_admin
from app.core.security import hash_password
from app.main import app
from app.models.settings import InstanceSetting, UserPreference
from app.models.user import User
from app.schemas.settings import InstanceSettings, UserPreferences
from app.services import settings_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1, username="ada", email="ada@example.com", password_hash="x", role="admin"))
    session.add(User(id=2, username="bob", email="bob@example.com", password_hash="x", role="user"))
    session.commit()
    yield session
    session.close()
    get_settings.cache_clear()


@pytest.fixture
def client(db):
    """A test client whose requests use the fixture session and a signed-in user."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    app.dependency_overrides[require_admin] = lambda: db.get(User, 1)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- the storage shape ------------------------------------------------------


def test_the_tables_hold_one_json_document_and_no_settings_columns(db):
    """Every setting has to live inside the payload, or upgrades break.

    ``create_all`` never adds a column to a table that already exists, so the
    moment a preference gets its own column, an upgraded installation runs a
    model the database on disk does not match.
    """
    for model in (UserPreference, InstanceSetting):
        columns = {column.name for column in model.__table__.columns}
        assert "data_json" in columns
        assert columns <= {"id", "user_id", "data_json", "updated_at"}, (
            f"{model.__tablename__} grew a settings column; use the JSON payload instead"
        )


def test_startup_creates_the_settings_tables(tmp_path):
    """The import in ``startup`` is load-bearing, and looks removable.

    ``create_all`` only creates tables whose model class was imported. Drop that
    import and the app still starts — the settings screen is what fails, with
    "no such table: user_preferences", and only for whoever opens it.
    """
    from app.core import startup

    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(bind=engine)

    assert {model.__tablename__ for model in startup.SETTINGS_TABLES} <= set(
        Base.metadata.tables
    )
    with engine.connect() as connection:
        for model in startup.SETTINGS_TABLES:
            connection.exec_driver_sql(f"SELECT 1 FROM {model.__tablename__}")


def test_a_payload_from_an_older_version_still_loads(db):
    """A key the current version does not know is ignored, not fatal."""
    db.add(UserPreference(user_id=1, data_json=json.dumps({"theme": "dark", "font_size": "huge"})))
    db.commit()

    preferences = settings_store.user_preferences(db, 1)

    assert preferences.theme == "dark"
    assert not hasattr(preferences, "font_size")


def test_a_payload_that_predates_a_new_setting_gets_its_default(db):
    """The other direction: a key that is missing falls back rather than crashing."""
    db.add(UserPreference(user_id=1, data_json=json.dumps({"theme": "dark"})))
    db.commit()

    preferences = settings_store.user_preferences(db, 1)

    assert preferences.default_unit == UserPreferences().default_unit
    assert preferences.prefill_documents is True


def test_unreadable_json_falls_back_instead_of_taking_the_app_down(db):
    """A corrupt row must leave a working app that can be fixed from the screen."""
    db.add(UserPreference(user_id=1, data_json="{not json"))
    db.add(InstanceSetting(id=1, data_json="}{"))
    db.commit()

    assert settings_store.user_preferences(db, 1).theme == "dark"
    assert settings_store.instance_settings(db).address_lookup_enabled is True


def test_a_value_that_no_longer_validates_does_not_lock_anyone_out(db):
    """Kept because a stored language could be dropped from SUPPORTED later.

    Everything that still validates is kept; only the offending field falls back.
    """
    db.add(
        InstanceSetting(
            id=1,
            data_json=json.dumps({"default_language": "it", "un_cards_enabled": False}),
        )
    )
    db.commit()

    settings = settings_store.instance_settings(db)

    assert settings.default_language == "nl"
    assert settings.un_cards_enabled is False


# --- the environment stays the starting point -------------------------------


def test_environment_variables_still_decide_when_nothing_is_saved(db, monkeypatch):
    """An installation that never opens this screen keeps its documented behaviour."""
    monkeypatch.setenv("GEO_ADDRESS_API_URL", "https://photon.example.org/api")
    monkeypatch.setenv("CATALOG_AUTO_SYNC", "false")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    get_settings.cache_clear()

    settings = settings_store.instance_settings(db)

    assert settings.address_api_url == "https://photon.example.org/api"
    assert settings.catalog_auto_sync is False
    assert settings.session_timeout_minutes == 60


def test_a_saved_value_overrules_the_environment(db, monkeypatch):
    monkeypatch.setenv("CATALOG_AUTO_SYNC", "true")
    get_settings.cache_clear()

    settings_store.save_instance_settings(
        db, settings_store.instance_settings(db).model_copy(update={"catalog_auto_sync": False})
    )

    assert settings_store.instance_settings(db).catalog_auto_sync is False


# --- the switches do something ---------------------------------------------


def test_switching_off_address_lookup_stops_the_outbound_request(db, client, monkeypatch):
    """The point of the switch: not made, rather than made and discarded."""
    calls = []

    class _NeverCalled:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs)

        def __enter__(self):
            raise AssertionError("an outbound request was made while lookup was disabled")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.api.routes.geo.httpx.Client", _NeverCalled)
    settings_store.save_instance_settings(
        db, InstanceSettings(address_lookup_enabled=False)
    )

    response = client.get("/api/geo/address?q=Rotterdam")

    assert response.status_code == 200
    assert response.json() == {"results": [], "available": False}


def test_switching_off_un_cards_hides_them_and_refuses_the_download(db, client):
    settings_store.save_instance_settings(db, InstanceSettings(un_cards_enabled=False))
    payload = {"dangerous_goods": [{"line_id": "1", "products": [{"un_number": "1203"}]}]}

    availability = client.post("/api/documents/un-cards/availability", json=payload)
    download = client.post("/api/documents/un-cards", json=payload)

    assert availability.json()["enabled"] is False
    assert availability.json()["count"] == 0
    assert download.status_code == 404


def test_the_session_lifetime_reaches_the_cookie(db, client):
    """A shorter session that only shortens the token leaves a stale cookie behind."""
    settings_store.save_instance_settings(db, InstanceSettings(session_timeout_minutes=30))
    db.query(User).filter(User.id == 1).update({"password_hash": hash_password("secret123")})
    db.commit()

    response = client.post("/api/auth/login", json={"username": "ada", "password": "secret123"})

    assert response.status_code == 200
    assert "Max-Age=1800" in response.headers["set-cookie"]


def test_catalog_auto_sync_setting_is_read_at_startup(db, monkeypatch):
    from app.core import startup

    settings_store.save_instance_settings(db, InstanceSettings(catalog_auto_sync=False))
    monkeypatch.setattr(
        startup, "sync_catalogs", lambda *args, **kwargs: pytest.fail("sync ran while disabled")
    )

    startup.sync_catalogs_on_startup(db)


# --- who may read and write what -------------------------------------------


def test_preferences_are_per_user(db):
    settings_store.save_user_preferences(db, 1, UserPreferences(theme="dark"))
    settings_store.save_user_preferences(db, 2, UserPreferences(theme="light"))

    assert settings_store.user_preferences(db, 1).theme == "dark"
    assert settings_store.user_preferences(db, 2).theme == "light"


def test_a_plain_user_cannot_read_or_write_the_instance_settings(db):
    """``require_admin`` is the guard; this proves the route actually carries it."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 2)
    try:
        with TestClient(app) as test_client:
            assert test_client.get("/api/settings/instance").status_code == 403
            assert test_client.put("/api/settings/instance", json={}).status_code == 403
            # Their own settings stay reachable.
            assert test_client.get("/api/settings/me").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_the_public_endpoint_does_not_leak_the_administrator_settings(db, client):
    """A signed-in user learns what the screen needs, and nothing more."""
    settings_store.save_instance_settings(
        db, InstanceSettings(address_api_url="https://internal.example.org/geocoder")
    )

    body = client.get("/api/settings/public").json()

    assert "address_api_url" not in body
    assert "session_timeout_minutes" not in body
    assert body["un_cards_enabled"] is True


# --- validation -------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"language": "it"},
        {"default_modality": "teleport"},
        {"signature_image": "javascript:alert(1)"},
    ],
)
def test_nonsense_preferences_are_refused(client, payload):
    response = client.put("/api/settings/me", json={**UserPreferences().model_dump(), **payload})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"default_language": "it"},
        {"address_api_url": "file:///etc/passwd"},
        {"session_timeout_minutes": 0},
        {"session_timeout_minutes": 99_999},
        {"address_timeout_seconds": 0.1},
    ],
)
def test_nonsense_instance_settings_are_refused(client, payload):
    response = client.put(
        "/api/settings/instance", json={**InstanceSettings().model_dump(), **payload}
    )
    assert response.status_code == 422


# --- the defaults that flow downwards ---------------------------------------


def test_a_user_without_a_language_gets_the_instance_default(db):
    settings_store.save_instance_settings(db, InstanceSettings(default_language="fr"))

    assert settings_store.user_preferences(db, 2).language == "fr"


def test_a_user_who_chose_a_language_keeps_it_when_the_default_changes(db):
    settings_store.save_user_preferences(db, 2, UserPreferences(language="de"))
    settings_store.save_instance_settings(db, InstanceSettings(default_language="fr"))

    assert settings_store.user_preferences(db, 2).language == "de"


def test_the_organisation_fills_in_the_consignor_for_someone_who_has_none(db):
    """A new colleague starts with the company already on the form."""
    settings_store.save_instance_settings(
        db,
        InstanceSettings(organisation_name="Mooiweer BV", organisation_address="Havenweg 1\nRotterdam"),
    )

    preferences = settings_store.user_preferences(db, 2)

    assert preferences.consignor_name == "Mooiweer BV"
    assert preferences.consignor_address.startswith("Havenweg 1")


def test_a_user_who_filled_in_their_own_consignor_is_not_overwritten(db):
    settings_store.save_user_preferences(db, 2, UserPreferences(consignor_name="Eigen Vervoer VOF"))
    settings_store.save_instance_settings(db, InstanceSettings(organisation_name="Mooiweer BV"))

    assert settings_store.user_preferences(db, 2).consignor_name == "Eigen Vervoer VOF"


def test_the_options_endpoint_offers_every_language_the_app_supports(client):
    """The screen asks the backend for the lists so the two cannot drift apart."""
    from app.core.languages import SUPPORTED

    body = client.get("/api/settings/options").json()

    assert body["languages"] == list(SUPPORTED)
    assert "road" in body["modalities"]
    assert any(unit["code"] == "pcs" for unit in body["units"])


def test_the_default_unit_is_a_unit_the_backend_knows(db):
    """It used to be the literal string "stuks" — a Dutch word on a French screen."""
    from app.services.units import UNITS

    assert UserPreferences().default_unit in UNITS
