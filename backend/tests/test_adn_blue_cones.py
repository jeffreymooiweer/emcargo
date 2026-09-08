"""Column (12) of the ADN's table A, and the two things it decides.

The ADN has a table A of its own. Its first columns identify the goods exactly
as the ADR's do, and then it asks a vessel's questions: whether the goods may go
in packages, in bulk or in a tank vessel, what equipment must be aboard, how the
holds are ventilated — and **how many blue cones or blue lights the vessel
shows**. That last one is column (12), and until v1.61.0 EMCargo did not hold
it.

Two provisions were the poorer for it, in different ways:

- **7.1.4.3** was half-answered. Its class rule fired and its two cone rules
  were named as unassessed, which is honest and not much use.
- **7.1.5.0.1** was not answered at all. Which signals a vessel must show is not
  a warning or a nuance; it is a plain fact about the voyage, and the
  application had nowhere to put the question.

What is checked below is mostly the *doubt*, because that is where this could go
wrong quietly. The ADN table is held one row per UN number and the book prints
several for 452 of them. UN 0015 smoke ammunition has three rows and all three
carry three cones, so the answer is safe. UN 1203 petrol has three and they do
not agree, so there is no answer to give — and the difference between those two
cases is measured from the printed rows rather than assumed either way.

Read from the Dutch ADN 2025, 3.2.1 (the column explanations), 7.1.4.3 and
7.1.5.0, by scripts/extract_adn_table_a.py.
"""

import json
from pathlib import Path

import pytest

from app.services.dg.compliance import check_adn_hold_separation, check_adn_signals
from app.services.dg.database import adn_blue_cones

SEED = Path(__file__).resolve().parents[1] / "seed" / "dg" / "adn_table_a.json"


def line(*products):
    return [{"line_id": "L1", "products": list(products)}]


def product(un, hazard_class, code="", **extra):
    return {"un_number": un, "class": hazard_class,
            "classification_code": code, **extra}


# --- the table itself ------------------------------------------------------


def test_the_table_is_the_adn_s_and_not_the_adr_s():
    """Different books, and the giveaway is the substances only one of them has.

    9000 to 9006 are ADN substance numbers — ammonia deeply refrigerated and its
    kind, carried in tank vessels and absent from every road table. If these were
    missing, what had been loaded would be the ADR table under another name.
    """
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    numbers = {entry["un"] for entry in payload["entries"]}
    assert {"9000", "9001", "9002", "9003", "9004", "9005", "9006"} <= numbers
    assert payload["edition"] == "ADN 2025"


def test_every_row_was_checked_against_the_other_rendering():
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    printed = payload["cross_check"]["against_the_printed_table"]
    assert printed["contradicted"] == 0
    assert printed["confirmed"] == 378


def test_the_row_count_prediction_is_checked_and_not_assumed():
    """The ADR table is used to say how many rows a substance has where the ADN
    list page is missing. That is a claim across two regimes, so it is verified
    on the range where both can be seen — and it must stay verified."""
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    prediction = payload["cross_check"]["row_counts_predicted_by_the_adr_table"]
    assert prediction["checked"] > 300
    assert prediction["wrong"] == 0


def test_the_identification_agrees_with_the_road_table():
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    fields = payload["against_the_adr"]["fields"]
    assert fields["class"]["agreement"] == 1.0
    assert fields["name"]["agreement"] == 1.0
    assert fields["classification_code"]["agreement"] > 0.999


def test_a_dash_in_column_12_is_not_a_zero():
    """Zero cones is a provision — the vessel shows none. A dash is the absence
    of one. Read as zero the two would be indistinguishable, and "the book says
    no signal" would be indistinguishable from "the book does not say"."""
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    values = {entry["blue_cones"] for entry in payload["entries"]}
    assert values == {0, 1, 2, 3, None}


# --- what the lookup says --------------------------------------------------


def test_ammonia_shows_two_cones():
    assert adn_blue_cones("1005") == {
        "cones": 2, "certain": True, "carriage_permitted": "T"}


def test_smoke_ammunition_is_settled_even_though_it_has_three_rows():
    """All three rows of UN 0015 carry three cones — they differ in the labels,
    plain against corrosive against toxic-by-inhalation. Several rows is not by
    itself a reason to withhold an answer; several rows that *differ* is."""
    assert adn_blue_cones("0015") == {
        "cones": 3, "certain": True, "carriage_permitted": ""}


def test_petrol_is_not_settled():
    signal = adn_blue_cones("1203")
    assert signal["certain"] is False


def test_a_substance_the_adn_does_not_list_gets_nothing():
    assert adn_blue_cones("9999") is None
    assert adn_blue_cones("") is None


# --- 7.1.4.3.2, which needs both sides -------------------------------------


def test_two_cones_may_not_share_a_hold_with_one_cone_flammable():
    out = check_adn_hold_separation(
        line(product("1005", "2", "2TC"), product("1090", "3", "F1")))
    found = {finding["provision"] for finding in out["findings"]}
    assert "7.1.4.3.2" in found
    finding = next(f for f in out["findings"] if f["provision"] == "7.1.4.3.2")
    assert finding["two_cones"] == ["UN 1005"]
    assert finding["one_cone_flammable"] == ["UN 1090"]


def test_one_cone_that_is_not_flammable_does_not_trip_it():
    """The provision names flammable goods on the one-cone side and not goods
    generally. A one-cone corrosive beside a two-cone toxic gas is a 3 m
    problem under 7.1.4.3.1 and not a shared-hold prohibition."""
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    rows = {entry["un"]: entry for entry in payload["entries"]}
    one_cone_not_flammable = next(
        un for un, entry in sorted(rows.items())
        if entry["blue_cones"] == 1 and entry["certain"]
        and entry["class"] not in ("3", "2")
        and "F" not in entry["classification_code"].upper())
    entry = rows[one_cone_not_flammable]
    out = check_adn_hold_separation(line(
        product("1005", "2", "2TC"),
        product(one_cone_not_flammable, entry["class"],
                entry["classification_code"])))
    assert "7.1.4.3.2" not in {f["provision"] for f in out["findings"]}


def test_two_cones_alone_is_not_a_finding():
    out = check_adn_hold_separation(line(product("1005", "2", "2TC")))
    assert "7.1.4.3.2" not in {f["provision"] for f in out["findings"]}


# --- 7.1.4.3.3, whose three-cone half was unassessed ------------------------


@pytest.mark.parametrize("un,hazard,code", [("3101", "5.2", "P1"),
                                            ("3221", "4.1", "SR1")])
def test_three_cone_goods_of_4_1_and_5_2_go_twelve_metres_away(un, hazard, code):
    out = check_adn_hold_separation(
        line(product(un, hazard, code), product("1090", "3", "F1")))
    finding = next(f for f in out["findings"] if f["provision"] == "7.1.4.3.3")
    assert finding["metres"] == 12.0
    assert f"UN {un}" in finding["message"]


def test_class_4_1_without_three_cones_stays_out_of_it():
    """Which is the whole reason the cones were needed: the provision does not
    say class 4.1, it says class 4.1 for which column (12) prescribes three."""
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    rows = {entry["un"]: entry for entry in payload["entries"]}
    quiet = next(un for un, entry in sorted(rows.items())
                 if entry["class"] == "4.1" and entry["certain"]
                 and entry["blue_cones"] == 0)
    out = check_adn_hold_separation(
        line(product(quiet, "4.1", rows[quiet]["classification_code"]),
             product("1090", "3", "F1")))
    assert "7.1.4.3.3" not in {f["provision"] for f in out["findings"]}


def test_class_1_still_goes_twelve_metres_away_without_any_cone_reading():
    out = check_adn_hold_separation(
        line(product("0004", "1", "1.1D"), product("1090", "3", "F1")))
    assert "7.1.4.3.3" in {f["provision"] for f in out["findings"]}


# --- the doubt, named per substance ----------------------------------------


def test_a_substance_whose_row_is_not_settled_is_named():
    out = check_adn_hold_separation(
        line(product("1203", "3", "F1"), product("1005", "2", "2TC")))
    assert out["cones_not_settled"] == ["UN 1203"]
    assert "UN 1203" in out["not_assessed"]


def test_the_cone_rules_do_not_fire_on_an_unsettled_row():
    """Petrol reads as one cone and is flammable, so a rule that used the value
    would report a shared-hold prohibition. It may well be right — and being
    right by accident on a document somebody signs is not the standard."""
    out = check_adn_hold_separation(
        line(product("1203", "3", "F1"), product("1005", "2", "2TC")))
    assert "7.1.4.3.2" not in {f["provision"] for f in out["findings"]}


def test_nothing_is_named_when_everything_was_settled():
    out = check_adn_hold_separation(
        line(product("1005", "2", "2TC"), product("1090", "3", "F1")))
    assert "not_assessed" not in out
    assert "cones_not_settled" not in out


# --- 7.1.5.0, which had no answer at all -----------------------------------


def test_the_signals_follow_column_12():
    out = check_adn_signals(line(product("1090", "3", "F1")))
    assert out["cones"] == 1
    assert out["provision"] == "7.1.5.0.1"


def test_the_heaviest_signal_on_board_wins():
    """7.1.5.0.4. A single package of a two-cone substance sets the signals for
    the whole vessel, which is why this is a question about the load and not
    about a line."""
    out = check_adn_signals(
        line(product("1090", "3", "F1"), product("1005", "2", "2TC")))
    assert out["cones"] == 2
    assert out["set_by"] == ["UN 1005"]
    assert "UN 1005" in out["highest_wins"]


def test_a_load_that_agrees_with_itself_is_not_told_about_the_tie_break():
    out = check_adn_signals(
        line(product("1090", "3", "F1"), product("1090", "3", "F1")))
    assert "highest_wins" not in out


def test_no_cones_is_an_answer_and_not_a_silence():
    """Most of the table is zero. A check that only ever spoke up when signals
    were needed would leave the commonest case looking like a gap."""
    out = check_adn_signals(line(product("3082", "9", "M6")))
    assert out["cones"] == 0
    assert out["status"] == "ok"


def test_the_container_reduction_is_declared_missing():
    """7.1.5.0.2 can lower the count for goods carried only in containers. Its
    absence can only overstate the signals, and that is worth saying out loud
    rather than leaving a user to discover the app is stricter than the book."""
    out = check_adn_signals(line(product("1005", "2", "2TC")))
    assert "7.1.5.0.2" in out["containers_note"] or "container" in \
        out["containers_note"].lower()


def test_an_unsettled_substance_does_not_set_the_signals():
    out = check_adn_signals(line(product("1203", "3", "F1")))
    assert out["status"] == "not_checked"
    assert "UN 1203" in out["not_assessed"]


def test_an_unsettled_substance_beside_a_settled_one_is_named_not_dropped():
    out = check_adn_signals(
        line(product("1203", "3", "F1"), product("1005", "2", "2TC")))
    assert out["cones"] == 2
    assert out["cones_not_settled"] == ["UN 1203"]


# --- and they reach the document -------------------------------------------
#
# v1.62.0 made the exporter's warnings visible on the document card. Until this
# release the ADN had nothing in that channel: the separation and the signals
# were computed for every inland waterway consignment and appeared on no
# document at all. Which cones a vessel shows is a fact about the voyage; it
# belongs with the papers.


def adn_warnings(products, language="nl"):
    from app.services.documents.exporter import validate_document
    from app.services.documents.registry import get_document

    _errors, warnings = validate_document(
        get_document("adn_transport_doc"), {}, [],
        [{"line_id": "1", "vehicle": "Ruim 1", "products": list(products)}], language)
    return warnings


def test_the_signals_are_on_the_document():
    warnings = adn_warnings([product("1005", "2", "2TC")])
    assert any("7.1.5.0.1" in w and "kegel" in w.lower() for w in warnings), warnings


def test_no_cones_is_stated_on_the_document_too():
    """Nought is the commonest answer and the easiest to mistake for silence."""
    warnings = adn_warnings([product("3082", "9", "M6")])
    assert any("7.1.5.0.1" in w for w in warnings), warnings


def test_the_separation_findings_are_on_the_document():
    warnings = adn_warnings([product("1005", "2", "2TC"), product("1090", "3", "F1")])
    assert any("7.1.4.3.2" in w for w in warnings), warnings
    assert any("7.1.4.3.1" in w for w in warnings), warnings


def test_the_tie_break_is_stated_when_the_load_disagrees_with_itself():
    warnings = adn_warnings([product("1005", "2", "2TC"), product("1090", "3", "F1")])
    assert any("7.1.5.0.4" in w for w in warnings), warnings


def test_an_unsettled_substance_is_named_on_the_document():
    warnings = adn_warnings([product("1203", "3", "F1")])
    assert any("1203" in w and "5.4.1.1.1" not in w for w in warnings), warnings


# --- 7.1.4.3.4, the class 1 compatibility table -----------------------------
#
# Twelve groups, four numbered conditions, and it took two readings to get. The
# Dutch HTML edition is damaged here: row N carries thirteen cells where twelve
# belong, and the D/B cell lost its footnote marker so the table read "1)" one
# way and "(*)" the other. A compatibility table must mirror across its
# diagonal — that is a property of the thing and not of a typesetting — and the
# English edition does, in all 144 cells. It is what this computes with.


def compat():
    from app.services.dg.compliance import get_compliance_rules
    return get_compliance_rules()["adn_hold_separation"]["class_1_compatibility"]


def test_the_table_mirrors_across_its_diagonal():
    """The check that caught the damage, kept as a test so it stays caught."""
    table, groups = compat()["table"], compat()["groups"]
    assert len(groups) == 12
    for a in groups:
        assert set(table[a]) == set(groups), a
        for b in groups:
            assert table[a][b] == table[b][a], f"{a}/{b}"


def test_every_condition_the_table_points_at_exists():
    table, conditions = compat()["table"], compat()["conditions"]
    used = {n for row in table.values() for cell in row.values()
            if isinstance(cell, list) for n in cell}
    assert used == {1, 2, 3, 4}
    for number in used:
        assert str(number) in conditions


def test_two_incompatible_explosives_may_not_share_a_hold():
    out = check_adn_hold_separation(
        line(product("0004", "1", "1.1D"), product("0072", "1", "1.1A")))
    finding = next(f for f in out["findings"] if f["provision"] == "7.1.4.3.4")
    assert sorted(finding["compatibility_groups"]) == ["A", "D"]
    assert "UN 0004" in finding["message"] and "UN 0072" in finding["message"]


def test_two_compatible_explosives_raise_nothing():
    """C with D is an X in the table: the check must stay quiet, or a consignor
    learns that every pair of explosives is a problem and stops reading."""
    out = check_adn_hold_separation(
        line(product("0160", "1", "1.1C"), product("0004", "1", "1.1D")))
    assert "7.1.4.3.4" not in {f["provision"] for f in out["findings"]}


def test_a_conditional_pair_names_its_condition():
    """B with D is permitted only in closed containers — the answer is neither
    yes nor no, and a check that rounded it either way would be wrong."""
    out = check_adn_hold_separation(
        line(product("0073", "1", "1.1B"), product("0004", "1", "1.1D")))
    finding = next(f for f in out["findings"] if f["provision"] == "7.1.4.3.4")
    assert sorted(finding["compatibility_groups"]) == ["B", "D"]
    assert any("gesloten containers" in c for c in finding["conditions"])


def test_group_n_with_c_d_or_e_carries_both_its_conditions():
    out = check_adn_hold_separation(
        line(product("0482", "1", "1.5D"), product("0501", "1", "1.6N")))
    finding = next(f for f in out["findings"] if f["provision"] == "7.1.4.3.4")
    assert len(finding["conditions"]) == 2


def test_a_single_explosive_is_not_paired_with_itself():
    out = check_adn_hold_separation(line(product("0004", "1", "1.1D")))
    assert "7.1.4.3.4" not in {f["provision"] for f in out["findings"]}


def test_two_packages_of_group_l_are_conditional_even_together():
    """L against L is the one diagonal cell that is not a plain X: two group L
    packages may share a hold only if they hold the same type of substance."""
    out = check_adn_hold_separation(
        line(product("0224", "1", "1.1L"), product("0224", "1", "1.1L")))
    finding = next(f for f in out["findings"] if f["provision"] == "7.1.4.3.4")
    assert finding["compatibility_groups"] == ["L", "L"]


def test_class_1_beside_another_class_still_gets_the_twelve_metres():
    out = check_adn_hold_separation(
        line(product("0004", "1", "1.1D"), product("1090", "3", "F1")))
    provisions = {f["provision"] for f in out["findings"]}
    assert "7.1.4.3.3" in provisions
    assert "7.1.4.3.4" not in provisions


# --- 7.1.5.0.2, the threshold that was not legible -------------------------
#
# The Dutch HTML edition lost the comparison sign: both rows of each pair read
# "> 130.000 kg" and "> 30.000 kg", which is not a rule, it is the same rule
# twice. v1.61.0 therefore left the reduction out and said so. The English
# edition has the signs, so the thresholds are recorded here rather than
# guessed — and the guess would have been right, which is exactly why it was
# not good enough.


def reduction():
    from app.services.dg.compliance import get_compliance_rules
    return get_compliance_rules()["adn_signals"]["containers_reduction"]


def test_each_threshold_has_a_side():
    """The defect in miniature: a row that says "above" needs a partner that
    says "at or below", or the table decides nothing."""
    rows = reduction()["rows"]
    for column in (1, 2):
        pair = [r for r in rows if r["column_12"] == column
                and r["selector"] == "class_2_or_pg_i"]
        assert len(pair) == 2, column
        assert {"above_kg"} <= set(pair[0]) or {"at_or_below_kg"} <= set(pair[0])
        limits = {r.get("above_kg") or r.get("at_or_below_kg") for r in pair}
        assert len(limits) == 1, f"the two sides must share one threshold: {limits}"
        assert {"above_kg" in r for r in pair} == {True, False}


def test_the_thresholds_are_the_ones_the_book_prints():
    rows = {(r["column_12"], "above" if "above_kg" in r else "below"): r
            for r in reduction()["rows"] if r["selector"] == "class_2_or_pg_i"}
    assert rows[(1, "above")]["above_kg"] == 130000
    assert rows[(1, "above")]["cones"] == 1
    assert rows[(1, "below")]["at_or_below_kg"] == 130000
    assert rows[(1, "below")]["cones"] == 0
    assert rows[(2, "above")]["above_kg"] == 30000
    assert rows[(2, "above")]["cones"] == 2
    assert rows[(2, "below")]["at_or_below_kg"] == 30000
    assert rows[(2, "below")]["cones"] == 0


def test_three_cones_are_never_reduced():
    three = [r for r in reduction()["rows"] if r["column_12"] == 3]
    assert len(three) == 1
    assert three[0]["cones"] == 3 and three[0]["selector"] == "all"


def test_the_reduction_is_recorded_and_applied_on_the_statement():
    """It sat recorded and unapplied from v1.64.0 to v1.94.0, waiting for the
    input the provision itself requires: the consignor's statement that the
    goods travel exclusively in containers. The statement exists now
    (containers_only) and is still never inferred from a packaging type."""
    assert reduction()["applied"] is True
    assert "containers_only" in reduction()["_why_not_applied"]


def test_the_note_names_the_provision_in_every_language():
    from app.services.dg.compliance import get_compliance_rules
    note = get_compliance_rules()["adn_signals"]["containers_note"]
    for language in ("nl", "en", "de", "fr"):
        text = note[language]
        assert "7.1.5.0.2" in text
