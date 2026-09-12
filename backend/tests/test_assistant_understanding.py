"""Failures reproduced during the v2.5 assistant review, through real services.

These are shipment data integrity tests: a wrong weight, accepted uncertainty
or invented model fact can reach a transport document. The fixtures include
corrections and multiple facts, not just examples that mirror the parser.
"""
import copy
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.services.assistant import orchestrator as assistant, runtime
from app.services.assistant.goods import parse_weight_kg, parse_dimensions

@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(runtime, "installed", lambda: False)
    with TestClient(app), SessionLocal() as session:
        yield session


def begin(db, text="4 pallets onderdelen ZXQ"):
    return assistant.step({"modality": "road"}, text, None, db)


def answer(db, result, text, **kwargs):
    return assistant.step(result["state"], text, result["pending"], db, **kwargs)


def document_questions(db, result):
    """Leave both optional measurements open to isolate document-field behavior."""
    for _ in range(4):
        if result['pending']['scope'] != 'goods_question':
            return result
        result = answer(db, result, 'overslaan')
    raise AssertionError('Goods questions did not finish')


@pytest.mark.parametrize("text", ["-20 kg", "20 of 30 kg", "20–30 kg", "ongeveer 20 kg", "1.000 kg", "misschien 900", "20 kg en 30 kg"])
def test_uncertain_or_ambiguous_weights_never_become_a_fact(text):
    assert parse_weight_kg(text) is None


def test_count_is_not_weight_and_total_is_distributed_once(db):
    result = answer(db, begin(db), "4 pallets totaal 800 kg")
    line = result["state"]["draft_lines"][0]
    assert line["weight_each_kg"] == 200
    assert line["weight_total_kg"] == 800
    again = assistant.step(result["state"], "", None, db)
    assert again["state"]["draft_lines"][0]["weight_total_kg"] == 800


@pytest.mark.parametrize("text", ["-120 x 80 x 100 cm", "120 x -80 x 100 cm", "ongeveer 120 x 80 x 100 cm", "120 x 80 x 100 of 120 x 80 x 200"])
def test_uncertain_dimensions_are_not_measured_dimensions(text):
    assert parse_dimensions(text) is None


@pytest.mark.parametrize("text", ["ik weet het niet", "geen idee", "I don't know", "ich weiß nicht", "je ne sais pas"])
def test_unknown_party_is_left_open_and_question_is_retained(db, text):
    question = document_questions(db, begin(db))
    assert question["pending"]["field"] == "consignor_name"
    result = answer(db, question, text)
    assert "consignor_name" not in result["state"]["doc_values"]
    assert result["pending"] == question["pending"]
    assert result["events"][0]["reason"] == "unknown"


def test_invalid_calendar_date_never_passes():
    assert assistant._read_date("2026-02-31") is None
    assert assistant._read_date("2028-02-29") == "2028-02-29"


@pytest.mark.parametrize("text", ["geen tank", "niet in een tankwagen", "not a tank", "kein Tank", "pas de tank", "tank of colli", "misschien tank"])
def test_negation_and_uncertainty_never_select_tank(db, text):
    result = answer(db, begin(db, "20 jerrycans diesel"), "ja")
    result = answer(db, result, text)
    assert result["pending"]["field"] == "carriage_mode"
    assert not result["state"]["dg_entries"][0]["products"][0].get("carriage_mode")
    assert result["events"][0]["kind"] == "clarify"


def test_empty_shipment_never_reaches_ready(db):
    result = assistant.step({"modality": "road", "selected_docs": []}, "", None, db)
    assert result["pending"]["scope"] == "goods_intake"
    assert result["review"]["remaining_required"] > 0


def test_missing_count_is_asked_instead_of_assuming_one(db):
    result = begin(db, "machineonderdelen")
    assert result["pending"]["scope"] == "goods_quantity"
    result = answer(db, result, "8")
    assert result["state"]["draft_lines"][0]["quantity"] == 8
    assert not result["state"]["draft_lines"][0].get("quantity_unconfirmed")


def test_many_explicit_facts_and_a_correction_are_not_one_field(db):
    result = document_questions(db, begin(db))
    result = answer(db, result, "Afzender: Voorbeeld BV; ontvanger: Demo GmbH; laadplaats: Rotterdam; losplaats: Duisburg")
    values = result["state"]["doc_values"]
    assert values["consignor_name"] == "Voorbeeld BV"
    assert values["consignee_name"] == "Demo GmbH"
    assert values["loading_point"] == "Rotterdam"
    assert result["pending"]["field"] == "consignor_address"
    changed = answer(db, result, "Correctie: ontvanger: Andere GmbH")
    assert changed["state"]["doc_values"]["consignee_name"] == "Andere GmbH"
    assert changed["pending"]["field"] == "consignor_address"
    assert result["state"]["doc_values"]["consignee_name"] == "Demo GmbH"


def test_intake_understands_labelled_details_without_a_model(db):
    result = begin(db, "4 pallets machineonderdelen van Rotterdam naar Duisburg; Afzender: Voorbeeld BV; ontvanger: Demo GmbH")
    assert len(result["state"]["draft_lines"]) == 1
    assert result["state"]["draft_lines"][0]["description"] == "machineonderdelen"
    assert result["state"]["doc_values"]["consignor_name"] == "Voorbeeld BV"


def test_failed_multiple_fact_answer_is_atomic(db):
    result = document_questions(db, begin(db))
    before = copy.deepcopy(result["state"])
    after = answer(db, result, "Afzender: Voorbeeld BV; laaddatum: 2026-02-31")
    assert after["state"] == before
    assert after["events"][0]["kind"] == "clarify"


def test_required_flag_and_options_are_owned_by_application(db):
    result = answer(db, begin(db, "20 jerrycans diesel"), "ja")
    result["pending"]["required"] = False
    result["pending"]["options"].append("submarine")
    rejected = answer(db, result, "overslaan")
    assert rejected["pending"]["required"]
    rejected = answer(db, result, "submarine")
    assert "submarine" not in rejected["pending"]["options"]
    assert rejected["events"][0]["kind"] == "clarify"


def test_revision_changes_one_fact_and_keeps_later_answers(db):
    result = document_questions(db, begin(db))
    result = answer(db, result, "Afzender: Voorbeeld BV; ontvanger: Demo GmbH")
    revision = assistant.step(result["state"], "", {"scope": "doc_question", "field": "consignor_name"}, db, action="revise")
    assert revision["pending"]["field"] == "consignor_name"
    changed = answer(db, revision, "Andere BV")
    assert changed["state"]["doc_values"]["consignor_name"] == "Andere BV"
    assert changed["state"]["doc_values"]["consignee_name"] == "Demo GmbH"


def test_shared_word_does_not_ground_an_invented_address(db, monkeypatch):
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(runtime, "extract_json", lambda *a, **k: {
        "lines": [{"description": "diesel", "quantity": 1000, "unit": "jerrycans"}],
        "consignor_address": "Kade 999 Rotterdam",
        "consignor_name": "Fiction BV",
    })
    result = begin(db, "1000 jerrycans diesel van Voorbeeld BV, Kade 1 Rotterdam naar Duisburg")
    assert not result["state"]["doc_values"].get("consignor_address")
    assert not result["state"]["doc_values"].get("consignor_name")


def test_imagined_goods_and_quantities_are_not_accepted(db, monkeypatch):
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(runtime, "extract_json", lambda *a, **k: {
        "lines": [{"description": "explosives", "quantity": 999, "unit": "pallets"}],
    })
    result = begin(db, "Ik wil twee pallets machineonderdelen laten vervoeren")
    assert all(l["description"] != "explosives" and l["quantity"] != 999 for l in result["state"].get("draft_lines", []))


def test_weight_answer_to_dimension_question_is_retained_and_basis_is_asked(db):
    result = begin(db, "4 pallets machineonderdelen")
    assert result["pending"]["field"] == "goods_dimensions"
    result = answer(db, result, "800 kg")
    assert result["pending"]["scope"] == "goods_weight_basis"
    result = answer(db, result, "total")
    assert result["state"]["draft_lines"][0]["weight_each_kg"] == 200
    assert result["state"]["draft_lines"][0]["weight_total_kg"] == 800


def test_revising_count_preserves_the_stated_total_not_the_old_division(db):
    result = answer(db, begin(db), "totaal 800 kg")
    revision = assistant.step(result["state"], "", {"scope": "goods_quantity", "field": "quantity", "line_id": 1}, db, action="revise")
    result = answer(db, revision, "8")
    assert result["state"]["draft_lines"][0]["weight_each_kg"] == 100
    assert result["state"]["draft_lines"][0]["weight_total_kg"] == 800


def test_model_cannot_fill_receiver_address_with_the_destination_city(db, monkeypatch):
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(runtime, "extract_json", lambda *a, **k: {
        "fields": {"consignee_name": "Demo GmbH", "consignee_address": "Duisburg", "shipment_reference": "4711", "purchase_order": "4711"},
        "lines": [{"description": "diesel", "quantity": 1000, "unit": "jerrycans"}],
    })
    result = begin(db, "1000 jerrycans diesel van Voorbeeld BV naar Demo GmbH in Duisburg, order 4711")
    values = result["state"]["doc_values"]
    assert values["consignee_name"] == "Demo GmbH"
    assert "consignee_address" not in values
    assert "shipment_reference" not in values
    assert values["purchase_order"] == "4711"


def test_an_explicit_reference_reuses_the_existing_sender_address(db):
    result = document_questions(db, begin(db))
    result = answer(db, result, "Voorbeeld BV")
    result = answer(db, result, "Kade 1, Rotterdam")
    result = answer(db, result, "Demo GmbH")
    assert result["pending"]["field"] == "consignee_address"
    result = answer(db, result, "hetzelfde adres als de afzender")
    assert result["state"]["doc_values"]["consignee_address"] == "Kade 1, Rotterdam"


def test_multi_goods_asks_each_omitted_quantity(db):
    result = begin(db, "4 pallets machineonderdelen; dozen met boeken")
    assert result["pending"]["scope"] == "goods_quantity"
    assert result["pending"]["line_id"] == 2


def test_installation_repairs_the_missing_soname_links(tmp_path):
    library = tmp_path / "libllama-common.so.0.0.10452"
    library.write_bytes(b"synthetic verified library")
    runtime._repair_library_links(tmp_path)
    assert (tmp_path / "libllama-common.so.0").read_bytes() == library.read_bytes()
    assert (tmp_path / "libllama-common.so").resolve().parent == tmp_path


def test_broken_runtime_keeps_the_assistant_available(monkeypatch):
    def broken(): raise OSError("unsupported executable")
    monkeypatch.setattr(runtime, "ensure_server", broken)
    assert runtime.extract_json("question", "answer", {"type": "object"}) is None


def test_changing_package_count_recalculates_dg_quantities(db):
    result = answer(db, begin(db, "20 jerrycans diesel van 25 L"), "ja")
    revision = assistant.step(result["state"], "", {"scope": "goods_quantity", "field": "quantity", "line_id": 1}, db, action="revise")
    result = answer(db, revision, "40")
    product = result["state"]["dg_entries"][0]["products"][0]
    assert product["quantity_packages"] == "40"
    assert product["adr_total_quantity"] == "1000 L"


@pytest.mark.parametrize("text", ["Ich möchte morgen vier Paletten Maschinenteile von Rotterdam nach Duisburg verschicken", "Je voudrais envoyer quatre palettes de pièces mécaniques depuis Rotterdam vers Duisbourg", "I want to ship four pallets of machine parts from Rotterdam to Duisburg"])
def test_spoken_counts_and_intent_work_in_each_interface_language(db, text):
    result = begin(db, text)
    assert result["state"]["draft_lines"][0]["quantity"] == 4
    assert not result["state"]["draft_lines"][0].get("quantity_unconfirmed")


def test_route_answer_fills_both_endpoints_instead_of_one_long_place(db):
    state = {"modality": "road", "draft_lines": [{"id": 1, "description": "goods", "quantity": 1}], "doc_values": {}}
    result = assistant.step(state, "", {"scope": "doc_question", "field": "loading_point"}, db, action="revise")
    result = answer(db, result, "Van Rotterdam naar Duisburg")
    assert result["state"]["doc_values"]["loading_point"] == "Rotterdam"
    assert result["state"]["doc_values"]["discharge_point"] == "Duisburg"


def test_small_mass_units_are_normalised_before_dg_calculation():
    assert parse_weight_kg("25 g") == 0.025
    state = {"dg_entries": [{"line_id": 1, "products": [{}]}]}
    question = {"scope": "dg_question", "line_id": 1, "product_index": 0, "field": "net_explosive_mass", "required": True}
    assistant._apply_answer(state, question, "25 g", "nl")
    assert state["dg_entries"][0]["products"][0]["net_explosive_mass"] == "0.025 kg"
    state["dg_entries"][0]["products"][0].clear()
    result = assistant._apply_answer(state, question, "25 L", "nl")
    assert result[0]["kind"] == "clarify"


def test_model_cannot_use_a_street_number_as_the_goods_count(db, monkeypatch):
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(runtime, "extract_json", lambda *a, **k: {
        "lines": [{"description": "diesel", "quantity": 99, "unit": "jerrycans"}],
        "consignor_address": "Kade 99 Rotterdam",
    })
    result = begin(db, "1000 jerrycans diesel van Voorbeeld BV, Kade 99 Rotterdam naar Duisburg")
    assert result["state"]["draft_lines"][0]["quantity"] == 1000


def test_explicit_individual_packages_are_understood_without_model(db):
    result = answer(db, begin(db, "20 jerrycans diesel"), "ja")
    result = answer(db, result, "het zit in losse verpakkingen")
    assert result["state"]["dg_entries"][0]["products"][0]["carriage_mode"] == "packages"


def test_unrelated_compound_does_not_select_bulk_transport(db):
    result = answer(db, begin(db, "20 jerrycans diesel"), "ja")
    result = answer(db, result, "there is a bulkhead behind the cab")
    assert result["pending"]["field"] == "carriage_mode"
    assert not result["state"]["dg_entries"][0]["products"][0].get("carriage_mode")


@pytest.mark.parametrize("text", ["portable tank", "it goes in a portable tank", "het gaat in een losse tank", "in einem ortsbeweglichen Tank", "dans une citerne mobile"])
def test_portable_tank_never_becomes_a_fixed_tank(db, text):
    """The word tank inside a more specific mode selected the wrong option.

    The distinction must survive both a bare answer and a complete sentence
    in each interface language, without needing the model to repair it.
    """
    result = answer(db, begin(db, "20 jerrycans diesel"), "ja")
    result = answer(db, result, text)
    assert result["state"]["dg_entries"][0]["products"][0]["carriage_mode"] == "portable_tank"


def test_model_interpretation_of_a_choice_requires_explicit_confirmation(db, monkeypatch):
    result = answer(db, begin(db, "20 jerrycans diesel"), "ja")
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(runtime, "extract_json", lambda *a, **k: {"choice": "tank"})
    proposal = answer(db, result, "de vloeistof wordt rechtstreeks in het reservoir op de wagen gepompt")
    assert proposal["events"][0]["reason"] == "confirm_choice"
    assert proposal["events"][0]["suggested_choice"] == "tank"
    assert not proposal["state"]["dg_entries"][0]["products"][0].get("carriage_mode")
    confirmed = answer(db, proposal, "tank")
    assert confirmed["state"]["dg_entries"][0]["products"][0]["carriage_mode"] == "tank"
