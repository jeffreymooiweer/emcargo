"""Offline UN number and packaging database.

Sources (see README):
- **ADR 2025 table A**, read out of the official Dutch edition by
  ``scripts/extract_adr_table_a.py`` and checked against the alphabetical index
  of the same edition: the Dutch name, class, classification code, packing
  group, labels, special provisions, LQ/EQ, packing instructions, the four
  carriage provision columns, transport category, tunnel code and hazard number.
  This is the table the application computes with.
- The ADR 2023 table A export, for the one thing the Dutch book cannot have:
  the **English and German** proper shipping names. Every other field it carried
  has been superseded.
- 49 CFR 172.101 (eCFR, public domain): English proper shipping names.
- UN packaging codes per ADR 6.1.2 / 6.5.1.4 / 6.6.2.

Note: this is a factual compilation as an aid to filling in; the current
ADR/IMDG/IATA edition remains authoritative.
"""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from functools import lru_cache
from pathlib import Path

from app.services.dg import amendment_42_24
from app.services.dg.enrichment import clean_value, enrich_un_entry, parse_hazards
from app.services.dg.names_nl import dutch_name
from app.services.dg.naming import proper_shipping_name

_SEED_DIR = Path(__file__).resolve().parents[3] / "seed" / "dg"

_lock = threading.Lock()
_un_cache: list[dict] | None = None
_pack_cache: list[dict] | None = None


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


#: The fields table A supplies, and which this application therefore no longer
#: takes from the 2023 export.
_TABLE_A_FIELDS = (
    "class", "classification_code", "packing_group", "labels",
    "special_provisions", "limited_quantity", "excepted_quantity",
    "packing_instructions", "carriage_packages", "carriage_bulk",
    "carriage_loading", "carriage_operation", "transport_category",
    "tunnel_code", "hazard_number",
    # The tank columns, carried since v1.65.0. (10) and (11) are the portable
    # tank instruction and its provisions, (12) the ADR tank code, (13) its
    # provisions, (14) the vehicle the substance then requires — FL, AT or EX/III.
    "portable_tank_instructions", "portable_tank_provisions",
    "tank_code", "tank_provisions", "tank_vehicle",
)

#: What decides that a row of the book and a row of the export describe the same
#: entry. Every one of these agreed exactly between the two independently
#: typeset readings of the book, which is what makes them usable as a key.
_ROW_KEY = ("classification_code", "packing_group", "labels",
            "transport_category", "tunnel_code", "hazard_number",
            "limited_quantity", "excepted_quantity")


@lru_cache(maxsize=1)
def _table_a() -> list[dict]:
    """Table A of ADR 2025, as read out of the official Dutch edition.

    Until v1.56.0 this application computed with an export of ADR **2023**,
    patched: the eleven rows 2025 added were carried in by hand and the two it
    withdrew were flagged in place. A patch covers what was added and nothing of
    what was changed, and 2025 changes a field on 316 of the 2,334 UN numbers
    the two editions share. UN 3423 tetramethylammonium hydroxide, solid moved
    from class 8 to class 6.1 — different labels, a different transport
    category, hazard number 668 instead of 80 — and the application went on
    saying class 8.
    """
    try:
        payload = json.loads(
            (_SEED_DIR / "adr_table_a.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - seed missing
        return []
    return list(payload.get("entries", []))


@lru_cache(maxsize=1)
def _adn_table_a() -> dict[str, dict]:
    """Table A of the ADN, by UN number — the inland waterway table.

    Its first columns hold the same identification as the ADR's, and then it
    asks a vessel's questions instead of a vehicle's. Column (12) is the one
    this application was missing: **the number of blue cones or blue lights**.
    Two of the three provisions of 7.1.4.3 are stated in cones and had to be
    named unassessed, and 7.1.5.0.1 — which signals the vessel must show — could
    not be answered at all.

    Only one row per UN number is available. Where the book gives a substance
    several rows the entry carries ``printed_rows`` above one, and the value may
    belong to a sibling: UN 1203 petrol has three rows. `blue_cones` is
    therefore read together with `cones_certain`, and a check that cannot tell
    the rows apart says so rather than picking one.
    """
    try:
        payload = json.loads(
            (_SEED_DIR / "adn_table_a.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - seed missing
        return {}
    return {entry["un"]: entry for entry in payload.get("entries", [])}


def _row_key(entry: dict) -> tuple[str, ...]:
    labels = "+".join(sorted(
        part.strip() for part in
        str(entry.get("labels", "")).replace("+", ",").split(",")
        if part.strip()))
    return tuple(labels if name == "labels" else str(entry.get(name, "")).strip()
                 for name in _ROW_KEY)


@lru_cache(maxsize=1)
def _export_rows() -> tuple[dict[str, dict[tuple, list[dict]]], dict[str, dict]]:
    """The 2023 export, indexed for the one thing it is still needed for.

    The Dutch edition of the ADR has no English or German column, and there is
    no other source for those names. So the export stays, reduced to that: a
    row's foreign names, found by the fields the two editions agree on, and the
    UN number's names as a fallback where 2025 moved one of those fields.
    """
    by_key: dict[str, dict[tuple, list[dict]]] = {}
    by_un: dict[str, dict] = {}
    try:
        rows = json.loads((_SEED_DIR / "un_numbers.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - seed missing
        return {}, {}
    for row in rows:
        by_key.setdefault(row["un"], {}).setdefault(_row_key(row), []).append(row)
        by_un.setdefault(row["un"], row)
    return by_key, by_un


def _foreign_names(entry: dict, used: dict[str, set[int]]) -> tuple[str, str]:
    """The English and German name for one row of table A.

    Matched on the key first, so that the three UN 0015 rows keep their own
    German names — "mit ätzenden Stoffen" against "mit beim Einatmen giftigen
    Stoffen" is the whole difference between them. Where 2025 changed a field in
    the key there is no match, and the UN number's name is used: a variant name
    is better wrong than a name absent.
    """
    by_key, by_un = _export_rows()
    rows = by_key.get(entry["un"], {}).get(_row_key(entry), [])
    for index, row in enumerate(rows):
        if index not in used.setdefault(entry["un"] + str(_row_key(entry)), set()):
            used[entry["un"] + str(_row_key(entry))].add(index)
            return row.get("name_en", ""), row.get("name_de", "")
    fallback = by_un.get(entry["un"], {})
    return fallback.get("name_en", ""), fallback.get("name_de", "")


@lru_cache(maxsize=1)
def forbidden_un_numbers() -> set[str]:
    """UN numbers ADR does not admit for carriage.

    Read from the 2023 export, which marks them in words, and not from the 2025
    table, which does not. The Dutch edition expresses a prohibition by leaving
    the row empty — no labels, no packing instruction, no transport category —
    and that is not a signature this application may act on, because it is the
    same signature as "not subject to ADR". UN 1327 hay, UN 1845 dry ice and
    seventeen others are equally blank and are the opposite case: goods that
    travel freely. Deriving a prohibition from an absence would refuse them.

    Fourteen UN numbers, and the 2025 table agrees with every one of them as far
    as it can: twelve are blank in it and the two that are not — UN 3137 and
    UN 3255 — carry no labels and no transport category either.
    """
    _by_key, by_un = _export_rows()
    return {un for un, row in by_un.items()
            if "VERBOTEN" in str(row.get("labels") or "").upper()}


def withdrawn_un_numbers() -> set[str]:
    """UN numbers the 2023 export carries and ADR 2025 no longer knows.

    Derived rather than listed. A hand-kept list of withdrawals has to be
    remembered at every edition; the difference between the two tables cannot be
    forgotten. Today it yields UN 1499 and UN 1999.
    """
    _by_key, by_un = _export_rows()
    return set(by_un) - {row["un"] for row in _table_a()}


def _imdg_only_entries(known: set[str]) -> list[dict]:
    """UN numbers IMDG 42-24 carries that ADR 2025 table A does not.

    Since v1.56.0 the road table is the 2025 edition, so the eleven entries of
    the 23rd revised edition of the UN Model Regulations are in it natively and
    no longer arrive here with sea data only. What is left is whatever the sea
    code knows and the road book does not, which is the case this was for.
    """
    entries: list[dict] = []
    for item in amendment_42_24.new_un_numbers():
        if item["un"] in known:
            continue
        hazard = str(item.get("class") or "")
        entries.append({
            "un": item["un"],
            "name_en": item.get("name_en", ""),
            "name_de": "",
            # The DGL names the division itself; Table A does so via the labels.
            "class": hazard.split(".")[0] if hazard.startswith("1.") else hazard,
            "classification_code": hazard if hazard.startswith("1.") else "",
            "packing_group": item.get("packing_group", ""),
            "labels": hazard,
            "special_provisions": item.get("special_provisions", ""),
            "limited_quantity": item.get("limited_quantity", "0"),
            "excepted_quantity": item.get("excepted_quantity", "E0"),
            "packing_instructions": item.get("packing_instructions", ""),
            "transport_category": "",
            "tunnel_code": "",
            "hazard_number": "",
            "imdg_only": True,
            "source_note": "IMDG 42-24 — niet in tabel A van ADR 2025",
        })
    return entries


def _withdrawn_entries(withdrawn: set[str]) -> list[dict]:
    """An entry ADR 2025 dropped, kept findable and marked as dropped.

    An older transport document may still refer to it, and a lookup that returns
    nothing reads as "this UN number does not exist" rather than "this edition
    no longer carries it". So the 2023 row stays, saying which it is.
    """
    _by_key, by_un = _export_rows()
    rows = json.loads((_SEED_DIR / "un_numbers.json").read_text(encoding="utf-8"))
    entries = []
    for row in rows:
        if row["un"] not in withdrawn:
            continue
        entry = dict(row)
        entry["withdrawn_in"] = "ADR 2025"
        entry["source_note"] = (
            "Niet meer in ADR 2025; deze rij komt uit de uitgave 2023")
        entries.append(entry)
    return entries


def _load_un() -> list[dict]:
    global _un_cache
    with _lock:
        if _un_cache is None:
            used: dict[str, set[int]] = {}
            entries: list[dict] = []
            from_the_sea = {item["un"]: item
                            for item in amendment_42_24.new_un_numbers()}
            for row in _table_a():
                name_en, name_de = _foreign_names(row, used)
                sea = from_the_sea.get(row["un"])
                if not name_en and sea:
                    # The eleven entries of the 23rd revised edition are in the
                    # 2025 book and were never in the 2023 export, so there is no
                    # English name to be had there. The sea code has one.
                    name_en = sea.get("name_en", "")
                entry = {"un": row["un"], "name_en": name_en, "name_de": name_de,
                         # The name a *document* carries is the whole of column
                         # (2), alternatives and all: UN 1203 is "BENZINE OF
                         # MOTORBRANDSTOF" and 5.4.1.4.1 wants it that way. The
                         # row's own reading is kept beside it, because that is
                         # what tells the three UN 0015 rows apart.
                         "name_nl": dutch_name(row["un"]) or row.get("name_nl", ""),
                         "name_nl_row": row.get("name_nl", "")}
                entry.update({field: row.get(field, "") for field in _TABLE_A_FIELDS})
                inland = _adn_table_a().get(row["un"])
                if inland:
                    entry["adn_blue_cones"] = inland.get("blue_cones")
                    entry["adn_carriage_permitted"] = inland.get(
                        "carriage_permitted", "")
                    # The ADN table gives one row per UN number. Where the book
                    # gives several *and they differ in the vessel's columns*,
                    # every ADR row of that number gets the same cone count here
                    # and one of them is the wrong one. UN 0015 has three rows
                    # and all three carry three cones; UN 1203 has three and they
                    # do not agree. The extraction settles which is which.
                    entry["adn_cones_certain"] = bool(inland.get("certain"))
                if sea:
                    entry["source_note"] = (
                        f"ADR 2025 tabel A (blz. {row.get('page')}) + IMDG 42-24")
                entries.append(entry)
            forbidden = forbidden_un_numbers()
            for entry in entries:
                if entry["un"] in forbidden:
                    entry["transport_forbidden"] = True
            withdrawn = withdrawn_un_numbers()
            entries += _withdrawn_entries(withdrawn)
            entries += _imdg_only_entries({e["un"] for e in entries})
            for entry in entries:
                # A Dutch name is what most of this application's users search
                # on: whoever typed "zoutzuur" used to get nothing at all,
                # because the index held only English and German.
                if not entry.get("name_nl"):
                    entry["name_nl"] = dutch_name(entry["un"])
                entry["_search"] = _normalize(
                    f"{entry.get('name_en', '')} {entry.get('name_de', '')} "
                    f"{entry['name_nl']} {entry.get('name_nl_row', '')}"
                )
            _un_cache = entries
    return _un_cache


def _load_packagings() -> list[dict]:
    global _pack_cache
    with _lock:
        if _pack_cache is None:
            entries = json.loads((_SEED_DIR / "packagings.json").read_text(encoding="utf-8"))
            for entry in entries:
                label = entry.get("label") or {}
                entry["_search"] = _normalize(f"{entry['code']} {label.get('nl', '')} {label.get('en', '')}")
            _pack_cache = entries
    return _pack_cache


def _public(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if not k.startswith("_")}


def search_un_numbers(
    query: str,
    limit: int = 12,
    language: str = "nl",
    profiles: list[str] | None = None,
) -> list[dict]:
    query = query.strip()
    if not query:
        return []
    digits = "".join(ch for ch in query if ch.isdigit())
    text = _normalize(query)
    entries = _load_un()

    scored: list[tuple[int, dict]] = []
    if digits and digits == query.replace("UN", "").replace("un", "").strip():
        for entry in entries:
            if entry["un"] == digits.zfill(4):
                scored.append((100, entry))
            elif entry["un"].startswith(digits) or entry["un"].lstrip("0").startswith(digits):
                scored.append((80, entry))
    elif len(text) >= 2:
        for entry in entries:
            hay = entry["_search"]
            # A name the entry *starts* with outranks one it merely contains, and
            # that has to hold for each of the three languages. Weighing only the
            # English put "zoutzuur" behind every entry with the word somewhere in
            # the middle, while it is the name of UN 1789 itself.
            names = [_normalize(entry.get(key) or "")
                     for key in ("name_en", "name_de", "name_nl")]
            if any(name.startswith(text) for name in names if name):
                scored.append((60, entry))
            elif any(word.startswith(text) for word in hay.split()):
                scored.append((40, entry))
            elif text in hay:
                scored.append((20, entry))

    scored.sort(key=lambda item: (-item[0], item[1]["un"], item[1].get("packing_group") or ""))
    # The suggestion carries the name that ends up on the document, so it has to
    # follow the same language choice as the export.
    return [
        {
            **_public(entry),
            **enrich_un_entry(entry, language),
            "proper_shipping_name": proper_shipping_name(entry, language, profiles),
        }
        for _, entry in scored[:limit]
    ]


def get_un_entries(un_number: str) -> list[dict]:
    digits = "".join(ch for ch in un_number if ch.isdigit()).zfill(4)
    return [_public(entry) for entry in _load_un() if entry["un"] == digits]


def offline_lookup(
    un_number: str, language: str = "nl", profiles: list[str] | None = None
) -> dict | None:
    """Same shape as the FreightUtils lookup, as an offline fallback."""
    entries = get_un_entries(un_number)
    if not entries:
        return None
    entry = entries[0]
    hazards = parse_hazards(entry)
    return {
        **enrich_un_entry(entry, language),
        "un_number": entry["un"],
        "proper_shipping_name": proper_shipping_name(entry, language, profiles),
        "class": hazards["division"],
        "subsidiary_risks": ", ".join(hazards["subsidiary_risks"]),
        "classification_code": hazards["classification_code"],
        "packing_group": clean_value(entry.get("packing_group")),
        # The first instruction, which is the P code. Table A separates them
        # with commas — "P001, IBC02, R001" — where the 2023 export used spaces.
        "packing_instruction": re.split(
            r"[,\s]+", clean_value(entry.get("packing_instructions")))[0] or None,
        "labels": clean_value(entry.get("labels")),
        "limited_quantity": clean_value(entry.get("limited_quantity")),
        "excepted_quantity": clean_value(entry.get("excepted_quantity")),
        "tunnel_restriction_code": f"({entry['tunnel_code']})" if entry.get("tunnel_code") else None,
        "transport_category": entry.get("transport_category"),
        "source": (
            f"EMCargo offline seed ({entry['source_note']})"
            if entry.get("source_note")
            else "EMCargo offline seed (ADR 2023 Tabel A / 49 CFR 172.101)"
        ),
        "variants": len(entries),
    }


def is_transport_forbidden(un_number: str) -> bool:
    """True when ADR Table A does not admit the substance for carriage."""
    return str(un_number).strip().zfill(4) in forbidden_un_numbers()


def search_packagings(query: str = "", limit: int = 150) -> list[dict]:
    entries = _load_packagings()
    query = query.strip()
    if not query:
        return [_public(entry) for entry in entries[:limit]]
    text = _normalize(query)
    scored: list[tuple[int, dict]] = []
    for entry in entries:
        code = _normalize(entry["code"])
        if code == text:
            scored.append((100, entry))
        elif code.startswith(text):
            scored.append((80, entry))
        elif any(word.startswith(text) for word in entry["_search"].split()):
            scored.append((40, entry))
        elif text in entry["_search"]:
            scored.append((20, entry))
    scored.sort(key=lambda item: (-item[0], item[1]["code"]))
    return [_public(entry) for _, entry in scored[:limit]]


@lru_cache(maxsize=1)
def _adn_table_c() -> dict[str, list[dict]]:
    """Table C of the ADN, by UN number — the tank vessel table.

    A substance can carry several rows (variants by benzene content, boiling
    point, vapour pressure), and unlike table A this seed holds them all: the
    English edition supplied the row set and every cell, the Dutch edition the
    corroboration. A row carries ``readings`` (2 where both editions were read,
    1 where the Dutch export lacks the row) and possibly ``disputed`` — cells
    the two readings give differently, stored with both values. A disputed
    cell is not settled and must not be presented as an answer.
    """
    try:
        payload = json.loads(
            (_SEED_DIR / "adn_table_c.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - seed missing
        return {}
    rows: dict[str, list[dict]] = {}
    for entry in payload.get("entries", []):
        rows.setdefault(entry["un"], []).append(entry)
    return rows


def adn_table_c_rows(un_number: str) -> list[dict]:
    """Every table C row for one UN number; empty where the ADN admits the
    substance to no tank vessel at all."""
    return list(_adn_table_c().get(str(un_number or "").strip(), []))


def adn_tank_vessel_answer(un_number: str) -> dict[str, Any] | None:
    """What table C settles for one UN number, and what it does not.

    The two questions the application asks of table C today: which vessel
    type(s) the substance's rows demand, and which signals the vessel shows.
    Either answer is offered only when every variant row agrees on it and no
    row disputes the cell — variants are real (petrol's plain rows sail type N,
    its high-benzene rows type C), and averaging them would answer a question
    the consignment has not answered yet.
    """
    rows = adn_table_c_rows(un_number)
    if not rows:
        return None

    def settled(field: str) -> str | None:
        values = set()
        for row in rows:
            if field in (row.get("disputed") or {}):
                return None
            value = str(row.get(field) or "").strip()
            if value in ("", "*", "-"):
                return None
            values.add(value)
        return values.pop() if len(values) == 1 else None

    return {
        "rows": len(rows),
        "vessel_type": settled("vessel_type"),
        "vessel_types_seen": sorted({
            str(r.get("vessel_type") or "").strip() for r in rows
            if str(r.get("vessel_type") or "").strip() not in ("", "*", "-")}),
        "cones": settled("blue_cones"),
        "readings_min": min(int(r.get("readings", 1)) for r in rows),
    }


def adn_blue_cones(un_number: str) -> dict[str, Any] | None:
    """Column (12) of the ADN's table A for one UN number, with its doubt.

    Returns the number of blue cones or blue lights the vessel must show, and
    whether that number is settled. It is not settled where the book gives the
    substance several rows that differ in the vessel's columns and only one of
    them could be read — UN 1203 petrol is the clearest case. A caller that
    cannot tell the rows apart is expected to say so rather than pick one.

    ``None`` where the ADN does not list the substance at all: the ADN's table A
    is not the ADR's, and 1,499 and 1,999 are gone from both while 9000 to 9006
    exist only here.
    """
    row = _adn_table_a().get(str(un_number or "").strip())
    if row is None:
        return None
    return {
        "cones": row.get("blue_cones"),
        "certain": bool(row.get("certain")),
        "carriage_permitted": row.get("carriage_permitted", ""),
    }


@lru_cache(maxsize=1)
def _rid_shunting() -> dict[str, list[str]] | None:
    """The shunting-model rows of RID table A column (5), or None unread.

    None and the empty list mean different things and the caller needs both:
    None says the seed is not there at all, so nothing per-substance can be
    claimed; an empty list says the seed was read and this substance prints
    no bracketed model in either edition — a real absence.
    """
    try:
        payload = json.loads(
            (_SEED_DIR / "rid_shunting_labels.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {un: list(models) for un, models in payload.get("rows", {}).items()}


def rid_shunting_models(un_number: str) -> list[str] | None:
    """Which shunting models (13, 15) RID's column (5) brackets for one UN.

    Read out of the OTIF English and German editions, which agree on all 351
    rows. ``None`` when the seed is absent; ``[]`` when the substance prints
    no bracketed model — the answer most substances get.
    """
    rows = _rid_shunting()
    if rows is None:
        return None
    return list(rows.get(str(un_number or "").strip(), []))


def adn_special_provisions(un_number: str) -> list[str]:
    """Column (6) of the ADN's table A: the special provisions, by number.

    The one the application acts on today is **802**, which gates the
    foodstuffs precaution of 7.1.4.10 — the inland waterway's own counterpart
    of the road's CV28, with its own separation measures. Empty where the ADN
    does not list the substance, which a caller that needs the difference
    tells apart via ``adn_blue_cones`` returning None.
    """
    row = _adn_table_a().get(str(un_number or "").strip())
    if row is None:
        return []
    return [code.strip() for code in
            str(row.get("special_provisions") or "").split(",") if code.strip()]


def adn_loading_measures(un_number: str) -> list[str]:
    """Column (11) of the ADN's table A: the additional requirements of 7.1.6.11.

    The codes are read there and nowhere else — CO01 to CO03 for the holds,
    ST01 and ST02 for stabilisation, RA01 and the rest for radioactive material.
    Only one of them reaches the transport document: 5.4.1.1.1 (j) asks for a
    confirmation of stabilisation where the column carries **ST01**.

    Empty where the ADN does not list the substance, which is not the same as a
    substance whose column (11) is blank; a caller that has to tell those apart
    reads ``adn_blue_cones`` first, which returns None for the former.
    """
    row = _adn_table_a().get(str(un_number or "").strip())
    if row is None:
        return []
    return [code.strip().upper()
            for code in str(row.get("loading_measures") or "").split(",")
            if code.strip()]


@lru_cache(maxsize=1)
def _tank_hierarchy() -> dict[str, Any]:
    """The two hierarchies of ADR 4.3, read from more than one book.

    ``gases`` is 4.3.3.1.2: a required code and the other codes a substance
    under it may also travel in, with the pressure figure of the permitted code
    at least that of the required one. ``rationalised`` is 4.3.4.1.2, and it is
    a different thing entirely: each tank code names the group of substances it
    may carry — class, classification code and packing group — and inherits the
    groups of the codes below it.

    A cell no two readings agree on is stored under ``disputed`` with every
    value read, and is not an answer. So is a cell only one book was read for.
    """
    try:
        return json.loads(
            (_SEED_DIR / "adr_tank_hierarchy.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - seed missing
        return {"gases": [], "rationalised": []}


def _tank_code(value: str) -> str:
    """One spelling: the editions differ on the decimal separator only."""
    return str(value or "").strip().upper().replace(",", ".")


def adr_gas_hierarchy(required: str) -> dict[str, Any] | None:
    """4.3.3.1.2 for one required code, or None where it names no such code."""
    wanted = _tank_code(required)
    for row in _tank_hierarchy().get("gases", []):
        if _tank_code(row["tank_code"]) == wanted:
            return row
    return None


def adr_tank_permissions(offered: str) -> dict[str, Any] | None:
    """4.3.4.1.2 for one offered code, with the groups it inherits folded in.

    The inheritance is what makes the table a hierarchy, so a code's permitted
    group is its own plus every group of the codes it inherits — read down the
    chain, because those codes inherit in their turn. Where any link in that
    chain has a cell no two readings settled, the answer says so instead of
    quietly presenting a shorter list as the whole of it.
    """
    table = {_tank_code(row["tank_code"]): row
             for row in _tank_hierarchy().get("rationalised", [])}
    start = table.get(_tank_code(offered))
    if start is None:
        return None

    permitted: list[dict] = []
    unsettled: set[str] = set()
    seen: set[str] = set()
    queue = [_tank_code(offered)]
    while queue:
        code = queue.pop(0)
        if code in seen:
            continue
        seen.add(code)
        row = table.get(code)
        if row is None:
            unsettled.add(code)
            continue
        disputed = row.get("disputed") or {}
        if "permitted" in disputed:
            unsettled.add(code)
        else:
            permitted.extend(row.get("permitted") or [])
        if "inherits" in disputed:
            unsettled.add(code)
        else:
            queue.extend(_tank_code(other) for other in row.get("inherits") or [])
    return {
        "tank_code": start["tank_code"],
        "permitted": permitted,
        "inherits": sorted(seen - {_tank_code(offered)}),
        "unsettled": sorted(unsettled),
    }
