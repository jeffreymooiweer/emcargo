"""Overview pages must not load saved documents or query each author separately."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.shipment import Shipment
from app.models.trip import Trip
from app.models.user import Department, User
from app.services import history, trips


@pytest.mark.parametrize("kind", ["shipments", "trips"])
def test_list_metadata_has_bounded_queries_and_keeps_payloads_for_detail(kind):
    """A page of six shipments used eight SELECTs and transferred every
    saved JSON document, although none is displayed in the overview. Separate
    authors and departments make that cost visible rather than letting the
    session identity map hide it. Detail reads must still return the same data,
    including when they reuse a session that just loaded the lighter list.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    model, service = (Shipment, history) if kind == "shipments" else (Trip, trips)
    payload_fields = (
        {"snapshot_json", "export_json", "bundle_json"}
        if kind == "shipments" else {"consignments_json", "result_json"}
    )
    with Session(engine) as db:
        for number in range(1, 7):
            db.add(Department(id=number, name=f"Department {number}"))
            db.add(User(id=number, username=f"author{number}",
                        email=f"author{number}@example.local", password_hash="x",
                        department_id=number))
            if kind == "shipments":
                record = Shipment(
                    reference=f"Shipment {number}", created_by_id=number,
                    department_id=number, regulations="ADR,IMDG", is_draft=False,
                    snapshot_json='{"entry":"saved"}', export_json='{"weight":42}',
                    bundle_json=[None, "", '{"documents":["cmr"]}'][number % 3])
            else:
                record = Trip(
                    name=f"Trip {number}", created_by_id=number, department_id=number,
                    regulations="ADR", consignments_json='[{"name":"Consignment"}]',
                    result_json='{"result":{"points":42},"editions":{"adr":"2025"}}')
            db.add(record)
        db.commit()
        expected = {
            row.id: service.detail(row).model_dump() for row in db.query(model).all()
        }
        db.expunge_all()
        statements = []

        def remember(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", remember)
        try:
            rows, total = service.search(db, SimpleNamespace(role="admin"))
            actual = [service.summary(row).model_dump() for row in rows]
            assert total == 6
            assert len(statements) == 2
            for row, summary in zip(rows, actual):
                assert payload_fields <= inspect(row).unloaded
                assert summary == {key: expected[row.id][key] for key in summary}
        finally:
            event.remove(engine, "before_cursor_execute", remember)

        # A later detail route may retrieve the same ORM identity; deferring
        # payloads must not prohibit that route from loading them on demand.
        for row in rows:
            assert service.detail(db.get(model, row.id)).model_dump() == expected[row.id]
        if kind == "shipments":
            for row in rows:
                assert row.has_documents is bool(row.bundle_json)
    engine.dispose()


@pytest.mark.parametrize("kind", ["shipments", "trips"])
@pytest.mark.parametrize("start_iso,next_iso,hours", [
    ("2026-09-08T00:00:00+02:00", "2026-09-09T00:00:00+02:00", 24),
    ("2026-03-29T00:00:00+01:00", "2026-03-30T00:00:00+02:00", 23),
    ("2026-10-25T00:00:00+02:00", "2026-10-26T00:00:00+01:00", 25),
])
def test_calendar_bounds_respect_offsets_and_include_the_final_microsecond(
        kind, start_iso, next_iso, hours):
    """The dashboard's day belongs to the browser's timezone. SQLite drops
    explicit offsets when binding dates, so +02:00 previously became an
    unrelated UTC midnight. Records on both sides of the boundary catch that
    shift, and the last microsecond pins the API's inclusive upper bound.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    model, service = (Shipment, history) if kind == "shipments" else (Trip, trips)
    start = datetime.fromisoformat(start_iso)
    next_day = datetime.fromisoformat(next_iso)
    first_utc = start.astimezone(timezone.utc)
    next_utc = next_day.astimezone(timezone.utc)
    assert next_utc - first_utc == timedelta(hours=hours)
    end = next_day - timedelta(microseconds=1)
    timestamps = [first_utc - timedelta(microseconds=1), first_utc,
                  first_utc + timedelta(hours=12), next_utc - timedelta(microseconds=1), next_utc]
    with Session(engine) as db:
        for index, timestamp in enumerate(timestamps, 1):
            db.add(model(id=index, created_at=timestamp))
        db.commit()
        viewer = SimpleNamespace(role="admin")
        for lower, upper in (
            (start, end),
            (first_utc, next_utc - timedelta(microseconds=1)),
            (first_utc.replace(tzinfo=None),
             (next_utc - timedelta(microseconds=1)).replace(tzinfo=None)),
        ):
            rows, total = service.search(db, viewer, date_from=lower, date_to=upper)
            assert total == 3
            assert [row.id for row in rows] == [4, 3, 2]
    engine.dispose()
