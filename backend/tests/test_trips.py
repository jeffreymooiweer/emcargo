"""Kept groupage trips: the judgement over a load, kept beside the shipments.

What is pinned here:

1. **Only with the switch.** With *Keep shipments* off the trips routes
   answer 404, like the shipments'.
2. **The server judges.** A kept trip carries the check's answer as the
   server computed it from the consignments sent, with the editions, and
   the index columns (points, the lost exemption) come out of that answer.
3. **Reopening returns what was kept**, consignments and result alike.
4. **Who sees it** follows the departments rule the shipments use.
5. **Switching the history off** counts the trips with the shipments, and
   deleting the history deletes them too.
6. **The audit log** gets a line per keep, update and forget.
7. **The schema step** exists for an old database.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.core import migrations
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.deps import get_current_user
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.trip import Trip
from app.models.user import Department, User
from app.services import departments, history, trips
from app.schemas.trips import TripIn


@pytest.fixture
def db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{data_dir / 'test.db'}")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CATALOG_AUTO_SYNC", "false")
    monkeypatch.delenv("EMCARGO_MODE", raising=False)
    monkeypatch.delenv("EMCARGO_HISTORY", raising=False)
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{data_dir / 'test.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    sales = Department(id=1, name="Sales")
    session.add(sales)
    session.add(User(id=1, username="ada", email="ada@example.com", password_hash="x",
                     role="user", department_id=1))
    session.add(User(id=2, username="bob", email="bob@example.com", password_hash="x",
                     role="user"))
    session.add(User(id=3, username="root", email="root@example.com", password_hash="x",
                     role="admin"))
    session.commit()
    yield session
    session.close()
    get_settings.cache_clear()


def application(db, monkeypatch, as_user: int = 1, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, as_user)
    return TestClient(app)


ADA = SimpleNamespace(id=1, username="ada", role="user", active=True, department_id=1)


def petrol(quantity: str) -> dict:
    return {"un_number": "1203", "proper_shipping_name": "BENZINE", "class": "3",
            "transport_category": "2", "adr_total_quantity": quantity}


def trip(**overrides) -> dict:
    payload = {
        "name": "Wezep - Rotterdam, 6 September",
        "consignments": [
            {"name": "Klant A", "entries": [{"products": [petrol("200")]}], "shipment_id": 7},
            {"name": "Klant B", "entries": [{"products": [petrol("200")]}]},
        ],
        "profiles": ["ADR"],
        "language": "en",
        "unit_max_mass_tonnes": 18,
    }
    payload.update(overrides)
    return payload


# --- 1. only with the switch ------------------------------------------------------


def test_without_the_switch_the_trips_routes_do_not_exist(db, monkeypatch):
    with application(db, monkeypatch, EMCARGO_HISTORY="false") as client:
        assert client.get("/api/trips").status_code == 404
        assert client.post("/api/trips", json=trip()).status_code == 404
        # The calculation itself is still there for everybody.
        assert client.post("/api/dg/trip", json={
            "consignments": trip()["consignments"], "profiles": ["ADR"]}).status_code == 200


# --- 2. the server judges -----------------------------------------------------------


def test_keeping_runs_the_check_and_indexes_its_answer(db, monkeypatch):
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        kept = client.post("/api/trips", json=trip())
        assert kept.status_code == 200, kept.text
        row = kept.json()
        assert row["name"] == "Wezep - Rotterdam, 6 September"
        assert row["consignment_count"] == 2
        assert row["total_points"] == 1200
        assert row["exemption_lost"] is True
        assert row["unit_max_mass_tonnes"] == 18
        assert row["regulations"] == ["ADR"]
        assert row["created_by"] == "ada" and row["department"] == "Sales"

        detail = client.get(f"/api/trips/{row['id']}").json()
        assert [c["name"] for c in detail["consignments"]] == ["Klant A", "Klant B"]
        assert detail["consignments"][0]["shipment_id"] == 7
        assert detail["result"]["adr_points"]["total_points"] == 1200
        assert detail["result"]["exemption_lost"]["consignments"] == ["Klant A", "Klant B"]
        assert detail["result"]["lq_marking"]["unit_max_mass_tonnes"] == 18
        # The editions the answer was computed against, from the manifest.
        assert "adr" in detail["editions"]


def test_a_trip_that_stays_exempt_is_indexed_so(db, monkeypatch):
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        payload = trip(consignments=[
            {"name": "A", "entries": [{"products": [petrol("100")]}]},
            {"name": "B", "entries": [{"products": [petrol("100")]}]}])
        row = client.post("/api/trips", json=payload).json()
        assert row["total_points"] == 600 and row["exemption_lost"] is False


def test_one_consignment_can_start_a_trip(db, monkeypatch):
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        alone = trip(consignments=trip()["consignments"][:1])
        response = client.post("/api/trips", json=alone)
        assert response.status_code == 200
        assert response.json()["consignment_count"] == 1
        assert response.json()["result"]["adr_points"]["total_points"] == 600
    assert trips.count(db) == 1


def test_empty_trip_is_refused_on_create_and_update(db, monkeypatch):
    """The unified editor starts empty, but an empty load must not be saved."""
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        assert client.post("/api/trips", json=trip(consignments=[])).status_code == 422
        kept = client.post("/api/trips", json=trip()).json()
        assert client.put(f"/api/trips/{kept['id']}", json=trip(consignments=[])).status_code == 422
        assert client.get(f"/api/trips/{kept['id']}").json()["consignment_count"] == 2


def test_general_freight_and_source_profiles_survive_reopening(db, monkeypatch):
    """Ordinary freight belongs on the same trip; source profiles must survive edits."""
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        payload = trip(consignments=[{"name": "Timber", "entries": [], "profiles": [],
                                     "route_label": "Wezep → Oirschot"}], profiles=[])
        kept = client.post("/api/trips", json=payload).json()
        detail = client.get(f"/api/trips/{kept['id']}").json()
        assert detail["consignments"][0]["entries"] == []
        assert detail["consignments"][0]["profiles"] == []
        assert detail["consignments"][0]["route_label"] == "Wezep → Oirschot"
        assert kept["result"] == detail["result"]
        assert kept["editions"] == detail["editions"]


def test_keeping_again_brings_the_same_row_up_to_date(db, monkeypatch):
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        first = client.post("/api/trips", json=trip()).json()
        second = client.put(f"/api/trips/{first['id']}",
                            json=trip(name="Renamed", unit_max_mass_tonnes=None)).json()
        assert second["id"] == first["id"]
        assert second["name"] == "Renamed" and second["unit_max_mass_tonnes"] is None
        assert client.get("/api/trips").json()["total"] == 1


def test_an_unknown_regime_is_refused_not_judged_as_adr(db, monkeypatch):
    """"IDMG" was kept and judged under ADR's points until v1.190.0."""
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        refused = client.post("/api/trips", json=trip(profiles=["IDMG"]))
        assert refused.status_code == 422
        assert "IDMG" in refused.text
        kept = client.post("/api/trips", json=trip(profiles=["adr", "IATA"]))
        assert kept.status_code == 200, kept.text
        assert kept.json()["regulations"] == ["ADR", "IATA_DGR"]


# --- 3/4. the list and who sees it ----------------------------------------------------


def test_the_list_filters_and_follows_the_departments(db, monkeypatch):
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        client.post("/api/trips", json=trip(name="Monday"))
        client.post("/api/trips", json=trip(name="Tuesday"))
    with application(db, monkeypatch, as_user=2) as bob:
        # Bob has no department; Sales' trips are not there for him.
        assert bob.get("/api/trips").json()["total"] == 0
        bob.post("/api/trips", json=trip(name="Bob's van"))
        assert bob.get("/api/trips").json()["total"] == 1
        assert bob.get("/api/trips/1").status_code == 404
    with application(db, monkeypatch, as_user=3) as root:
        everything = root.get("/api/trips").json()
        assert everything["total"] == 3
        assert [t["name"] for t in everything["items"]] == ["Bob's van", "Tuesday", "Monday"]
        assert root.get("/api/trips", params={"q": "tues"}).json()["total"] == 1
        assert root.get("/api/trips", params={"department": "1"}).json()["total"] == 2
        assert root.get("/api/trips", params={"department": "none"}).json()["total"] == 1
        assert root.get("/api/trips/1").status_code == 200


def test_forgetting_removes_the_row(db, monkeypatch):
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        kept = client.post("/api/trips", json=trip()).json()
        assert client.delete(f"/api/trips/{kept['id']}").json()["ok"] is True
        assert client.get(f"/api/trips/{kept['id']}").status_code == 404
        assert client.delete(f"/api/trips/{kept['id']}").status_code == 404
    assert trips.count(db) == 0


def test_a_removed_department_leaves_no_trip_behind_under_its_id(db, monkeypatch):
    """SQLite hands a new department the old id; a trip still carrying it
    would be that department's. Until v1.190.0 the removal cleared users
    and shipments and forgot the trips."""
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        kept = client.post("/api/trips", json=trip()).json()
        assert kept["department_id"] == 1
    gone = departments.remove(db, db.get(Department, 1))
    assert gone["trips"] == 1
    db.expire_all()
    assert db.get(Trip, kept["id"]).department_id is None
    docks = departments.create(db, "Docks")
    assert docks.id == 1  # the id came back; the trip did not come with it
    assert trips.search(db, SimpleNamespace(id=9, role="user", department_id=1))[1] == 0


# --- 5. the switch ----------------------------------------------------------------------


def test_trips_are_counted_when_the_history_is_switched_off(db, monkeypatch):
    monkeypatch.setenv("EMCARGO_HISTORY", "true")
    get_settings.cache_clear()
    trips.keep(db, ADA, TripIn(**trip()))
    assert history.kept_counts(db) == {"shipments": 0, "trips": 1}
    # Start-up with the setting off and a trip in the table switches it on.
    monkeypatch.setenv("EMCARGO_HISTORY", "false")
    get_settings.cache_clear()
    assert history.adopt_kept_data(db) is True
    assert trips.count(db) == 1


def test_discarding_the_history_deletes_trips_too(db, monkeypatch, caplog):
    monkeypatch.setenv("EMCARGO_HISTORY", "true")
    get_settings.cache_clear()
    trips.keep(db, ADA, TripIn(**trip()))
    with caplog.at_level(logging.WARNING):
        assert history.discard_kept(db) == {"shipments": 0, "trips": 1}
    assert trips.count(db) == 0
    assert "1 kept trip(s)" in caplog.text


# --- 6. the audit log ---------------------------------------------------------------------


def test_the_audit_log_names_the_trip_and_nothing_on_it(db, monkeypatch):
    with application(db, monkeypatch, EMCARGO_HISTORY="true") as client:
        kept = client.post("/api/trips", json=trip()).json()
        client.put(f"/api/trips/{kept['id']}", json=trip())
        client.delete(f"/api/trips/{kept['id']}")
    events = list(db.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars())
    assert [e.action for e in events] == ["trip.kept", "trip.updated", "trip.forgotten"]
    assert all(e.target_type == "trip" and e.summary == "Wezep - Rotterdam, 6 September"
               for e in events)
    assert not any("Klant" in e.summary or "1203" in e.summary for e in events)


# --- 7. the schema ------------------------------------------------------------------------


def test_the_schema_step_makes_the_table_on_an_old_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    User.__table__.create(engine)
    Department.__table__.create(engine)
    assert not inspect(engine).has_table("trips")
    migrations.run(engine, fresh=False)
    assert inspect(engine).has_table("trips")
    assert "trips" in [name for _v, name, _s in migrations.MIGRATIONS]
