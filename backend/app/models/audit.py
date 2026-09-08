"""The audit log: who did what, when — and never what a material list said.

One row per event, written by the routes that do something worth an
administrator's attention: signing in and failing to, keeping and
forgetting a shipment, handing out documents, changing a setting, managing
an account. Metadata only, by design: the action, its target's kind and
identifier, a short summary in the application's own words, the actor and
the address the request came from. The contents of a consignment never
enter this table, so the log can be kept longer than the shipments and
shown to an administrator without showing them a customer's goods.

Every installation records these events for its administrators.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    #: Who. The identifier may outlive the account (an administrator deleted
    #: a user, and the log still says who kept what), so the name is kept
    #: beside it as it was at the time.
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_username: Mapped[str] = mapped_column(String(150), default="", index=True)
    #: What, as a dotted code from ``services/audit.py``: ``auth.login``,
    #: ``shipment.kept``, ``settings.changed`` …
    action: Mapped[str] = mapped_column(String(64), index=True)
    #: On what: a kind and an identifier, both optional.
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str] = mapped_column(String(64), default="")
    #: A line for a person: the document keys downloaded, the settings keys
    #: changed, the reference of the shipment. Never a value from the form.
    summary: Mapped[str] = mapped_column(String(255), default="")
    #: Where from, as the rate limiter sees it (the peer, or the address the
    #: trusted proxy vouched for).
    client: Mapped[str] = mapped_column(String(64), default="")
