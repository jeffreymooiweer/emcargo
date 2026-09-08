"""ADR 8.1.4 and 8.1.5: what has to be aboard, derived from the load.

Equipment was the one heading in `docs/dg-coverage.md` that named itself "the
most common real-world failure" and was absent from every mode. It was absent
for a reason worth stating: EMCargo cannot see a vehicle, so it can never
establish that a wheel chock is in the cab.

What it *can* do is derive the list, and that turns out to be most of the value.
8.1.5.1 says so itself: the equipment is chosen **according to the hazard label
numbers of the goods loaded**, and it points at the transport document to
identify them — which is exactly the document this application produces. So the
label numbers are the input and the checklist is the output.

Three things in the text decide whether the list is right, and each is a test
here:

1. **The eye-rinsing liquid is an exemption, not a requirement.** The footnote to
   8.1.5.2 says it is *not* prescribed for label numbers 1, 1.4, 1.5, 1.6, 2.1,
   2.2 and 2.3. Read the other way round, a truck of propane cylinders would
   carry an eye wash the ADR does not ask for.
2. **The label number is not the class.** Class 2 is "2" in the class column and
   2.1, 2.2 or 2.3 on the label, and that footnote lists the divisions. Reading
   the class column would have made the exemption never apply to gases at all.
3. **The shovel is for solids and liquids.** 8.1.5.3's second footnote limits the
   shovel, the drain seal and the collecting container to solids and liquids with
   label numbers 3, 4.1, 4.3, 8 and 9. A gas cylinder with a subsidiary 8 label
   needs no shovel.

And one that changes the answer rather than adding to it: **8.1.4.2** replaces
the whole extinguisher table with a single 2 kg extinguisher when the load stays
inside 1.1.3.6. That is one of the few places where the exemption makes a visible
difference to what has to be in the cab.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.dg.autofill import prepare_entries
from app.services.dg.compliance import check_adr_equipment, check_compliance

CONFIG = Path(__file__).resolve().parents[1] / "app" / "config" / "dg_compliance.json"


def loaded(un: str, quantity: str = "400", **extra) -> list[dict]:
    """The consignment as the wizard would have prepared it.

    Deliberately routed through `prepare_entries` rather than hand-built: the
    labels column is what this check reads, and that is filled in from Table A
    rather than typed. A hand-built product would test the check against data
    the application never actually produces.
    """
    entries = [{"line_id": "1", "vehicle": "TRAILER-1",
                "products": [dict(un_number=un, adr_total_quantity=quantity, **extra)]}]
    lines = [{"line_id": "1", "quantity": 1, "unit": "kist", "weight_each_kg": 10}]
    return prepare_entries(entries, lines, ["ADR"], "nl")["entries"]


def keys(un: str, quantity: str = "400", **extra) -> list[str]:
    result = check_compliance(loaded(un, quantity, **extra), ["ADR"], "nl")
    return [item["key"] for item in result["adr_equipment"]["items"]]


# --- The table of 8.1.4.1 --------------------------------------------------


def test_the_extinguisher_table_is_the_one_in_the_book():
    """Three rows, read off page 1432 of the Dutch ADR 2025: up to 3.5 tonnes 4
    kg in total, up to 7.5 tonnes 8 kg, above that 12 kg — always two
    extinguishers, always one of at least 2 kg for the engine or the cab."""
    table = json.loads(CONFIG.read_text(encoding="utf-8"))["adr_equipment"]
    assert table["fire_extinguishers"]["rows"] == [
        {"max_mass_tonnes": 3.5, "count": 2, "total_kg": 4, "engine_kg": 2, "extra_kg": 2},
        {"max_mass_tonnes": 7.5, "count": 2, "total_kg": 8, "engine_kg": 2, "extra_kg": 6},
        {"max_mass_tonnes": None, "count": 2, "total_kg": 12, "engine_kg": 2, "extra_kg": 6},
    ]
    assert table["fire_extinguishers"]["exempt"] == {
        "source": "8.1.4.2", "count": 1, "total_kg": 2}


def test_a_load_over_the_threshold_gets_the_whole_table():
    """The maximum permissible mass is a property of the vehicle and EMCargo
    does not know it, so all three rows are given rather than one answer."""
    result = check_compliance(loaded("1203", "400"), ["ADR"], "nl")
    extinguisher = result["adr_equipment"]["items"][0]
    assert extinguisher["rule"] == "ADR 8.1.4.1"
    assert "4 kg" in extinguisher["text"] and "12 kg" in extinguisher["text"]


def test_inside_the_1_1_3_6_exemption_one_extinguisher_of_2_kg_is_enough():
    """8.1.4.2, and one of the few places where the exemption changes what is in
    the cab rather than only what is on the paperwork."""
    result = check_compliance(loaded("1203", "200", transport_category="3"), ["ADR"], "nl")
    assert result["adr_points"]["status"] == "exempt_possible"
    extinguisher = result["adr_equipment"]["items"][0]
    assert extinguisher["rule"] == "ADR 8.1.4.2"
    assert "1.1.3.6" in extinguisher["text"]


# --- 8.1.5.2, and the footnote that is an exemption -----------------------


def test_every_load_carries_the_general_equipment():
    for key in ("wheel_chock", "warning_signs", "warning_vest",
                "portable_lighting", "gloves", "eye_protection"):
        assert key in keys("1203"), key


@pytest.mark.parametrize("un", ["1965", "0004"])
def test_gases_and_explosives_need_no_eye_rinsing_liquid(un):
    """The footnote to 8.1.5.2 exempts label numbers 1, 1.4, 1.5, 1.6, 2.1, 2.2
    and 2.3. UN 1965 is propane (2.1), UN 0004 an explosive (1)."""
    assert "eye_rinsing_liquid" not in keys(un)


def test_a_flammable_liquid_does_need_it():
    assert "eye_rinsing_liquid" in keys("1203")


def test_one_exempt_label_does_not_exempt_the_whole_load():
    """UN 1005 is anhydrous ammonia: label 2.3, which is on the exempt list, plus
    a subsidiary 8, which is not. One package that needs the eye wash puts it on
    the unit."""
    assert "eye_rinsing_liquid" in keys("1005")


# --- 8.1.5.3, the additions per class -------------------------------------


def test_a_toxic_gas_puts_an_escape_mask_aboard():
    """Prescribed for label numbers 2.3 and 6.1, per crew member."""
    assert "escape_mask" in keys("1005")
    assert "escape_mask" not in keys("1203")


def test_a_toxic_liquid_puts_one_aboard_too():
    assert "escape_mask" in keys("1098")  # allyl alcohol, 6.1 (3)


def test_the_spill_kit_follows_the_labels_the_footnote_lists():
    """Shovel, drain seal and collecting container for labels 3, 4.1, 4.3, 8 and
    9 — and for those only."""
    for un in ("1203", "1830", "3480"):  # 3, 8, 9
        assert "shovel" in keys(un), un
    assert "shovel" not in keys("0004")  # class 1


def test_a_gas_cylinder_needs_no_shovel_even_with_a_corrosive_label():
    """The second footnote to 8.1.5.3 limits these three to *solids and liquids*.
    UN 1005 carries label 8 and is a gas; a shovel is of no use to it."""
    assert "shovel" not in keys("1005")
    assert "drain_seal" not in keys("1005")


def test_the_label_numbers_the_list_was_built_from_are_reported():
    """A checklist a user disagrees with has to be traceable to its input."""
    result = check_compliance(loaded("1005"), ["ADR"], "nl")
    assert result["adr_equipment"]["labels"] == ["2.3", "8"]


# --- Where it applies, and what it does not claim --------------------------


def test_the_check_is_road_only():
    """8.1 is part of ADR Part 8, the road-specific part. RID has its own
    provisions for the train crew and the IMDG Code addresses the ship."""
    goods = loaded("1203")
    assert "adr_equipment" in check_compliance(goods, ["ADR"], "nl")
    for profile in ("RID", "ADN", "IMDG", "IATA_DGR"):
        assert "adr_equipment" not in check_compliance(goods, [profile], "nl"), profile


def test_a_consignment_without_dangerous_goods_gets_no_list():
    result = check_adr_equipment([{"line_id": "1", "products": []}], "nl")
    assert result["status"] == "not_checked"
    assert result["items"] == []


def test_a_forbidden_substance_does_not_put_equipment_aboard():
    """There is nothing to equip for something that may not be carried, and the
    prohibition is already in view."""
    result = check_adr_equipment(
        [{"line_id": "1", "products": [
            {"un_number": "1051", "labels": "6.1+3", "transport_forbidden": True}]}],
        "nl")
    assert result["status"] == "not_checked"


def test_the_answer_says_it_is_a_checklist_and_not_a_finding():
    """The honest limit of this section: the application cannot see a vehicle.
    Presenting a derived list as a verified one would be worse than not deriving
    it."""
    result = check_compliance(loaded("1203"), ["ADR"], "nl")["adr_equipment"]
    assert "8.1.5.1" in result["note"]
    assert "niet" in result["note"]


@pytest.mark.parametrize("language", ["nl", "en", "de", "fr"])
def test_every_item_is_written_in_the_language_of_the_screen(language):
    result = check_adr_equipment(loaded("1005"), language)
    assert result["items"]
    assert all(item["text"] for item in result["items"])
    assert result["note"]
