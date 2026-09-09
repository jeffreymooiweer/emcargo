"""The assistant chain, end to end and without any language model.

The deterministic floor of the design: parser, name recognition, the open
questions of dg/prepare and the registry's required fields carry a complete
conversation from "1000 jerrycans diesel" to a consignment ready for export.
A model (phase 23) may read free text more flexibly; it can never change what
is asked or what may be answered, because the orchestrator owns both lists —
which is exactly what these tests pin.
"""
import pytest

from app.core.database import SessionLocal
from app.services.assistant.orchestrator import step


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def fresh_state():
    return {"modality": "road", "draft_lines": [], "dg_entries": [], "doc_values": {}}


def drive(db, turns, state=None, pending=None):
    events = []
    state = state or fresh_state()
    for message in turns:
        result = step(state, message, pending, db, "nl")
        state, pending = result["state"], result["pending"]
        events.extend(result["events"])
    return state, pending, events


def skip_rest(db, state, pending, events):
    """Skip through the optional remainder; every question left after the
    listed answers must be skippable, or the ride can never end."""
    for _ in range(80):
        if pending is None:
            return state, pending, events
        assert pending.get("required") is False, pending
        result = step(state, "overslaan", pending, db, "nl")
        state, pending = result["state"], result["pending"]
        events.extend(result["events"])
    raise AssertionError("the optional questions never ran out")


def test_the_first_message_becomes_goods_lines_through_the_real_pipeline(db):
    state, pending, events = drive(db, ["1000 jerrycans diesel"])
    assert [e["kind"] for e in events][0] == "lines_added"
    line = state["draft_lines"][0]
    assert line["quantity"] == 1000 and line["unit"] == "jerrycan"
    # The recognition offered UN 1202; the assistant asks, it never decides.
    assert pending["scope"] == "un_confirm"
    assert [c["un"] for c in pending["candidates"]] == ["1202"]
    assert not line.get("confirmed_un")


def test_confirming_records_the_un_and_the_backend_s_questions_take_over(db):
    state, pending, events = drive(db, ["1000 jerrycans diesel", "ja"])
    assert state["draft_lines"][0]["confirmed_un"] == "1202"
    # The next question is dg/prepare's own, options included.
    assert pending["scope"] == "dg_question"
    assert pending["field"] == "carriage_mode"
    assert "packages" in pending["options"]


def test_answers_match_labels_as_well_as_values(db):
    """The stored value is "packages"; the person typed "colli". Both are the
    same answer, through the option labels the wizard already carries."""
    state, pending, _ = drive(db, ["1000 jerrycans diesel", "ja", "colli"])
    product = state["dg_entries"][0]["products"][0]
    assert product["carriage_mode"] == "packages"
    # Next: what kind of jerrican — the 5.4.1.1.1 (e) packaging code choice.
    assert pending["field"] == "type_of_package"
    assert pending["reason"] == "packaging_spec"
    state, pending, _ = drive(db, ["3A1"], state, pending)
    assert state["dg_entries"][0]["products"][0]["type_of_package"].startswith("3A1")
    assert pending["field"] == "chosen_name"
    assert pending["options"] == ["DIESELOLIE", "GASOLIE", "STOOKOLIE, LICHT"]


def test_a_wrong_option_answer_is_corrected_with_the_attempt_named(db):
    state, pending, events = drive(
        db, ["1000 jerrycans diesel", "ja", "per onderzeeboot"])
    clarify = [e for e in events if e["kind"] == "clarify"]
    assert clarify and clarify[0]["attempt"] == "per onderzeeboot"
    assert pending["field"] == "carriage_mode"
    assert not state["dg_entries"][0]["products"][0].get("carriage_mode")


def test_the_whole_diesel_ride_reaches_ready_without_a_model(db):
    turns = ["1000 jerrycans diesel", "ja", "colli", "3A1", "DIESELOLIE",
             "DIESEL FUEL", "25 L", "30 x 25 x 35 cm", "Mooiweer BV",
             "Kade 1, Rotterdam", "Afnemer GmbH", "Hafenstr. 2, Duisburg",
             "Rotterdam", "Duisburg", "Franco", "Rotterdam", "vandaag"]
    state, pending, events = drive(db, turns)
    state, pending, events = skip_rest(db, state, pending, events)
    assert pending is None
    ready = [e for e in events if e["kind"] == "ready"]
    assert ready and "cmr" in ready[-1]["documents"]
    product = state["dg_entries"][0]["products"][0]
    # Everything came through the same derivation the wizard uses.
    assert product["proper_shipping_name"] == "DIESELOLIE (DIESEL FUEL)"
    assert product["adr_total_quantity"] == "25000 L"
    assert state["doc_values"]["freight_payment"] == "prepaid"
    assert state["doc_values"]["established_date"].count("-") == 2


def test_rejecting_the_recognition_clears_the_dg_route(db):
    state, pending, events = drive(db, ["1000 jerrycans diesel", "nee"])
    assert any(e["kind"] == "un_dismissed" for e in events)
    assert state["draft_lines"][0]["dg_dismissed"] is True
    # No DG questions follow; what is left is about the goods themselves
    # and about the document, never about a regulation.
    assert pending is None or pending["scope"] in ("goods_question", "doc_question")


def test_optional_questions_can_be_skipped_required_ones_cannot(db):
    state, pending, _ = drive(
        db, ["1000 jerrycans diesel", "ja", "skip"])
    # carriage_mode is required: skip does not move past it.
    assert pending["field"] == "carriage_mode"


def test_the_assistant_never_asks_a_question_of_its_own(db):
    """Every question the conversation raised is either a recognition
    confirmation, an open question of dg/prepare, or a registry field — the
    three lists the backend owns."""
    _state, _pending, events = drive(
        db, ["1000 jerrycans diesel", "ja", "colli", "overslaan",
             "DIESELOLIE", "DIESEL FUEL", "25 L"])
    kinds = {e["kind"] for e in events}
    assert kinds <= {"lines_added", "un_question", "un_confirmed", "answered",
                     "dg_question", "doc_question", "ready", "skipped",
                     "not_understood", "un_dismissed", "clarify",
                     "goods_question"}


def test_the_content_per_package_is_read_from_the_sentence(db):
    """"1000 jerrycans van 25l met benzine" already says what one jerrican
    holds; the assistant must not ask for it again — and the goods line must
    read "benzine", not the leftover "van 25l met benzine"."""
    state, pending, _ = drive(db, ["1000 jerrycans van 25l met benzine", "ja"])
    line = state["draft_lines"][0]
    assert line["description"] == "benzine"
    assert line["package_content"] == "25 L"
    product = state["dg_entries"][0]["products"][0]
    assert product["net_mass_liters_per_package"] == "25 L"
    assert product["quantity_packages"] == "1000"
    assert product["adr_total_quantity"] == "25000 L"


def test_the_content_reads_for_drums_too_not_only_jerricans(db):
    state, pending, _ = drive(db, ["10 vaten à 200 liter dieselolie", "ja"])
    line = state["draft_lines"][0]
    assert line["package_content"] == "200 L"
    product = state["dg_entries"][0]["products"][0]
    assert product["net_mass_liters_per_package"] == "200 L"
    assert product["adr_total_quantity"] == "2000 L"


def test_the_packaging_kind_question_offers_the_un_codes(db):
    """A jerrican is a shape, not a specification; the catalogue's kinds of
    jerrican (steel 3A1 against plastic 3H1) become the optional choice."""
    _state, pending, _ = drive(db, ["1000 jerrycans diesel", "ja", "colli"])
    assert pending["field"] == "type_of_package"
    assert pending["required"] is False
    codes = {option.split()[0] for option in pending["options"]}
    assert {"3A1", "3H1"} <= codes


def test_a_vague_amount_gets_a_follow_up_with_an_example(db):
    state, pending, events = drive(
        db, ["1000 jerrycans diesel", "ja", "colli", "overslaan",
             "DIESELOLIE", "DIESEL FUEL", "vijfentwintig liter ofzo"])
    clarify = [e for e in events if e["kind"] == "clarify"]
    assert clarify and clarify[-1]["example"] == "25 L"
    assert pending["field"] == "net_mass_liters_per_package"
    assert not state["dg_entries"][0]["products"][0].get(
        "net_mass_liters_per_package")


def test_a_bare_number_where_the_unit_matters_gets_the_same_follow_up(db):
    """"25" per package could be litres or kilograms, and 1.1.3.6 computes
    differently with each; the follow-up shows what a full answer looks like."""
    _state, pending, events = drive(
        db, ["1000 jerrycans diesel", "ja", "colli", "overslaan",
             "DIESELOLIE", "DIESEL FUEL", "25"])
    assert [e for e in events if e["kind"] == "clarify"]
    assert pending["field"] == "net_mass_liters_per_package"


def test_a_typed_date_is_understood_day_first_and_nonsense_is_asked_again(db):
    turns = ["1000 jerrycans diesel", "ja", "colli", "3A1", "DIESELOLIE",
             "DIESEL FUEL", "25 L", "overslaan", "Mooiweer BV",
             "Kade 1, Rotterdam", "Afnemer GmbH", "Hafenstr. 2, Duisburg",
             "Rotterdam", "Duisburg", "Franco", "Rotterdam"]
    state, pending, _ = drive(db, turns)
    assert pending["field"] == "established_date"
    state, pending, events = drive(db, ["binnenkort ofzo"], state, pending)
    assert [e for e in events if e["kind"] == "clarify"]
    assert pending["field"] == "established_date"
    state, pending, _ = drive(db, ["16-08-2026"], state, pending)
    assert state["doc_values"]["established_date"] == "2026-08-16"


def test_optional_details_are_an_explicit_choice_after_essential_questions(db):
    """Complete documents are the goal: after the required fields the optional
    ones follow, every one of them skippable — the ride ends on ready."""
    turns = ["1000 jerrycans diesel", "ja", "colli", "3A1", "DIESELOLIE",
             "DIESEL FUEL", "25 L", "overslaan", "Mooiweer BV",
             "Kade 1, Rotterdam", "Afnemer GmbH", "Hafenstr. 2, Duisburg",
             "Rotterdam", "Duisburg", "Franco", "Rotterdam", "vandaag"]
    state, pending, events = drive(db, turns)
    assert pending is None
    result = step(state, "", None, db, "nl", action="optional")
    state, pending = result["state"], result["pending"]
    assert pending is not None and pending["required"] is False
    state, pending, events = skip_rest(db, state, pending, events)
    assert pending is None
    assert [e for e in events if e["kind"] == "ready"]


def test_the_question_carries_its_lay_phrasing_and_its_help(db):
    _state, pending, _ = drive(db, ["1000 jerrycans diesel", "ja"])
    assert pending["field"] == "carriage_mode"
    assert "vervoerd" in pending["simple"]["nl"]
    assert pending["help"]["nl"]


def test_the_state_travels_and_nothing_is_stored_server_side(db):
    """Stateless contract: the same call with the same state and message is
    reproducible, and the input state object is not mutated."""
    state = fresh_state()
    before = str(state)
    step(state, "1000 jerrycans diesel", None, db, "nl")
    assert str(state) == before
