"""ADR 1.10.3 — high consequence dangerous goods.

Chapter 1.10 was named in the 1.1.3.6 exemption text and nowhere else: the last
heading in `docs/dg-coverage.md` with nothing behind it.

Table 1.10.3.1.2 turns out to be easier than it looks, but only once it has been
read. For carriage in packages its column holds two values and no others: **0**,
meaning any quantity at all, and footnote **b)**, "whatever the quantity, the
provisions of 1.10.3 do not apply". There is no threshold to compare against and
no arithmetic to get wrong — it is a membership test.

It is worth having because the intuition it corrects runs the other way.
Flammable liquids, corrosives and packing group I oxidisers all look like the
dangerous end of a load and are all footnote b) in packages. What the table
catches instead is class 1, the toxic gases, the desensitised explosives,
packing group I toxics and category A infectious substances.
"""
from __future__ import annotations

import pytest

from app.services.dg.compliance import check_adr_security


def load(*products):
    return [{"products": list(products)}]


def status(*products):
    return check_adr_security(load(*products), "en")["status"]


# --- the no, which is the surprising half -----------------------------------

@pytest.mark.parametrize("product,why", [
    ({"un_number": "1203", "class": "3", "classification_code": "F1",
      "packing_group": "II"}, "petrol, the commonest dangerous load there is"),
    ({"un_number": "1830", "class": "8", "classification_code": "C1",
      "packing_group": "I"}, "sulphuric acid, packing group I"),
    ({"un_number": "1230", "class": "6.1", "classification_code": "FT1",
      "packing_group": "III"}, "a toxic of packing group III"),
    ({"un_number": "0012", "class": "1", "classification_code": "1.4S"},
     "division 1.4 not named in the table"),
    ({"un_number": "0335", "class": "1", "classification_code": "1.3G"},
     "division 1.3 outside compatibility group C"),
    ({"un_number": "1950", "class": "2", "classification_code": "5T"},
     "an aerosol, excepted in the table's own words"),
])
def test_this_is_not_high_consequence(product, why):
    assert status(product) == "ok", why


def test_quantity_never_turns_a_footnote_b_row_into_one():
    """The whole point of the b) rows. A packing group II flammable liquid is
    outside 1.10.3 at any quantity — the column says so rather than giving a
    number to exceed."""
    petrol = {"un_number": "1203", "class": "3", "classification_code": "F1",
              "packing_group": "II", "quantity": 24000, "unit": "kg"}
    assert status(petrol) == "ok"


def test_the_no_is_explained_and_not_left_blank():
    result = check_adr_security(load(
        {"un_number": "1203", "class": "3", "classification_code": "F1",
         "packing_group": "II"}), "en")
    assert "whatever the quantity" in result["message"]
    assert result["provision"] == "1.10.3.1.2"


# --- the yes -----------------------------------------------------------------

@pytest.mark.parametrize("product,why", [
    ({"un_number": "0015", "class": "1", "classification_code": "1.2G"},
     "division 1.2"),
    ({"un_number": "0161", "class": "1", "classification_code": "1.3C"},
     "division 1.3, compatibility group C"),
    ({"un_number": "0104", "class": "1", "classification_code": "1.4D"},
     "division 1.4, named in the table"),
    ({"un_number": "1017", "class": "2", "classification_code": "2TOC"},
     "chlorine, a toxic gas"),
    ({"un_number": "1051", "class": "6.1", "classification_code": "TF1",
      "packing_group": "I"}, "hydrogen cyanide, packing group I"),
    ({"un_number": "2814", "class": "6.2", "classification_code": "I1"},
     "category A infectious substance"),
])
def test_this_is_high_consequence(product, why):
    assert status(product) == "high_consequence", why


def test_the_finding_names_the_line_and_asks_for_the_plan():
    result = check_adr_security(load(
        {"un_number": "1017", "class": "2", "classification_code": "2TOC"}), "en")
    assert result["provision"] == "1.10.3.2"
    assert "security plan" in result["message"]
    assert result["items"][0]["un_number"] == "1017"
    # 0 is the table's own value and not a missing one: any quantity qualifies.
    assert result["items"][0]["threshold_kg"] == 0


def test_the_division_is_quoted_as_the_table_writes_it():
    """"division 1.2G" would quote table 1.10.3.1.2 as saying something it does
    not: it sorts on the division, and the compatibility group only enters for
    1.3."""
    result = check_adr_security(load(
        {"un_number": "0015", "class": "1", "classification_code": "1.2G"}), "en")
    assert "division 1.2" in result["items"][0]["reason"]
    assert "1.2G" not in result["items"][0]["reason"]


def test_one_qualifying_line_is_enough():
    result = check_adr_security(load(
        {"un_number": "1203", "class": "3", "classification_code": "F1",
         "packing_group": "II"},
        {"un_number": "1017", "class": "2", "classification_code": "2TOC"}), "en")
    assert result["status"] == "high_consequence"
    assert len([i for i in result["items"] if not i.get("not_answered")]) == 1


# --- what it does not answer -------------------------------------------------

def test_class_7_is_not_answered_and_says_so():
    """1.10.3.1.3 measures it in activity against 3,000 A2 with its own limits
    per radionuclide. EMCargo is not told an activity, and a silent "ok"
    there would be a wrong answer rather than an absent one."""
    result = check_adr_security(load(
        {"un_number": "2915", "class": "7", "classification_code": "7X"}), "en")
    unanswered = [i for i in result["items"] if i.get("not_answered")]
    assert unanswered and "3000 A2" in unanswered[0]["reason"]
    assert result["status"] == "ok"


def test_the_answer_says_it_is_about_packages():
    """The tank and bulk columns carry 3,000 litre and 3,000 kg thresholds of
    their own, and footnotes c) and d) make them relevant only where table A
    permits that form of carriage."""
    assert check_adr_security(load(
        {"un_number": "1203", "class": "3", "classification_code": "F1",
         "packing_group": "II"}), "en")["scope"] == "packages"


@pytest.mark.parametrize("language", ["nl", "en", "de", "fr"])
def test_it_speaks_the_four_languages(language):
    for products in ([{"un_number": "1017", "class": "2", "classification_code": "2TOC"}],
                     [{"un_number": "1203", "class": "3", "classification_code": "F1",
                       "packing_group": "II"}]):
        result = check_adr_security(load(*products), language)
        assert result["message"].strip() and "{" not in result["message"]
