"""Table 7.5.2.2 read instead of referred on — and RID reads differently.

Until v1.41.0 EMCargo only counted how many compatibility groups there were
and handed the question back: "check the compatibility groups". That is honest in
itself, but it is also precisely the question the user cannot answer — they do
not have the books. The table is now in the configuration and is read.

The texts were retrieved verbatim with `scripts/read_land_regulations.py`:

- **ADR 2025 Volume II (ECE/TRANS/352 Vol. II), 7.5.2.2, printed page 593**
  (`--doc adr2 --page 602-603`)
- **RID 2025 (Appendix C to COTIF, Annex), 7.5.2.2, page 1102**
  (`--doc rid --page 1101-1103`)

And there is a difference there worth recording: **the RID table is the ADR table
without compatibility group A.** ADR runs from A to S, RID from B to S. Neither
knows group K. That is a difference in what the table answers and not in the
answer — so a rail leg gets the rail table, and a package of group A on the
railway is told that the table says nothing about it. Borrowing a prohibition is
cautious, borrowing a permission is not, and borrowing a table row that does not
*exist* in the other regime is neither.

The four footnotes appear in both texts in the same wording (RID says "wagon"
where ADR says "vehicle"):

    (a) Packages of group B and packages of group D may be loaded together
        provided they are effectively segregated, so that detonation cannot pass
        from B to D. Segregation by separate compartments or a special
        containment system, and the competent authority has to approve the method.
    (b) Different types of articles of 1.6N together only where it has been
        demonstrated by testing or analogy that no sympathetic detonation occurs.
    (c) Articles of group N together with C, D or E: N is treated as D.
    (d) Packages of group L only together with packages holding the same type of
        substance or article of that group.

One thing that could have gone wrong here and did not: **1.4S does belong.**
Footnote (a) to 7.5.2.1 removes 1.4S from the comparison with *other* classes,
and the old code therefore left 1.4S out everywhere. But 7.5.2.2 is about
explosives among themselves and has an S row — which is not X everywhere. S next
to group L is empty, hence forbidden. Carrying an exception from one provision
over to the other would have approved that combination silently.
"""

import pytest

from app.services.dg.compliance import check_adr_mixed_loading, get_compliance_rules


def product(un, code, name="ARTICLES"):
    return {"un_number": un, "class": code, "classification_code": code,
            "proper_shipping_name": name}


def load(*products, profiles=("ADR",), language="nl"):
    entries = [{"line_id": "L1", "products": list(products)}]
    return [
        w for w in check_adr_mixed_loading(entries, language, list(profiles))
        if "7.5.2.2" in w["rule"]
    ]


def table(which):
    return get_compliance_rules()["adr_mixed_loading"]["compatibility"][which]


@pytest.mark.parametrize("which,size", [("road", 12), ("rail", 11)])
def test_de_tabel_is_symmetrisch(which, size):
    """The check with which the reading of the grid was verified.

    A table of crosses comes out of a PDF as a column of loose characters;
    counting one column wrong yields a table that looks plausible. But mixed
    loading is reciprocal: if B may travel next to D, D may travel next to B. A
    shifted column almost certainly breaks that symmetry somewhere. That is the
    only independent test on the reading here, and that is why it is pinned.
    """
    data = table(which)
    order, matrix = data["group_order"], data["matrix"]

    assert len(order) == size
    assert sorted(matrix) == sorted(order)
    for group in order:
        assert len(matrix[group]) == size, f"rij {group} heeft niet {size} vakjes"
    for a in order:
        for b in order:
            assert matrix[a][order.index(b)] == matrix[b][order.index(a)], f"{a} × {b}"


def test_de_spoortabel_is_de_wegtabel_zonder_groep_a():
    """The only difference between the two texts, recorded here.

    Were RID to deviate from ADR somewhere else, this test should break rather
    than quietly go along with it.
    """
    road, rail = table("road"), table("rail")

    assert set(road["group_order"]) - set(rail["group_order"]) == {"A"}
    for group in rail["group_order"]:
        expected = [road["matrix"][group][road["group_order"].index(other)]
                    for other in rail["group_order"]]
        assert rail["matrix"][group] == expected, f"rij {group} wijkt af"
    assert "K" not in road["group_order"] and "K" not in rail["group_order"]


def test_toegestane_combinatie_levert_geen_melding():
    """C next to D is an X in the table; then the user should hear nothing."""
    assert load(product("0160", "1.1C", "POWDER"), product("0027", "1.1D")) == []


def test_verboden_combinatie_is_een_fout_en_geen_waarschuwing():
    """Group A next to D is an empty cell: that is a prohibition, not a caveat."""
    found = load(product("0473", "1.1A"), product("0027", "1.1D"))

    assert len(found) == 1
    assert found[0]["severity"] == "error"
    assert found[0]["rule"] == "ADR 7.5.2.2 (A × D)"


def test_voetnoot_a_maakt_van_een_verbod_een_voorwaarde():
    """B next to D is allowed, but only with approved segregation — and it says so."""
    found = load(product("0029", "1.1B", "DETONATORS"), product("0027", "1.1D"))

    assert len(found) == 1
    assert found[0]["severity"] == "warning"
    assert "bevoegde autoriteit" in found[0]["message"]


def test_een_vakje_met_twee_voetnoten_geeft_ze_allebei():
    """At D × N the table says "(b), (c)"; both conditions apply, so both are named."""
    found = load(product("0027", "1.1D"), product("0486", "1.6N"))

    assert {w["rule"] for w in found} == {
        "ADR 7.5.2.2 (D × N) (b)",
        "ADR 7.5.2.2 (D × N) (c)",
    }


def test_veertien_s_telt_mee_voor_de_compatibiliteitstabel():
    """1.4S falls outside 7.5.2.1, but not outside 7.5.2.2 — and S × L is empty.

    The old code excluded 1.4S everywhere with the exception belonging to
    7.5.2.1. This combination therefore never even reached the table.
    """
    found = load(product("0349", "1.4S"), product("0190", "1.1L", "SAMPLES"))

    assert len(found) == 1
    assert found[0]["severity"] == "error"
    assert found[0]["rule"] == "ADR 7.5.2.2 (L × S)"


def test_twee_colli_van_groep_l_krijgen_voetnoot_d():
    """On the diagonal this is about two packages of the same group."""
    found = load(product("0190", "1.1L", "SAMPLES A"), product("0224", "1.1L", "SAMPLES B"))

    assert [w["rule"] for w in found] == ["ADR 7.5.2.2 (L × L) (d)"]


def test_een_enkel_collo_van_groep_l_valt_niets_samen_te_laden():
    """With one package there is no combination; footnote (d) is then about nothing."""
    assert load(product("0190", "1.1L", "SAMPLES")) == []


def test_het_spoor_zegt_dat_groep_a_niet_in_zijn_tabel_staat():
    """No ADR row on loan: RID does not know group A and says so."""
    found = load(product("0473", "1.1A"), product("0027", "1.1D"), profiles=("RID",))

    assert len(found) == 1
    assert found[0]["rule"] == "RID 7.5.2.2"
    assert found[0]["severity"] == "warning"
    assert "A" in found[0]["message"] and "RID" in found[0]["message"]


def test_zonder_groep_wordt_er_niet_gegokt():
    """A class 1 package without a classification code cannot be tested; it says so."""
    found = load({"un_number": "0027", "class": "1", "proper_shipping_name": "BLACK POWDER"},
                 product("0029", "1.1B", "DETONATORS"))

    assert len(found) == 1
    assert "niet bekend" in found[0]["message"]


def test_de_bron_staat_bij_de_tabel():
    """Regulatory values carry their source here; otherwise there is nothing to check."""
    compatibility = get_compliance_rules()["adr_mixed_loading"]["compatibility"]

    assert "7.5.2.2" in compatibility["_source"]
    assert "page 593" in compatibility["_source"]
    assert "1102" in compatibility["_source"]
