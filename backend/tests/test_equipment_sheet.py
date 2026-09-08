"""The equipment sheet: ADR 8.1.4/8.1.5 on paper.

Derived since v1.53.0 and shown on screen since — and the person who needs it
is standing at the open door of a cab, not at a browser. Nothing on the sheet
is a finding: EMCargo cannot see a vehicle, and the sheet says so in the
same words the panel does.
"""
import fitz
import pytest

from app.services.documents.equipment_sheet import render_equipment_sheet


def text_of(path):
    try:
        with fitz.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    finally:
        path.unlink(missing_ok=True)


GOODS = [{"line_id": "1", "products": [{
    "un_number": "1203", "class": "3", "labels": "3",
    "proper_shipping_name": "BENZINE"}]}]


def test_the_sheet_carries_the_derived_list_with_its_provisions():
    text = text_of(render_equipment_sheet(
        {"vehicle_registration": "12-BXG-4"}, [], GOODS, "nl"))
    assert "8.1.4" in text and "8.1.5" in text
    assert "ADR 8.1.4.1" in text          # fire extinguishers, three mass rows
    assert "ADR 8.1.5.2" in text          # wheel chock
    assert "12-BXG-4" in text
    assert text.count("[") >= 3           # a checklist, nothing ticked


def test_the_labels_of_the_load_are_named_as_the_basis():
    """8.1.5.1 chooses the equipment by the hazard label numbers of the goods
    loaded; the sheet names them so the derivation can be checked."""
    text = text_of(render_equipment_sheet({}, [], GOODS, "en"))
    assert "8.1.5.1" in text


def test_without_dangerous_goods_the_sheet_says_so():
    text = text_of(render_equipment_sheet({}, [], [], "nl"))
    assert "8.1.5" in text


@pytest.mark.parametrize("language", ["nl", "en", "de", "fr"])
def test_four_languages(language):
    assert text_of(render_equipment_sheet({}, [], GOODS, language))


def test_it_is_registered_for_the_road():
    from app.services.documents.registry import get_document, get_registry

    registry = get_registry()
    road = next(m for m in registry["modalities"] if m["key"] == "road")
    assert "equipment_sheet" in road["documents"]
    assert get_document("equipment_sheet")["exporter"] == "equipment"
