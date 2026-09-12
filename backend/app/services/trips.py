"""Kept groupage trips: keeping, listing and letting go.

The sibling of ``services/history.py`` for the level above the consignment.
A trip is kept only on an installation that keeps its shipments — the routes
that call this are mounted with the history's — and it is kept with the
check's answer of the moment and the editions that answer was computed
against, because the point of keeping a judgement is to be able to show
later what was judged, not to judge again.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, defer, joinedload

from app.core.dates import utc_filter_bound, utc_timestamp
from app.models.trip import Trip
from app.models.user import Department, User
from app.schemas.trips import TripDetail, TripIn, TripSummary
from app.services import departments
from app.services.dg.trip import check_trip
from app.services.regulatory_manifest import summary as regulatory_summary

#: What one kept trip may weigh: the consignments and the answer together.
MAX_RECORD_BYTES = 4 * 1024 * 1024

PER_PAGE_MAX = 100


class RecordTooLarge(ValueError):
    """More than :data:`MAX_RECORD_BYTES` of consignments and result."""


def count(db: Session) -> int:
    return int(db.query(func.count(Trip.id)).scalar() or 0)


def discard_all(db: Session) -> int:
    removed = db.query(Trip).delete()
    db.commit()
    return int(removed or 0)


# --- keeping -----------------------------------------------------------------


def keep(db: Session, user: User, payload: TripIn, existing: Trip | None = None) -> Trip:
    """Keep a trip — a new row, or the same row brought up to date.

    The check runs here, on what was sent, and its answer is what is kept.
    """
    consignments = [c.model_dump() for c in payload.consignments]
    result = check_trip(
        [{"name": c["name"], "entries": c["entries"]} for c in consignments],
        payload.profiles, payload.language, payload.unit_max_mass_tonnes)
    record_json = {
        "result": result,
        "editions": regulatory_summary().get("editions") or {},
        "profiles": list(payload.profiles),
    }
    consignments_json = json.dumps(consignments, ensure_ascii=False)
    result_json = json.dumps(record_json, ensure_ascii=False, default=str)
    size = len(consignments_json) + len(result_json)
    if size > MAX_RECORD_BYTES:
        raise RecordTooLarge(
            f"The trip is {size / 1024 / 1024:.1f} MB, more than the "
            f"{MAX_RECORD_BYTES // 1024 // 1024} MB one kept trip may be.")

    record = existing or Trip(created_by_id=user.id if user.id else None,
                              department_id=getattr(user, "department_id", None))
    record.name = (payload.name or "").strip()[:120]
    record.language = (payload.language or "nl")[:8]
    record.regulations = ",".join(payload.profiles)[:64]
    record.consignment_count = len(consignments)
    points = (result.get("adr_points") or {}).get("total_points")
    record.total_points = float(points) if isinstance(points, (int, float)) else None
    record.exemption_lost = result.get("exemption_lost") is not None
    record.unit_max_mass_tonnes = payload.unit_max_mass_tonnes
    record.consignments_json = consignments_json
    record.result_json = result_json
    if existing is None:
        db.add(record)
    db.commit()
    db.refresh(record)
    return record


def forget(db: Session, record: Trip) -> None:
    db.delete(record)
    db.commit()


# --- reading -----------------------------------------------------------------


def _loads(text: str | None, default: Any) -> Any:
    try:
        value = json.loads(text or "")
    except ValueError:
        return default
    return value if isinstance(value, type(default)) else default


def summary(record: Trip) -> TripSummary:
    return TripSummary(
        id=record.id,
        name=record.name,
        language=record.language,
        regulations=[r for r in (record.regulations or "").split(",") if r],
        consignment_count=record.consignment_count,
        total_points=record.total_points,
        exemption_lost=bool(record.exemption_lost),
        unit_max_mass_tonnes=record.unit_max_mass_tonnes,
        created_by=record.creator.username if record.creator else "",
        department_id=record.department_id,
        department=record.department.name if record.department else "",
        created_at=utc_timestamp(record.created_at),
        updated_at=utc_timestamp(record.updated_at),
    )


def detail(record: Trip) -> TripDetail:
    kept = _loads(record.result_json, {})
    return TripDetail(
        **summary(record).model_dump(),
        consignments=_loads(record.consignments_json, []),
        result=kept.get("result") or {},
        editions=kept.get("editions") or {},
    )


def search(db: Session, viewer: User, q: str = "",
           date_from: datetime | None = None, date_to: datetime | None = None,
           page: int = 1, per_page: int = 25,
           department: str = "") -> tuple[list[Trip], int]:
    """The page of trips ``viewer`` may see, newest first, and the total."""
    query = departments.visible_to(db.query(Trip), viewer, department, model=Trip)
    needle = (q or "").strip()
    if needle:
        query = query.filter(Trip.name.ilike(f"%{needle}%"))
    if date_from:
        query = query.filter(Trip.created_at >= utc_filter_bound(date_from))
    if date_to:
        query = query.filter(Trip.created_at <= utc_filter_bound(date_to))
    total = int(query.with_entities(func.count(Trip.id)).scalar() or 0)
    per_page = max(1, min(int(per_page), PER_PAGE_MAX))
    page = max(1, int(page))
    # The planner's list reads metadata, not every consignment and assessment.
    rows = (query.options(
                defer(Trip.consignments_json), defer(Trip.result_json),
                joinedload(Trip.creator).load_only(User.username),
                joinedload(Trip.department).load_only(Department.name))
            .order_by(Trip.created_at.desc(), Trip.id.desc())
            .offset((page - 1) * per_page).limit(per_page).all())
    return rows, total
