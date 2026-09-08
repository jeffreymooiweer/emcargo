"""RID 7.5.3: the provision ADR could not stand in for.

For nearly everything that separates rail from road, EMCargo used the ADR
table with a basis note under it: usable as an indication, check it against the
text. For 7.5.3 that was not possible, and it is worth saying why: **ADR has no
counterpart to it.** 7.5.3 is about how a train is assembled, and a transport
unit on the road travels alone. So the ADR chapter did not give a less precise
answer here — it gave none.

The text, retrieved verbatim from RID 2025 (Appendix C to COTIF, Annex), page
1103, with `scripts/read_land_regulations.py --doc rid --page 1101-1103`:

    "Every wagon, large container, portable tank or road vehicle containing
     substances or articles of Class 1 and bearing a placard conforming to models
     Nos. 1, 1.5 or 1.6, shall be separated on the same train from wagons, large
     containers, portable tanks, tank-containers, MEGCs or road vehicles bearing a
     placard conforming to models Nos. 2.1, 3, 4.1, 4.2, 4.3, 5.1 or 5.2 [...] by a
     protective distance.
     The requirement for this protective distance is met if the space [...] is:
     (a) at least 18 m, or
     (b) occupied by two 2-axle wagons or a wagon with 4 or more axles."

Two things the text says precisely and that are easy to read past:

**The trigger is the placard, not the division.** Models 1, 1.5 and 1.6 are
named. Model 1.4 is *not* named, and that is not an omission — 1.4 has its own
placard model. A wagon carrying only division 1.4 goods therefore falls outside
this provision.

**The counterpart is a short list.** 2.1, 3, 4.1, 4.2, 4.3, 5.1 and 5.2 — the
flammable and oxidising sides. Class 8, 6.1 and 9 are not among them, however
dangerous they may otherwise be.

And what EMCargo cannot know here, it says: the rest of the train is not in
the application. A consignment with one class 1 wagon and nothing else therefore
gets not "nothing to worry about" but the provision itself, to pass on to the
carrier.
"""

import pytest

from app.services.dg.compliance import check_compliance, check_rid_protective_distance

BLACK_POWDER = {"un_number": "0027", "class": "1.1D", "classification_code": "1.1D",
                "proper_shipping_name": "BLACK POWDER"}
FIREWORKS_14 = {"un_number": "0336", "class": "1.4G", "classification_code": "1.4G",
                "proper_shipping_name": "FIREWORKS"}
GASOLINE = {"un_number": "1203", "class": "3", "proper_shipping_name": "GASOLINE"}
ACID = {"un_number": "1789", "class": "8", "proper_shipping_name": "HYDROCHLORIC ACID"}
PROPANE = {"un_number": "1978", "class": "2.1", "proper_shipping_name": "PROPANE"}


def wagons(*positions):
    return [{"vehicle": name, "products": list(products)} for name, products in positions]


def findings(entries, language="nl"):
    return check_rid_protective_distance(entries, language)


def test_klasse_1_en_een_brandbare_wagen_vragen_om_de_afstand():
    found = findings(wagons(("Wagen 1", [BLACK_POWDER]), ("Wagen 2", [GASOLINE])))

    assert len(found) == 1
    assert found[0]["rule"] == "RID 7.5.3"
    assert found[0]["products"] == "Wagen 1 ↔ Wagen 2"
    assert "18 m" in found[0]["message"]


def test_de_tegenhangerlijst_is_geen_lijst_van_gevaarlijke_stoffen():
    """Class 8 is not in 7.5.3, however corrosive it may be.

    A message does remain, but the general one: the train holds more than this
    consignment. What must *not* happen is that the wagon with hydrochloric acid
    is designated as the counterpart — that would prescribe a distance the text
    does not ask for.
    """
    found = findings(wagons(("Wagen 1", [BLACK_POWDER]), ("Wagen 2", [ACID])))

    assert len(found) == 1
    assert "Wagen 2" not in found[0]["products"]


def test_divisie_14_zet_de_bepaling_niet_in_werking():
    """Model 1.4 is not named in 7.5.3; only 1, 1.5 and 1.6."""
    assert findings(wagons(("Wagen 1", [FIREWORKS_14]), ("Wagen 2", [GASOLINE]))) == []


@pytest.mark.parametrize("counterpart", [GASOLINE, PROPANE])
def test_elke_genoemde_tegenhanger_telt(counterpart):
    found = findings(wagons(("W1", [BLACK_POWDER]), ("W2", [counterpart])))

    assert found and "↔" in found[0]["products"]


def test_een_zending_zonder_tegenhanger_krijgt_de_bepaling_toch_te_horen():
    """EMCargo does not see the train, and that must not look like a clear road."""
    found = findings(wagons(("Wagen 1", [BLACK_POWDER])))

    assert len(found) == 1
    assert found[0]["products"] == "Wagen 1"
    assert "vervoerder" in found[0]["message"]


def test_zonder_klasse_1_gebeurt_er_niets():
    assert findings(wagons(("W1", [GASOLINE]), ("W2", [PROPANE]))) == []


def test_binnen_een_wagen_gaat_het_niet_over_afstand_maar_over_samenlading():
    """7.5.3 separates units in the train; within one wagon 7.5.2 applies."""
    found = findings([{"vehicle": "Wagen 1", "products": [BLACK_POWDER, GASOLINE]}])

    assert len(found) == 1
    assert "↔" not in found[0]["products"]


def test_de_bepaling_hoort_bij_het_spoor_en_niet_bij_de_weg():
    entries = wagons(("Wagen 1", [BLACK_POWDER]), ("Wagen 2", [GASOLINE]))

    rail = check_compliance(entries, ["RID"], "nl")["adr_mixed_loading"]
    road = check_compliance(entries, ["ADR"], "nl")["adr_mixed_loading"]

    assert any(w["rule"] == "RID 7.5.3" for w in rail)
    assert not any("7.5.3" in w["rule"] for w in road)


def test_het_spoor_haalt_de_levensmiddelenbepaling_onder_zijn_eigen_naam_aan():
    """RID 7.5.4 refers to CW 28 in column (18), ADR to CV28.

    The text of 7.5.4 is word for word the same in both regimes, so nothing
    changes in substance. But a CIM waybill citing "CV28" names a code that does
    not exist in RID, and that is incorrect information the application adds
    itself — the same fault as the tunnel code on a CIM.
    """
    toxic = {"un_number": "1230", "class": "3", "subsidiary_risks": "6.1",
             "proper_shipping_name": "METHANOL"}
    entries = [{"vehicle": "Wagen 1", "products": [toxic]}]

    rail = check_compliance(entries, ["RID"], "nl")["adr_mixed_loading"]
    road = check_compliance(entries, ["ADR"], "nl")["adr_mixed_loading"]

    assert any(w["rule"] == "RID CW28 / 7.5.4" for w in rail)
    assert any(w["rule"] == "ADR CV28 / 7.5.4" for w in road)


def test_de_bevinding_komt_in_de_lijst_die_ook_de_export_leest():
    """A rail provision that is only on the screen is not on the document.

    The export reads `adr_mixed_loading`; that is why 7.5.3 is in there and not
    under a key of its own that only the panel knows.
    """
    entries = wagons(("Wagen 1", [BLACK_POWDER]), ("Wagen 2", [GASOLINE]))

    outcome = check_compliance(entries, ["RID"], "nl")

    assert any(w["rule"] == "RID 7.5.3" for w in outcome["adr_mixed_loading"])
