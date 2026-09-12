"""The assistant over its real API, the way the panel calls it.

Two rides end to end through ``POST /api/assistant/step``: the dangerous
goods archetype (diesel in jerrycans) and a plain steel consignment that
never touches the DG route. The local-model installation prerequisite is
simulated independently of inference, so these tests exercise real application
rules. Separate checks require installation before any interview action.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.main import app
from app.services.assistant import runtime


@pytest.fixture
def api():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, username="verify", role="admin", active=True)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)


def drive(api, turns, modality="road"):
    state = {"modality": modality, "draft_lines": [], "dg_entries": [], "doc_values": {}}
    pending = None
    events = []
    for message in turns:
        response = api.post("/api/assistant/step", json={
            "message": message, "state": state, "pending": pending, "language": "nl"})
        assert response.status_code == 200, response.text
        payload = response.json()
        state, pending = payload["state"], payload["pending"]
        events.extend(payload["events"])
    # The survey pursues complete documents: every optional field left after
    # the listed answers is offered, and skipping each must reach "ready".
    for _ in range(80):
        if pending is None:
            break
        assert pending.get("required") is False, pending
        response = api.post("/api/assistant/step", json={
            "message": "overslaan", "state": state, "pending": pending,
            "language": "nl"})
        payload = response.json()
        state, pending = payload["state"], payload["pending"]
        events.extend(payload["events"])
    return state, pending, events


def test_the_diesel_archetype_through_the_api(api, monkeypatch):
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(runtime, "extract_json", lambda *args, **kwargs: None)
    turns = ["1000 jerrycans diesel", "ja", "colli", "3A1", "DIESELOLIE",
             "DIESEL FUEL", "25 L", "30 x 25 x 35 cm", "Mooiweer BV",
             "Kade 1, Rotterdam", "Afnemer GmbH", "Hafenstr. 2, Duisburg",
             "Rotterdam", "Duisburg", "Franco", "Rotterdam", "vandaag"]
    state, pending, events = drive(api, turns)
    assert pending is None
    ready = [e for e in events if e["kind"] == "ready"][-1]
    assert "cmr" in ready["documents"]
    assert "placarding_sheet" in ready["documents"]
    product = state["dg_entries"][0]["products"][0]
    assert product["proper_shipping_name"] == "DIESELOLIE (DIESEL FUEL)"


def test_a_plain_steel_consignment_never_meets_the_dg_route(api, monkeypatch):
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(runtime, "extract_json", lambda *args, **kwargs: None)
    turns = ["8 stuks staal hoekprofiel 80x80x8x6000",
             "Mooiweer BV", "Kade 1, Rotterdam", "Afnemer GmbH",
             "Hafenstr. 2, Duisburg", "Rotterdam", "Duisburg", "Franco",
             "Rotterdam", "vandaag"]
    state, pending, events = drive(api, turns)
    assert pending is None
    kinds = [e["kind"] for e in events]
    assert "un_question" not in kinds and "dg_question" not in kinds
    ready = [e for e in events if e["kind"] == "ready"][-1]
    assert ready["documents"] == ["cmr"]
    assert state["doc_values"]["consignee_name"] == "Afnemer GmbH"


def test_the_status_endpoint_tells_the_settings_page_the_truth(api):
    payload = api.get("/api/assistant/status").json()
    assert payload["mode"] == "unavailable"
    assert payload["available"] is False
    assert payload["installed"] is False
    # The shipped pins are real, so the install button may be offered.
    assert payload["installable"] is True


def test_the_model_endpoint_is_admin_only(api):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2, username="user", role="user", active=True)
    response = api.post("/api/assistant/model", json={"action": "remove"})
    assert response.status_code in (401, 403)


@pytest.mark.parametrize("action", ["answer", "revise", "optional", "add_goods"])
def test_no_interview_action_runs_without_the_local_model(api, monkeypatch, action):
    """The owner requires local-model installation, not merely an AI label.

    Hiding a button cannot enforce that requirement: every stateless API
    action, including resuming a populated draft, must enforce it too.
    """
    monkeypatch.setattr(runtime, "installed", lambda: False)
    response = api.post("/api/assistant/step", json={
        "message": "4 pallets parts", "action": action,
        "state": {"modality": "road", "draft_lines": [{"id": 1, "description": "parts", "quantity": 4}]},
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "assistant.model_required"


def test_installed_status_enables_the_assistant(api, monkeypatch):
    monkeypatch.setattr(runtime, "installed", lambda: True)
    payload = api.get("/api/assistant/status").json()
    assert payload["available"] is True
    assert payload["mode"] == "model"
