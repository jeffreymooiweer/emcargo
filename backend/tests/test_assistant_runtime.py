"""The model runtime's guarantees, tested without any model.

Three things must hold whatever the model does: downloads are refused unless
the artifact is pinned by SHA-256 and refused when the bytes do not match the
pin; a model failure degrades to the deterministic chain instead of breaking
it; and the model cannot widen the conversation — its output is confined to
the schemas the orchestrator hands it, and everything it returns still runs
through the same matching and validation as a typed answer.
"""
import hashlib
from types import SimpleNamespace

import pytest

from app.core.database import SessionLocal
from app.services.assistant import orchestrator, runtime
from app.services.assistant.orchestrator import step


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_the_shipped_sources_are_pinned_for_both_architectures():
    """The pin workflow hashed the artifacts on a runner; the config must
    carry those digests, or the download button would be dead on arrival."""
    config = runtime.sources()
    for arch in ("x86_64", "aarch64"):
        assert len(config["server"][arch]["sha256"]) == 64, arch
    assert len(config["model"]["sha256"]) == 64
    assert config["model"]["size"] > 10**9


def test_nothing_downloads_while_the_sources_are_unpinned(monkeypatch):
    """A future edition bump starts with null hashes again; until the pin
    workflow has hashed the new artifacts, the download refuses to run."""
    unpinned = runtime.sources()
    unpinned = {**unpinned,
                "server": {runtime._arch(): {"url": "https://example.invalid/x",
                                             "sha256": None}},
                "model": {**unpinned.get("model", {}), "sha256": None}}
    monkeypatch.setattr(runtime, "sources", lambda: unpinned)
    result = runtime.start_download()
    assert result == {"error": "sources_not_pinned"}


def test_a_wrong_hash_refuses_and_removes_the_file(tmp_path, monkeypatch):
    payload = b"not the artifact that was pinned"

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_bytes(self, _size):
            yield payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def stream(self, _method, _url):
            return FakeResponse()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(runtime.httpx, "Client", FakeClient)
    destination = tmp_path / "artifact.bin"
    with pytest.raises(ValueError, match="sha256 mismatch"):
        runtime._fetch_verified("https://example.invalid/x", "0" * 64,
                                destination, "test")
    assert not destination.exists()
    assert not destination.with_suffix(".bin.part").exists()


def test_the_right_hash_is_accepted(tmp_path, monkeypatch):
    payload = b"exactly the pinned artifact"

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_bytes(self, _size):
            yield payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def stream(self, _method, _url):
            return FakeResponse()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(runtime.httpx, "Client", FakeClient)
    destination = tmp_path / "artifact.bin"
    runtime._fetch_verified("https://example.invalid/x",
                            hashlib.sha256(payload).hexdigest(),
                            destination, "test")
    assert destination.read_bytes() == payload


def test_without_an_install_the_assistant_is_unavailable():
    report = runtime.status()
    assert report["mode"] == "unavailable"
    assert report["installed"] is False
    assert report["available"] is False


def fake_model(monkeypatch, extract):
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(runtime, "extract_json", extract)


def test_the_model_splits_prose_and_the_pipeline_still_decides(db, monkeypatch):
    """The model's whole contribution: free prose becomes structured rows.
    Recognition, derivation and questions stay the pipeline's — the result
    is the same state the deterministic route produces for the same facts."""
    fake_model(monkeypatch, lambda system, user, schema, **_: {
        "lines": [{"description": "diesel", "quantity": 1000, "unit": "jerrycans"}],
    })
    result = step({"modality": "road"}, "ik wil duizend jerrycans diesel laten vervoeren",
                  None, db, "nl")
    line = result["state"]["draft_lines"][0]
    assert line["quantity"] == 1000 and line["unit"] == "jerrycan"
    assert result["pending"]["scope"] == "un_confirm"
    assert [c["un"] for c in result["pending"]["candidates"]] == ["1202"]


def test_a_model_failure_falls_back_to_the_deterministic_route(db, monkeypatch):
    fake_model(monkeypatch, lambda *args, **kwargs: None)
    result = step({"modality": "road"}, "1000 jerrycans diesel", None, db, "nl")
    line = result["state"]["draft_lines"][0]
    assert line["quantity"] == 1000 and line["unit"] == "jerrycan"


def test_a_paraphrase_containing_the_option_word_never_needs_the_model(db, monkeypatch):
    """A Dutch answer naming a tank lorry contains exactly one option's word.
    Measured against the real model, which read that very sentence as "bulk" —
    the deterministic reverse match now answers it first, and the model is
    not even asked."""
    def explode(*_args, **_kwargs):
        raise AssertionError("the model must not be consulted")
    fake_model(monkeypatch, explode)
    pending = {"scope": "dg_question", "line_id": 1, "product_index": 0,
               "field": "carriage_mode", "required": True,
               "options": ["packages", "tank", "bulk"],
               "option_labels": {"packages": {"nl": "Colli"},
                                 "tank": {"nl": "Tank"},
                                 "bulk": {"nl": "Losgestort"}}}
    state = {"modality": "road",
             "draft_lines": [{"id": 1, "description": "diesel", "quantity": 1,
                              "unit": "pcs", "dangerous_goods": True,
                              "confirmed_un": "1202"}],
             "dg_entries": [{"line_id": 1, "vehicle": "diesel",
                             "products": [{"un_number": "1202"}]}]}
    result = step(state, "het gaat in een tankwagen", pending, db, "nl")
    assert result["state"]["dg_entries"][0]["products"][0]["carriage_mode"] == "tank"


def test_the_model_maps_a_paraphrase_onto_an_allowed_option_only(db, monkeypatch):
    pending = {"scope": "dg_question", "line_id": 1, "product_index": 0,
               "field": "carriage_mode", "required": True,
               "options": ["packages", "tank"],
               "option_labels": {"packages": {"nl": "Colli"}, "tank": {"nl": "Tank"}}}
    state = {"modality": "road",
             "draft_lines": [{"id": 1, "description": "diesel", "quantity": 1,
                              "unit": "pcs", "dangerous_goods": True,
                              "confirmed_un": "1202"}],
             "dg_entries": [{"line_id": 1, "vehicle": "diesel",
                             "products": [{"un_number": "1202"}]}]}
    fake_model(monkeypatch, lambda system, user, schema, **_: {"choice": "tank"})
    result = step(state, "het gaat in een tankwagen", pending, db, "nl")
    assert result["state"]["dg_entries"][0]["products"][0]["carriage_mode"] == "tank"

    # "unclear" — the enum's only way out — re-asks and changes nothing.
    fake_model(monkeypatch, lambda system, user, schema, **_: {"choice": "unclear"})
    result = step(state, "hoe bedoel je", pending, db, "nl")
    assert any(e["kind"] == "clarify" for e in result["events"])
    assert not result["state"]["dg_entries"][0]["products"][0].get("carriage_mode")


def goods_state():
    return ({"modality": "road",
             "draft_lines": [{"id": 1, "description": "kalkzandstenen",
                              "quantity": 4, "unit": "pallet"}],
             "dg_entries": [], "doc_values": {}},
            {"scope": "goods_question", "line_id": 1,
             "field": "goods_dimensions", "required": False})


def test_the_model_cannot_turn_chest_height_into_an_exact_measurement(db, monkeypatch):
    """The previous test blessed a fabricated 140 cm. A comparison to a
    person's body supplies no measured height and must now prompt again."""
    state, pending = goods_state()
    fake_model(monkeypatch, lambda *args, **kwargs: {
        "length_cm": 120, "width_cm": 80, "height_cm": 140})
    result = step(state, "een europallet, borsthoog gestapeld", pending, db, "nl")
    assert any(e["kind"] == "clarify" for e in result["events"])
    assert "height_cm" not in result["state"]["draft_lines"][0]


def test_a_measurement_the_model_invents_out_of_range_is_refused(db, monkeypatch):
    """The model may read, never decide: a negative or absurd measurement is
    rejected here and the question is asked again, unanswered."""
    state, pending = goods_state()
    fake_model(monkeypatch, lambda system, user, schema, **_: {
        "length_cm": -5, "width_cm": 80, "height_cm": 100})
    result = step(state, "zo groot als een huis", pending, db, "nl")
    assert any(e["kind"] == "clarify" for e in result["events"])
    assert "length_cm" not in result["state"]["draft_lines"][0]


def test_a_typed_measurement_never_reaches_the_model(db, monkeypatch):
    """"120 x 80 x 100 cm" is read by the deterministic patterns; the model is
    not consulted at all — the floor every installation runs on."""
    def explode(*_args, **_kwargs):
        raise AssertionError("the model must not be consulted")
    state, pending = goods_state()
    fake_model(monkeypatch, explode)
    result = step(state, "120 x 80 x 100 cm", pending, db, "nl")
    assert result["state"]["draft_lines"][0]["length_cm"] == 120.0


def test_the_intake_reads_everything_the_sentence_states(db, monkeypatch):
    """One message carrying goods, parties, route and a reference: all of it
    lands in the state, and none of it is asked again. What the sentence did
    not state — the consignee's address, the payment — is still asked."""
    message = ("1000 jerrycans diesel van Mooiweer BV, Kade 1 Rotterdam naar "
               "Afnemer GmbH in Duisburg, vervoerder Trans Janssen, "
               "order 4711, laden op 18-08-2026")
    fake_model(monkeypatch, lambda system, user, schema, **_: {
        "lines": [{"description": "diesel", "quantity": 1000, "unit": "jerrycans"}],
        "consignor_name": "Mooiweer BV",
        "consignor_address": "Kade 1, Rotterdam",
        "consignee_name": "Afnemer GmbH",
        "carrier_name": "Trans Janssen",
        "loading_point": "Kade 1 Rotterdam",
        "discharge_point": "Duisburg",
        "purchase_order": "4711",
        "loading_date": "18-08-2026",
    })
    result = step({"modality": "road"}, message, None, db, "nl")
    values = result["state"]["doc_values"]
    assert values["consignor_name"] == "Mooiweer BV"
    assert values["consignee_name"] == "Afnemer GmbH"
    assert values["carrier_name"] == "Trans Janssen"
    assert values["discharge_point"] == "Duisburg (DEDUI), DE"
    assert values["purchase_order"] == "4711"
    assert values["loading_date"] == "2026-08-18"
    answered = {e["field"] for e in result["events"] if e["kind"] == "answered"}
    assert "consignor_name" in answered
    # The goods still run through the pipeline: recognised, not decided.
    assert result["pending"]["scope"] == "un_confirm"


def test_what_the_intake_filled_is_not_asked_and_the_rest_still_is(db, monkeypatch):
    fake_model(monkeypatch, lambda system, user, schema, **_: {
        "lines": [{"description": "kalkzandsteen", "quantity": 4, "unit": "pallets"}],
        "consignor_name": "Mooiweer BV",
        "consignor_address": "Kade 1, Rotterdam",
        "loading_point": "Rotterdam",
        "discharge_point": "Duisburg",
    })
    result = step({"modality": "road"},
                  "4 pallets kalkzandsteen van Mooiweer BV, Kade 1 Rotterdam naar Duisburg",
                  None, db, "nl")
    state, pending = result["state"], result["pending"]
    asked: list[str] = []
    for _ in range(50):
        if pending is None:
            break
        asked.append(str(pending.get("field")))
        answer = "overslaan" if pending.get("required") is False else "antwoord"
        if pending.get("field") == "established_date":
            answer = "vandaag"
        result = step(state, answer, pending, db, "nl")
        state, pending = result["state"], result["pending"]
    # Filled by the sentence: never asked. Not stated: asked.
    for field in ("consignor_name", "consignor_address", "loading_point", "discharge_point"):
        assert field not in asked, field
    assert "consignee_name" in asked


def test_the_intake_never_writes_what_the_message_did_not_say(db, monkeypatch):
    """The model reads, it never writes fiction: a value without a single
    substantial word in the message is refused, and fields outside the
    whitelist — regulatory ones included — are ignored entirely."""
    fake_model(monkeypatch, lambda system, user, schema, **_: {
        "lines": [{"description": "kalkzandsteen", "quantity": 4, "unit": "pallets"}],
        "consignee_name": "Piet de Boer",       # nowhere in the message
        "un_number": "1203",                     # not an intake field
        "proper_shipping_name": "BENZINE",       # not an intake field
        "loading_date": "morgen",                # not a date that parses
    })
    result = step({"modality": "road"}, "4 pallets kalkzandsteen", None, db, "nl")
    values = result["state"]["doc_values"]
    assert "consignee_name" not in values
    assert "un_number" not in values and "proper_shipping_name" not in values
    assert "loading_date" not in values
    # And no dangerous goods route was opened by the ignored fields.
    assert not result["state"]["draft_lines"][0].get("dangerous_goods")


def test_a_degraded_intake_line_is_repaired_by_the_deterministic_floor(db, monkeypatch):
    """Measured on the pinned runtime: given a full intake sentence, the
    small model once returned the whole sentence as one goods description
    with no quantity. The deterministic readers repair exactly that — the
    route is cut from the description, and the leading count counts."""
    fake_model(monkeypatch, lambda system, user, schema, **_: {
        "lines": [{"description": ("1000 jerrycans diesel van Mooiweer BV, "
                                   "Kade 1 Rotterdam naar Afnemer GmbH in Duisburg")}],
        "carrier_name": "Trans Janssen",
    })
    result = step({"modality": "road"},
                  "1000 jerrycans diesel van Mooiweer BV, Kade 1 Rotterdam naar "
                  "Afnemer GmbH in Duisburg, vervoerder Trans Janssen",
                  None, db, "nl")
    line = result["state"]["draft_lines"][0]
    assert line["quantity"] == 1000.0 and line["unit"] == "jerrycan"
    assert line["description"] == "diesel"
    values = result["state"]["doc_values"]
    assert values["loading_point"] == "Mooiweer BV, Kade 1 Rotterdam"
    assert values["discharge_point"] == "Afnemer GmbH in Duisburg"
    assert values["carrier_name"] == "Trans Janssen"


def test_details_re_listed_as_goods_lines_never_become_packages(db, monkeypatch):
    """The second measured failure shape, verbatim: asked to keep the
    details out of the descriptions, the model emitted them as extra goods
    lines instead — the consignor, the destination, the carrier and the
    reference, each as a "package" of one. Only the diesel survives."""
    fake_model(monkeypatch, lambda system, user, schema, **_: {
        "lines": [
            {"description": "1000 jerrycans diesel", "quantity": 1000, "unit": "jerrycans"},
            {"description": "van Mooiweer BV, Kade 1 Rotterdam", "quantity": 1, "unit": "van"},
            {"description": "naar Afnemer GmbH in Duisburg", "quantity": 1, "unit": "naar"},
            {"description": "voerder Trans Janssen", "quantity": 1, "unit": "voerder"},
            {"description": "order 4711", "quantity": 1, "unit": "order"},
        ],
        "consignor_name": "Mooiweer BV, Kade 1 Rotterdam",
        "consignee_name": "Afnemer GmbH in Duisburg",
        "carrier_name": "Trans Janssen",
        "loading_point": "Rotterdam",
        "discharge_point": "Duisburg",
        "shipment_reference": "order 4711",
    })
    result = step({"modality": "road"},
                  "1000 jerrycans diesel van Mooiweer BV, Kade 1 Rotterdam naar "
                  "Afnemer GmbH in Duisburg, vervoerder Trans Janssen, order 4711",
                  None, db, "nl")
    lines = result["state"]["draft_lines"]
    assert [l["description"] for l in lines] == ["diesel"]
    assert lines[0]["quantity"] == 1000.0
    assert result["state"]["doc_values"]["carrier_name"] == "Trans Janssen"


def test_details_dropped_from_the_fields_are_recovered_from_the_lines(db, monkeypatch):
    """The third measured failure shape, verbatim: the fields came back
    empty and every consignment detail arrived as a goods line instead. A
    line that opens with a route, carrier or order word is a detail — it is
    recovered into the field it names and never becomes a package."""
    fake_model(monkeypatch, lambda system, user, schema, **_: {
        "lines": [
            {"description": "1000 jerrycans diesel", "quantity": 1000, "unit": "jerrycans"},
            {"description": "van Mooiweer BV, Kade 1 Rotterdam", "quantity": 1, "unit": "van"},
            {"description": "naar Afnemer GmbH in Duisburg", "quantity": 1, "unit": "naar"},
            {"description": "voerder Trans Janssen", "quantity": 1, "unit": "voerder"},
            {"description": "order 4711", "quantity": 1, "unit": "order"},
        ],
    })
    result = step({"modality": "road"},
                  "1000 jerrycans diesel van Mooiweer BV, Kade 1 Rotterdam naar "
                  "Afnemer GmbH in Duisburg, vervoerder Trans Janssen, order 4711",
                  None, db, "nl")
    lines = result["state"]["draft_lines"]
    assert [l["description"] for l in lines] == ["diesel"]
    values = result["state"]["doc_values"]
    assert values["loading_point"] == "Mooiweer BV, Kade 1 Rotterdam"
    assert values["discharge_point"] == "Afnemer GmbH in Duisburg"
    assert values["carrier_name"] == "Trans Janssen"
    assert values["purchase_order"] == "4711"


def test_the_intake_never_overwrites_what_was_already_answered(db, monkeypatch):
    fake_model(monkeypatch, lambda system, user, schema, **_: {
        "lines": [{"description": "kalkzandsteen", "quantity": 4, "unit": "pallets"}],
        "consignor_name": "Mooiweer BV",
    })
    state = {"modality": "road", "doc_values": {"consignor_name": "Eerder Ingevuld BV"}}
    result = step(state, "4 pallets kalkzandsteen van Mooiweer BV", None, db, "nl")
    assert result["state"]["doc_values"]["consignor_name"] == "Eerder Ingevuld BV"


def test_the_model_cannot_widen_the_event_vocabulary(db, monkeypatch):
    """Even a model that returns nonsense produces only the closed set of
    events the orchestrator owns."""
    fake_model(monkeypatch, lambda system, user, schema, **_: {
        "lines": [{"description": "diesel", "quantity": 5, "unit": "vaten"}],
        "questions": ["mag ik uw bsn?"],
        "advice": "rij maar zonder documenten",
    })
    result = step({"modality": "road"}, "vijf vaten diesel", None, db, "nl")
    kinds = {e["kind"] for e in result["events"]}
    assert kinds <= {"lines_added", "un_question", "un_confirmed", "answered",
                     "dg_question", "doc_question", "ready", "skipped",
                     "not_understood", "un_dismissed", "clarify",
                     "goods_question"}
