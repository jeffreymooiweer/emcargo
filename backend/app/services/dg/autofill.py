"""Automatic completion of dangerous goods data.

The aim: the user fills in as little as possible. The UN number yields almost
the complete classification (offline ADR table A plus derived per-mode data),
the package lines already entered yield counts and masses, and from those the
official description lines for the transport documents are composed.

Legal basis of the generated lines:
- ADR/RID/ADN 5.4.1.1.1: UN number, proper shipping name, hazard labels,
  packing group, tunnel restriction code, number and description of the packages
  and the total quantity per substance.
- ADR 5.4.1.1.1.1: when using the 1.1.3.6 exemption, the total quantity per
  transport category must appear in the transport document.
- IMDG 5.4.1.4/5.4.1.5: additionally flashpoint, marine pollutant and EmS.
- IATA DGR 8.1.6: UN number, PSN, class/division, packing group, number and type
  of packages, net quantity per package and packing instruction.

All results are an aid to filling in; the consignor stays responsible
(DISCLAIMER.md).
"""
from __future__ import annotations

import re
from typing import Any

from app.core.languages import normalise, pick
from app.services.dg.naming import (
    ENGLISH_ONLY_PROFILES,
    is_derived_name,
    proper_shipping_name,
    requires_english_name,
    resolve_for_profile,
)
from app.services.dg.database import get_un_entries, search_packagings
from app.services.units import UNITS, Dimension
from app.services.dg.enrichment import (
    CLASS_DOCUMENT_NOTES,
    PROFILE_DOCUMENT_NOTES,
    clean_value,
    enrich_un_entry,
    parse_hazards,
)

# Fields that are never overwritten automatically once the user has filled them.
_AUTOFILL_FIELDS = (
    "proper_shipping_name",
    "class",
    "subsidiary_risks",
    "packing_group",
    "packing_instruction",
    "transport_category",
    "tunnel_code",
    "labels",
    "hazard_number",
    "ems_code",
    "marine_pollutant",
    "cargo_aircraft_only",
    "limited_quantity",
    "excepted_quantity",
    "quantity_packages",
    "gross_mass_per_package",
    "type_of_package",
)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:[.,]\d+)?", str(value))
    return float(match.group(0).replace(",", ".")) if match else None


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


#: Kilograms before litres, because "kilogram" and "kilo" both contain an "l"
#: and would otherwise be read as litres. The lookarounds are letter-only rather
#: than `\b`: a word boundary does not fire between a digit and a letter, so
#: "100L" — which is how people type it — would have fallen through to the
#: default and become kilograms.
_KILOGRAMS = re.compile(r"(?<![a-z])(kg|kilo(?:gram)?s?)(?![a-z])", re.IGNORECASE)
_LITRES = re.compile(r"(?<![a-z])(l|ltr|lit(?:er|re)s?)(?![a-z])", re.IGNORECASE)


def _unit_of(raw: Any) -> str:
    """The unit written in a quantity, or nothing at all.

    Nothing means nothing: this deliberately does not fall back to kilograms.
    Whether a substance travels by mass or by volume is not reliably derivable
    from table A, and a unit invented here ends up on a signed consignment note
    — 100 litres of acetone is about 79 kg, and 1.1.3.6.3 counts the two
    differently. An absent unit is reported to the user instead (ADR
    5.4.1.1.1 (f)).
    """
    text = str(raw or "")
    if _KILOGRAMS.search(text):
        return "kg"
    if _LITRES.search(text):
        return "L"
    return ""


def _amount(value: float, unit: str) -> str:
    """A quantity for a document: the number, and the unit only if there is one."""
    return f"{_fmt(value)} {unit}".strip()


def _un_prefixed(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.upper().startswith(("UN", "ID")) else f"UN {text}"


#: The columns of Table A that differ between the rows of one UN number and that
#: the application fills in from them. Two rows that agree on all of these are
#: interchangeable for everything EMCargo derives, and choosing between them
#: is not worth a word to the user.
TABLE_A_VARIANT_FIELDS = (
    "packing_group",
    "classification_code",
    "labels",
    "transport_category",
    "tunnel_code",
    "limited_quantity",
    "excepted_quantity",
    "hazard_number",
    "packing_instructions",
)

#: How each of those columns is named to the user. Short, because they end up in
#: one sentence together.
TABLE_A_FIELD_LABELS: dict[str, dict[str, str]] = {
    "packing_group": {"nl": "verpakkingsgroep", "en": "packing group",
                      "de": "Verpackungsgruppe", "fr": "groupe d'emballage"},
    "classification_code": {"nl": "classificatiecode", "en": "classification code",
                            "de": "Klassifizierungscode", "fr": "code de classification"},
    "labels": {"nl": "etiketten", "en": "labels", "de": "Gefahrzettel",
               "fr": "étiquettes"},
    "transport_category": {"nl": "vervoerscategorie", "en": "transport category",
                           "de": "Beförderungskategorie", "fr": "catégorie de transport"},
    "tunnel_code": {"nl": "tunnelcode", "en": "tunnel code", "de": "Tunnelcode",
                    "fr": "code tunnel"},
    "limited_quantity": {"nl": "LQ", "en": "LQ", "de": "LQ", "fr": "QL"},
    "excepted_quantity": {"nl": "E-code", "en": "E code", "de": "E-Code",
                          "fr": "code E"},
    "hazard_number": {"nl": "gevaarsidentificatienummer", "en": "hazard identification No.",
                      "de": "Gefahrnummer", "fr": "numéro d'identification du danger"},
    "packing_instructions": {"nl": "verpakkingsinstructie", "en": "packing instruction",
                             "de": "Verpackungsanweisung", "fr": "instruction d'emballage"},
}

#: The two shapes of the variant note: one that can name a field to enter, and
#: one for the rows no field the user fills in can tell apart.
_VARIANT_NOTE = {
    "nl": "UN {un} heeft {count} rijen in tabel A die verschillen in {fields}. Rij "
          "{chosen} is voorlopig ingevuld. Vul de {settle} in om de juiste rij te "
          "kiezen: {variants}.",
    "en": "UN {un} has {count} rows in Table A differing in {fields}. Row {chosen} was "
          "filled in provisionally. Enter the {settle} to pick the right one: {variants}.",
    "de": "UN {un} hat {count} Zeilen in Tabelle A, die sich in {fields} unterscheiden. "
          "Zeile {chosen} wurde vorläufig eingetragen. Geben Sie die {settle} ein, um die "
          "richtige zu wählen: {variants}.",
    "fr": "L'ONU {un} a {count} lignes au tableau A qui diffèrent par {fields}. La ligne "
          "{chosen} a été remplie à titre provisoire. Indiquez le {settle} pour choisir "
          "la bonne : {variants}.",
}

_VARIANT_NOTE_UNRESOLVABLE = {
    "nl": "UN {un} heeft {count} rijen in tabel A die verschillen in {fields}. Rij "
          "{chosen} is voorlopig ingevuld; classificatiecode en verpakkingsgroep zijn "
          "voor alle rijen gelijk, dus controleer zelf welke van deze op uw zending "
          "slaat: {variants}.",
    "en": "UN {un} has {count} rows in Table A differing in {fields}. Row {chosen} was "
          "filled in provisionally; the classification code and packing group are the "
          "same for every row, so check for yourself which of these describes your "
          "consignment: {variants}.",
    "de": "UN {un} hat {count} Zeilen in Tabelle A, die sich in {fields} unterscheiden. "
          "Zeile {chosen} wurde vorläufig eingetragen; Klassifizierungscode und "
          "Verpackungsgruppe sind für alle Zeilen gleich, prüfen Sie daher selbst, welche "
          "auf Ihre Sendung zutrifft: {variants}.",
    "fr": "L'ONU {un} a {count} lignes au tableau A qui diffèrent par {fields}. La ligne "
          "{chosen} a été remplie à titre provisoire ; le code de classification et le "
          "groupe d'emballage sont identiques pour toutes les lignes, vérifiez donc "
          "vous-même laquelle correspond à votre envoi : {variants}.",
}


def _same_value(value: Any, given: str) -> bool:
    return clean_value(value).strip().upper() == given


def select_table_a_row(
    entries: list[dict[str, Any]], product: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The Table A row to fill from, and the rows that were still in the running.

    Until v1.51.0 this looked at the packing group only, and where every row had
    the same one — or none — the first row was taken in silence. That is not a
    marginal case. **UN 1950, aerosols, has twelve rows in Table A** and they all
    have no packing group: 5A is non-flammable, transport category 3, tunnel code
    E; 5F is flammable (2.1), category 2, tunnel code D; 5T is toxic, category 1.
    A user shipping ordinary flammable spray cans was given the row for the
    non-flammable ones — a points factor three times too low, the wrong tunnel
    code and no flammability label — without a word about it. UN 2037, gas
    cartridges, has nine rows and the same problem, and UN 0015, 0016 and 0303
    differ only in whether the ammunition carries a corrosive or a toxic label.

    What tells the rows apart in ADR is the **classification code** of column
    (3b): 5A, 5F, 5T, 1.2G. So that is looked at first, then the packing group.
    Whatever the user has filled in narrows the field; what is left over is
    returned so the caller can say that a choice is still open.
    """
    candidates = list(entries)
    for field in ("classification_code", "packing_group"):
        given = str(product.get(field) or "").strip().upper()
        if not given:
            continue
        narrowed = [e for e in candidates if _same_value(e.get(field), given)]
        if narrowed:
            candidates = narrowed
    return (candidates[0] if candidates else entries[0]), candidates


def table_a_variant_note(
    entry: dict[str, Any], candidates: list[dict[str, Any]], language: str = "nl"
) -> str | None:
    """What the rows still in the running differ in, and how to choose between them.

    A note that only said "there are several packing groups" could not describe
    UN 1950 at all, because its twelve rows have no packing group. This one names
    the columns that actually differ and lists the alternatives by their
    classification code, which is the field the user can enter to settle it.
    """
    if len(candidates) < 2:
        return None
    differing = [
        field for field in TABLE_A_VARIANT_FIELDS
        if len({clean_value(e.get(field)).strip().upper() for e in candidates}) > 1
    ]
    if not differing:
        # Rows that agree on everything the application uses. UN 1202 has three
        # of them, apart from a special provision it does not compute with.
        return None

    def describe(row: dict[str, Any]) -> str:
        code = clean_value(row.get("classification_code")).strip().upper()
        pg = clean_value(row.get("packing_group")).strip().upper()
        head = " ".join(part for part in (code, f"VG {pg}" if pg else "") if part) or "?"
        detail = ", ".join(
            f"{pick(TABLE_A_FIELD_LABELS[field], language)} "
            f"{clean_value(row.get(field)) or '—'}"
            for field in differing
            if field not in ("classification_code", "packing_group")
        )
        return f"{head} ({detail})" if detail else head

    # What to tell the user to enter. The classification code settles it for UN
    # 1950 and UN 2037, but not for UN 0015, whose three rows are all 1.2G and
    # differ only in the label. Naming a field that does not discriminate is
    # worse than naming none.
    key = next((field for field in ("classification_code", "packing_group")
                if field in differing), None)
    template = _VARIANT_NOTE if key else _VARIANT_NOTE_UNRESOLVABLE
    return pick(template, language).format(
        settle=pick(TABLE_A_FIELD_LABELS[key], language) if key else "",
        un=clean_value(entry.get("un")),
        count=len(candidates),
        fields=", ".join(pick(TABLE_A_FIELD_LABELS[field], language)
                         for field in differing),
        chosen=describe(entry),
        variants="; ".join(describe(row) for row in candidates),
    )


def derive_product(
    product: dict[str, Any], language: str = "nl", profiles: list[str] | None = None
) -> dict[str, Any]:
    """Fill in everything that follows from the UN number; existing input stays."""
    un = str(product.get("un_number") or "").strip()
    if not un:
        return {}
    entries = get_un_entries(un)
    if not entries:
        return {}

    # One UN number can have several Table A rows, and picking the wrong one is
    # not a detail: it changes the transport category (and with it the points
    # factor), the tunnel code, the labels and the LQ. What the user has already
    # filled in narrows the choice — the classification code first, because that
    # is the column ADR uses to tell the rows apart.
    entry, candidates = select_table_a_row(entries, product)

    extras = enrich_un_entry(entry, language)
    hazards = parse_hazards(entry)

    derived: dict[str, Any] = {
        "proper_shipping_name": proper_shipping_name(entry, language, profiles),
        "class": hazards["division"],
        "subsidiary_risks": ", ".join(hazards["subsidiary_risks"]),
        "classification_code": hazards["classification_code"],
        "packing_group": clean_value(entry.get("packing_group")),
        "packing_instruction": clean_value(entry.get("packing_instructions")).split(" ")[0],
        "transport_category": clean_value(entry.get("transport_category")),
        "tunnel_code": clean_value(entry.get("tunnel_code")),
        "labels": clean_value(entry.get("labels")),
        "hazard_number": clean_value(entry.get("hazard_number")),
        "limited_quantity": clean_value(entry.get("limited_quantity")),
        "excepted_quantity": clean_value(entry.get("excepted_quantity")),
    }
    if extras.get("ems_code"):
        derived["ems_code"] = extras["ems_code"]
    if extras.get("environmentally_hazardous"):
        derived["marine_pollutant"] = "P"
    if extras.get("cargo_aircraft_only"):
        derived["cargo_aircraft_only"] = "Y"
    if extras.get("iata_packing_instruction"):
        derived["iata_packing_instruction"] = extras["iata_packing_instruction"]

    # Complete empty fields only: manual corrections are preserved.
    patch = {
        key: value
        for key, value in derived.items()
        if value not in (None, "") and not str(product.get(key) or "").strip()
    }
    hints = {
        key: value
        for key, value in extras.items()
        if key.endswith(("_text", "_note", "_default", "_source", "_description", "_variants",
                         "_options", "_codes", "_changes", "_requirement", "_category"))
    }

    # More than one row still in the running: the first was filled in, and that
    # was a choice nobody made. It has to be said, and it has to say what the
    # rows differ in — otherwise the user cannot tell whether it matters.
    note = table_a_variant_note(entry, candidates, language)
    if note:
        hints["table_a_variant_note"] = note
        # Kept under the old key as well: the interface, the export and the
        # tests all read that one, and a note nobody renders is no note.
        hints["packing_group_note"] = note

    if extras.get("air_forbidden"):
        hints["air_forbidden"] = True
    if extras.get("transport_forbidden"):
        hints["transport_forbidden"] = True

    # B8: points of attention belong to the active mode. Sea information (EmS,
    # stowage, segregation, marine pollutant) is noise on a pure road leg, and
    # the aviation prohibition says nothing on an inland waterway document.
    # Without profiles nothing is filtered.
    active = {p.upper() for p in (profiles or [])}
    if active:
        def _relevant(key: str) -> bool:
            if key.startswith(("ems_", "imdg_", "marine_pollutant_", "segregation_groups_")):
                return "IMDG" in active
            if key.startswith("air_"):
                return "IATA_DGR" in active
            if key in ("limited_quantity_text", "excepted_quantity_text"):
                return bool({"ADR", "RID", "ADN", "IMDG"} & active)
            return True

        hints = {key: value for key, value in hints.items() if _relevant(key)}

    return {"patch": patch, "hints": hints}


def _unit_names_a_packaging(unit: str) -> bool:
    """Whether the line's unit says what the goods are packed in.

    "1000 jerrycans" counts packagings and answers 5.4.1.1.1 (e); "1000 kg"
    counts mass and answers nothing about the package. The unit was taken
    over regardless, which put "kg" on the document as the kind of package —
    and for a line without any stated unit it took over ``pcs``, the bare
    piece count the parser falls back to. That is not a packaging either:
    the catalogue then matched "pcs" through "pc" to the code 6PC and the
    searchable packaging field turned into a dropdown with that one
    nonsensical choice.

    A unit the table does not know is the consignor's own word ("fust",
    "octabin") and is taken over as before.
    """
    known = UNITS.get(unit.strip().lower())
    if known is None:
        return True
    return known.dimension is Dimension.COUNT and known.code != "pcs"


def derive_from_line(product: dict[str, Any], line: dict[str, Any] | None) -> dict[str, Any]:
    """Take counts and masses over from the package line already entered."""
    if not line:
        return {}
    patch: dict[str, Any] = {}
    quantity = line.get("quantity")
    if quantity not in (None, "") and not str(product.get("quantity_packages") or "").strip():
        number = _num(quantity)
        patch["quantity_packages"] = (
            _fmt(number) if number is not None else str(quantity))
    unit = str(line.get("unit") or "").strip()
    if (unit and _unit_names_a_packaging(unit)
            and not str(product.get("type_of_package") or "").strip()):
        patch["type_of_package"] = unit
    per_package = _num(line.get("weight_each_kg"))
    if per_package and not str(product.get("gross_mass_per_package") or "").strip():
        patch["gross_mass_per_package"] = f"{_fmt(per_package)} kg"
    # "1000 jerrycans van 25l": the content of one package was in the
    # description all along; the pipeline read it, so it is never asked.
    content = str(line.get("package_content") or "").strip()
    if content and not str(product.get("net_mass_liters_per_package") or "").strip():
        patch["net_mass_liters_per_package"] = content
    return patch


def total_quantity(product: dict[str, Any]) -> tuple[float | None, str]:
    """Total quantity of a product: net per package × number of packages.

    The unit is read from **the same field the number came from**. It used to be
    read from the per-package field alone, which is right while that field is
    filled and wrong the moment it is empty: the number then fell back to
    `adr_total_quantity` while the unit stayed on its "kg" default, so "100 L"
    came out as "100 kg" — on the document, in the category totals of
    5.4.1.1.1.1, and written back over what the user had typed.

    That is not a corner: the wizard requires only UN number, name and class for
    ADR, RID and ADN, so a consignor who fills in nothing but the total quantity
    the 1.1.3.6 points count needs takes this path every time.
    """
    per_package = _num(product.get("net_mass_liters_per_package"))
    count = _num(product.get("quantity_packages"))
    if per_package is None:
        raw_total = product.get("adr_total_quantity")
        return _num(raw_total), _unit_of(raw_total)
    unit = _unit_of(product.get("net_mass_liters_per_package"))
    if count is None:
        return per_package, unit
    return per_package * count, unit


def _is_class1(product: dict[str, Any]) -> bool:
    return str(product.get("class") or "").strip().startswith("1")


#: UN 0333 to 0337, the fireworks entries of 5.4.1.2.1 (g).
_FIREWORK_UN_NUMBERS = {"0333", "0334", "0335", "0336", "0337"}


def _entry_name(product: dict[str, Any]) -> str:
    """The list's own name for this entry, upper-cased.

    Read from table A rather than from whatever the consignor typed: the
    two conditions below are properties of the *entry*, and a shipper who
    writes "waterstofperoxide" must still get the right answer.
    """
    un = "".join(c for c in str(product.get("un_number")
                                or product.get("un") or "") if c.isdigit())
    rows = get_un_entries(un.zfill(4)) if un else []
    name = str((rows[0] if rows else {}).get("name_en")
               or product.get("proper_shipping_name") or "")
    return name.upper()


def _needs_temperature_control(product: dict[str, Any]) -> bool:
    """Does 5.4.1.2.3.1 apply to this entry?

    The provision points at 2.2.41.1.17, 2.2.41.1.21 and 2.2.52.1.15 for
    *which* substances need control. Those criteria turn on the SADT and the
    formulation, which no table holds — but the Dangerous Goods List names the
    outcome: the entries that require it say "TEMPERATURE CONTROLLED" in the
    proper shipping name itself. That is the measured signal, and it is the
    same one the label and the packing instruction key off.

    A consignment the consignor has already marked as temperature controlled
    counts too, because a substance can require control under a formulation
    the entry name does not carry.
    """
    if product.get("temperature_controlled"):
        return True
    return "TEMPERATURE CONTROLLED" in _entry_name(product)


def _is_refrigerated_liquefied(product: dict[str, Any]) -> bool:
    """5.4.1.2.2 (d) speaks of refrigerated liquefied gases, and the list
    names them: the entries read "REFRIGERATED LIQUID"."""
    return "REFRIGERATED LIQUID" in _entry_name(product)


_LAND_PROFILES = {"ADR", "RID", "ADN"}


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


#: The plural a cargo line speaks in, against the singular the packagings
#: catalogue labels carry.
_PACKAGE_PLURALS = {
    "vaten": "vat", "drums": "vat", "jerrycans": "jerrycan",
    "flessen": "fles", "dozen": "doos", "zakken": "zak", "kisten": "kist",
    "cans": "jerrycan", "bags": "zak", "boxes": "doos",
}


def _packaging_kind_options(word: str, language: str = "nl") -> list[str]:
    """The catalogue's kinds of one packaging word, as choosable values.

    "jerrycan" finds 3A1/3A2/3B1/3B2/3H1/3H2 with their labels; a word the
    catalogue does not know finds nothing and no question is asked. The value
    carries code plus label, exactly the shape the wizard's packaging picker
    writes — the document then renders it as "label (code)" per 5.4.1.1.1 (e).
    """
    label_language = "nl" if normalise(language) == "nl" else "en"
    for query in (word, _PACKAGE_PLURALS.get(word.lower()), word.rstrip("s")):
        if not query:
            continue
        hits = search_packagings(query, limit=10)
        if hits:
            return [
                f"{p['code']} {(p.get('label') or {}).get(label_language) or (p.get('label') or {}).get('en', '')}".strip()
                for p in hits
            ]
    return []

#: A footnote marker at the end of a table C density cell ("0,68 - 0,72 10)").
_DENSITY_FOOTNOTE = re.compile(r"\s*\d+\)\s*$")

#: What the density note says, per document language. The value is the book's,
#: the caveat is the consignor's: table C prints the relative density of the
#: substance as listed, and the actual product may differ.
_DENSITY_NOTE = {
    "nl": ("ADN 3.2 tabel C geeft als relatieve dichtheid: {values}. "
           "Controleer de waarde voor uw eigen product "
           "(veiligheidsinformatieblad, rubriek 9); daar staat ook d50."),
    "en": ("ADN 3.2 Table C gives the relative density as: {values}. "
           "Check the value against your own product "
           "(safety data sheet, section 9), which also gives d50."),
    "de": ("ADN 3.2 Tabelle C nennt als relative Dichte: {values}. "
           "Prüfen Sie den Wert für Ihr eigenes Produkt "
           "(Sicherheitsdatenblatt, Abschnitt 9); dort steht auch d50."),
    "fr": ("Le tableau C du 3.2 de l'ADN donne comme densité relative : "
           "{values}. Vérifiez la valeur pour votre propre produit "
           "(fiche de données de sécurité, rubrique 9), qui donne aussi d50."),
}


def table_c_density(un_number: str) -> dict[str, Any] | None:
    """The relative density column of ADN table C, as printed.

    The consignor was being asked for the density of petrol at 15 °C as if
    everyone knows it, while a read edition of the ADN prints a density for
    329 of the 678 table C rows. What the book prints is returned verbatim
    (footnote markers stripped); only where the column gives one single clean
    number is a machine-readable value offered alongside — a range or a bound
    ("0,68 - 0,72", "< 0,85") is shown, never averaged into an answer.
    """
    from app.services.dg.database import adn_table_c_rows

    printed: list[str] = []
    for row in adn_table_c_rows(un_number):
        cell = _DENSITY_FOOTNOTE.sub("", str(row.get("density") or "").strip())
        if cell and cell not in printed:
            printed.append(cell)
    if not printed:
        return None
    single = None
    if len(printed) == 1 and re.fullmatch(r"\d+(?:[.,]\d+)?", printed[0]):
        single = printed[0].replace(",", ".")
    return {"printed": printed, "single": single}


def open_questions_for(
    product: dict[str, Any], profiles: list[str], language: str = "nl"
) -> list[dict[str, Any]]:
    """The questions that remain genuinely open after everything derivable is in.

    The DG step used to show every field as if it were a question, and the ones
    the derivation had already answered looked like work. This names the
    remainder: facts of the consignment no table can supply, each with the
    reason it is asked. The interface renders exactly this list and nothing
    else as a question; everything answered is shown as an answer.

    Computed on the *merged* product — after `derive_product` and
    `derive_from_line` — so a value the line or the table already supplied is
    never asked again.
    """
    un = str(product.get("un_number") or "").strip()
    if not un or product.get("transport_forbidden"):
        # Without a UN number the substance itself is the question; with a
        # prohibition there is no consignment to complete.
        return []

    def empty(field: str) -> bool:
        return not str(product.get(field) or "").strip()

    active = {p.upper() for p in profiles}
    land = bool(_LAND_PROFILES & active)
    questions: list[dict[str, Any]] = []

    def ask(field: str, required: bool, reason: str) -> None:
        if empty(field) and not any(q["field"] == field for q in questions):
            questions.append({"field": field, "required": required, "reason": reason})

    if land:
        # The mode decides what every other answer means: admission, tunnel,
        # placarding and the tank checks all branch on it.
        ask("carriage_mode", True, "carriage_mode_decides")

    # "jerrycan" says what kind of thing the package is; 5.4.1.1.1 (e) lets
    # the UN packaging code supplement that description. Where the package is
    # still a bare word, the catalogue's kinds of that word become an
    # optional choice — 3A1 steel against 3H1 plastic is a fact of the
    # consignment the consignor knows by looking at the yard.
    package = _clean_str(product.get("type_of_package"))
    if package and not _PACKAGING_CODE.match(package):
        kinds = _packaging_kind_options(package, language)
        if kinds and not any(q["field"] == "type_of_package" for q in questions):
            questions.append({"field": "type_of_package", "required": False,
                              "reason": "packaging_spec", "options": kinds})

    # 3.1.2.2: where the position combines several proper shipping names,
    # only the most applicable one goes on the document — and which one that
    # is, only the consignor knows. The choice is asked in the language(s)
    # the document will carry: the document language itself, and English
    # beside it where a Dutch document pairs the names (5.4.1.4.1) or a
    # profile forces English outright.
    from app.services.dg.name_detection import name_choices

    def ask_choice(field: str, choice_language: str) -> None:
        if not empty(field):
            return
        choices = name_choices(un, choice_language)
        if len(choices) > 1 and not any(q["field"] == field for q in questions):
            questions.append({"field": field, "required": True,
                              "reason": "sp3122", "options": choices})

    if requires_english_name(profiles):
        ask_choice("chosen_name_en", "en")
    else:
        lang = normalise(language)
        if lang == "en":
            ask_choice("chosen_name_en", "en")
        else:
            ask_choice("chosen_name", lang)
            if lang not in ("de", "fr"):
                # The German and French names stand alone on a document; any
                # other language pairs the name with English (5.4.1.4.1).
                ask_choice("chosen_name_en", "en")

    rows = get_un_entries(un)
    provisions = str((rows[0] if rows else {}).get("special_provisions") or "")
    if "274" in provisions.replace(",", " ").split():
        ask("technical_name", True, "sp274")

    # 5.4.1.2, what certain classes add to the transport document. Each of
    # these was named in the guidance panel as something to remember, which is
    # not the same as a field that reaches the paper — a consignor who reads
    # "state the control temperature" and has nowhere to state it has been
    # told about a gap rather than helped across it. Asked only in the
    # situation the provision describes, so an ordinary load sees none of them.
    hazard_class = str(product.get("class") or "").strip()
    if land:
        # 5.4.1.2.3.1: self-reactive substances and polymerizing substances of
        # class 4.1 and organic peroxides of class 5.2 that need temperature
        # control. Which entries those are is table A's to say through the
        # temperature-control special provisions; what the temperatures are is
        # the consignor's. Both are asked together because the provision
        # prints them together and one without the other says nothing.
        if hazard_class in ("4.1", "5.2") and _needs_temperature_control(product):
            ask("control_temperature", True, "temperature_control_541231")
            ask("emergency_temperature", True, "temperature_control_541231")
        # 5.4.1.2.2 (d): a refrigerated liquefied gas in a tank carries the
        # date its actual holding time ends. Only in a tank — a cylinder has
        # no holding time to end.
        if (hazard_class.startswith("2")
                and str(product.get("carriage_mode") or "").strip()
                in ("tank", "portable_tank")
                and _is_refrigerated_liquefied(product)):
            ask("end_of_holding_time", True, "holding_time_541222d")
        # 5.4.1.2.2 (e): UN 1012 is four different gases under one number, and
        # special provision 398 asks which one, in brackets after the name.
        if un.zfill(4) == "1012":
            ask("specific_gas_name", True, "gas_name_541222e")
        # 5.4.1.2.4: class 6.2 names a responsible person with a telephone
        # number, over and above the consignee's own details.
        if hazard_class.startswith("6.2"):
            ask("responsible_person", True, "responsible_541224")
        # 5.4.1.2.1 (g): fireworks carry the classification reference the
        # competent authority issued, in the form XX/YYZZZZ.
        if un.zfill(4) in _FIREWORK_UN_NUMBERS:
            ask("firework_classification", True, "fireworks_541219")

    if _is_class1(product):
        ask("net_explosive_mass", True, "nem_class1")
    elif land and empty("adr_total_quantity"):
        # The total computes from count × net contents; what is missing is
        # whichever of the two the line did not supply.
        ask("quantity_packages", False, "totals_11136")
        ask("net_mass_liters_per_package", False, "totals_11136")

    if "ADN" in active and str(product.get("carriage_mode") or "") != "tank":
        if empty("hold") and empty("container_number"):
            ask("hold", False, "hold_74111")
    if str(product.get("carriage_mode") or "") == "tank":
        ask("density_15", False, "filling_degree")

    if "IMDG" in active:
        ask("quantity_packages", True, "imdg_document")
        ask("type_of_package", True, "imdg_document")
        # 5.4.1.5.11: the 24-hour emergency number. Usually prefilled from the
        # saved preferences; asked only while nothing supplied it.
        ask("emergency_contact", True, "imdg_document")
    if "IATA_DGR" in active:
        for field in ("packing_instruction", "quantity_packages",
                      "type_of_package", "net_mass_liters_per_package",
                      "emergency_contact"):
            ask(field, True, "iata_declaration")
    return questions


def adr_quantity(product: dict[str, Any]) -> tuple[float | None, str]:
    """The quantity 1.1.3.6 computes with.

    For class 1 that is the net explosive mass (1.1.3.6.3), not the product
    mass: 50 kg of fireworks is not 50 kg of explosive substance. Without a NEM
    filled in this deliberately yields nothing, so that the points count reports
    "incomplete" instead of computing with the wrong mass.
    """
    if _is_class1(product):
        nem = _num(product.get("net_explosive_mass"))
        return (nem, "kg") if nem is not None else (None, "kg")
    return total_quantity(product)


#: The modes of carriage for which RID 5.3.2.1.1 prescribes the orange plate,
#: and therefore the modes in which RID 5.4.1.1.1 (j) puts the hazard
#: identification number on the transport document. Read twice — the English
#: edition on printed page 5-27 and the German on 5-27 of its own numbering —
#: which list tank-wagons, battery-wagons, wagons with demountable tanks,
#: tank-containers, MEGCs, portable tanks and wagons or containers for carriage
#: in bulk. For a full load of packages of one and the same substance the plate
#: *may* be affixed rather than shall, and whether it was is not something this
#: application can see; that case is reported instead (see check_rid_hazard_id).
_RID_MARKED_MODES = {"tank", "portable_tank", "bulk"}


def rid_marking_prescribed(product: dict[str, Any]) -> bool:
    """Whether RID 5.3.2.1 marking is prescribed for how these goods travel."""
    return str(product.get("carriage_mode") or "").strip() in _RID_MARKED_MODES


#: The words 5.4.1.1.3, 5.4.1.1.5, 5.4.1.1.6.1 and 5.4.1.1.18 put on the
#: document, in the languages this application writes documents in. Read in the
#: official Dutch edition (pages 991-996), the RID English and German editions
#: (846/906 — the provisions are shared word for word) and the UNECE English
#: and French volumes II. These are document entries, not interface strings:
#: the regulation prescribes the word itself, so it follows the language of the
#: document under 5.4.1.4.1 and is always English where the document must be
#: (IMDG 5.4.1.4.1, IATA DGR 8.1.2.1).
_WASTE_WORD = {
    "nl": "AFVAL", "en": "WASTE", "de": "ABFALL", "fr": "DÉCHET"}
_EMPTY_UNCLEANED = {
    "nl": "LEEG, ONGEREINIGD", "en": "EMPTY, UNCLEANED",
    "de": "LEER, UNGEREINIGT", "fr": "VIDE, NON NETTOYÉ"}
_SALVAGE = {
    "packaging": {
        "nl": "BERGINGSVERPAKKING", "en": "SALVAGE PACKAGING",
        "de": "BERGUNGSVERPACKUNG", "fr": "EMBALLAGE DE SECOURS"},
    "pressure_receptacle": {
        "nl": "BERGINGSDRUKHOUDER", "en": "SALVAGE PRESSURE RECEPTACLE",
        "de": "BERGUNGSDRUCKGEFÄSS", "fr": "RÉCIPIENT À PRESSION DE SECOURS"},
}
_ENVIRONMENTALLY_HAZARDOUS = {
    "nl": "MILIEUGEVAARLIJK", "en": "ENVIRONMENTALLY HAZARDOUS",
    "de": "UMWELTGEFÄHRDEND", "fr": "DANGEREUX POUR L'ENVIRONNEMENT"}

#: 5.4.1.1.18's own exception: the names of UN 3077 and 3082 already say it,
#: and the additional entry is expressly not required for them.
_ENV_SELF_EVIDENT = {"3077", "3082"}

#: 5.4.1.1.23: a substance solid by the definition of 1.2.1, offered molten,
#: carries the qualifying word as part of the proper shipping name — unless the
#: name already says it (3.1.2.5). Read in the UNECE English and French volumes
#: II, the RID German edition and the Dutch edition (page 996).
_MOLTEN = {"nl": "GESMOLTEN", "en": "MOLTEN",
           "de": "GESCHMOLZEN", "fr": "FONDU"}

#: 5.4.1.1.19, UN 3509 alone: the name is complemented with the residues'
#: classes and subsidiary hazards, in class-numbering order — and 5.4.1.1.1 (f)
#: then does not apply. The book's own example is
#: "UN 3509 PACKAGINGS, DISCARDED, EMPTY, UNCLEANED (WITH RESIDUES OF 3, 4.1,
#: 6.1), 9".
_RESIDUES_OF = {"nl": "BEVAT RESTEN VAN", "en": "WITH RESIDUES OF",
                "de": "MIT RÜCKSTÄNDEN VON", "fr": "AVEC DES RÉSIDUS DE"}

#: 5.4.1.1.20: carriage under 2.1.2.8 puts a statement in the transport
#: document, and the provision prescribes its wording — the German edition
#: even sets it in capitals, which is kept as that edition prints it.
_CLASSIFIED_2_1_2_8 = {
    "nl": "Ingedeeld overeenkomstig 2.1.2.8",
    "en": "Classified in accordance with 2.1.2.8",
    "de": "GEMÄSS UNTERABSCHNITT 2.1.2.8 KLASSIFIZIERT",
    "fr": "Classé conformément au 2.1.2.8",
}

#: 5.4.1.2.3.1 prints its own sentence, and the words are the provision's
#: rather than ours: "Control temperature: ... °C Emergency temperature: ... °C".
_TEMPERATURE_CONTROL = {
    "nl": "Controletemperatuur: {control} °C Noodtemperatuur: {emergency} °C",
    "en": "Control temperature: {control} °C Emergency temperature: {emergency} °C",
    "de": "Kontrolltemperatur: {control} °C Notfalltemperatur: {emergency} °C",
    "fr": "Température de régulation : {control} °C Température critique : {emergency} °C",
}

#: 5.4.1.2.2 (d) prints the format as well as the words.
_END_OF_HOLDING_TIME = {
    "nl": "Einde holdingtijd: {date}",
    "en": "End of holding time: {date}",
    "de": "Ende der Haltezeit: {date}",
    "fr": "Fin du temps de retenue : {date}",
}

#: 5.4.1.2.4: the person, beside the consignee of (h).
_RESPONSIBLE_PERSON = {
    "nl": "Verantwoordelijke persoon: {person}",
    "en": "Responsible person: {person}",
    "de": "Verantwortliche Person: {person}",
    "fr": "Personne responsable : {person}",
}

#: 5.4.1.2.1 (g), with the reference the authority issued.
_FIREWORK_CLASSIFICATION = {
    "nl": "Classificatie van vuurwerk door de bevoegde autoriteit met vuurwerkreferentie {reference}",
    "en": "Classification of fireworks by the competent authority with the firework reference {reference}",
    "de": "Klassifizierung der Feuerwerkskörper durch die zuständige Behörde mit der Feuerwerksreferenz {reference}",
    "fr": "Classification des artifices par l'autorité compétente avec la référence d'artifice {reference}",
}


def _document_word(words: dict[str, str], profile: str, language: str) -> str:
    """The regulation's word in the language of *this* document."""
    if profile in ENGLISH_ONLY_PROFILES:
        return words["en"]
    return words.get((language or "nl").split("-")[0].lower(), words["en"])


def _adn_tank_vessel_line(product: dict[str, Any], language: str) -> str | None:
    """The description of ADN 5.4.1.1.2, for carriage in tank vessels.

    A cargo tank consignment used to get the packages line of 5.4.1.1.1, and
    the two are not the same document entry. 5.4.1.1.2 takes its data from
    **table C**: (b) the proper shipping name of column (2), (c) the data of
    column (5) with the numbers after the first in brackets — the ADN's own
    example is "UN 1203 MOTOR SPIRIT, 3 (N2, CMR, F), II" — (d) the packing
    group, and (e) the mass in tonnes. Read on printed page 349 of the UNECE
    English edition; table C itself is in the repository since v1.73.0, read
    from three books.

    Returns None where table C does not list the substance: composing the
    packages line instead is wrong twice over, so the caller falls back to it
    only as the least-bad line and the compliance side already refuses the
    carriage (3.2.1 column (8)).
    """
    from app.services.dg.database import adn_table_c_rows

    un = str(product.get("un_number") or "").strip()
    rows = adn_table_c_rows(un)
    if not rows:
        return None
    given_pg = str(product.get("packing_group") or "").strip().upper()
    fitting = [r for r in rows
               if not given_pg
               or str(r.get("packing_group") or "").strip().upper() == given_pg]
    rows = fitting or rows

    # (b): the name of column (2), in the language of the document — and, the
    # ADN being authentic in English and French with no German table C here,
    # a German document gets the English name rather than an invented one.
    lang = (language or "nl").split("-")[0].lower()
    name = str(rows[0].get({"nl": "name_nl", "fr": "name_fr"}.get(lang, "name_en"))
               or rows[0].get("name_en") or "").strip().upper()
    technical = str(product.get("technical_name") or "").strip()
    if technical:
        name = f"{name} ({technical})"

    # (c): the data of column (5). The reading splits tokens on "+" and may
    # carry a line-break space inside one ("C MR"); whitespace inside a token
    # is typesetting, not content. Where the rows in the running disagree on
    # the cell, nothing is invented: the substance's own class stands alone,
    # which is what 5.4.1.1.2 (c) itself prescribes for goods not mentioned by
    # name in table C.
    cells = {re.sub(r"\s+", "", str(r.get("dangers") or "")) for r in rows}
    if len(cells) == 1 and next(iter(cells)):
        tokens = [t for t in next(iter(cells)).split("+") if t]
    else:
        tokens = [str(product.get("class") or "").strip()]
    hazard = tokens[0] if tokens else ""
    if len(tokens) > 1:
        hazard = f"{hazard} ({', '.join(tokens[1:])})"

    parts = [_un_prefixed(un), name, hazard,
             str(product.get("packing_group") or "").strip()]
    line = ", ".join(p for p in parts if p)

    # (e): the mass in tonnes. Litres are not tonnes without a density this
    # application does not presume to apply, so only a mass converts; anything
    # else is left to the quantity fields, where its absence is already
    # reported rather than papered over.
    total, unit = total_quantity(product)
    if total is not None and unit == "kg":
        line = f"{line}, {_fmt(total / 1000.0)} t"
    return line


def description_line(product: dict[str, Any], profile: str, language: str = "",
                     values: dict[str, Any] | None = None) -> str:
    """Official description line for the transport document.

    One builder for every caller. The exporter used to compose its own, and two
    renderings of one provision drift the moment either is corrected: the
    subsidiary label models and the hazard identification number below would
    have reached the wizard and not the CMR.
    """
    values = values or {}

    # ADN, carriage in tank vessels: a different provision entirely.
    # 5.4.1.1.2 composes from table C, and 7.1.1.21 is what makes a cargo tank
    # load a tank vessel. The waste word of 5.4.1.1.3 applies there as much as
    # anywhere — it is a special provision of 5.4.1.1, not of the packages line.
    if (profile == "ADN"
            and str(product.get("carriage_mode") or "").strip() == "tank"):
        vessel_line = _adn_tank_vessel_line(product, language)
        if vessel_line is not None:
            if product.get("is_waste"):
                word = _document_word(_WASTE_WORD, profile, language)
                if word not in vessel_line:
                    prefix, _, rest = vessel_line.partition(", ")
                    vessel_line = f"{prefix}, {word} {rest}"
            return vessel_line

    # The name follows the document: on an IMDG or IATA line it should be
    # English, even when the consignment was drawn up in German (IMDG 5.4.1.4.1,
    # IATA DGR 8.1.2.1).
    psn = resolve_for_profile(product, profile, language)[0].upper()
    # 5.4.1.1.3: waste containing dangerous goods carries the word before the
    # proper shipping name, unless the name already says it — the provision's
    # own example is "UN 1230 AFVAL METHANOL, 3 (6.1), II, (D/E)".
    if product.get("is_waste"):
        word = _document_word(_WASTE_WORD, profile, language)
        if word not in psn:
            psn = f"{word} {psn}"
    # 5.4.1.1.23: offered molten, the qualifying word joins the name — unless
    # the name already says it, as SULPHUR, MOLTEN does.
    if product.get("molten"):
        word = _document_word(_MOLTEN, profile, language)
        if word not in psn:
            psn = f"{psn}, {word}"
    # 5.4.1.1.19, UN 3509 alone: the residues' classes complement the name.
    un_digits = "".join(
        c for c in str(product.get("un_number") or "") if c.isdigit()).zfill(4)
    discarded = un_digits == "3509"
    if discarded:
        residues = str(product.get("residue_classes") or "").strip()
        if residues:
            word = _document_word(_RESIDUES_OF, profile, language)
            psn = f"{psn} ({word} {residues})"
    technical = str(product.get("technical_name") or "").strip()
    if technical:
        psn = f"{psn} ({technical})"
    hazard = str(product.get("class") or "").strip()
    subsidiary = str(product.get("subsidiary_risks") or "").strip()
    if subsidiary:
        hazard = f"{hazard} ({subsidiary})"
    parts = [
        _un_prefixed(product.get("un_number")),
        psn,
        hazard,
        str(product.get("packing_group") or "").strip(),
    ]
    # ADR only. The tunnel restriction code comes from column 15 of ADR Table A
    # and belongs on the road document under 5.4.1.1.1 (k). RID Table A does not
    # have that column and the ADN transport document does not carry it either —
    # "(D/E)" on a CIM or an ADN document is an invented entry on an official
    # piece of paper.
    if profile == "ADR":
        tunnel = str(values.get("tunnel_restriction")
                     or product.get("tunnel_code") or "").strip().strip("()")
        if tunnel:
            parts.append(f"({tunnel})")
    if profile == "IATA_DGR":
        # Show an IATA packing instruction only: the ADR instruction (P001,
        # IBC02, …) is not valid for air freight.
        instruction = str(product.get("iata_packing_instruction") or "").strip()
        if instruction:
            parts.append(f"PI {instruction}")
        if str(product.get("cargo_aircraft_only") or "").strip().upper() in {"Y", "YES", "JA", "TRUE", "1"}:
            parts.append("CARGO AIRCRAFT ONLY")
    if profile == "IMDG":
        flashpoint = str(product.get("flashpoint") or "").strip()
        if flashpoint:
            parts.append(f"vlampunt {flashpoint}" if not flashpoint.lower().startswith("v") else flashpoint)
        if str(product.get("marine_pollutant") or "").strip().upper() in {"P", "Y", "YES", "JA", "TRUE", "1"}:
            parts.append("MARINE POLLUTANT")
        ems = str(product.get("ems_code") or "").strip()
        if ems:
            parts.append(f"EmS {ems}")

    line = ", ".join(p for p in parts if p)

    # RID 5.4.1.1.1 (j), and rail alone. Where a marking under 5.3.2.1 is
    # prescribed, the hazard identification number goes *before* the letters
    # "UN", and the text is explicit about the order: (j), (a), (b), (c), (d)
    # with no information interspersed. Its own example is
    # "663, UN 1098 ALLYL ALCOHOL, 6.1(3), I". The ADR has no such paragraph —
    # its (k) is the tunnel restriction code — so a number in front of a CMR
    # would be an entry nobody asked for.
    if profile == "RID" and rid_marking_prescribed(product):
        hazard_number = str(product.get("hazard_number") or "").strip()
        if hazard_number:
            line = f"{hazard_number}, {line}"

    # 5.4.1.1.6.1: an empty means of containment, uncleaned, carrying residues
    # of anything but class 7, says so before or after the description — and
    # 5.4.1.1.1 (f) then does not apply, so no total quantity is composed for
    # residues nobody has weighed. The fuller substitutions of 5.4.1.1.6.2 are
    # permissions, not requirements ("may be replaced"); the form always
    # allowed is the one composed.
    empty_uncleaned = bool(product.get("empty_uncleaned"))
    if empty_uncleaned:
        line = f"{line}, {_document_word(_EMPTY_UNCLEANED, profile, language)}"

    # 5.4.1.1.5: goods travelling in a salvage packaging or salvage pressure
    # receptacle carry the word after the description of the goods.
    salvage = str(product.get("salvage_packaging") or "").strip().lower()
    if salvage:
        words = _SALVAGE.get(salvage, _SALVAGE["packaging"])
        line = f"{line}, {_document_word(words, profile, language)}"

    # 5.4.1.1.18: a substance meeting 2.2.9.1.10 carries the additional entry —
    # except UN 3077 and 3082, whose names already say it, and except at sea,
    # where "MARINE POLLUTANT" (which the IMDG branch above already adds) is
    # the entry the provision itself points at.
    if (profile in ("ADR", "RID", "ADN")
            and (product.get("environmentally_hazardous")
                 or str(product.get("marine_pollutant") or "").strip().upper()
                 in {"P", "Y", "YES", "JA", "TRUE", "1"})):
        if un_digits not in _ENV_SELF_EVIDENT:
            line = (f"{line}, "
                    f"{_document_word(_ENVIRONMENTALLY_HAZARDOUS, profile, language)}")

    # Number and type of packages + total quantity (ADR 5.4.1.1.1 e/f).
    count = str(product.get("quantity_packages") or "").strip()
    package = _package_description(str(product.get("type_of_package") or "").strip())
    packages = " ".join(p for p in [count, package] if p)
    total, unit = total_quantity(product)
    tail = []
    if packages:
        tail.append(packages)
    # (f) does not apply to empty uncleaned containment (5.4.1.1.6.1) nor to
    # UN 3509 (5.4.1.1.19): both carry residues nobody has weighed.
    if total is not None and not empty_uncleaned and not discarded:
        tail.append(_amount(total, unit))
    # Class 1 on a land document: the total net explosive mass belongs in the
    # transport document (ADR 5.4.1.2.1 (a)).
    if profile in ("ADR", "RID", "ADN") and _is_class1(product):
        nem = _num(product.get("net_explosive_mass"))
        if nem is not None:
            tail.append(f"NEM {_fmt(nem)} kg")
    if tail:
        line = f"{line}, {', '.join(tail)}"

    # 5.4.1.1.20: carriage under 2.1.2.8 adds the prescribed statement, worded
    # as the provision sets it in the language of the document.
    if profile in ("ADR", "RID", "ADN") and product.get("classified_2_1_2_8"):
        line = f"{line}, {_document_word(_CLASSIFIED_2_1_2_8, profile, language)}"

    # 5.4.1.2, what certain classes add. Each is printed in the provision's own
    # words, and each appears only when its field was filled in: an empty
    # control temperature must leave no half-sentence like "Control
    # temperature:  °C" on a signed document.
    if profile in ("ADR", "RID", "ADN"):
        control = str(product.get("control_temperature") or "").strip()
        emergency = str(product.get("emergency_temperature") or "").strip()
        # Both or neither: 5.4.1.2.3.1 prints one sentence carrying the pair,
        # and half of it is not the statement the provision asks for.
        if control and emergency:
            line = (f"{line}, "
                    + _document_word(_TEMPERATURE_CONTROL, profile, language).format(
                        control=_degrees(control), emergency=_degrees(emergency)))
        holding = str(product.get("end_of_holding_time") or "").strip()
        if holding:
            line = (f"{line}, "
                    + _document_word(_END_OF_HOLDING_TIME, profile, language).format(
                        date=holding))
        person = str(product.get("responsible_person") or "").strip()
        if person:
            line = (f"{line}, "
                    + _document_word(_RESPONSIBLE_PERSON, profile, language).format(
                        person=person))
        reference = str(product.get("firework_classification") or "").strip()
        if reference:
            line = (f"{line}, "
                    + _document_word(
                        _FIREWORK_CLASSIFICATION, profile, language).format(
                            reference=reference))
    return line


def _degrees(value: str) -> str:
    """A temperature as the document wants it: the number, sign kept, without
    a unit — the provision's sentence supplies the "°C" itself, and "−20 °C °C"
    is how that goes wrong."""
    text = str(value).strip()
    match = re.search(r"-?\d+(?:[.,]\d+)?", text)
    return match.group(0) if match else text


def _name_was_ours(current: Any, entry: dict[str, Any]) -> bool:
    """Did this application write the current shipping name itself?

    True for a derived full-column name and for a previously chosen 3.1.2.2
    alternative (alone or as a "NAME (ENGLISH NAME)" pair) — those may be
    replaced when the consignor picks differently. Anything else is the
    user's own wording and is never overwritten.
    """
    current = str(current or "").strip()
    if not current:
        return True
    if is_derived_name(entry, current):
        return True
    from app.services.dg.name_detection import name_choices

    un = str(entry.get("un") or "")
    choices = {c for lang in ("nl", "en", "de", "fr")
               for c in name_choices(un, lang)}
    if current in choices:
        return True
    match = re.fullmatch(r"(.+?) \((.+)\)", current)
    return bool(match and match.group(1) in choices and match.group(2) in choices)


_PACKAGING_CODE = re.compile(r"^(\d{1,2}[A-Z]{1,2}\d?)\s+(.+)$")


def _package_description(package: str) -> str:
    """The package on the document as 5.4.1.1.1 (e) words it.

    "UN packaging codes may only be used as a supplement to the description of
    the kind of package [e.g. one box (4G)]" — so a field that starts with the
    code the packaging picker wrote ("3H1 Kunststof jerrycan…") is turned
    around into "Kunststof jerrycan… (3H1)". Only a code the packagings
    catalogue actually knows is treated as one: "25 L" also matches the shape
    of a code, and is not one.
    """
    match = _PACKAGING_CODE.match(package)
    if not match:
        return package
    code, description = match.group(1), match.group(2)
    if any(p["code"] == code for p in search_packagings(code, limit=20)):
        return f"{description} ({code})"
    return package


def adr_category_totals(entries: list[dict[str, Any]], language: str = "nl") -> dict[str, Any]:
    """Totale hoeveelheid per vervoerscategorie (ADR 5.4.1.1.1.1)."""
    totals: dict[str, dict[str, float]] = {}
    for entry in entries:
        for product in entry.get("products") or []:
            if product.get("transport_forbidden"):
                continue
            category = str(product.get("transport_category") or "").strip()
            if not category:
                continue
            total, unit = adr_quantity(product)
            if total is None:
                continue
            totals.setdefault(category, {}).setdefault(unit, 0.0)
            totals[category][unit] += total

    if not totals:
        return {"statement": "", "categories": []}

    rows = []
    for category in sorted(totals):
        amounts = ", ".join(_amount(value, unit) for unit, value in sorted(totals[category].items()))
        rows.append({"transport_category": category, "total": amounts})
    prefix = pick(
        {
            "nl": "Totale hoeveelheid per vervoerscategorie",
            "en": "Total quantity per transport category",
            "de": "Gesamtmenge je Beförderungskategorie", "fr": 'Quantité totale par catégorie de transport'},
        language,
    )
    statement = f"{prefix}: " + "; ".join(f"{r['transport_category']}: {r['total']}" for r in rows)
    return {"statement": statement, "categories": rows}


def prepare_entries(
    entries: list[dict[str, Any]],
    lines: list[dict[str, Any]] | None = None,
    profiles: list[str] | None = None,
    language: str = "nl",
) -> dict[str, Any]:
    """Complete DG positions automatically and compose the document lines."""
    lines_by_id = {line.get("line_id"): line for line in (lines or [])}
    profiles = [p.upper() for p in (profiles or [])] or ["ADR"]
    prepared: list[dict[str, Any]] = []
    hints: list[dict[str, Any]] = []

    for entry in entries:
        products = []
        for index, product in enumerate(entry.get("products") or []):
            merged = dict(product)
            derived = derive_product(merged, language, profiles)
            if derived:
                merged.update(derived["patch"])
                if derived["hints"]:
                    hints.append({
                        "line_id": entry.get("line_id"),
                        "product_index": index,
                        "un_number": merged.get("un_number"),
                        **derived["hints"],
                    })
            merged.update(derive_from_line(merged, lines_by_id.get(entry.get("line_id"))))
            # 3.1.2.2: a chosen name replaces the whole column — but only a
            # name this application derived itself. Wording of the user's own
            # in the shipping-name field is never overwritten.
            chosen = str(merged.get("chosen_name") or "").strip()
            chosen_en = str(merged.get("chosen_name_en") or "").strip()
            if chosen or chosen_en:
                rows_for_name = get_un_entries(str(merged.get("un_number") or ""))
                current_name = merged.get("proper_shipping_name")
                if rows_for_name and _name_was_ours(current_name, rows_for_name[0]):
                    if requires_english_name(profiles):
                        if chosen_en:
                            merged["proper_shipping_name"] = chosen_en
                    elif chosen and chosen_en:
                        # A Dutch document pairs the chosen Dutch name with the
                        # chosen English one, the way 5.4.1.4.1 is served.
                        merged["proper_shipping_name"] = f"{chosen} ({chosen_en})"
                    elif chosen:
                        merged["proper_shipping_name"] = chosen
            # The density the tank questions need, pulled from where it is
            # already known: table C of the read ADN edition. One clean number
            # fills d15 (visible in the summary, editable); a printed range is
            # shown and never averaged into an answer.
            if (str(merged.get("carriage_mode") or "") == "tank"
                    and _LAND_PROFILES & set(profiles)):
                density = table_c_density(str(merged.get("un_number") or ""))
                if density:
                    if density["single"] and not str(merged.get("density_15") or "").strip():
                        merged["density_15"] = density["single"]
                    note = _DENSITY_NOTE.get(language, _DENSITY_NOTE["nl"])
                    hints.append({
                        "line_id": entry.get("line_id"),
                        "product_index": index,
                        "un_number": merged.get("un_number"),
                        "density_note": note.format(values="; ".join(density["printed"])),
                    })
            # A transport prohibition belongs on the product itself: the points
            # count, document lines and totals then skip such a line instead of
            # computing with it.
            if derived and derived["hints"].get("transport_forbidden"):
                merged["transport_forbidden"] = True
            # Total quantity for the 1.1.3.6 points calculation and the Q value.
            # These two are COMPUTED values and are derived afresh from the
            # current package input on every call. They used to be filled in only
            # when empty, so after a change of count or contents the old totals
            # stayed and the points count and Q value computed with stale
            # figures. Anyone wanting to fix the total sets
            # adr_total_quantity_override or q_net_quantity_override
            # respectively. For class 1, 1.1.3.6.3 computes with the net
            # explosive mass; without a NEM the total deliberately stays empty so
            # the count reports "incomplete".
            total, unit = adr_quantity(merged)
            override = str(merged.get("adr_total_quantity_override") or "").strip()
            if override:
                merged["adr_total_quantity"] = override
            elif total is not None:
                merged["adr_total_quantity"] = _amount(total, unit)
            elif _is_class1(merged):
                merged.pop("adr_total_quantity", None)
            per_package = merged.get("net_mass_liters_per_package")
            q_override = str(merged.get("q_net_quantity_override") or "").strip()
            if q_override:
                merged["q_net_quantity"] = q_override
            elif per_package:
                merged["q_net_quantity"] = str(per_package)
            products.append(merged)
        prepared.append({**entry, "products": products})

    open_questions: list[dict[str, Any]] = []
    for entry in prepared:
        for index, product in enumerate(entry["products"]):
            questions = open_questions_for(product, profiles, language)
            if questions:
                open_questions.append({
                    "line_id": entry.get("line_id"),
                    "product_index": index,
                    "un_number": product.get("un_number"),
                    "questions": questions,
                })

    document_lines: dict[str, list[str]] = {}
    for profile in profiles:
        rows = [
            description_line(product, profile)
            for entry in prepared
            for product in entry["products"]
            # For a substance that may not be offered for carriage there is no
            # document line to compose; the prohibition is already there.
            if str(product.get("un_number") or "").strip()
            and not product.get("transport_forbidden")
        ]
        document_lines[profile] = [row for row in rows if row]

    # Additional document requirements the user has to supply themselves.
    requirements: list[str] = []
    seen_classes: set[str] = set()
    for entry in prepared:
        for product in entry["products"]:
            base_class = str(product.get("class") or "").split(".")[0]
            division = str(product.get("class") or "")
            for key in (division, base_class):
                note = CLASS_DOCUMENT_NOTES.get(key)
                if note and key not in seen_classes:
                    seen_classes.add(key)
                    requirements.append(note[language if language in note else "nl"])
                    break
    for profile in profiles:
        note = PROFILE_DOCUMENT_NOTES.get(profile)
        if note:
            requirements.append(note[language if language in note else "nl"])

    result: dict[str, Any] = {
        "entries": prepared,
        "document_lines": document_lines,
        "hints": hints,
        "requirements": requirements,
        "open_questions": open_questions,
    }
    if {"ADR", "RID", "ADN"} & set(profiles):
        result["adr_category_totals"] = adr_category_totals(prepared, language)
    return result
