"""What ADR, RID and ADN say — looked up, not remembered.

These rules are taken from the official texts: ADR 2025 (UNECE,
ECE/TRANS/352), RID 2025 (OTIF, Appendix C to COTIF) and ADN 2025 (UNECE). All
three are published free of charge. ``scripts/read_land_regulations.py`` fetches
them and quotes the provisions; the source is named per test so that somebody
with the text in front of them can check whether it was read correctly.

The reason is that EMCargo had these rules from an ADR data export and from
general knowledge of the regimes. That is not the same as having read the
regulations, and the difference turned out to sit in exactly the two places where
it costs money and safety.
"""

import pytest

from app.services.dg.compliance import check_adn_exemption, check_compliance

# --- ADR/RID 1.1.3.6.3 note (a) -------------------------------------------
#
# "For UN Nos. 0081, 0082, 0084, 0241, 0331, 0332, 0482, 1005 and 1017, the
#  total maximum quantity per transport unit shall be 50 kg."   ADR 1.1.3.6.3
#
# And RID 1.1.3.6.4 names the corresponding factor in so many words: the quantity
# of transport category 1 "referred to in Note a" times "20".

NOTE_A = ["0081", "0082", "0084", "0241", "0331", "0332", "0482", "1005", "1017"]


def points(products, profiles=("ADR",), language="en"):
    entries = [{"line_id": "L1", "products": products}]
    return check_compliance(entries, list(profiles), language)["adr_points"]


@pytest.mark.parametrize("un", NOTE_A)
def test_the_nine_note_a_substances_count_times_twenty(un):
    out = points([{"un_number": un, "class": "1", "transport_category": "1",
                   "adr_total_quantity": "10"}])
    assert out["rows"][0]["factor"] == 20
    assert out["rows"][0]["note_a"] is True
    assert out["total_points"] == 200.0


def test_fifty_kilos_of_chlorine_stays_within_the_exemption():
    """50 kg is exactly the maximum of note (a), and 50 x 20 is exactly 1000.

    With the factor 50 of ordinary category 1 this became 2500 and the user lost
    an exemption the text gives them: orange plates, an ADR driver's certificate
    and an ADR vehicle for a consignment that does not need it.
    """
    out = points([{"un_number": "1017", "proper_shipping_name": "CHLORINE",
                   "class": "2", "transport_category": "1",
                   "adr_total_quantity": "50"}])
    assert out["total_points"] == 1000.0
    assert out["status"] == "exempt_possible"


def test_an_ordinary_category_one_substance_still_counts_times_fifty():
    out = points([{"un_number": "1051", "class": "6.1", "transport_category": "1",
                   "adr_total_quantity": "10"}])
    assert out["rows"][0]["factor"] == 50
    assert "note_a" not in out["rows"][0]
    assert out["total_points"] == 500.0


def test_the_exception_applies_on_rail_as_well():
    """RID 1.1.3.6.3 carries the same note (a) and 1.1.3.6.4 the same factor."""
    out = points([{"un_number": "1005", "class": "2", "transport_category": "1",
                   "adr_total_quantity": "50"}], profiles=("RID",))
    assert out["total_points"] == 1000.0


# --- RID 1.1.3.6.3 and 1.1.3.6.4 ------------------------------------------


def test_rail_no_longer_hedges_about_its_own_chapter():
    """The basis has been checked: RID computes the same as ADR.

    The old note said RID "has a 1.1.3.6 of its own that is not in EMCargo".
    That was true and too cautious: the categories, the factors and the value
    1000 are identical. What differs is the unit.
    """
    note = points([{"un_number": "1263", "class": "3", "packing_group": "III",
                    "transport_category": "3", "adr_total_quantity": "10"}],
                  profiles=("RID",))["basis_note"]
    assert "1.1.3.6.3" in note and "1.1.3.6.4" in note
    assert "wagon or large container" in note
    assert "does not hold" not in note


# --- ADN 1.1.3.6.1 --------------------------------------------------------
#
# "the provisions of ADN other than those of 1.1.3.6.2 are not applicable when
#  the gross mass of all the dangerous goods carried does not exceed 3,000 kg
#  and for the individual classes does not exceed the quantity that is indicated
#  in the Table below"                                          ADN 1.1.3.6.1
#
# No transport categories, no factors, no points count.


def adn(products, language="en"):
    return check_adn_exemption([{"line_id": "L1", "products": products}], language)


PAINT = {"un_number": "1263", "proper_shipping_name": "PAINT", "class": "3",
         "packing_group": "III", "transport_category": "3"}


def test_the_inland_waterway_answer_is_not_the_road_answer():
    """The same consignment, two opposite outcomes — and that is right.

    1200 litres of a liquid in packing group III costs 1200 ADR points and loses
    the exemption there. ADN exempts the same consignment: the class 3 limit for
    "any other substances" is 3000 kg and the total stays below it. Until v1.32.0
    an ADN user saw only the road answer.
    """
    entries = [{"line_id": "L1", "products": [dict(PAINT, adr_total_quantity="1200")]}]
    out = check_compliance(entries, ["ADN"], "en")
    assert out["adr_points"]["status"] == "above_threshold"
    assert out["adn_exemption"]["status"] == "exempt_possible"


def test_a_packing_group_one_liquid_is_held_to_three_hundred_kilos():
    out = adn([dict(PAINT, packing_group="I", adr_total_quantity="400")])
    assert out["status"] == "not_exempt"
    assert out["over_class_limit"] == [
        {"class": "3", "selector": "pg_i", "limit": 300, "carried": 400.0}
    ]


def test_the_same_liquid_under_three_hundred_kilos_qualifies():
    assert adn([dict(PAINT, packing_group="I", adr_total_quantity="250")])["status"] == (
        "exempt_possible"
    )


def test_class_one_is_never_exempt_under_adn():
    """The table puts class 1 at 0 kg: there is no exempted quantity."""
    out = adn([{"un_number": "0081", "class": "1", "adr_total_quantity": "1"}])
    assert out["status"] == "not_exempt"
    assert out["over_class_limit"][0]["limit"] == 0


def test_a_toxic_gas_is_never_exempt_but_an_inert_one_may_be():
    toxic = adn([{"un_number": "1017", "class": "2", "classification_code": "2TC",
                  "adr_total_quantity": "1"}])
    assert toxic["status"] == "not_exempt"
    inert = adn([{"un_number": "1066", "class": "2", "classification_code": "1A",
                  "adr_total_quantity": "1000"}])
    assert inert["status"] == "exempt_possible"


def test_a_flammable_gas_gets_the_three_hundred_kilo_row():
    out = adn([{"un_number": "1965", "class": "2", "classification_code": "2F",
                "adr_total_quantity": "400"}])
    assert out["status"] == "not_exempt"
    assert out["over_class_limit"][0]["limit"] == 300


def test_the_three_thousand_kilo_ceiling_applies_across_the_classes():
    """Every class within its limit, and together too much all the same:
    1.1.3.6.1 sets both requirements and the second is a total over everything."""
    out = adn([
        dict(PAINT, adr_total_quantity="2000"),
        {"un_number": "1789", "class": "8", "packing_group": "II",
         "adr_total_quantity": "2000"},
    ])
    assert out["over_class_limit"] == []
    assert out["total_gross_mass_kg"] == 4000.0
    assert out["status"] == "above_threshold"


def test_missing_quantity_is_reported_rather_than_assumed():
    out = adn([dict(PAINT)])
    assert out["status"] == "incomplete"
    assert out["incomplete_products"]


def test_the_conditions_of_1_1_3_6_2_are_carried_with_the_outcome():
    """Exempted is not free: 1.1.3.6.2 keeps the notification duty, the transport
    document, the stowage plan and 3 m of separation in place."""
    out = adn([dict(PAINT, adr_total_quantity="100")])
    joined = " ".join(out["conditions"])
    assert "1.8.5" in joined and "stowage plan" in joined and "3 m" in joined


def test_the_adn_result_appears_only_for_the_adn_profile():
    entries = [{"line_id": "L1", "products": [dict(PAINT, adr_total_quantity="100")]}]
    assert "adn_exemption" not in check_compliance(entries, ["ADR"], "en")
    assert "adn_exemption" in check_compliance(entries, ["ADN"], "en")


@pytest.mark.parametrize("language", ["nl", "en", "de"])
def test_the_adn_outcome_speaks_every_interface_language(language):
    out = adn([dict(PAINT, adr_total_quantity="100")], language)
    assert "1.1.3.6" in out["note"]
    assert out["conditions"]
