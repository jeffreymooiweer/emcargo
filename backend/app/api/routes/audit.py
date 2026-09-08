"""The administrator's audit log: read, filter and export authenticated activity."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.models.user import User
from app.services import audit

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def audit_page(
    actor: str = Query(default="", max_length=150),
    action: str = Query(default="", max_length=64),
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=500),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return audit.page(db, actor=actor, action=action, since=since, until=until,
                      number=page, per_page=per_page)


@router.get("/actions")
def audit_actions(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """The action codes the log can carry, and the names that occur in it."""
    return {"actions": list(audit.ACTIONS), "actors": audit.actors(db)}


@router.get("/export.csv")
def audit_export(
    actor: str = Query(default="", max_length=150),
    action: str = Query(default="", max_length=64),
    since: datetime | None = None,
    until: datetime | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    body = audit.export_csv(db, actor=actor, action=action, since=since, until=until)
    return PlainTextResponse(body, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="emcargo-audit.csv"'})
