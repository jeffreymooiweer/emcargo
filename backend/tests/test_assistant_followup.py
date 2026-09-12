"""Shipment defects found after the 8.2/10 review.

The old assistant dropped a supplied 800 kg while computing 1536 kg from
dimensions, accepted alternative counts, and wrote a count as the consignor.
These scenarios go through the real calculation and question sources so the
assertions cover resulting shipment facts and the next useful question.
"""
import copy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.services.assistant import orchestrator as assistant, runtime


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(runtime, "installed", lambda: False)
    with TestClient(app), SessionLocal() as session:
        yield session


def begin(db, text="4 pallets machineonderdelen"):
    return assistant.step({"modality": "road"}, text, None, db)


def answer(db, result, text):
    return assistant.step(result["state"], text, result["pending"], db)


@pytest.mark.parametrize("text", ["acht", "acht pallets", "Het zijn acht pallets", "eight pallets", "Es sind acht Paletten", "Ce sont huit palettes"])
def test_spoken_quantity_is_accepted_without_changing_the_goods_unit(db, text):
    result = begin(db)
    revision = assistant.step(result["state"], "", {"scope": "goods_quantity", "field": "quantity", "line_id": 1}, db, action="revise")
    changed = answer(db, revision, text)
    assert changed["state"]["draft_lines"][0]["quantity"] == 8
    assert changed["state"]["draft_lines"][0]["unit"] == "pallet"


@pytest.mark.parametrize("text", ["acht dozen", "4 of 8 pallets", "-8", "ongeveer acht pallets"])
def test_quantity_unit_mismatch_and_ambiguity_leave_the_original_count(db, text):
    result = begin(db)
    revision = assistant.step(result["state"], "", {"scope": "goods_quantity", "field": "quantity", "line_id": 1}, db, action="revise")
    changed = answer(db, revision, text)
    assert changed["state"] == revision["state"]
    assert changed["events"][0]["kind"] == "clarify"


@pytest.mark.parametrize("text", [
    "120 x 80 x 100 cm, totaal 800 kg", "120 x 80 x 100 cm, total 800 kg",
    "120 x 80 x 100 cm, insgesamt 800 kg", "120 x 80 x 100 cm, au total 800 kg",
])
def test_dimensions_never_replace_the_weight_stated_in_the_same_answer(db, text):
    result = answer(db, begin(db), text)
    line = result["state"]["draft_lines"][0]
    assert line["length_cm"] == 120
    assert line["weight_total_kg"] == 800
    assert line["weight_each_kg"] == 200
    assert line["transport_volume_m3"] == pytest.approx(3.84)
    assert len([event for event in result["events"] if event["kind"] == "answered"]) == 2


def test_combined_answer_asks_which_weight_basis_without_losing_dimensions(db):
    result = answer(db, begin(db), "120 x 80 x 100 cm, 800 kg")
    assert result["pending"]["scope"] == "goods_weight_basis"
    result = answer(db, result, "total")
    assert result["state"]["draft_lines"][0]["weight_total_kg"] == 800
    assert result["state"]["draft_lines"][0]["height_cm"] == 100


@pytest.mark.parametrize("text", ["120 x 80 x 100 cm, 800 of 900 kg", "120 x 80 x 100 cm, -800 kg"])
def test_ambiguous_combined_measurements_are_not_partially_saved(db, text):
    result = begin(db)
    before = copy.deepcopy(result["state"])
    changed = answer(db, result, text)
    assert changed["state"] == before
    assert changed["events"][0]["kind"] == "clarify"


def test_quantity_correction_during_sender_question_updates_the_only_matching_line(db):
    result = answer(db, begin(db), "overslaan")
    changed = answer(db, result, "Het zijn acht pallets")
    assert changed["state"]["draft_lines"][0]["quantity"] == 8
    assert not changed["state"]["doc_values"].get("consignor_name")
    assert changed["pending"]["field"] == "consignor_name"


def test_quantity_correction_with_two_matching_lines_asks_instead_of_guessing(db):
    result = begin(db, "4 pallets machineonderdelen; 2 pallets boeken")
    revision = assistant.step(result["state"], "", {"scope": "doc_question", "field": "consignor_name"}, db, action="revise")
    changed = answer(db, revision, "Het zijn acht pallets")
    assert changed["state"] == revision["state"]
    assert changed["events"][0]["reason"] == "wrong_field"


def test_explicit_intake_address_has_the_same_validation_as_a_later_answer(db):
    result = begin(db, "4 pallets onderdelen; adres afzender: Rotterdam")
    assert not result["state"].get("doc_values", {}).get("consignor_address")
    assert result["events"][0]["reason"] == "address"


@pytest.mark.parametrize("text", ["2 of 3 pallets onderdelen", "two or three pallets parts", "zwei oder drei Paletten Teile", "deux ou trois palettes de pièces", "2–3 pallets onderdelen"])
def test_alternative_intake_counts_never_become_a_confirmed_quantity(db, text):
    result = begin(db, text)
    assert not result["state"].get("draft_lines")
    assert result["events"][0]["kind"] == "clarify"


@pytest.mark.parametrize("text", ["4 pallets onderdelen op 2026-12-20", "4 pallets onderdelen op 20-12-2026"])
def test_calendar_date_is_not_mistaken_for_a_quantity_range(db, text):
    result = begin(db, text)
    assert result["state"]["doc_values"]["loading_date"] == "2026-12-20"
    assert result["state"]["draft_lines"][0]["quantity"] == 4


def test_weight_can_be_revised_after_dimensions_and_later_answers(db):
    result = answer(db, begin(db), "120 x 80 x 100 cm, totaal 800 kg")
    result = answer(db, result, "Voorbeeld BV")
    revision = assistant.step(result["state"], "", {"scope": "goods_question", "field": "goods_weight_each", "line_id": 1}, db, action="revise")
    assert revision["pending"]["field"] == "goods_weight_each"
    changed = answer(db, revision, "totaal 1000 kg")
    assert changed["state"]["draft_lines"][0]["weight_total_kg"] == 1000
    assert changed["state"]["draft_lines"][0]["length_cm"] == 120
    assert changed["state"]["doc_values"]["consignor_name"] == "Voorbeeld BV"


def test_a_combined_count_and_measurement_answer_updates_all_stated_facts(db):
    result = answer(db, begin(db), "8 pallets, 120 x 80 x 100 cm, totaal 800 kg")
    line = result["state"]["draft_lines"][0]
    assert line["quantity"] == 8
    assert line["weight_each_kg"] == 100
    assert line["weight_total_kg"] == 800
    assert line["transport_volume_m3"] == pytest.approx(7.68)


def test_a_bare_number_after_dimensions_is_not_assumed_to_be_kilograms(db):
    from app.services.assistant.goods import parse_weight_kg
    assert parse_weight_kg("120 x 80 x 100 cm, 800") is None


def test_revising_dimensions_keeps_the_stated_weight_and_later_answers(db):
    result = answer(db, begin(db), "120 x 80 x 100 cm, totaal 800 kg")
    result = answer(db, result, "Voorbeeld BV")
    revision = assistant.step(result["state"], "", {"scope": "goods_question", "field": "goods_dimensions", "line_id": 1}, db, action="revise")
    changed = answer(db, revision, "120 x 80 x 150 cm")
    assert changed["state"]["draft_lines"][0]["weight_total_kg"] == 800
    assert changed["state"]["draft_lines"][0]["height_cm"] == 150
    assert changed["state"]["doc_values"]["consignor_name"] == "Voorbeeld BV"


def test_real_model_street_only_output_cannot_suppress_the_address_question(db, monkeypatch):
    """The pinned model returned only Kade 1 in all four prose scenarios.

    The source also stated Rotterdam, but saving just the street made the
    application treat an incomplete address as an answered question.
    """
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(runtime, "extract_json", lambda *args, **kwargs: {
        "lines": [{"description": "onderdelen", "quantity": 4, "unit": "pallets"}],
        "fields": {"consignor_name": "Voorbeeld BV", "consignor_address": "Kade 1"},
    })
    result = begin(db, "4 pallets onderdelen van Voorbeeld BV aan Kade 1 in Rotterdam naar Duisburg")
    assert not result["state"]["doc_values"].get("consignor_address")
    result = answer(db, result, "overslaan")
    assert result["pending"]["field"] == "consignor_address"


def test_a_model_timeout_never_turns_the_entire_story_into_one_piece_of_goods(db, monkeypatch):
    """A real busy-runtime timeout stored the narrative as one goods line.

    Recognizing an isolated number is not evidence that a whole prose
    description was understood. A failed model read must keep the draft
    unchanged and ask the user to retry with the original text still present.
    """
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(runtime, "extract_json", lambda *args, **kwargs: None)
    result = begin(db, "Morgen moeten vier pallets onderdelen naar Demo GmbH in Duisburg, vanuit Voorbeeld BV aan Kade 1 in Rotterdam.")
    assert not result["state"].get("draft_lines")
    assert not result["state"].get("doc_values")
    assert result["events"][0]["reason"] == "model_unavailable"
