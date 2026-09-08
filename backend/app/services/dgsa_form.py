"""The adviser's half of the annual report: the form, its answers, the checklist.

The form follows the DVSA's *DGSA Annual Report for the Carriage of
Dangerous Goods* (December 2025) — a competent authority's rendering of
ADR 1.8.3.3 — section for section; ``config/dgsa_form.json`` holds the
questions in four languages and says where they come from.

Two halves, kept apart on purpose:

- **what the history can fill in** is offered as a pre-fill and never as an
  answer: the transport table's classes and quantities, the method of
  carriage, the high consequence dangerous goods found by the 1.10.3 check,
  the annual tonnage. The adviser confirms or corrects them;
- **what the adviser owes** — every yes/no, every judgement, the risk rating
  — stays empty until the adviser writes it. Nothing here invents an opinion.

The answers are kept per year and scope (``models/dgsa_report.py``), so a
report is filled in over weeks and found again in five years' time.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.languages import normalise, pick
from app.models.dgsa_report import DgsaReport
from app.models.user import User

#: One answer set may not grow past this; it is a form, not a filing cabinet.
MAX_ANSWERS_BYTES = 200_000
MAX_TEXT = 8000
MAX_INCIDENTS = 100
YES_NO = ("yes", "no", "na", "")


@lru_cache
def form() -> dict[str, Any]:
    path = get_settings().config_dir / "dgsa_form.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _questions() -> dict[str, dict[str, Any]]:
    return {q["key"]: q for q in form()["questions"]}


# --- scope -------------------------------------------------------------------


def scope_for(viewer: User, department: str = "") -> str:
    """Whose shipments the report covers, as the viewer may ask for it.

    An administrator chooses: everything, the unassigned, or one department.
    Anybody else gets their own department whatever they ask — the same rule
    the shipments page applies.
    """
    if getattr(viewer, "role", "") in {"admin", "super_user", "dg_specialist"}:
        wanted = (department or "").strip()
        return wanted if wanted == "none" or wanted.isdigit() else ""
    own = getattr(viewer, "department_id", None)
    return str(own) if own else "none"


# --- the definition, localised -------------------------------------------------


def _localised(item: dict[str, Any], lang: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in item.items():
        if key in ("text", "title", "intro", "band_note"):
            out[key] = pick(value, lang)
        elif key in ("option_labels", "operation_labels", "package_design_labels", "columns"):
            out[key] = {k: pick(v, lang) for k, v in value.items()}
        else:
            out[key] = value
    return out


def definition(language: str = "nl") -> dict[str, Any]:
    """Sections and questions in one language, as the page and the PDF draw them."""
    lang = normalise(language)
    data = form()
    return {
        "source": data["source"],
        "answer_labels": {k: pick(v, lang) for k, v in data["answer_labels"].items()},
        "sections": [_localised(s, lang) for s in data["sections"]],
        "questions": [_localised(q, lang) for q in data["questions"]],
        "checklist": {
            "title": pick(data["checklist"]["title"], lang),
            "columns": {k: pick(v, lang) for k, v in data["checklist"]["columns"].items()},
            "additional_heading": pick(data["checklist"]["additional_heading"], lang),
            "items": [_localised(i, lang) for i in data["checklist"]["items"]],
        },
    }


# --- what the history can fill in ----------------------------------------------


def _band(tonnes: float) -> str:
    if tonnes < 5:
        return "<5"
    if tonnes <= 50:
        return "5-50"
    if tonnes <= 1000:
        return ">50-1000"
    return ">1000"


def prefill(report: dict[str, Any], brand_name: str) -> dict[str, Any]:
    """Answers the count can propose. Offered, not asserted: the page shows
    them as suggestions and the adviser keeps or changes them."""
    lang = report.get("language", "nl")
    labels = form()["answer_labels"]
    filled: dict[str, Any] = {"company_name": brand_name}

    table: dict[str, dict[str, Any]] = {}
    for row in report.get("by_class") or []:
        cls = str(row["class"])
        kg, litres = float(row["quantity_kg"] or 0), float(row["quantity_l"] or 0)
        entry: dict[str, Any] = {"operations": ["consigning"], "band": "",
                                 "quantity_kg": kg, "quantity_l": litres,
                                 "shipments": row["shipments"]}
        if cls.split(".")[0] == "7":
            entry["packages"] = report.get("class7_packages", 0)
            entry["band"] = _band(float(entry["packages"])) if entry["packages"] else ""
        elif kg and not litres:
            # Tonnes from kilograms only. Litres are not tonnes, so a class
            # carried by volume (or by both) is shown with its figures and
            # left for the adviser to band.
            entry["band"] = _band(kg / 1000)
        table[cls] = entry
    filled["transport_table"] = table

    modes = report.get("carriage_modes") or []
    filled["method_of_carriage"] = [m for m in ("package", "tank", "bulk") if m in modes]

    found = report.get("high_consequence") or []
    if found:
        lines = [f"UN {item['un_number']} — {item['reason']}" for item in found]
        filled["hcdg_carried"] = {"answer": "yes", "details": "\n".join(lines)}
    elif report.get("totals", {}).get("with_dangerous_goods"):
        filled["hcdg_carried"] = {"answer": "no", "details": ""}
    else:
        filled["hcdg_carried"] = {"answer": "", "details": ""}

    totals = report.get("totals") or {}
    parts = []
    if totals.get("quantity_kg"):
        parts.append(f"{totals['quantity_kg'] / 1000:.3f} t")
    if totals.get("quantity_l"):
        parts.append(f"{totals['quantity_l']:.0f} L")
    if totals.get("quantity_unknown"):
        unknown = pick({"nl": "{n} stofregel(s) zonder bruikbare eenheid", "en": "{n} substance line(s) without a usable unit",
                        "de": "{n} Stoffzeile(n) ohne verwertbare Einheit", "fr": "{n} ligne(s) sans unité exploitable"}, lang)
        parts.append(unknown.format(n=totals["quantity_unknown"]))
    filled["annual_tonnage"] = "; ".join(parts)
    filled["_labels"] = {k: pick(v, lang) for k, v in labels.items()}
    return filled


# --- keeping the answers -------------------------------------------------------


def _clean_text(value: Any) -> str:
    return str(value or "")[:MAX_TEXT]


def sanitise(answers: dict[str, Any]) -> dict[str, Any]:
    """Only the keys the form knows, in the shape the form gives them."""
    questions = _questions()
    clean: dict[str, Any] = {}
    for key, value in (answers or {}).items():
        question = questions.get(key)
        if question is None:
            continue
        kind = question["kind"]
        if kind in ("text", "textarea", "date"):
            clean[key] = _clean_text(value)
        elif kind in ("yesno", "yesnona"):
            value = value if isinstance(value, dict) else {}
            answer = str(value.get("answer") or "")
            clean[key] = {"answer": answer if answer in YES_NO else "",
                          "details": _clean_text(value.get("details"))}
        elif kind == "choice":
            clean[key] = str(value or "") if str(value or "") in question.get("options", []) else ""
        elif kind == "multi":
            allowed = question.get("options", [])
            clean[key] = [str(v) for v in (value if isinstance(value, list) else []) if str(v) in allowed]
        elif kind == "incidents":
            rows = value if isinstance(value, list) else []
            clean[key] = [{"date": _clean_text(r.get("date"))[:40], "place": _clean_text(r.get("place"))[:255],
                           "description": _clean_text(r.get("description"))}
                          for r in rows[:MAX_INCIDENTS] if isinstance(r, dict)]
        elif kind == "transport_table":
            operations = set(question.get("operations", []))
            bands = set(question.get("bands", []))
            designs = set(question.get("package_designs", []))
            table = value if isinstance(value, dict) else {}
            clean[key] = {
                str(cls): {
                    "operations": [o for o in (row.get("operations") or []) if o in operations],
                    "band": row.get("band") if row.get("band") in bands else "",
                    "designs": [d for d in (row.get("designs") or []) if d in designs],
                    "other": _clean_text(row.get("other"))[:120],
                }
                for cls, row in table.items()
                if str(cls) in question.get("classes", []) and isinstance(row, dict)
            }
    return clean


def load(db: Session, year: int, scope: str) -> DgsaReport | None:
    return db.query(DgsaReport).filter(DgsaReport.year == year, DgsaReport.scope == scope).first()


def answers_of(record: DgsaReport | None) -> dict[str, Any]:
    if record is None:
        return {}
    try:
        value = json.loads(record.answers_json or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def save(db: Session, user: User, year: int, scope: str, answers: dict[str, Any]) -> DgsaReport:
    clean = sanitise(answers)
    encoded = json.dumps(clean, ensure_ascii=False)
    if len(encoded) > MAX_ANSWERS_BYTES:
        raise ValueError("The answers are larger than one report may be.")
    record = load(db, year, scope)
    if record is None:
        record = DgsaReport(year=year, scope=scope, created_by_id=user.id if user.id else None)
        db.add(record)
    record.answers_json = encoded
    db.commit()
    db.refresh(record)
    return record


# --- the checklist ---------------------------------------------------------------


def checklist_rows(report: dict[str, Any], answers: dict[str, Any], language: str = "nl") -> list[dict[str, Any]]:
    """DGSA1 to DGSA21: what was answered, and where in the report it is."""
    lang = normalise(language)
    data = form()
    labels = {k: pick(v, lang) for k, v in data["answer_labels"].items()}
    sections = {s["key"]: pick(s["title"], lang) for s in data["sections"]}
    questions = _questions()
    rows = []
    for item in data["checklist"]["items"]:
        code, kind = item["code"], item.get("kind")
        if kind == "name":
            answer, section = str(answers.get("adviser_full_name") or answers.get("dgsa_name") or ""), sections["prepared"]
        elif kind == "year":
            answer, section = str(report.get("year", "")), ""
        else:
            question = questions.get(item.get("question", ""), {})
            value = answers.get(question.get("key", ""))
            section = sections.get(question.get("section", ""), "")
            if isinstance(value, dict):
                answer = labels.get(value.get("answer") or "", "")
            elif isinstance(value, str):
                answer = value[:200]
            else:
                answer = ""
        rows.append({"code": code, "text": pick(item["text"], lang), "answer": answer,
                     "section": section, "additional": bool(item.get("additional"))})
    return rows
