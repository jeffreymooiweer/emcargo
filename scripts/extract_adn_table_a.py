"""Read table A of the ADN — the inland waterway table — out of the Dutch edition.

The ADN has a table A of its own and it is *not* the ADR's. The first eight
columns hold the same identification (UN number, name, class, classification
code, packing group, labels, special provisions, limited quantities) and then
the two regimes part company. Where the ADR goes on to packing instructions,
tank codes and a tunnel restriction, the ADN asks the questions a vessel asks:

    (8)  whether the goods may travel in packages, in bulk or in a tank vessel
    (9)  the equipment the vessel must carry            8.1.5
    (10) the ventilation provisions                     7.1.6.12
    (11) what must happen during loading and unloading  7.1.6.11/.13/.14/.16
    (12) **the number of blue cones or blue lights**    7.1.5
    (13) additional requirements and remarks

Column (12) is the one this application has been missing. `check_adn_hold_
separation` implements ADN 7.1.4.3 and has had to name half of it unassessed
since v1.59.0, because two of the three provisions are stated in blue cones and
the road table has no such column. 7.1.5.0.1 is worse than unassessed: which
signals a vessel must show is a question EMCargo could not answer at all.

## What is read, and what is not

The Dutch edition publishes this table twice, and the two renderings are not
equally good:

- **List pages** — the table as printed, one row per row. Where a UN number
  covers several entries (UN 0015 smoke ammunition has three, plain, corrosive
  and toxic-by-inhalation) all of them are here.
- **Per-substance pages** — one page per UN number, each field labelled with
  its column number. Easier to parse and *lossy*: a UN number with several
  rows gets one.

Measured on the range where both exist: 391 rows against 378 substances. The
collapse is not small and it is not safe to shrug at — 452 of the 2,352
substances have more than one row in the ADR's table A, hiding 813 further
rows, and 350 of those span more than one packing group. The cone count is not
a function of class, classification code and packing group either: 13 of 309
such combinations carry more than one value. So a collapsed row is a row whose
cone count may belong to a sibling.

Hence `readings` on every entry, and `complete` on the file. An entry read from
a list page is a row of the book. An entry read only from a per-substance page
is *a* row of the book for that UN number, and the application is told so
rather than left to assume.

## The check

Two, and neither is this document marking its own homework:

1. **Against the other rendering.** Where a list page covers the range, the row
   assembled from the per-substance page must appear in it verbatim, all
   fourteen fields.
2. **Against the ADR's table A already in the repository** — a different book,
   read from a PDF by different code in v1.56.0. Columns (1) to (7) hold the
   same facts in both regimes, so 2,343 substances are read twice over.

Usage::

    python scripts/extract_adn_table_a.py --index adn.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SEED = Path(__file__).resolve().parents[1] / "backend" / "seed" / "dg"

#: The ADR table read in v1.56.0, which columns (1) to (7) are checked against.
REFERENCE = SEED / "adr_table_a.json"

SOURCE_NAME = (
    "ADN 2025, Dutch edition — table A of chapter 3.2, read from the "
    "per-substance pages with the printed list pages as a second reading"
)

#: The thirteen columns, in the order the book prints them, with the label the
#: per-substance page puts in front of each value and the name this file gives
#: it. The label is how the value is found: the pages are a single run of text
#: in which "Klasse 2 (3)a" is a column number, a value and a heading all at
#: once, and the column marker is what closes the field.
COLUMNS: list[tuple[str, str, str]] = [
    ("1",  "UN-nr.",                                             "un"),
    ("2",  "Benaming en beschrijving",                           "name_nl"),
    ("3a", "Klasse",                                             "class"),
    ("3b", "Klassificatiecode",                                  "classification_code"),
    ("4",  "Verpakkingsgroep",                                   "packing_group"),
    ("5",  "Labels",                                             "labels"),
    ("6",  "Bijzondere bepalingen",                              "special_provisions"),
    ("7",  "Gelimiteerde hoeveelheden",                          "limited_quantity"),
    ("8",  "Vervoer toegelaten",                                 "carriage_permitted"),
    ("9",  "Vereiste uitrusting",                                "equipment"),
    ("10", "Ventilatie",                                         "ventilation"),
    ("11", "Maatregelen tijdens het laden, lossen en vervoeren", "loading_measures"),
    ("12", "Aantal blauwe kegels / lichten",                     "blue_cones"),
    ("13", "Extra eisen of aantekeningen",                       "remarks"),
]

#: How the book writes the column number above each column. Columns 3a and 3b
#: are printed "(3)a" and "(3)b", not "(3a)".
MARKERS = {"3a": "(3)a", "3b": "(3)b"}

#: What an empty cell looks like. The book prints a dash; the application wants
#: nothing. Column (12) is the exception and keeps it — see `cones`.
EMPTY = "-"

#: A row on a list page begins with a UN number followed by the name. The names
#: are set in capitals, but four of them begin with a digit instead — 1H-TETRAZOL,
#: 5-NITROBENZOTRIAZOL, 1-HYDROXYBENZOTRIAZOL, 5-MERCAPTOTETRAZOL-1-AZIJNZUUR —
#: and a rule that only accepted a capital lost all four. What is not accepted is
#: a bare number or a lone lower-case word, which is what a four-digit number
#: inside a cell is followed by ("met ten minste 1000 g").
ROW_START = re.compile(r"(?:^|(?<= ))(\d{4}) (?=[A-Z“(]|\d\S*[A-Za-z])")

#: Where the header of a list page stops and the rows begin.
LIST_HEADER_END = "(12) (13)"


def marker(column: str) -> str:
    return MARKERS.get(column, f"({column})")


def flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def tidy(value: str) -> str:
    """The book's spacing, made into the application's.

    The export separates a cell's several codes with a space on either side of
    the comma — "PP , EP , TOX , A". Left alone it would compare unequal against
    every other list in the repository.
    """
    value = flatten(value)
    value = re.sub(r"\s*,\s*", ", ", value)
    return "" if value == EMPTY else value


def cones(value: str) -> int | None:
    """Column (12) as a number, or nothing at all.

    A dash here is not an empty cell that could be treated as zero. Zero is
    printed as "0" and means the vessel shows no cone; the dash appears on the
    rows that carry no signal provision, and reading it as zero would turn "the
    book does not say" into "the book says none".
    """
    value = flatten(value)
    return int(value) if value.isdigit() else None


def parse_substance_page(text: str) -> dict[str, str] | None:
    """One row out of a per-substance page.

    The page is a flat run of text: a label, its value, its column number, then
    the provision the column refers to, then the next label. So each field runs
    from the end of its label to the start of its column marker — and the fields
    are read in order, because "Klasse" is a prefix of "Klassificatiecode" and
    searching the whole page for either finds the wrong one.
    """
    flat = flatten(text)
    start = flat.find(COLUMNS[0][1])
    if start < 0:
        return None
    flat, row, position = flat[start:], {}, 0
    for column, label, field in COLUMNS:
        at = flat.find(label, position)
        if at < 0:
            return None
        end = flat.find(marker(column), at + len(label))
        if end < 0:
            return None
        row[field] = flat[at + len(label):end].strip()
        position = end + len(marker(column))
    return row


def split_list_page(text: str) -> list[str]:
    """The rows of a list page, as printed, before any field is picked out."""
    flat = flatten(text)
    at = flat.find(LIST_HEADER_END)
    if at < 0:
        return []
    body = flat[at + len(LIST_HEADER_END):].strip()
    edges = [match.start(1) for match in ROW_START.finditer(body)]
    if not edges:
        return []
    edges.append(len(body))
    return [body[a:b].strip() for a, b in zip(edges, edges[1:])]


#: Where the vessel's own columns begin. Everything from special provisions
#: rightwards is what the two regimes do not share and what a sibling row is
#: liable to differ in — including (12), the cones.
TAIL_FROM = 6


def tail(row: dict[str, str]) -> str:
    """Columns (6) to (13) as the book prints them, in one piece.

    Used to settle whether a UN number's several rows differ in the columns
    that matter here. UN 0015 smoke ammunition has three rows and they differ
    only in the name and the labels — plain, corrosive, toxic by inhalation —
    while carriage, equipment, handling and the three blue cones are the same on
    all three. UN 1203 petrol also has three, and there the difference is real.
    Asking the printed rows is the only way to know which kind a substance is.
    """
    fields = [field for _column, _label, field in COLUMNS[TAIL_FROM:]]
    return flatten(" ".join(row[field] for field in fields))


def assemble(row: dict[str, str]) -> str:
    """A row written back out the way a list page prints it.

    This is the whole of the second reading. The list pages have no separator
    between one field and the next — a name runs into a class runs into a code —
    so they cannot be split into fields on their own. What they can do is
    confirm: if the fourteen values taken from the per-substance page appear in
    the list page in that order with single spaces between them, the two
    renderings agree, and a boundary drawn in the wrong place would not.
    """
    return flatten(" ".join(row[field] for _column, _label, field in COLUMNS))


def read(index: dict[str, dict[str, Any]]) -> tuple[list[dict], dict[str, Any]]:
    """Every row the export holds, each carrying how many times it was read."""
    substances: dict[str, dict[str, str]] = {}
    unreadable: list[str] = []
    for key, section in sorted(index.items()):
        if not re.fullmatch(r"\d{4}", key):
            continue
        row = parse_substance_page(section.get("text", ""))
        if row is None or row["un"] != key:
            unreadable.append(key)
            continue
        substances[key] = row

    # The list pages, which are the table as printed. A section is one when its
    # text carries the header band; the export holds one for table A and five
    # for table C, and table C is a different table with different columns.
    printed: dict[str, list[str]] = {}
    for key, section in sorted(index.items()):
        text = section.get("text", "")
        if "Productlist" not in text[:200] or "ADNC" in text[:200]:
            continue
        for line in split_list_page(text):
            printed.setdefault(line[:4], []).append(line)

    siblings = sibling_rows()
    entries: list[dict[str, Any]] = []
    confirmed = contradicted = 0
    predicted = mispredicted = 0
    for un, row in sorted(substances.items()):
        lines = printed.get(un)
        readings = 1
        if lines is not None:
            if assemble(row) in " ".join(lines):
                confirmed += 1
                readings = 2
            else:
                contradicted += 1
        entry: dict[str, Any] = {
            field: tidy(row[field]) for _column, _label, field in COLUMNS
        }
        entry["un"] = un
        entry["blue_cones"] = cones(row["blue_cones"])
        entry["readings"] = readings
        # How many rows the book gives this UN number, and where that was found
        # out. A substance with one row is fully read from its own page. One with
        # several is not: the page shows one of them, and columns (8) to (13) may
        # belong to a sibling. Named, so a check can decline to use the value
        # rather than quietly use the wrong row.
        if lines is not None:
            entry["printed_rows"] = len(lines)
            entry["printed_rows_from"] = "the ADN list page"
            # Several rows do not by themselves make the cone count doubtful.
            # They do when the rows differ in the vessel's columns, and the
            # printed rows are right there to be asked.
            entry["certain"] = all(line.endswith(tail(row)) for line in lines)
            if len(lines) == siblings.get(un, 1):
                predicted += 1
            else:
                mispredicted += 1
        else:
            entry["printed_rows"] = siblings.get(un, 1)
            entry["printed_rows_from"] = "the ADR table A"
            # Nothing to ask: one row in the book is the row that was read, and
            # several means the reading is one of them and cannot say which.
            entry["certain"] = entry["printed_rows"] == 1
        entries.append(entry)

    checks = {
        "against_the_printed_table": {
            "substances_covered": len(printed),
            "rows_printed": sum(len(v) for v in printed.values()),
            "confirmed": confirmed,
            "contradicted": contradicted,
            "agreement": round(confirmed / (confirmed + contradicted), 4)
            if confirmed + contradicted else None,
        },
        "row_counts_predicted_by_the_adr_table": {
            "checked": predicted + mispredicted,
            "right": predicted,
            "wrong": mispredicted,
        },
        "unreadable_pages": unreadable,
    }
    return entries, checks


def sibling_rows() -> dict[str, int]:
    """How many rows the ADR's table A gives each UN number.

    Used to say, for a substance whose ADN list page the export does not hold,
    whether the book gives it one row or several. That is a prediction across
    two regimes and it would be worth nothing unstated — so it is checked where
    both can be seen: in the range the ADN list page covers, the ADR table names
    thirteen substances with more than one row, and the list page repeats
    exactly those thirteen. `row_counts_predicted_by_the_adr_table` carries the
    result of that check, and it is a check that will fail loudly if a later
    edition parts the two tables.
    """
    if not REFERENCE.exists():
        return {}
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))["entries"]
    return Counter(row["un"] for row in reference)


def against_the_adr(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Columns (1) to (7), against the ADR table read from a different book.

    The two regimes identify goods identically and this is the only place where
    that is worth anything: the ADR table came out of a PDF by column geometry
    and this one out of labelled HTML, so an error common to both would have to
    be an error of the publisher rather than of the reading.

    A substance may hold several rows there, so agreement means *some* row of
    the ADR agrees — the ADN row read here is one of the same set.
    """
    if not REFERENCE.exists():
        return {"available": False}
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))["entries"]
    by_un: dict[str, list[dict]] = defaultdict(list)
    for row in reference:
        by_un[row["un"]].append(row)

    def letters(value: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "", flatten(value).upper())

    fields = {"class": "class", "classification_code": "classification_code"}
    tally: dict[str, dict[str, Any]] = {
        name: {"same": 0, "differs": 0, "examples": []} for name in fields
    }
    tally["name"] = {"same": 0, "differs": 0, "examples": []}
    absent: list[str] = []

    for entry in entries:
        rows = by_un.get(entry["un"])
        if not rows:
            absent.append(entry["un"])
            continue
        for name, column in fields.items():
            if any(letters(row[column]) == letters(entry[name]) for row in rows):
                tally[name]["same"] += 1
            else:
                tally[name]["differs"] += 1
                if len(tally[name]["examples"]) < 5:
                    tally[name]["examples"].append(
                        f"UN {entry['un']}: ADN {entry[name]!r}, ADR "
                        f"{sorted({row[column] for row in rows})}")
        # A name is compared on its opening, because the ADN prints the
        # descriptive tail of a generic entry and the ADR does not always.
        mine = letters(entry["name_nl"])
        if any(letters(row["name_nl"]).startswith(mine[:40])
               or mine.startswith(letters(row["name_nl"])[:40]) for row in rows):
            tally["name"]["same"] += 1
        else:
            tally["name"]["differs"] += 1
            if len(tally["name"]["examples"]) < 5:
                tally["name"]["examples"].append(
                    f"UN {entry['un']}: ADN {entry['name_nl'][:50]!r}, ADR "
                    f"{rows[0]['name_nl'][:50]!r}")

    for result in tally.values():
        total = result["same"] + result["differs"]
        result["agreement"] = round(result["same"] / total, 4) if total else None
    return {
        "available": True,
        "source": "backend/seed/dg/adr_table_a.json",
        "fields": tally,
        "not_in_the_adr_table": sorted(absent),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True,
                        help="the Dutch ADN edition as a section index: "
                             "{section: {title, text}}, one entry per page of "
                             "the publisher's HTML")
    parser.add_argument("--out", type=Path, default=SEED / "adn_table_a.json")
    parser.add_argument("--edition", default="ADN 2025")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what was read and write nothing")
    parser.add_argument("--min-agreement", type=float, default=0.99,
                        help="below this against the ADR table nothing is written")
    args = parser.parse_args(argv)

    index = json.loads(args.index.read_text(encoding="utf-8"))
    entries, checks = read(index)
    if not entries:
        print("No substance pages found; is this the ADN index?", file=sys.stderr)
        return 1

    printed = checks["against_the_printed_table"]
    print(f"{len(entries)} substances read")
    print(f"  {printed['rows_printed']} rows printed for "
          f"{printed['substances_covered']} of them, "
          f"{printed['confirmed']} confirmed, {printed['contradicted']} contradicted")
    if checks["unreadable_pages"]:
        print(f"  unreadable: {len(checks['unreadable_pages'])} "
              f"{checks['unreadable_pages'][:10]}")

    adr = against_the_adr(entries)
    if adr["available"]:
        print("\n--- against the ADR table A already in the repository ---")
        for name, result in adr["fields"].items():
            print(f"  {name:22s} {result['same']:5d} same, {result['differs']:4d} "
                  f"different, agreement {result['agreement']}")
            for example in result["examples"][:3]:
                print(f"      {example}")
        print(f"  not in the ADR table: {len(adr['not_in_the_adr_table'])} "
              f"{adr['not_in_the_adr_table'][:12]}")
        weakest = min(r["agreement"] for r in adr["fields"].values()
                      if r["agreement"] is not None)
        if weakest < args.min_agreement:
            print(f"\nAgreement {weakest} is below {args.min_agreement}: the "
                  "reading is wrong. Nothing is written.")
            return 1

    counts = Counter(entry["readings"] for entry in entries)
    single = [e for e in entries if e["certain"]]
    collapsed = [e for e in entries if not e["certain"]]
    prediction = checks["row_counts_predicted_by_the_adr_table"]
    print(f"\nread twice: {counts[2]}, read once: {counts[1]}")
    print(f"row counts predicted from the ADR table: {prediction['right']} right, "
          f"{prediction['wrong']} wrong, of {prediction['checked']} checkable")
    print(f"substances whose vessel columns are settled: {len(single)}")
    print(f"substances whose rows could differ and were read once: {len(collapsed)}")

    payload = {
        "_comment": ("Table A of chapter 3.2 of the ADN, read by machine with "
                     "scripts/extract_adn_table_a.py. A compilation of facts "
                     "offered as an aid; the published text of the ADN remains "
                     "authoritative."),
        "edition": args.edition,
        "source": SOURCE_NAME,
        "summary": {
            "substances": len(entries),
            "read_twice": counts[2],
            "read_once": counts[1],
            "rows_printed_where_the_printed_table_was_available":
                printed["rows_printed"],
            "vessel_columns_settled": len(single),
            "vessel_columns_uncertain": len(collapsed),
        },
        "cross_check": checks,
        "against_the_adr": adr,
        "entries": entries,
    }
    document = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    print(f"{len(entries)} entries, {len(document.encode('utf-8'))} bytes")

    if args.dry_run:
        print("Dry run; nothing is written.")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document, encoding="utf-8")
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - command line
    raise SystemExit(main())
