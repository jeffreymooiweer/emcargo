"""The shipment as data: complete, versioned, and honest about what it is not.

The assertions that matter here are the ones about absence. A structured export
that turns every untouched field into an empty string looks complete and is
noise; one that reports a check as passing when it never ran is worse than that.
"""
import json
import pytest

from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.main import app
from app.services.dg import database
from app.services.documents.shipment_export import (
    FORMAT,
    FORMAT_VERSION,
    build_shipment_export,
    render_shipment_export,
)

VALUES = {
    "consignor_name": "Afzender BV",
    "consignee_name": "Ontvanger GmbH",
    "reference": "CP-2026-700",
}
LINES = [{"description": "Verf", "quantity": 10, "unit": "vaten"}]


def goods(un, **extra):
    rows = database.get_un_entries(un)
    row = rows[0] if rows else {}
    item = {
        "un_number": un,
        "proper_shipping_name": row.get("name_nl") or "",
        "class": row.get("class") or "",
        "labels": row.get("labels") or "",
        "packing_group": row.get("packing_group") or "",
    }
    item.update(extra)
    return item


def entries(*products):
    return [{"line_id": "1", "products": list(products)}]


def export(**kwargs):
    payload = {
        "values": VALUES, "lines": LINES,
        "dangerous_goods": entries(goods("1263")),
        "language": "nl", "profiles": ["ADR"], "modality": "road",
    }
    payload.update(kwargs)
    return build_shipment_export(
        payload["values"], payload["lines"], payload["dangerous_goods"],
        payload["language"], payload["profiles"], payload["modality"])


# --- what it says about itself ---


def test_it_names_its_own_format_and_version_first():
    """A reader has to be able to tell what it is holding before parsing it."""
    result = export()
    assert result["format"] == FORMAT == "emcargo.shipment"
    assert result["format_version"] == FORMAT_VERSION
    assert list(result)[:2] == ["format", "format_version"]


def test_it_records_which_release_produced_it():
    generator = export()["generator"]
    assert generator["application"] == "EMCargo"
    assert generator["version"]


def test_the_timestamp_is_utc():
    assert export()["generated_at"].endswith("+00:00")


# --- what it refuses to invent ---


def test_an_untouched_field_is_absent_rather_than_empty():
    """The wizard writes an empty string into every field it renders. Exporting
    those would fill the file with keys that mean "untouched" while reading as
    answers."""
    result = export(values=dict(VALUES, notify_party="", carrier_name="   "))
    assert "notify_party" not in result["consignment"]
    assert "carrier_name" not in result["consignment"]
    assert result["consignment"]["consignor_name"] == "Afzender BV"


def test_a_deliberate_zero_or_false_survives():
    """Somebody chose those. Dropping them would lose the distinction between
    "no" and "not said"."""
    result = export(lines=[{"description": "Leeg", "quantity": 0, "stackable": False}])
    assert result["goods"][0]["quantity"] == 0
    assert result["goods"][0]["stackable"] is False


def test_a_shipment_without_dangerous_goods_carries_no_compliance_key():
    """Absent, rather than an empty assessment that reads as "nothing found"."""
    result = export(dangerous_goods=[])
    assert "dangerous_goods" not in result
    assert "compliance" not in result


def test_without_a_regime_nothing_is_assessed():
    """No profile means nobody said which rules apply, and guessing one would
    put an answer in the file that nobody asked for."""
    result = export(profiles=[])
    assert "regulations" not in result
    assert "compliance" not in result
    assert "dangerous_goods" in result


# --- the derived half, which is the point ---


def test_the_derived_findings_travel_with_the_declaration():
    """A reader that gets only the declaration computes its own assessment, and
    that is where two systems start to disagree about one consignment."""
    result = export()
    assert "compliance" in result
    assert "adr_points" in result["compliance"]


def test_the_findings_name_the_editions_they_were_computed_against():
    """So a shipment exported under one edition can be told apart from the same
    shipment re-derived under a later one."""
    compliance = export()["compliance"]
    assert "sources" in compliance
    assert "regulatory_manifest" in compliance


def test_chapter_5_2_rides_along_since_it_is_part_of_the_answer():
    result = export()
    assert "package_marking" in result["compliance"]


# --- the file, and the route ---


def test_the_file_is_utf8_json_a_person_can_read():
    path = render_shipment_export(
        VALUES, LINES, entries(goods("1263")), "nl", ["ADR"], "road")
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "\n  " in text, "indented, because the first thing anyone does is open it"
    assert json.loads(text)["format"] == FORMAT


def user():
    from types import SimpleNamespace
    return SimpleNamespace(id=1, username="verify", role="admin", active=True)


def test_the_route_serves_it_as_json_and_not_as_a_pdf():
    """Every exporter before this one produced a PDF, and the route named one.
    A JSON file served as application/pdf is a file the browser will not open."""
    app.dependency_overrides[get_current_user] = user
    with TestClient(app) as api:
        response = api.post("/api/documents/export", json={
            "document_key": "shipment_export",
            "values": VALUES, "lines": LINES,
            "dangerous_goods": entries(goods("1263")),
            "output_language": "nl", "profiles": ["ADR"], "modality": "road",
        })
    app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert ".json" in response.headers.get("content-disposition", "")
    assert json.loads(response.content)["format"] == FORMAT


def test_the_pdf_documents_are_still_served_as_pdf():
    """The generalisation must not have cost the ninety-nine documents that do
    produce a PDF."""
    app.dependency_overrides[get_current_user] = user
    with TestClient(app) as api:
        response = api.post("/api/documents/export", json={
            # A complete consignment: the packing list has mandatory fields,
            # which the structured export deliberately does not.
            "document_key": "packing_list",
            "values": dict(
                VALUES,
                consignor_address="Havenweg 1, 3011 Rotterdam, Nederland",
                consignee_address="Hafenstrasse 4, 47119 Duisburg, Duitsland",
                established_place="Rotterdam",
                established_date="2026-08-23",
                document_date="2026-08-23",
            ),
            "lines": LINES,
            "output_language": "nl",
        })
    app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


def test_every_mode_can_leave_as_data():
    """Including air: nothing here derives an air rule, it records what was
    entered, so the locked mode's regulatory gap does not reach it."""
    from app.services.documents.registry import get_registry
    per_mode = {mode["key"]: mode["documents"] for mode in get_registry()["modalities"]}
    for mode in per_mode:
        assert "shipment_export" in per_mode[mode], mode


# These fixtures exercise document/retention behaviour with optional review off.
pytestmark = pytest.mark.usefixtures("dg_review_disabled")
