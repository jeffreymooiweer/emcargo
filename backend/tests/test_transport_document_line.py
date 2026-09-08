"""5.4.1.1.1: what the description line must say, and in which regime.

Three books were read for this, and they do not say the same thing. ADR, RID
and ADN share paragraphs (a) to (d) almost word for word — and then each adds
one of its own: the ADR a tunnel restriction code under (k), the RID the hazard
identification number under (j), the ADN a confirmation of stabilisation under
its own (j). A line that carries another regime's addition is an invented entry
on an official piece of paper.

The defect this file was written for is older and larger than any of those.
Paragraph (c) asks for the **label model numbers**, with the ones after the
first in brackets — the RID's own example is "663, UN 1098 ALLYL ALCOHOL,
6.1(3), I". EMCargo printed "6.1" and dropped the "(3)". The cause was a
separator: the 2023 export writes "6.1+3" and the Dutch 2025 edition writes
"6.1, 3", and the reader split on the plus alone. 718 of the 3,158 rows of that
table carry more than one label model, and every one of them reached the
transport document a label short.
"""
import pytest

from app.services.dg.autofill import description_line, prepare_entries
from app.services.dg.compliance import (
    check_adn_stabilisation,
    check_rid_limited_quantities_with_explosives,
    check_rid_transport_document,
)


def prepared(*products, profile="ADR"):
    return prepare_entries(
        [{"line_id": "L1", "products": list(products)}], profiles=[profile])


def line(un, profile="ADR", **extra):
    return prepared({"un_number": un, **extra},
                    profile=profile)["document_lines"][profile][0]


def entries(*products, profile="ADR"):
    return prepared(*products, profile=profile)["entries"]


# --- (c): the label models, all of them ------------------------------------


def test_the_subsidiary_label_model_reaches_the_line():
    """UN 1098 is the substance RID 5.4.1.1.1 uses for its own example, and the
    example reads "6.1(3)". Until now the application printed "6.1"."""
    assert "6.1 (3)" in line("1098")


def test_a_gas_carries_its_second_label_too():
    """UN 1005 anhydrous ammonia is 2.3 with a corrosive subsidiary label. The
    class column says only "2"; the division and the subsidiary are both in
    column (5), which is why that column has to be read as a list."""
    assert "2.3 (8)" in line("1005")


def test_two_subsidiary_labels_are_both_shown():
    """UN 0018 tear-producing ammunition carries 1, 6.1 and 8."""
    assert "1.2G (6.1, 8)" in line("0018")


def test_class_one_shows_the_classification_code_and_not_the_class():
    """(c) first indent: for class 1 the classification code of column (3b) is
    the entry, not the "1" of column (3a)."""
    assert ", 1.1D," in line("0004")


def test_the_class_one_own_label_models_stay_out_of_the_brackets():
    """(c) puts the label models *other than* 1, 1.4, 1.5 and 1.6 behind the
    classification code. The label "1" is the class's own and is not repeated,
    which is a set and not a position: a row whose label cell begins with
    something else must not push "1" into the brackets."""
    assert "1.1D ()" not in line("0004")
    assert line("0004").count("1.1D") == 1


def test_a_row_without_a_label_model_falls_back_to_the_class():
    """The last indent of (c): where column (5) gives no label model, the class
    of column (3a) is given instead. Two rows of the Dutch edition spell out the
    word for "none" and twelve read "See 5.2.2.1.12"; neither is a number to put
    in brackets after the class."""
    for un in ("2211", "3537"):
        composed = line(un)
        assert "(" not in composed.split(", ")[-2] or "E" in composed
        assert "5.2.2.1.12" not in composed


def test_the_lithium_battery_entries_carry_the_class_number():
    """(c) names UN 3090, 3091, 3480, 3481, 3551 and 3552 and the battery
    powered vehicles 3556 to 3558: the class number "9", not the label model 9A
    that column (5) gives them."""
    assert ", 9," in line("3480")


# --- RID (j): the hazard identification number ------------------------------


def test_rail_puts_the_hazard_number_in_front_for_a_tank():
    """5.3.2.1.1 prescribes the orange plate for a tank-wagon or tank-container,
    and 5.4.1.1.1 (j) then puts the number before the letters "UN", in the
    sequence (j), (a), (b), (c), (d). The RID's example is
    "663, UN 1098 ALLYL ALCOHOL, 6.1(3), I"."""
    composed = line("1098", profile="RID", carriage_mode="tank")
    assert composed.startswith("663, UN 1098")
    assert "6.1 (3)" in composed


def test_bulk_carriage_is_marked_as_well():
    """5.3.2.1.1 lists wagons and containers for carriage in bulk beside the
    tanks."""
    assert line("1098", profile="RID", carriage_mode="bulk").startswith("663, ")


def test_packages_on_rail_do_not_get_the_number_in_front():
    """For packages the plate is at most permitted, and the number in front of a
    description that does not need it is as wrong as a missing one."""
    assert line("1098", profile="RID").startswith("UN 1098")


def test_the_road_document_never_gets_it():
    """ADR 5.4.1.1.1 has no such paragraph — its (k) is the tunnel restriction
    code. A hazard identification number in front of a CMR description is an
    entry the ADR does not ask for."""
    assert line("1098", carriage_mode="tank").startswith("UN 1098")


def test_the_permitted_case_is_asked_rather_than_decided():
    """A full load of packages of one and the same substance *may* be plated,
    and then (j) applies. Whether it was is not something this application can
    see, so it asks instead of composing a line either way."""
    findings = check_rid_transport_document(entries(
        {"un_number": "1098"}, profile="RID"))
    assert [f["severity"] for f in findings] == ["warning"]
    assert "5.3.2.1.1" in findings[0]["rule"]


def test_two_substances_in_packages_raise_no_question():
    """The permission of 5.3.2.1.1 is for a full load of *one and the same*
    substance. With two on board it does not arise, and neither does (j)."""
    assert check_rid_transport_document(entries(
        {"un_number": "1098"}, {"un_number": "1203"}, profile="RID")) == []


def test_a_tank_without_a_hazard_number_says_so():
    """Table A does not give every substance a number in column (20). Composing
    the line silently without it would hide a description the RID calls
    incomplete."""
    findings = check_rid_transport_document(entries(
        {"un_number": "0004", "carriage_mode": "tank"}, profile="RID"))
    assert [f["severity"] for f in findings] == ["warning"]
    assert "5.4.1.1.1 (j)" in findings[0]["rule"]


# --- RID 7.5.2.4 ------------------------------------------------------------


def _lq_rows(*labels):
    return [{"product": label, "lq": {"status": "within_limits"}} for label in labels]


def test_limited_quantities_may_not_travel_with_explosives_by_rail():
    """Read in the English edition on page 1103 and the German on 1187, which
    agree: mixed loading of goods packed in limited quantities with any type of
    explosive substances and articles, except division 1.4 and UN 0161 and 0499,
    is prohibited. There is no ADR equivalent."""
    goods = entries(
        {"un_number": "1263", "packing_group": "III"},
        {"un_number": "0004"}, profile="RID")
    label = goods[0]["products"][0]["proper_shipping_name"]
    findings = check_rid_limited_quantities_with_explosives(
        goods, "en", _lq_rows(f"UN 1263 {label}"))
    assert [f["rule"] for f in findings] == ["RID 7.5.2.4"]
    assert findings[0]["severity"] == "error"


def test_division_one_point_four_is_excepted():
    """The text names division 1.4 and UN 0161 and 0499 as the exceptions."""
    goods = entries(
        {"un_number": "1263", "packing_group": "III"},
        {"un_number": "0323"}, profile="RID")  # 1.4S cartridges, power device
    label = goods[0]["products"][0]["proper_shipping_name"]
    assert check_rid_limited_quantities_with_explosives(
        goods, "en", _lq_rows(f"UN 1263 {label}")) == []


def test_without_a_limited_quantity_assessment_nothing_is_claimed():
    """Which lines count as packed in limited quantities is the 3.4 check's
    answer. Recomputing it here would let the two disagree about one package."""
    goods = entries({"un_number": "1263"}, {"un_number": "0004"}, profile="RID")
    assert check_rid_limited_quantities_with_explosives(goods, "en", []) == []


def test_it_reaches_the_consignment_note():
    """A prohibition on screen only is a prohibition nobody acts on."""
    from app.services.documents.exporter import validate_document
    from app.services.documents.registry import get_document

    values = {
        "consignor_name": "Afzender", "consignor_address": "Havenweg 1",
        "consignee_name": "Ontvanger", "consignee_address": "Bahnhofstrasse 4",
        "loading_point": "Rotterdam", "discharge_point": "Duisburg",
        "freight_payment": "Franco", "established_place": "Rotterdam",
        "established_date": "2026-08-15",
    }
    goods = entries(
        {"un_number": "1263", "packing_group": "III",
         "net_per_inner_packaging": "1 L", "quantity_packages": "2",
         "gross_mass_per_package": "10"},
        {"un_number": "0004", "net_explosive_mass": "5"}, profile="RID")
    errors, _warnings = validate_document(
        get_document("cim"), values, [], goods, "nl")
    assert any("7.5.2.4" in error for error in errors), errors


# --- ADN (j): the confirmation of stabilisation -----------------------------


def test_st01_asks_for_the_confirmation_of_stabilisation():
    """ADN 5.4.1.1.1 (j): where column (11) of its table A carries ST01, the
    document needs a confirmation of stabilisation. 7.1.6.11 says what it
    confirms — stabilized as the IMSBC Code requires for ammonium nitrate
    fertilizers, certified by the consignor in the transport document."""
    findings = check_adn_stabilisation(entries(
        {"un_number": "1942", "carriage_mode": "bulk"}, profile="ADN"))
    assert len(findings) == 1
    assert "ST01" in findings[0]["rule"]


def test_the_same_substance_in_packages_is_not_asked():
    """7.1.6.11 is headed "Carriage in bulk" and applies where column (11) says
    so. The same ammonium nitrate in packages does not carry the requirement."""
    assert check_adn_stabilisation(entries(
        {"un_number": "1942"}, profile="ADN")) == []


def test_st02_is_not_a_document_requirement():
    """UN 2071 carries ST02, which is a condition on the carriage — a trough
    test — and not on the paper. Only ST01 is named in 5.4.1.1.1 (j)."""
    assert check_adn_stabilisation(entries(
        {"un_number": "2071", "carriage_mode": "bulk"}, profile="ADN")) == []


# --- one builder, not two ---------------------------------------------------


def test_the_form_and_the_wizard_compose_the_same_line():
    """The exporter used to render 5.4.1.1.1 for itself, and a second rendering
    of one provision drifts the moment either is corrected: the label models and
    the hazard identification number would have reached the wizard and not the
    consignment note."""
    from app.services.documents.exporter import _dg_description

    product = entries({"un_number": "1098", "carriage_mode": "tank"},
                      profile="RID")[0]["products"][0]
    assert _dg_description(product, "RID", {}, "nl") == description_line(
        product, "RID", "nl")


def test_the_form_keeps_its_own_tunnel_code():
    """The one thing that is genuinely the form's: a tunnel code the user typed
    over the one table A gives."""
    from app.services.documents.exporter import _dg_description

    product = entries({"un_number": "1203"})[0]["products"][0]
    assert _dg_description(
        product, "ADR", {"tunnel_restriction": "B/E"}, "nl").endswith("(B/E)")


def test_the_form_column_holds_the_description_alone():
    """The form has columns of its own for the package count and the mass, so
    the description must not repeat them — that is what the form's own renderer
    did, and delegating must not change it."""
    from app.services.documents.exporter import _dg_description

    product = entries({"un_number": "1203", "quantity_packages": "4",
                       "type_of_package": "vaten"})[0]["products"][0]
    assert "vaten" not in _dg_description(product, "ADR", {}, "nl")
    assert "vaten" in description_line(product, "ADR")


@pytest.mark.parametrize("language", ["nl", "en", "de", "fr"])
def test_every_new_message_speaks_four_languages(language):
    from app.services.dg.compliance import get_compliance_rules

    rules = get_compliance_rules()
    for block in ("rid_transport_document", "rid_limited_quantities_with_explosives",
                  "adn_stabilisation"):
        for name, message in rules[block]["rules"].items():
            assert message.get(language), f"{block}.{name} lacks {language}"
