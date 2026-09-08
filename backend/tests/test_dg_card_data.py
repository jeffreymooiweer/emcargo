"""Tests for the per-substance IMDG data read from the UN cards.

`card_data.json` is the first source EMCargo has for column 16a (stowage, SW)
and column 16b (segregation, SG) per substance. Until now the app knew which
segregation *group* a substance belonged to and had to send the user to the
Dangerous Goods List for what that meant in practice.

The dataset was validated on extraction by comparing its EmS codes against
`ems.json`, which comes from the official EmS Guide: 2,282 agreed and none
disagreed. These tests guard the values the app depends on.
"""

import json
from pathlib import Path

import pytest

from app.services.dg.autofill import derive_product
from app.services.dg.enrichment import card_data_for, enrich_un_entry

SEED = Path(__file__).resolve().parents[1] / "seed" / "dg" / "card_data.json"


@pytest.fixture(scope="module")
def data():
    return json.loads(SEED.read_text(encoding="utf-8"))


def test_the_dataset_covers_every_un_number_we_have_a_card_for(data):
    assert data["summary"]["un_numbers"] == 2336
    assert data["summary"]["failed"] == 0
    # Every card parsed; none was skipped for a malformed layout.
    assert data["summary"]["cards_read"] == 2849


def test_the_ems_codes_agreed_with_the_official_guide(data):
    """Two independent sources for the same field, and they matched."""
    check = data["summary"]["ems_cross_check"]
    assert check["differ"] == 0
    assert check["agree"] > 2200


def test_chlorine_carries_its_stowage_and_segregation_codes():
    card = card_data_for("1017")
    assert card["marine_pollutant"] == "yes"
    assert card["stowage_codes"] == ["SW2"]
    assert card["segregation_codes"] == ["SG6", "SG19"]
    assert "living quarters" in card["stowage_text"]


def test_nitric_acid_carries_the_full_segregation_list():
    card = card_data_for("2031")
    assert card["segregation_codes"] == ["SG6", "SG16", "SG17", "SG19", "SG36", "SG49"]
    assert card["segregation_groups"] == ["SGG1", "SGG6", "SGG18"]


def test_an_unknown_un_number_yields_nothing_rather_than_an_error():
    assert card_data_for("9999") == {}
    assert card_data_for("") == {}


def test_the_codes_reach_the_dangerous_goods_step():
    """The wizard shows them as hints, so they have to survive enrichment."""
    extras = enrich_un_entry({"un": "1017", "name_en": "Chlorine", "class": "2", "labels": "2.3"}, "nl")
    assert extras["imdg_stowage_codes"] == ["SW2"]
    assert extras["imdg_segregation_codes"] == ["SG6", "SG19"]
    assert extras["card_source"] == "imdg_un_card"
    # A bare "SG6" means nothing to a user; the card's own wording comes along.
    assert "class 5.1" in extras["imdg_segregation_text"]


def test_marine_pollutant_is_reported_as_the_source_states_it():
    """yes / no / maybe — "maybe" is a real answer, not missing data."""
    definite = enrich_un_entry({"un": "1017", "name_en": "Chlorine", "class": "2"}, "nl")
    assert definite["marine_pollutant_status"] == "yes"
    assert "ja" in definite["marine_pollutant_text"]

    # An n.o.s. entry depends on the actual substance, and the card says so.
    depends = enrich_un_entry({"un": "1203", "name_en": "Gasoline", "class": "3"}, "nl")
    assert depends["marine_pollutant_status"] == "maybe"
    assert "2.10" in depends["marine_pollutant_text"]


def test_a_confirmed_marine_pollutant_fills_the_document_field():
    """202 substances now fill column 4 by themselves."""
    derived = derive_product({"un_number": "1017"}, "nl")
    assert derived["patch"]["marine_pollutant"] == "P"


def test_bulk_carriage_is_recorded_where_it_is_allowed(data):
    """28 substances may travel in bulk, spelled as a BK instruction."""
    with_bulk = [un for un, e in data["entries"].items() if "bk" in str(e.get("bulk", ""))]
    assert len(with_bulk) == 28
    extras = enrich_un_entry({"un": with_bulk[0], "name_en": "x", "class": "9"}, "nl")
    assert extras["imdg_bulk"].startswith("BK")


def test_substances_without_special_requirements_say_so_rather_than_stay_silent():
    extras = enrich_un_entry({"un": "1203", "name_en": "Gasoline", "class": "3"}, "nl")
    assert "no special requirements" in extras["imdg_stowage_text"]
    assert "imdg_stowage_codes" not in extras
