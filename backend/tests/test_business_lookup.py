"""Business proposals must match the named place and never fabricate addresses."""
from types import SimpleNamespace
import pytest
from app.services.geo.businesses import match_businesses, split_business_place
from app.api.routes.geo import lookup_addresses


def candidate(name="PLUS", city="Wezep", street="Clematisstraat", number="3"):
    return dict(name=name, city=city, street=street, housenumber=number,
                postcode="8091 VJ", country="Netherlands")


def test_multiple_establishments_are_not_collapsed_to_the_first():
    data = [candidate(), candidate(street="Andere straat"), candidate()]
    result = match_businesses(data, "supermarkt Plus", "Wezep")
    assert len(result) == 2
    assert result[0]["address"] == "Clematisstraat 3\n8091 VJ Wezep\nNetherlands"


def test_wrong_town_brand_and_incomplete_addresses_are_not_proposed():
    assert match_businesses([candidate(city="Zwolle"), candidate(name="PLUSpunt"),
                            candidate(number="")], "PLUS", "Wezep") == []
    assert match_businesses([candidate()], "supermarkt", "Wezep") == []


@pytest.mark.parametrize("name,city", [("Bosch", "Stuttgart"), ("Renault", "Paris"),
                                      ("IKEA", "Stockholm"), ("Škoda", "Mladá Boleslav")])
def test_matching_is_not_limited_to_supermarkets_or_the_netherlands(name, city):
    assert len(match_businesses([candidate(name=name, city=city)], name, city)) == 1


@pytest.mark.parametrize("text,expected", [
    ("supermarkt Plus in Wezep", ("supermarkt Plus", "Wezep")),
    ("Bosch in Stuttgart", ("Bosch", "Stuttgart")),
    ("usine Renault à Paris", ("usine Renault", "Paris")),
    ("de haven in Rotterdam", None), ("Wezep", None),
])
def test_endpoint_extraction_keeps_ports_and_bare_cities_out_of_company_names(text, expected):
    assert split_business_place(text) == expected


def test_disabled_lookup_makes_no_external_request(monkeypatch):
    monkeypatch.setattr("httpx.Client", lambda **kw: pytest.fail("Lookup is disabled"))
    assert lookup_addresses("PLUS Wezep", "nl", 15,
                            SimpleNamespace(address_lookup_enabled=False)) == {"results": [], "available": False}
