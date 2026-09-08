"""May *this* tank carry these goods — ADR 4.3, and the shape of its answer.

Column (12) says which tank code a substance requires, and until now that was
the whole of what EMCargo could say about a tank load. It is not the
consignor's question: the vehicle standing on the yard has the code it has, and
what has to be decided is whether that code is good enough.

ADR answers it twice, and the two answers have nothing in common but their
purpose. 4.3.3.1.2 is a hierarchy of *codes* and applies to gases. 4.3.4.1.2 is
the rationalized approach and applies to classes 3 to 9: the offered code names
the group of substances it may carry, the required code is not compared with it
at all, and the groups of the codes below it are inherited. Rounding those two
to one rule is the mistake these tests exist to catch.

The third outcome is the one worth pinning hardest: **cannot be assessed**. The
seed's cells are settled by two readings or they are not settled, and where the
answer would rest on an unsettled cell the check says so rather than guessing in
either direction.
"""
import json
from pathlib import Path

from app.services.dg import database
from app.services.dg.compliance import check_adr_tank_fit

SEED = Path(__file__).resolve().parents[1] / "seed" / "dg" / "adr_tank_hierarchy.json"


def line(*products):
    return [{"line_id": "L1", "products": list(products)}]


def tank(un, code, **extra):
    return {"un_number": un, "carriage_mode": "tank", "tank_code": code, **extra}


def only(result):
    assert len(result["items"]) == 1, result["items"]
    return result["items"][0]


# --- when the check speaks at all -----------------------------------------


def test_packages_are_not_asked_about_tanks():
    """Every consignment drawn up before this release is a packages one, and
    the tank question must not appear on any of them."""
    result = check_adr_tank_fit(line({"un_number": "1203"}))
    assert result["status"] == "not_checked"
    assert result["items"] == []


def test_a_tank_without_a_code_asks_nothing():
    """The consignor may not know the tank's code yet. That is not a finding —
    it is a question that has not been asked."""
    result = check_adr_tank_fit(line({"un_number": "1203", "carriage_mode": "tank"}))
    assert result["status"] == "not_checked"


# --- 4.3.4.1.2, the rationalized approach ---------------------------------


def test_petrol_travels_in_the_tank_one_step_up():
    """UN 1203 requires LGBF. An L4BN semi-trailer is the tank that actually
    turns up, and 4.3.4.1.2 permits it: class 3, F1, packing group II is in
    L4BN's own group. This is the case the whole check exists for."""
    item = only(check_adr_tank_fit(line(tank("1203", "L4BN"))))
    assert item["fit"] == "fits"
    assert item["required"] == "LGBF"
    assert "4.3.4.1.2" in item["message"]


def test_the_required_code_itself_always_fits():
    item = only(check_adr_tank_fit(line(tank("1203", "LGBF"))))
    assert item["fit"] == "fits"
    assert "LGBF" in item["message"]


def test_a_code_the_regulation_does_not_name():
    """A typo on the approval document must not be answered with a fit."""
    item = only(check_adr_tank_fit(line(tank("1203", "L4BQ"))))
    assert item["fit"] == "cannot_be_assessed"


def test_column_thirteen_is_named_with_every_answer():
    """The regulation's own note: the hierarchy takes no account of the special
    provisions of 4.3.5 and 6.8.4. Those are column (13), and one of them can
    require equipment the hierarchy knows nothing about — so a fit is never
    presented as the whole of the answer while column (13) has something in
    it."""
    item = only(check_adr_tank_fit(line(tank("1203", "L4BN"))))
    assert item["tank_provisions"] == "TU9"
    assert "TU9" in item["provisions_note"]
    assert "4.3.5" in item["provisions_note"]


# --- 4.3.3.1.2, the gases -------------------------------------------------


def test_a_gas_is_answered_from_the_code_hierarchy():
    """UN 1005 requires PxBH(M). P22BH is above it in 4.3.3.1.2 on its letters,
    but the required test pressure is printed as x — it comes from the table of
    4.3.3.2.5, which this application does not hold. So the fit is real and
    conditional, and the condition is named."""
    item = only(check_adr_tank_fit(line(tank("1005", "P22BH"))))
    assert item["fit"] == "fits_under_condition"
    assert "4.3.3.2.5" in item["message"]


def test_a_gas_tank_of_the_wrong_family_does_not_fit():
    """C is a refrigerated tank and P a pressure tank; neither stands in for
    the other, and BN is not BH."""
    assert only(check_adr_tank_fit(line(tank("1005", "C10DH"))))["fit"] == "does_not_fit"
    assert only(check_adr_tank_fit(line(tank("1005", "P10BN"))))["fit"] == "does_not_fit"


def test_the_gas_hierarchy_is_read_from_the_seed():
    """Fifteen rows, and the one line of arithmetic in the whole hierarchy —
    the figure for # is at least the figure for *."""
    row = database.adr_gas_hierarchy("C*BN")
    assert row["also_permitted"] == ["C#BN", "C#CN", "C#DN", "C#BH", "C#CH", "C#DH"]
    assert database.adr_gas_hierarchy("R*DN")["also_permitted"] == ["R#DN"]


# --- what the seed does and does not settle --------------------------------


def test_the_inheritance_is_followed_down_the_chain():
    """A code's group is its own plus the groups of the codes it inherits, and
    those inherit in their turn. L4BN reaches LGAV that way."""
    answer = database.adr_tank_permissions("L4BN")
    assert "LGAV" in answer["inherits"]
    assert any(row["classification_code"] == "F1" for row in answer["permitted"])


def test_no_cell_is_left_unsettled():
    """Where a cell of the chain is not confirmed by two readings, the answer
    is neither yes nor no — that rule stands, and since the fourth reading it
    has nothing left to fire on. The French volume II, the treaty's other
    authentic language, sided with the Dutch on L10BH's group, with the German
    on L10DH's inheritance, and with everyone on S10AH's nine codes — the
    strays of the other readings spell the inheritance sentence (S, G, A, V is
    SGAV leaking into the cell). Every code answers now."""
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    unsettled = [row["tank_code"] for row in seed["rationalised"]
                 if row.get("disputed")]
    assert unsettled == []
    for code in ("L10BH", "L10DH", "S10AH"):
        answer = database.adr_tank_permissions(code)
        assert not answer.get("unsettled"), code


def test_the_seed_says_which_books_it_was_read_from():
    """A seed that cannot name its sources cannot be checked by anyone later."""
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    assert seed["provisions"] == ["4.3.3.1.2", "4.3.4.1.2"]
    assert len(seed["cross_check"]["readings"]) >= 2
    assert seed["editions"]
    counted = seed["cross_check"]["tank_codes"]
    assert counted == len(seed["rationalised"])


def test_a_disputed_cell_carries_every_value_read():
    """The rule every regulatory table in this repository follows: a cell no
    two readings agree on is stored with both values and is not an answer."""
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    languages = set(seed["cross_check"]["readings"])
    for row in seed["rationalised"] + seed["gases"]:
        for field, sides in (row.get("disputed") or {}).items():
            assert set(sides) <= languages, (row["tank_code"], field)
            assert field not in row, (row["tank_code"], field)


# --- what the third reading changed ---------------------------------------


def test_three_books_settle_what_two_could_not():
    """The German volume II joined the English and the printed Dutch in
    v1.86.0, and the difference is what a third reading is for: where one
    edition's reading stands alone against the other two, the other two settle
    the cell. Seven of eighteen codes were settled on every cell before; the
    bookkeeping below is what the seed must keep carrying."""
    check = json.loads(SEED.read_text(encoding="utf-8"))["cross_check"]
    assert check["readings"] == ["en", "nl", "de", "fr"]
    assert check["tank_codes"] == 18
    assert check["codes_settled_on_every_cell"] == 18
    assert check["cells_a_third_reading_settled"] >= 15
    assert check["cells_the_fourth_reading_settled"] == 3
    assert check["cells_no_two_readings_agree_on"] == 0


def test_petrol_in_an_l15bn_tank_is_a_condition_and_not_a_refusal():
    """The plan for this check expected "does not fit" here. The book says
    otherwise: L1.5BN's group holds class 3 F1 packing group II *where the
    vapour pressure at 50 °C is at most 1.1 bar*, and whether this petrol meets
    that is not in table A. So the answer is the condition, named — which is
    the whole difference between a check that reads and one that remembers."""
    item = only(check_adr_tank_fit(line(tank("1203", "L1.5BN"))))
    assert item["fit"] == "fits_under_condition"
    assert item["condition"]
    assert "1,1" in item["condition"] or "1.1" in item["condition"]


def test_a_solids_tank_now_refuses_a_liquid():
    """SGAN is a tank for solids. Before the third reading its group carried a
    cell no two readings agreed on, so the check could only decline; now it can
    say no, which is the answer that protects someone."""
    assert only(check_adr_tank_fit(line(tank("1203", "SGAN"))))["fit"] == "does_not_fit"
