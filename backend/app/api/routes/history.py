"""The shipments page's routes.

Mounted in the organisation application behind ``require_history`` — see
``main.py`` — so these addresses answer 404 while the administrator's *Keep
shipments* setting is off, and do not exist at all in the open application.
That is how the promise "nothing is kept" is enforced rather than described.

Every signed-in user of the organisation sees every kept shipment. The
roadmap's departments — who sees whose — are the next phase and will narrow
this; until then the organisation is the unit.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routes.documents import build_bundle, delete_file
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.http import attachment
from app.core.ratelimit import DGSA_REPORT, DOCUMENT_BUNDLE, DRAFT_SAVE, limiter
from app.models.shipment import Shipment
from app.models.user import User
from app.schemas import DocumentBundleRequest
from app.schemas.history import ShipmentDetail, ShipmentIn, ShipmentPage, ShipmentSummary
from app.services import audit, departments, dgsa_form, dgsa_report, history
from app.services.documents import brand
from app.services.documents.dgsa_report_pdf import render_dgsa_report
from app.services.documents.signature import decode_signature_image
from app.services.settings_store import user_preferences

router = APIRouter(prefix="/shipments", tags=["shipments"])


def _record(shipment_id: int, db: Session, viewer: User) -> Shipment:
    """The shipment, if it exists and ``viewer`` may see it.

    One answer for both: a shipment another department kept is, for this
    viewer, not there — not "there but forbidden", which would tell them
    it exists.
    """
    record = db.get(Shipment, shipment_id)
    if record is None or not departments.may_see(record, viewer):
        raise HTTPException(status_code=404, detail="No such shipment")
    return record


@router.get("", response_model=ShipmentPage)
def list_shipments(
    q: str = Query(default="", max_length=120),
    modality: str = Query(default="", max_length=16),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=history.PER_PAGE_MAX),
    department: str = Query(default="", max_length=16),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows, total = history.search(db, user, q, modality, date_from, date_to, page, per_page,
                                 department=department)
    return ShipmentPage(items=[history.summary(r) for r in rows],
                        total=total, page=page, per_page=per_page)


# The report routes come before ``/{shipment_id}``: a path is matched in
# order, and "report" would otherwise be tried as a shipment id and refused.


@router.get("/draft", response_model=ShipmentDetail | None)
def running_draft(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The entry this user was in the middle of, or nothing.

    Answering with ``null`` rather than a 404: "you have no draft" is an
    ordinary answer to this question, not a failure to find something.
    """
    record = history.running_draft(db, user)
    return history.detail(record) if record else None


@router.put("/draft", response_model=ShipmentSummary)
@limiter.limit(DRAFT_SAVE)
def save_draft(request: Request, payload: ShipmentIn,
               user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """Keep the running entry, so a reload does not lose it.

    One draft per person: saving again writes the same row. It is not a kept
    shipment and never becomes one here — the export step's *keep* does that,
    with the same row and the draft flag off.
    """
    existing = history.running_draft(db, user)
    try:
        record = history.keep(db, user, payload.model_copy(update={"draft": True}),
                              existing=existing)
    except history.RecordTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    # Deliberately not audited: an audit line per keystroke-batch would drown
    # the log that exists to show who read and kept what.
    return history.summary(record)


@router.delete("/draft")
def discard_draft(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Throw the running entry away. Nothing is kept of it."""
    record = history.running_draft(db, user)
    if record:
        history.forget(db, record)
    return {"ok": True}


@router.get("/report/years")
def report_years(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The calendar years the viewer could draw a report over."""
    return {"years": dgsa_report.years_kept(db, user)}


@router.get("/report")
@limiter.limit(DGSA_REPORT)
def shipment_report(request: Request,
                    year: int = Query(ge=2000, le=2100),
                    department: str = Query(default="", max_length=16),
                    language: str = Query(default="nl", max_length=8),
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """The safety adviser's annual report (ADR 1.8.3.3) over one year, as
    figures — see ``services/dgsa_report.py`` for what is counted and what is
    deliberately left to the adviser."""
    return dgsa_report.build_report(db, user, year, department, language)


class ReportAnswers(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)


@router.get("/report/form")
@limiter.limit(DGSA_REPORT)
def shipment_report_form(request: Request,
                         year: int = Query(ge=2000, le=2100),
                         department: str = Query(default="", max_length=16),
                         language: str = Query(default="nl", max_length=8),
                         user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """The report in the DVSA's shape: the figures, the form's definition in
    one language, what the history can pre-fill, and the answers kept so
    far for this year and scope."""
    scope = dgsa_form.scope_for(user, department)
    report = dgsa_report.build_report(db, user, year, scope, language)
    record = dgsa_form.load(db, year, scope)
    return {
        "report": report,
        "scope": scope,
        "definition": dgsa_form.definition(language),
        "prefill": dgsa_form.prefill(report, brand.resolve(db).name),
        "answers": dgsa_form.answers_of(record),
        "saved_at": record.updated_at.isoformat() if record else None,
        "has_signature": bool(user_preferences(db, user.id).signature_image) if user.id else False,
    }


@router.put("/report/answers")
def shipment_report_answers(payload: ReportAnswers,
                            year: int = Query(ge=2000, le=2100),
                            department: str = Query(default="", max_length=16),
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Keep the adviser's answers for this year and scope. Only the keys the
    form knows survive, in the shape the form gives them."""
    scope = dgsa_form.scope_for(user, department)
    try:
        record = dgsa_form.save(db, user, year, scope, payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return {"ok": True, "saved_at": record.updated_at.isoformat(), "answers": dgsa_form.answers_of(record)}


@router.get("/report.pdf")
@limiter.limit(DGSA_REPORT)
def shipment_report_pdf(request: Request,
                        background_tasks: BackgroundTasks,
                        year: int = Query(ge=2000, le=2100),
                        department: str = Query(default="", max_length=16),
                        language: str = Query(default="nl", max_length=8),
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """The report as paper, in the installation's style, in the DVSA's
    order, with the adviser's saved signature where they kept one."""
    scope = dgsa_form.scope_for(user, department)
    current_brand = brand.use(db)
    report = dgsa_report.build_report(db, user, year, scope, language)
    answers = dgsa_form.answers_of(dgsa_form.load(db, year, scope))
    signature_png = None
    if user.id:
        data_url = user_preferences(db, user.id).signature_image
        if data_url:
            try:
                signature_png = decode_signature_image(data_url)
            except ValueError:
                signature_png = None
    path = render_dgsa_report(report, dgsa_form.definition(language), answers,
                              signature_png=signature_png, brand_name=current_brand.name)
    background_tasks.add_task(delete_file, path)
    audit.record(db, "report.rendered", actor=user, target=("report", str(year)),
                 summary=f"{year} pdf", request=request)
    return FileResponse(path=path, filename=f"emcargo-dgsa-report-{year}.pdf",
                        media_type="application/pdf")


@router.get("/report.xlsx")
@limiter.limit(DGSA_REPORT)
def shipment_report_workbook(request: Request,
                             year: int = Query(ge=2000, le=2100),
                             department: str = Query(default="", max_length=16),
                             language: str = Query(default="nl", max_length=8),
                             user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    """The same report as a workbook, one sheet per table and the adviser's
    duties last with an empty column for the finding."""
    report = dgsa_report.build_report(db, user, year, department, language)
    content = dgsa_report.build_workbook(report)
    audit.record(db, "report.rendered", actor=user, target=("report", str(year)),
                 summary=f"{year} xlsx", request=request)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="emcargo-dgsa-report-{year}.xlsx"'})


def _kept(request: Request, db: Session, user: User, record: Shipment, action: str) -> Shipment:
    """The audit line for a kept shipment: its reference, never its contents."""
    audit.record(db, action, actor=user, target=("shipment", record.id),
                 summary=record.reference or "", request=request)
    return record


@router.post("", response_model=ShipmentSummary)
def keep_shipment(request: Request, payload: ShipmentIn,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    try:
        record = history.keep(db, user, payload)
    except history.RecordTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return history.summary(_kept(request, db, user, record, "shipment.kept"))


@router.put("/{shipment_id}", response_model=ShipmentSummary)
def update_shipment(request: Request, shipment_id: int, payload: ShipmentIn,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    record = _record(shipment_id, db, user)
    try:
        record = history.keep(db, user, payload, existing=record)
    except history.RecordTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return history.summary(_kept(request, db, user, record, "shipment.updated"))


@router.get("/{shipment_id}", response_model=ShipmentDetail)
def get_shipment(shipment_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return history.detail(_record(shipment_id, db, user))


@router.get("/{shipment_id}/export.json")
def shipment_export(request: Request, shipment_id: int,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """The structured export as it was kept — the record, not a re-render."""
    record = _kept(request, db, user, _record(shipment_id, db, user), "shipment.export")
    name = f"emcargo-shipment-{record.reference or record.id}.json"
    return JSONResponse(content=history.detail(record).export,
                        headers={"Content-Disposition": attachment(name)})


@router.post("/{shipment_id}/documents")
@limiter.limit(DOCUMENT_BUNDLE)
def shipment_documents(request: Request, shipment_id: int,
                       background_tasks: BackgroundTasks,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """The documents again, re-rendered from the kept bundle request.

    Rendered by the same code path as the export step's download, from the
    same payload — so what comes back is what went out, on today's build.
    A shipment kept without a ready document has nothing to re-render, and
    says so rather than handing over an empty archive.
    """
    record = _record(shipment_id, db, user)
    bundle = history.bundle_of(record)
    if not bundle or not bundle.get("documents"):
        raise HTTPException(status_code=404,
                            detail="This shipment was kept without ready documents.")
    bundle_path, ref = build_bundle(DocumentBundleRequest(**bundle), db)
    background_tasks.add_task(delete_file, bundle_path)
    _kept(request, db, user, record, "shipment.documents")
    return FileResponse(path=bundle_path,
                        filename=f"emcargo-documents-{record.reference or ref}.zip",
                        media_type="application/zip")


@router.delete("/{shipment_id}")
def forget_shipment(request: Request, shipment_id: int,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    record = _record(shipment_id, db, user)
    gone_id, reference = record.id, record.reference or ""
    history.forget(db, record)
    audit.record(db, "shipment.forgotten", actor=user, target=("shipment", gone_id),
                 summary=reference, request=request)
    return {"ok": True}
