"""Which language the proper shipping name belongs in on the document.

The ADR table in `seed/dg/un_numbers.json` carries two official names per UN
number: `name_en` and `name_de`. Until now the app always took the English one,
even for a German user with a German waybill — while the official German name
was sitting right next to it.

Putting that right is not simply "translate along with the screen", because the
regulations say something different about it per mode:

* **ADR 5.4.1.4.1** (road), and along the same lines RID and ADN: the transport
  document is drawn up in an official language of the forwarding country, and if
  that is not German, English or French, additionally in one of those three. A
  German name on a CMR or CIM is therefore exactly what a German consignor
  needs.
* **IMDG 5.4.1.4.1** (sea) requires English, French or Spanish — not German.
* **IATA DGR 8.1.2.1** (air) requires English.

"SALZSÄURE" on a Shipper's Declaration is therefore not a translation choice but
a refused consignment. Hence: German only when no sea or air profile is in play.

**French is the ADR's own second language.** The treaty is authentic in English
and in French, and column (2) of table A is printed in both; since v1.75.0 the
French column is read (``seed/dg/adr_names_fr.json``) and a French reader is
given ESSENCE rather than GASOLINE. It stands on its own, as 5.4.1.4.1 allows.

**Dutch is the case where that "and additionally" bites.** Dutch is not one of
the three, so ADR 5.4.1.4.1 permits ZOUTZUUR only *together with* the English,
French or German name — not instead of it. So a Dutch road document does not get
"ZOUTZUUR" but "ZOUTZUUR (HYDROCHLORIC ACID)": both names, in one field, exactly
as the article requires. Where the ADR knows no Dutch name for a UN number, the
English one stays on its own.

For a multimodal consignment English satisfies all three regimes and German only
one, so the name in the field is then English — including on the CMR, where
German would have been allowed. That is deliberate. A consignment with a road
and a sea leg then carries the same goods description on every piece of paper,
and that is exactly what a forwarder and customs want to see match; two
languages for the same substance on two documents of the same consignment is a
question you do not want to be asked.

What remains is the case you cannot rule out: first drawing up a Dutch or German
road document, then adding a sea leg. The name is already in the field by then
and is not derived again. That is what :func:`resolve_for_profile` is for, which
resolves the name per document at the moment it goes on paper.
"""

from __future__ import annotations

from typing import Any

from app.core.languages import normalise
from app.services.dg.names_de import german_name
# Aliased: this module has had its own ``english_name(entry)`` since before the
# column was read, and it answers a different question — the name for a
# document, German fallback included. The import is the table's own column.
from app.services.dg.names_en import english_name as english_name_in_table_a
from app.services.dg.names_fr import french_name
from app.services.dg.names_nl import dutch_name

#: Profiles for which the name has to stay English.
ENGLISH_ONLY_PROFILES = {"IMDG", "IATA_DGR"}


def requires_english_name(profiles: list[str] | set[str] | None) -> bool:
    """Does one of the chosen profiles force an English name?"""
    chosen = {str(profile).strip().upper() for profile in (profiles or [])}
    return bool(chosen & ENGLISH_ONLY_PROFILES)


def _whole(name: str) -> bool:
    """A name that was not cut off where the column ran out."""
    return bool(name) and name.count("(") == name.count(")")


def english_name_of(entry: dict[str, Any]) -> str:
    """The English name of an entry, from the 2025 edition where it has one.

    Same shape as the German and the French: the reading of the book comes
    first and the 2023 export is what is left underneath it, for the entries
    the book does not have — the IMDG-only additions have no ADR row at all.

    With one addition the other two languages do not need. A name can run past
    the edge of the column and come back cut off, and one does: UN 2857 reads
    "REFRIGERATING MACHINES ... or ammonia solutions (UN" in the 2025 volume,
    where the export has the whole of it. A truncated name is not a name, and
    preferring the newer edition is not a reason to put half a name on a
    consignment note — so the export carries that one, and where both are cut
    off ``english_name_is_usable`` still says so.
    """
    fresh = english_name_in_table_a(
        str(entry.get("un") or entry.get("un_number") or "")).upper()
    export = str(entry.get("name_en") or "").strip().upper()
    if fresh and not _whole(fresh) and _whole(export):
        return export
    return fresh or export


def english_name(entry: dict[str, Any]) -> str:
    """The English name, falling back on the German rather than on nothing."""
    return (english_name_of(entry)
            or str(entry.get("name_de") or "").strip().upper())


def english_name_is_usable(entry: dict[str, Any]) -> bool:
    """Is there an English proper shipping name, and is it whole?

    Fourteen entries in the Table A **export** carry an empty ``name_en`` — UN
    3245 genetically modified organisms, UN 3374 acetylene solvent free, UN 2807
    magnetized material and eleven more — and UN 1139 carries the truncated
    "Coating solution (". ``english_name`` falls back on the German so a field
    is never blank, but on an IMDG or IATA document a German name is not a
    fallback: 5.4.1.4.1 and 8.1.2.1 require English, and a Dutch road document
    reading "BESCHERMLAK, OPLOSSING (SCHUTZANSTRICHLÖSUNG)" satisfies nothing
    either. So it has to be visible rather than papered over.

    Since the English column is read from the 2025 volume this asks the book
    first, and the check has almost nothing left to refuse — which is the point
    of reading it. What it still refuses is an entry neither source names, and
    the bracket test stays for the same reason it was written: a name cut off
    mid-parenthesis is not an English name, wherever it came from.
    """
    return _whole(english_name_of(entry))


def german_name_of(entry: dict[str, Any]) -> str:
    """The German name of an entry, from the 2025 edition where it has one.

    ``un_numbers.json`` carries a German name from a 2023 export; since v1.79.0
    the same column is read from the ADR 2025 of the Bundesamt für Strassen and
    that reading comes first. Same language, newer edition — and where the 2025
    reading has no name for an entry (the IMDG-only additions have none) the
    older one still carries the field.
    """
    fresh = german_name(str(entry.get("un") or ""))
    if fresh:
        return fresh.upper()
    return str(entry.get("name_de") or "").strip().upper()


def french_name_of(entry: dict[str, Any]) -> str:
    """The French name of an entry, from the entry or from the ADR seed."""
    given = str(entry.get("name_fr") or "").strip()
    return given.upper() if given else french_name(str(entry.get("un") or "")).upper()


def dutch_name_of(entry: dict[str, Any]) -> str:
    """The Dutch name of an entry, from the entry or from the ADR seed."""
    given = str(entry.get("name_nl") or "").strip()
    return given.upper() if given else dutch_name(str(entry.get("un") or "")).upper()


def dutch_document_name(entry: dict[str, Any]) -> str:
    """The Dutch name as ADR 5.4.1.4.1 wants it: with one of the three beside it.

    Dutch is not English, French or German, so the article permits it only
    *together with* one of those three. "ZOUTZUUR" on its own is short of a
    requirement; "ZOUTZUUR (HYDROCHLORIC ACID)" is not. Where the ADR knows no
    Dutch name, or where it reads the same as the English, the English name
    stays on its own — an entry repeated twice in brackets helps nobody.
    """
    dutch = dutch_name_of(entry)
    english = english_name(entry)
    if not dutch or dutch == english:
        return english
    return f"{dutch} ({english})" if english else dutch


def proper_shipping_name(
    entry: dict[str, Any],
    language: str = "nl",
    profiles: list[str] | set[str] | None = None,
) -> str:
    """The proper shipping name from an ADR entry, in capitals.

    German when the user reads German, French when they read French, and
    Dutch-plus-English when they read Dutch; English as soon as a chosen profile
    forces it. The French name is the ADR's own — the treaty is authentic in
    English and in French and table A prints both columns — so it stands alone,
    as 5.4.1.4.1 allows. Where the French edition gives no name for an entry
    the English one carries the field rather than nothing.
    """
    if not requires_english_name(profiles):
        if normalise(language) == "de":
            german = german_name_of(entry)
            if german:
                return german
        elif normalise(language) == "fr":
            french = french_name_of(entry)
            if french:
                return french
        elif normalise(language) == "nl":
            return dutch_document_name(entry)
    return english_name(entry)


def is_german_name(entry: dict[str, Any], name: Any) -> bool:
    """Does this text carry the German name of this entry?

    Used by the export check: whoever first draws up a road document in German
    and then adds a sea leg keeps the German name already filled in — and it may
    not stand there.
    """
    german = german_name_of(entry)
    english = english_name(entry)
    given = str(name or "").strip()
    if not german or not given:
        return False
    if german.casefold() == english.casefold():
        # Some entries read the same in both languages; then there is nothing to
        # report.
        return False
    return given.casefold() == german.casefold()


def is_dutch_name(entry: dict[str, Any], name: Any) -> bool:
    """Does this text carry the Dutch document name of this entry?

    Not merely the Dutch name but the whole "ZOUTZUUR (HYDROCHLORIC ACID)" that
    a road document gets, because that is what stands in the field. On a sea
    document the bracketed English is not an addition of the consignor's but a
    second name, and there only one belongs.
    """
    dutch = dutch_document_name(entry)
    given = str(name or "").strip()
    if not dutch or not given or dutch.casefold() == english_name(entry).casefold():
        return False
    return given.casefold() == dutch.casefold()


def is_french_name(entry: dict[str, Any], name: Any) -> bool:
    """Does this text carry the French name of this entry?"""
    french = french_name_of(entry)
    given = str(name or "").strip()
    if not french or not given:
        return False
    if french.casefold() == english_name(entry).casefold():
        return False
    return given.casefold() == french.casefold()


def is_english_name(entry: dict[str, Any], name: Any) -> bool:
    english = english_name(entry)
    return bool(english) and str(name or "").strip().casefold() == english.casefold()


def is_derived_name(entry: dict[str, Any], name: Any) -> bool:
    """Is this a name EMCargo itself put in the field?

    Only what the app derived is adjusted for another document. Wording of the
    user's own — a technical name with an n.o.s. entry, an addition by the
    consignor — stays as it is; we cannot assess that and must not overwrite it
    silently. All four of the languages the app can derive count, because all
    four can be the one a document was first drawn up in.
    """
    return (is_german_name(entry, name) or is_dutch_name(entry, name)
            or is_french_name(entry, name) or is_english_name(entry, name))


def resolve_for_profile(product: dict[str, Any], profile: str,
                        language: str = "") -> tuple[str, str]:
    """The shipping name belonging on *this* document, and the name replaced.

    The language of the name belongs to the document, not to the consignment.
    One consignment produces a CMR with "BENZIN ODER OTTOKRAFTSTOFF" and an IMO
    DGF with "GASOLINE", from the same data. So there is no point in refusing
    the export and making the user retype the English: EMCargo knows what has
    to be there and puts it there itself.

    Only what EMCargo derived itself is adjusted. If there is wording of the
    user's own — a technical name with an n.o.s. entry, an addition by the
    consignor — it stays; we cannot assess that and certainly must not overwrite
    it silently.

    Since v1.76.0 the same applies to the language the *document* is drawn up
    in, which the export step asks for separately from the language of the
    screen: a consignment entered in Dutch and exported in French carries
    ESSENCE, without anyone retyping it. A profile that forces English still
    wins over that choice — 5.4.1.4.1 at sea and 8.1.2.1 in the air leave no
    room for a preference.

    Returns ``(name_for_this_document, replaced_name)``. When nothing was
    adjusted, the second field is empty.
    """
    current = str(product.get("proper_shipping_name") or "").strip()
    if not current:
        return current, ""
    if requires_english_name([profile]):
        wanted_language = "en"
    elif language:
        wanted_language = normalise(language)
    else:
        return current, ""

    # Enclosed import: database reads naming, so the other way round only here.
    from app.services.dg.database import get_un_entries

    for entry in get_un_entries(str(product.get("un_number") or "")):
        if is_derived_name(entry, current):
            wanted = proper_shipping_name(entry, wanted_language, [profile])
            if wanted and wanted.casefold() != current.casefold():
                return wanted, current
        break
    return current, ""
