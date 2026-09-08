"""The compliance endpoint has to refuse unusable input, not convert it.

The check was `list[dict]`, so Pydantic did not look at it. Everything that came
in went into the calculation layer, which defensively made the best of it. Two
cases are dangerous there, because they do not come out as an error message but
as a *more favourable* outcome than reality:

- A negative quantity lowers the ADR points total and can suggest an exemption
  that does not exist.
- A misspelled profile ("IDMG") silently produces no sea-transport check, and the
  screen then shows a clean result without anything having been examined.

Both should give HTTP 422 before anything is computed.
"""

import pytest
from pydantic import ValidationError

from app.schemas.dg_compliance import ComplianceRequest


def request(**product):
    return ComplianceRequest(
        entries=[{"vehicle": "WAGEN-1", "products": [product]}],
        profiles=["ADR"],
    )


def test_a_normal_request_passes_and_keeps_the_class_field_name():
    """"class" cannot be a field name in Python, but the calculation layer and
    the frontend know the field that way. It must not get renamed in transit."""
    payload = ComplianceRequest(
        entries=[{
            "vehicle": "WAGEN-1",
            "products": [{
                "un_number": "1203",
                "class": "3",
                "packing_group": "II",
                "transport_category": "2",
                "adr_total_quantity": "20 L",
            }],
        }],
        profiles=["ADR", "IMDG"],
    )
    product = payload.as_dicts()[0]["products"][0]
    assert product["class"] == "3"
    assert product["adr_total_quantity"] == "20 L"
    assert payload.profile_names() == ["ADR", "IMDG"]


def test_an_unknown_profile_is_refused():
    with pytest.raises(ValidationError):
        ComplianceRequest(entries=[], profiles=["IDMG"])


@pytest.mark.parametrize("quantity", ["-5 L", "0", "0 kg", "-0,5"])
def test_a_quantity_that_is_not_positive_is_refused(quantity):
    with pytest.raises(ValidationError) as error:
        request(un_number="1203", adr_total_quantity=quantity)
    # The code, not the sentence: the sentence is an English fallback that the
    # interface replaces with its own wording, and a test that pins the wording
    # is a test that breaks on every translation.
    assert error.value.errors()[0]["type"] == "dg.quantity_not_positive"


@pytest.mark.parametrize("quantity", ["a few drums", "10 x 20 L", "10-20 L", "1e3 kg", "999" * 150])
def test_a_quantity_without_a_number_is_refused(quantity):
    with pytest.raises(ValidationError) as error:
        request(un_number="1203", adr_total_quantity=quantity)
    assert error.value.errors()[0]["type"] == "dg.quantity_not_a_number"


def test_an_empty_quantity_is_allowed_because_the_check_reports_it_itself():
    """Half-finished input is normal: the wizard sends along the way and the
    check should report 'incomplete'. Refusing would block the screen."""
    payload = request(un_number="1203", adr_total_quantity="")
    assert payload.entries[0].products[0].un_number == "1203"


def test_an_unknown_packing_group_is_refused():
    with pytest.raises(ValidationError):
        request(un_number="1203", packing_group="IV")


def test_a_packing_group_is_normalised_to_upper_case():
    payload = request(un_number="1203", packing_group="ii")
    assert payload.as_dicts()[0]["products"][0]["packing_group"] == "II"


def test_an_unknown_transport_category_is_refused():
    """ADR 1.1.3.6 has 0 to 4. A 5 would have no factor and would let the
    position drop out of the points total silently."""
    with pytest.raises(ValidationError):
        request(un_number="1203", transport_category="5")


def test_a_q_component_of_zero_is_refused_before_it_can_disappear():
    """n or M at zero made the component drop out of the Q sum. Now it does not
    even get in."""
    with pytest.raises(ValidationError):
        request(un_number="1203", q_net_quantity="5", q_max_net_quantity="0")


def test_fields_the_schema_does_not_name_are_kept():
    """The wizard sends more than the check reads. That must not be lost at the
    edge — the calculation layer and the documents use those fields."""
    payload = request(un_number="1203", ems_code="F-E, S-E")
    assert payload.as_dicts()[0]["products"][0]["ems_code"] == "F-E, S-E"
