"""The assistant endpoints: one conversational turn, and a status probe.

Stateless on the server: the wizard state travels with the request and comes
back patched. Nothing of the conversation is stored — the same privacy stance
the rest of the application takes with pasted data and documents.
"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.core.ratelimit import ASSISTANT_MODEL, ASSISTANT_STEP, limiter
from app.models.user import User
from app.services.assistant import runtime
from app.services.assistant.orchestrator import step

router = APIRouter(prefix="/assistant", tags=["assistant"])
#: Model installation and maintenance require an administrator.
admin_router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantStepRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    state: dict[str, Any] = Field(default_factory=dict)
    pending: dict[str, Any] | None = None
    language: str = Field(default="nl", max_length=10)
    action: Literal["answer", "revise", "optional", "add_goods"] = "answer"


@router.post("/step")
@limiter.limit(ASSISTANT_STEP)
def assistant_step(
    request: Request,
    payload: AssistantStepRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return step(payload.state, payload.message, payload.pending, db, payload.language, payload.action)


@router.get("/status")
def assistant_status(user: User = Depends(get_current_user)):
    """Whether the assistant can run, and in which mode.

    The deterministic chain is always available; "model" mode only changes
    how flexibly free text is read, never what may be asked or answered. The
    status also carries the download state, so the settings page can show an
    install in progress.
    """
    return runtime.status()


class AssistantModelRequest(BaseModel):
    action: str = Field(pattern="^(download|remove|stop)$")


@admin_router.post("/model")
@limiter.limit(ASSISTANT_MODEL)
def assistant_model(
    request: Request,
    payload: AssistantModelRequest,
    user: User = Depends(require_admin),
):
    """Install or remove the local model runtime. Admin only: the download
    is the assistant's single external fetch, verified against the pinned
    SHA-256 in assistant_runtime.json, into /data/assistant."""
    if payload.action == "download":
        return runtime.start_download()
    if payload.action == "stop":
        runtime.stop()
        return {"stopped": True}
    return runtime.remove()
