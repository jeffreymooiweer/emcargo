"""The LQ/EQ check of chapters 3.4 and 3.5.

The LQ value (column 7a) and the E code (column 7b) had been in the data for
years and were shown with their meaning, but never compared with what had been
filled in. These tests record that comparison: the limits themselves were
verified against ADR 3.4.2/3.4.3 (30 kg gross, 20 kg for foil trays), table
3.5.1.2 (E codes) and 3.5.5 (at most 1000 packages).

Just as important is what the check does *not* do: a line within the limits is
reported, but never disappears from the 1.1.3.6 points count — qualifying on
quantity is not the same as being exempt.
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.main import app
from app.services.dg.compliance import check_compliance, check_lq_eq


def _entry(products: list[dict]) -> list[dict]:
    return [{"vehicle": "TRAILER-1", "line_id": "1", "products": products}]


def _product(**overrides) -> dict:
    base = {
        "un_number": "1263",
        "proper_shipping_name": "PAINT",
        "class": "3",
        "packing_group": "II",
        "limited_quantity": "5 L",
        "excepted_quantity": "E2",
    }
    base.update(overrides)
    return base


def _single(result: dict) -> dict:
    assert len(result["rows"]) == 1
    return result["rows"][0]


# --- LQ (3.4) -----------------------------------------------------------


def test_lq_within_limits_names_both_boundaries():
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="0,5 L",
                         gross_mass_per_package="20 kg")]),
        language="nl", profiles=["ADR"],
    )
    row = _single(result)
    assert row["lq"]["status"] == "within_limits"
    assert "5 L" in row["lq"]["message"]
    assert "30 kg" in row["lq"]["message"]
    # The exemption does not take the line out of the points count.
    assert "1.1.3.6.5" in row["lq"]["message"]
    assert result["status"] == "checked"


def test_lq_points_note_is_absent_without_a_land_profile():
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="0,5 L",
                         gross_mass_per_package="20 kg")]),
        language="nl", profiles=["IMDG"],
    )
    row = _single(result)
    assert row["lq"]["status"] == "within_limits"
    assert "1.1.3.6.5" not in row["lq"]["message"]


def test_lq_inner_packaging_above_the_column_7a_limit():
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="6 L",
                         gross_mass_per_package="20 kg")]),
        profiles=["ADR"],
    )
    assert _single(result)["lq"]["status"] == "not_within"


def test_lq_gross_mass_above_30_kg_disqualifies_the_package():
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="0,5 L",
                         gross_mass_per_package="35 kg")]),
        profiles=["ADR"],
    )
    row = _single(result)
    assert row["lq"]["status"] == "not_within"
    assert "35" in row["lq"]["message"]


def test_lq_zero_means_not_permitted():
    result = check_lq_eq(
        _entry([_product(limited_quantity="0", net_per_inner_packaging="0,5 L")]),
        profiles=["ADR"],
    )
    assert _single(result)["lq"]["status"] == "not_permitted"


def test_lq_without_inner_quantity_is_incomplete_not_silent():
    result = check_lq_eq(_entry([_product()]), profiles=["ADR"])
    row = _single(result)
    assert row["lq"]["status"] == "incomplete"
    assert result["status"] == "incomplete"


def test_a_number_without_a_unit_is_not_guessed_at():
    # "0,5" can mean 0.5 g or 0.5 kg; guessing is more dangerous here than asking.
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="0,5",
                         gross_mass_per_package="20 kg")]),
        profiles=["ADR"],
    )
    assert _single(result)["lq"]["status"] == "incomplete"


def test_mass_input_against_a_volume_limit_is_flagged_not_compared():
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="500 g",
                         gross_mass_per_package="20 kg")]),
        profiles=["ADR"],
    )
    row = _single(result)
    assert row["lq"]["status"] == "incomplete"
    assert "5 L" in row["lq"]["message"]


def test_lq_alternative_limits_match_the_kind_of_the_input():
    # UN 3175 style: "500 ml oder 500 g" — the variant of the entered unit counts.
    result = check_lq_eq(
        _entry([_product(limited_quantity="500 ml oder 500 g",
                         net_per_inner_packaging="300 g",
                         gross_mass_per_package="20 kg")]),
        profiles=["ADR"],
    )
    assert _single(result)["lq"]["status"] == "within_limits"


def test_a_special_provision_reference_is_reported_as_unreadable():
    result = check_lq_eq(
        _entry([_product(limited_quantity="siehe SV 251",
                         net_per_inner_packaging="1 L")]),
        language="en", profiles=["ADR"],
    )
    row = _single(result)
    assert row["lq"]["status"] == "no_data"
    assert "special provision" in row["lq"]["message"]


# --- EQ (3.5) -----------------------------------------------------------


def test_eq_within_the_e2_limits():
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="25 g",
                         net_mass_liters_per_package="400 g",
                         gross_mass_per_package="20 kg")]),
        profiles=["ADR"],
    )
    row = _single(result)
    assert row["eq"]["status"] == "within_limits"
    assert "E2" in row["eq"]["message"]


def test_eq_inner_packaging_above_the_code_limit():
    # E2: ten hoogste 30 g/ml per binnenverpakking (tabel 3.5.1.2).
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="40 g",
                         net_mass_liters_per_package="400 g")]),
        profiles=["ADR"],
    )
    assert _single(result)["eq"]["status"] == "not_within"


def test_eq_outer_packaging_above_the_code_limit():
    # E2: ten hoogste 500 g/ml per buitenverpakking.
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="25 g",
                         net_mass_liters_per_package="600 g")]),
        profiles=["ADR"],
    )
    assert _single(result)["eq"]["status"] == "not_within"


def test_e0_is_not_permitted_as_excepted_quantity():
    result = check_lq_eq(
        _entry([_product(excepted_quantity="E0", net_per_inner_packaging="1 g")]),
        profiles=["ADR"],
    )
    assert _single(result)["eq"]["status"] == "not_permitted"


def test_eq_package_cap_of_3_5_5_raises_a_warning():
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="25 g",
                         net_mass_liters_per_package="400 g",
                         gross_mass_per_package="20 kg",
                         quantity_packages="1200")]),
        profiles=["ADR"],
    )
    assert any(w["rule"] == "ADR/IMDG 3.5.5" for w in result["warnings"])


def test_no_warning_when_the_position_stays_under_1000_packages():
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="25 g",
                         net_mass_liters_per_package="400 g",
                         gross_mass_per_package="20 kg",
                         quantity_packages="900")]),
        profiles=["ADR"],
    )
    assert result["warnings"] == []


# --- Basis and profiles ---------------------------------------------------


def test_rid_gets_the_same_basis_note_as_the_points_table():
    result = check_lq_eq(_entry([_product()]), language="en", profiles=["RID"])
    assert result["basis_note"] and "RID" in result["basis_note"]


def test_adr_alone_carries_no_basis_note():
    result = check_lq_eq(_entry([_product()]), profiles=["ADR"])
    assert result["basis_note"] is None


def test_no_dangerous_goods_means_not_checked():
    result = check_lq_eq(_entry([{"description": "geen UN"}]), profiles=["ADR"])
    assert result["status"] == "not_checked"
    assert result["rows"] == []


def test_imdg_profile_fills_a_missing_value_from_the_dgl():
    # UN 1203 is in the IMDG list with "1 L"/E2; without an ADR value on the
    # product, the list supplies the limit.
    result = check_lq_eq(
        _entry([{
            "un_number": "1203",
            "proper_shipping_name": "GASOLINE",
            "class": "3",
            "packing_group": "II",
            "net_per_inner_packaging": "0,5 L",
            "gross_mass_per_package": "20 kg",
        }]),
        profiles=["IMDG"],
    )
    row = _single(result)
    assert row["lq"]["value"] == "1 L"  # aangevuld uit de IMDG-lijst
    assert row["lq"]["status"] == "within_limits"
    assert "1 L" in row["lq"]["message"]


def test_a_differing_imdg_value_is_flagged_next_to_the_adr_outcome():
    result = check_lq_eq(
        _entry([_product(un_number="1203", limited_quantity="2 L",
                         net_per_inner_packaging="0,5 L",
                         gross_mass_per_package="20 kg")]),
        language="en", profiles=["IMDG"],
    )
    row = _single(result)
    assert row["lq"]["status"] == "within_limits"
    assert "42-24" in row["lq"]["message"]
    assert "1 L" in row["lq"]["message"]


# --- Integration with check_compliance and the API ------------------------


def test_check_compliance_includes_lq_eq_for_land_and_sea_profiles():
    outcome = check_compliance(_entry([_product()]), ["ADR"], "nl")
    assert outcome["lq_eq"]["status"] == "incomplete"

    outcome = check_compliance(_entry([_product()]), ["IMDG"], "nl")
    assert "lq_eq" in outcome


def test_check_compliance_omits_lq_eq_for_air_only():
    # Air has its own LQ system in the Y packing instructions, which EMCargo
    # does not carry; showing an ADR result would be a claim.
    outcome = check_compliance(_entry([_product()]), ["IATA_DGR"], "nl")
    assert "lq_eq" not in outcome


def test_the_points_table_is_not_reduced_by_a_qualifying_lq_line():
    products = [_product(
        transport_category="2",
        adr_total_quantity="100 L",
        net_per_inner_packaging="0,5 L",
        gross_mass_per_package="20 kg",
    )]
    outcome = check_compliance(_entry(products), ["ADR"], "nl")
    lq_row = outcome["lq_eq"]["rows"][0]
    assert lq_row["lq"]["status"] == "within_limits"
    # 100 L × factor 3 simply stays in the count.
    assert outcome["adr_points"]["total_points"] == 300.0


def _post(payload: dict):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, username="test", role="admin", active=True
    )
    try:
        with TestClient(app) as client:
            return client.post("/api/dg/compliance", json=payload)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_the_api_returns_the_lq_eq_result_for_the_road_wizard_payload():
    response = _post({
        "entries": _entry([_product(net_per_inner_packaging="0,5 L",
                                    gross_mass_per_package="20 kg")]),
        "profiles": ["ADR"],
        "language": "en",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lq_eq"]["status"] == "checked"
    assert body["lq_eq"]["rows"][0]["lq"]["status"] == "within_limits"


def test_a_zero_inner_quantity_is_rejected_at_the_boundary():
    response = _post({
        "entries": _entry([_product(net_per_inner_packaging="0 L")]),
        "profiles": ["ADR"],
        "language": "en",
    })
    assert response.status_code == 422


# --- The two provisions that only show up across lines ---------------------
#
# 3.5.1.3 and 3.5.1.4 were both read from ADR 2025 and both left unimplemented
# for several releases, and they fail in opposite directions: the first lets a
# package through that the text caps, the second refuses a load the text
# permits. Neither can be seen while assessing one line at a time, which is why
# they sat unnoticed.


def _eq(**overrides) -> dict:
    base = {
        "un_number": "1263",
        "class": "3",
        "packing_group": "II",
        "limited_quantity": "0",
        "excepted_quantity": "E1",
        "net_per_inner_packaging": "20 g",
        "net_mass_liters_per_package": "400 g",
    }
    base.update(overrides)
    return base


def test_mixed_e_codes_in_one_outer_packaging_are_capped_by_the_strictest():
    """ADR/IMDG 3.5.1.3. E1 allows 1000 g per outer packaging and E3 allows 300.
    Packed together, 300 is the cap for the two of them — and 400 + 200 is over
    it, while each line on its own is comfortably within its own code. That is
    exactly the package the old line-by-line check waved through."""
    products = [
        _eq(excepted_quantity="E1", net_mass_liters_per_package="400 g"),
        _eq(un_number="1993", excepted_quantity="E3", net_mass_liters_per_package="200 g"),
    ]
    result = check_lq_eq(_entry(products), "nl", ["ADR"])

    together = [w for w in result["warnings"] if w["rule"] == "ADR/IMDG 3.5.1.3"]
    assert together, result["warnings"]
    assert "300" in together[0]["message"]
    assert "E3" in together[0]["message"]
    # Both lines are named: the fault is the combination, not one of the two.
    assert "UN 1263" in together[0]["products"] and "UN 1993" in together[0]["products"]


def test_mixed_e_codes_that_stay_under_the_strictest_cap_are_not_reported():
    products = [
        _eq(excepted_quantity="E1", net_mass_liters_per_package="200 g"),
        _eq(un_number="1993", excepted_quantity="E3", net_mass_liters_per_package="50 g"),
    ]
    result = check_lq_eq(_entry(products), "nl", ["ADR"])
    assert [w for w in result["warnings"] if w["rule"] == "ADR/IMDG 3.5.1.3"] == []


def test_one_e_code_twice_is_not_a_mixed_packing():
    """3.5.1.3 applies where goods "to which different codes are assigned" are
    packed together. Two lines of the same code are governed by their own code's
    limit, which the per-line check already applies."""
    products = [
        _eq(excepted_quantity="E3", net_mass_liters_per_package="200 g"),
        _eq(un_number="1993", excepted_quantity="E3", net_mass_liters_per_package="200 g"),
    ]
    result = check_lq_eq(_entry(products), "nl", ["ADR"])
    assert [w for w in result["warnings"] if w["rule"] == "ADR/IMDG 3.5.1.3"] == []


def test_the_smallest_quantities_are_relieved_by_3_5_1_4():
    """1 g per inner packaging and 100 g per package, under E1: only 3.5.2 and
    3.5.3 apply. The message says so, because a user reading "within the limits
    of E1" would otherwise go on to apply the mark and the package cap."""
    result = check_lq_eq(
        _entry([_eq(net_per_inner_packaging="1 g", net_mass_liters_per_package="100 g")]),
        "nl", ["ADR"],
    )
    row = _single(result)["eq"]
    assert row["status"] == "within_limits"
    assert row.get("relief_3_5_1_4") is True
    assert "3.5.1.4" in row["message"]


def test_a_hair_over_the_relief_limit_is_not_relieved():
    """The boundary is the whole content of 3.5.1.4: 101 g per outer packaging is
    an ordinary E1 package again, with the mark and the cap."""
    result = check_lq_eq(
        _entry([_eq(net_per_inner_packaging="1 g", net_mass_liters_per_package="101 g")]),
        "nl", ["ADR"],
    )
    row = _single(result)["eq"]
    assert row["status"] == "within_limits"
    assert "relief_3_5_1_4" not in row


def test_e3_is_not_relieved_however_small_the_quantity():
    """3.5.1.4 lists E1, E2, E4 and E5 and leaves E3 out. Reading "the smallest
    quantities" as a rule about quantities alone would relieve a code the text
    does not name."""
    result = check_lq_eq(
        _entry([_eq(excepted_quantity="E3", net_per_inner_packaging="1 g",
                    net_mass_liters_per_package="50 g")]),
        "nl", ["ADR"],
    )
    assert "relief_3_5_1_4" not in _single(result)["eq"]


def test_relieved_packages_do_not_count_towards_the_1000_of_3_5_5():
    """The consequence that makes 3.5.1.4 more than a sentence on screen. 3.5.5
    is part of chapter 3.5 and 3.5.1.4 leaves only 3.5.2 and 3.5.3 standing, so
    counting these packages would refuse a load the text permits."""
    relieved = _eq(net_per_inner_packaging="1 g", net_mass_liters_per_package="100 g",
                   quantity_packages="1500")
    result = check_lq_eq(_entry([relieved]), "nl", ["ADR"])
    assert [w for w in result["warnings"] if w["rule"] == "ADR/IMDG 3.5.5"] == []

    ordinary = _eq(net_per_inner_packaging="20 g", net_mass_liters_per_package="400 g",
                   quantity_packages="1500")
    result = check_lq_eq(_entry([ordinary]), "nl", ["ADR"])
    assert [w for w in result["warnings"] if w["rule"] == "ADR/IMDG 3.5.5"]


# --- what the sea asks that the land does not (IMDG 3.4, read 2026-08-26) ---


def test_a_sea_lq_line_is_told_about_ltd_qty_and_the_unit_mark():
    """IMDG 3.4.6.1 and 3.4.5.5, the two duties ADR's chapter 3.4 does not have.

    On land chapter 3.4 lifts the transport document altogether; at sea
    chapter 5.4 stays applicable (3.4.1.2.5) and "LTD QTY" joins the
    description. And the sea's unit mark turns on no tonnage at all — no 12 t
    trigger, no 8 t dispensation — which is exactly why the sea was never
    answered out of the land's book while its own chapter was unread.
    """
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="0,5 L",
                         gross_mass_per_package="20 kg")]),
        language="en", profiles=["IMDG"],
    )
    message = _single(result)["lq"]["message"]
    assert "LTD QTY" in message
    assert "3.4.6.1" in message
    assert "3.4.5.5" in message


def test_a_land_only_line_is_not_told_about_the_sea():
    """The sea's duties must not leak onto a road consignment."""
    result = check_lq_eq(
        _entry([_product(net_per_inner_packaging="0,5 L",
                         gross_mass_per_package="20 kg")]),
        language="en", profiles=["ADR"],
    )
    message = _single(result)["lq"]["message"]
    assert "LTD QTY" not in message
    assert "3.4.5.5" not in message
