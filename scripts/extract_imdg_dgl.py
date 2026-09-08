"""Read out the Dangerous Goods List of IMDG Code Amendment 42-24.

The list sits on about 170 landscape pages 1180 points wide, with eighteen
columns in a fixed grid. The survey (scripts/survey_imdg_dgl.py) established
that it contains all 2,336 UN numbers we currently know from the 41-22 cards,
plus the eleven 42-24 adds.

This step turns that into data. The danger with such a table is not that the
parser falls over but that it silently shifts one column: then there are 2,300
substances with the wrong segregation code in the app and nobody sees it. So this
script checks itself against what we already know by two other routes — class and
packing group from ADR Table A, EmS from the EmS Guide — and refuses to write out
when too much deviates.

Usage::

    python scripts/extract_imdg_dgl.py --out backend/seed/dg/imdg_dgl.json
    python scripts/extract_imdg_dgl.py --dry-run --pages 600,601,627
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

SOURCE_URL = "https://www.cepa.be/wp-content/uploads/IMDG_Code-amdt_42_24.pdf"
SOURCE_NAME = ("IMO-resolutie MSC.556(108), aangenomen 23 mei 2024 — IMDG-code "
               "Amendment 42-24, hoofdstuk 3.2 Dangerous Goods List")
UA = {"User-Agent": "EMCargo data extraction (github.com/jeffreymooiweer/emcargo)"}

SEED = Path(__file__).resolve().parents[1] / "backend" / "seed" / "dg"

# In the heading the columns carry their number from the Code: "(1)" above the
# UN number, "(16b)" above the segregation. That number band appears on every
# list page, precisely above the column it names, and is thereby the only source
# that can give the measured cell rules a *name* without counting.
#
# Counting went wrong, you see. A table of measured x positions assumed nineteen
# columns; the drawn rules produce twenty-one, because the list appears as a
# spread on one landscape sheet and the gutter between the two halves counts as a
# cell, and column (12) had been overlooked. The alignment was therefore wrong
# everywhere, the parser fell back on the middle between two headings, and the
# shipping name — which starts at x 68, just left of that estimate — ended up
# with the first word of every line in the UN column:
# "1354 TRINITROBENZENE, with by G".
COLUMN_NAMES: dict[str, str] = {
    "1": "un_number",
    "2": "proper_shipping_name",
    "3": "class",
    "4": "subsidiary_hazards",
    "5": "packing_group",
    "6": "special_provisions",
    "7a": "limited_quantity",
    "7b": "excepted_quantity",
    "8": "packing_instructions",
    "9": "packing_provisions",
    "10": "ibc_instructions",
    "11": "ibc_provisions",
    "12": "imo_tank_instructions",
    "13": "tank_instructions",
    "14": "tank_provisions",
    "15": "ems",
    "16a": "stowage_and_handling",
    "16b": "segregation",
    "17": "properties_and_observations",
    "18": "_un_number_repeat",
}

# Without these columns a page has not been read as a list page and is skipped
# rather than half recorded.
REQUIRED_COLUMNS = frozenset({
    "un_number", "proper_shipping_name", "class", "packing_group",
    "special_provisions", "ems", "stowage_and_handling", "segregation",
    "properties_and_observations",
})

# The number band sits between the headings and the data. Below it, at y 140.5,
# are the references to the sections governing each column; those carry no
# brackets and therefore do not come in as a number.
MARKER_BAND = (120.0, 150.0)
MARKER = re.compile(r"^\((\d{1,2}[ab]?)\)$")

# Two or more headings make a page a list page. The segregation group lists of
# 3.1.4.4 also start with UN numbers and do not belong here.
HEADINGS = ["UN No.", "Proper shipping name", "Class or division", "Subsidiary",
            "Packing group", "Special provisions", "Limited and excepted",
            "Portable tanks", "EmS", "Stowage and handling", "Segregation",
            "Properties and observations"]

# Everything above this y is header text, everything below it footer text. The
# boundary lies below two bands that look as if they belong but are not data: the
# column numbers "(1) (2) (3) …" at y 131.7 and the references to the sections
# governing each column ("3.1.2", "2.0.1.3", "7.2–7.7") at y 140.5.
BODY_TOP, BODY_BOTTOM = 150.0, 795.0

# Fallback when a page yields no horizontal rules: words within this distance in
# y then belong to the same text line. As a measure of a table row that is too
# crude — it glued UN 0291 and UN 0292 into one entry — so the row bands come
# from the drawn rules by preference.
LINE_TOLERANCE = 3.0

# An entry amended by 42-24 carries a triangle before the UN number, and PyMuPDF
# delivers that as one word: "△1361". If that was not recognised, the row counted
# as a continuation line and was pulled into the substance above it — UN 1360 got
# "4.3 4.2 4.2 4.2" as its class and the EmS codes of four substances in a row.
# The character is moreover data in itself: it marks precisely the entries the
# amendment touched.
UN_CELL = re.compile(r"^([^\w\s]?)\s*(\d{4})$")

# The same, but on a single word: where a row begins in the first column.
UN_WORD = re.compile(r"^[^\w\s]?\d{4}$")

# A cell that starts with a UN number but runs on means the text was read across
# the column boundary. That must not pass silently.
UN_OVERFLOW = re.compile(r"^[^\w\s]?\s*(\d{4})\s+\S")


def download(url: str, target: Path, timeout: int = 600) -> Path:
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        target.write_bytes(response.read())
    return target


def find_rules(page, tolerance: float = 2.5) -> list[float]:
    """The x positions of the table's vertical cell rules.

    The list draws no continuous column line across the page but frames each row
    block separately; the tallest vertical is some eighty points high. Requiring
    a line to span half the page therefore yields none — that was the first
    attempt. What gives the column boundaries away is that the same x keeps
    recurring: a real boundary carries dozens of little rules under each other, a
    stray line one.
    """
    counts: dict[float, int] = {}
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.width <= 2.0 and rect.height >= 10.0:
            key = round((rect.x0 + rect.x1) / 2, 1)
            counts[key] = counts.get(key, 0) + 1
    # A boundary recurs through the whole table; a single stroke does not.
    return _recurring(counts, tolerance)


def column_markers(page) -> list[tuple[float, str]]:
    """The column numbers from the heading, with the centre they stand above."""
    found: list[tuple[float, str]] = []
    for x0, y0, x1, _y1, word, *_ in page.get_text("words"):
        if not MARKER_BAND[0] <= y0 < MARKER_BAND[1]:
            continue
        match = MARKER.match(word.strip())
        if match:
            found.append(((x0 + x1) / 2, match.group(1)))
    return sorted(found)


def boundaries(rules: list[float], markers: list[tuple[float, str]]
               ) -> list[tuple[str, float, float]]:
    """(name, left boundary, right boundary) per cell of the drawn grid.

    The rules come from the drawing and are therefore exact; the names come from
    the number band above them. If no number falls in a cell, that is the gutter
    between the two halves of the spread and the cell stays nameless. If *two*
    fall in it, rules and number band do not line up and the whole layout is
    unusable — then nothing is better than a grid that merely looks precise.
    """
    if len(rules) < 2 or not markers:
        return []

    cells: list[tuple[str, float, float]] = []
    for left, right in zip(rules, rules[1:]):
        inside = [label for x, label in markers if left <= x < right]
        if len(inside) == 1:
            name = COLUMN_NAMES.get(inside[0], f"_column_{inside[0]}")
        else:
            name = f"_unnamed_{left:.0f}"
        cells.append((name, left, right))

    names = [name for name, _, _ in cells]
    if len(set(names)) != len(names):
        return []
    if not REQUIRED_COLUMNS.issubset(names):
        return []
    return cells


def find_row_rules(page, tolerance: float = 2.5, coverage: float = 0.4) -> list[float]:
    """The y positions where one row ends and the next begins.

    The vertical cell rules already carry this: each segment is some eighty
    points high and runs across exactly one row band, and there are eighteen of
    them side by side — one per column. Their tops and bottoms are therefore the
    row boundaries, and a boundary that recurs eighteen times is one. The first
    version threw those y values away and went looking for horizontal lines, of
    which there turn out to be too few; then the whole page became one band with
    twelve substances in it.

    If that yields nothing, the horizontal rules after all, measured on the width
    that all the fragments at the same height cover together.
    """
    ends: dict[float, int] = {}
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.width <= 2.0 and rect.height >= 10.0:
            for y in (round(rect.y0, 1), round(rect.y1, 1)):
                ends[y] = ends.get(y, 0) + 1
    edges = _recurring(ends, tolerance)
    if len(edges) >= 2:
        return edges

    spans: dict[float, float] = {}
    widest = 0.0
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.height > 2.0 or rect.width <= 0:
            continue
        key = round((rect.y0 + rect.y1) / 2, 1)
        spans[key] = spans.get(key, 0.0) + rect.width
        widest = max(widest, rect.x1)
    if not spans:
        return []

    merged: list[tuple[float, float]] = []
    for y in sorted(spans):
        if merged and y - merged[-1][0] <= tolerance:
            previous, width = merged[-1]
            merged[-1] = (previous, width + spans[y])
        else:
            merged.append((y, spans[y]))
    needed = max(widest, 1.0) * coverage
    return [y for y, width in merged if width >= needed]


def un_number_rows(page, bounds: list[tuple[str, float, float]]) -> list[float]:
    """The heights at which the first column holds a UN number."""
    found = []
    for x0, y0, x1, _y1, word, *_ in page.get_text("words"):
        if not BODY_TOP <= y0 <= BODY_BOTTOM:
            continue
        if column_of((x0 + x1) / 2, bounds) == "un_number" and UN_WORD.match(word.strip()):
            found.append(y0)
    return sorted(found)


def row_rules_for(page, bounds: list[tuple[str, float, float]],
                  clearance: float = 3.0, tolerance: float = 4.0) -> list[float]:
    """The row boundaries, filled in where the table draws none.

    The drawn rules frame a *block* of rows as soon as the entries are short. On
    p627 UN 1360, UN 1361 (two packing groups) and UN 1362 ended up in one band
    that way and therefore in one entry, with '4.3 4.2 4.2 4.2' as the class.
    Every row begins with a UN number in the first column, so just above such a
    number there should be a boundary — whether the table draws a line there or
    not.
    """
    candidates = list(find_row_rules(page))
    candidates += [y - clearance for y in un_number_rows(page, bounds)]
    merged: list[float] = []
    for y in sorted(candidates):
        if not merged or y - merged[-1] > tolerance:
            merged.append(y)
    return merged


def _recurring(counts: dict[float, int], tolerance: float) -> list[float]:
    """Positions that recur often enough to be a real rule."""
    if not counts:
        return []
    merged: list[tuple[float, int]] = []
    for value in sorted(counts):
        if merged and value - merged[-1][0] <= tolerance:
            previous, count = merged[-1]
            merged[-1] = (previous, count + counts[value])
        else:
            merged.append((value, counts[value]))
    threshold = max(2, max(count for _, count in merged) // 4)
    return [value for value, count in merged if count >= threshold]


def column_of(x: float, bounds: list[tuple[str, float, float]]) -> str:
    """The column x falls in, or "" for what sits outside the table.

    Outside the rules lies the margin: page numbers, the triangle marking an
    amended entry. Adding that to the nearest column would let it pass for data.
    """
    for name, left, right in bounds:
        if left <= x < right:
            return name
    return ""


def band_of(y: float, rules: list[float]) -> int:
    """Which row band a word falls in, counted between the horizontal rules."""
    band = 0
    for rule in rules:
        if y < rule:
            return band
        band += 1
    return band


def page_lines(page, bounds: list[tuple[str, float, float]],
               row_rules: list[float] | None = None) -> list[dict[str, str]]:
    """The rows of a list page, split out per column.

    With the horizontal rules included, a row is exactly what sits between two
    rules, however many text lines that is: a long shipping name that runs on
    belongs to the same entry, and the next entry only starts after the rule.
    Without those rules the layout falls back on distance in y, which is enough
    to read on with but can glue two short entries together.

    A word belongs to the column its *centre* falls in, not its left edge. An
    amended entry carries a triangle before the UN number, and that puts the word
    "△1361" with its left edge outside the table; going by the left edge left
    those rows without a UN number, after which they were pulled into UN 1360 as
    continuation lines — class '4.3 4.2 4.2 4.2'. Cell text moreover never
    protrudes across a column boundary, so the centre points at the same column.

    Within a row the words are put in reading order: first top to bottom, then
    left to right, so that a name across two lines joins up in the right order.
    """
    rows: dict[Any, dict[str, list[tuple[float, float, str]]]] = defaultdict(
        lambda: defaultdict(list))
    for x0, y0, x1, _y1, word, *_ in page.get_text("words"):
        if not BODY_TOP <= y0 <= BODY_BOTTOM:
            continue
        column = column_of((x0 + x1) / 2, bounds)
        if not column:
            continue
        if row_rules:
            key: Any = band_of(y0, row_rules)
        else:
            key = next((k for k in rows if abs(k - y0) <= LINE_TOLERANCE), round(y0, 1))
        rows[key][column].append((y0, x0, word))

    lines = []
    for key in sorted(rows):
        cells = {}
        for name, words in rows[key].items():
            ordered = sorted(words, key=lambda w: (round(w[0], 1), w[1]))
            cells[name] = " ".join(word for _y, _x, word in ordered)
        lines.append(cells)
    return lines


def merge_rows(lines: list[dict[str, str]]) -> list[dict[str, str]]:
    """Join text lines into entries.

    A new entry begins where the first column carries a UN number. Everything
    after it without a UN number of its own is a continuation line and belongs to
    the previous one — that way "GASOLINE" does not end up detached from the line
    below it.
    """
    entries: list[dict[str, str]] = []
    for cells in lines:
        first = cells.get("un_number", "").strip()
        if UN_OVERFLOW.match(first):
            # Reading it along as an entry would produce a truncated name;
            # skipping it would hide it. The cell stays as it is, so the count in
            # extract() can report it as an overflow.
            entries.append({k: v for k, v in cells.items() if not k.startswith("_")})
            continue
        clean = UN_CELL.match(first)
        if clean:
            entry = {k: v for k, v in cells.items() if not k.startswith("_")}
            entry["un_number"] = clean.group(2)
            if clean.group(1):
                entry["amended"] = "42-24"
            entries.append(entry)
            continue
        if not entries:
            continue
        for name, value in cells.items():
            if name.startswith("_") or not value.strip():
                continue
            entries[-1][name] = f"{entries[-1].get(name, '')} {value}".strip()
    return entries


def normalise(entry: dict[str, str]) -> dict[str, Any]:
    return {k: re.sub(r"\s+", " ", v).strip() for k, v in entry.items() if v.strip()}


def extract(path: Path, only_pages: list[int] | None = None) -> tuple[list[dict], dict]:
    import fitz

    entries: list[dict[str, Any]] = []
    pages_read: list[int] = []
    skipped: list[int] = []
    rule_shapes: dict[tuple[float, ...], int] = {}
    # A page without a readable number band may piggyback on a page with exactly
    # the same rule pattern; otherwise it goes into the count unread.
    layouts: dict[tuple[float, ...], list[tuple[str, float, float]]] = {}

    with fitz.open(path) as document:
        for index in range(document.page_count):
            number = index + 1
            if only_pages and number not in only_pages:
                continue
            page = document[index]
            if not only_pages:
                text = page.get_text()
                if sum(1 for h in HEADINGS if h in text) < 2:
                    continue

            rules = find_rules(page)
            shape = tuple(rules)
            bounds = boundaries(rules, column_markers(page))
            if bounds:
                layouts[shape] = bounds
            else:
                bounds = layouts.get(shape, [])
            if not bounds:
                skipped.append(number)
                continue

            pages_read.append(number)
            rule_shapes[shape] = rule_shapes.get(shape, 0) + 1
            row_rules = row_rules_for(page, bounds)
            for entry in merge_rows(page_lines(page, bounds, row_rules)):
                clean = normalise(entry)
                cell = clean.get("un_number", "")
                if UN_CELL.match(cell) or UN_OVERFLOW.match(cell):
                    clean["_page"] = number
                    entries.append(clean)

    # One grid layout for the whole list is the sign that the detection is right;
    # many different ones mean some pages are laid out differently.
    shapes = sorted(rule_shapes.items(), key=lambda kv: -kv[1])
    overflow = [e["un_number"] for e in entries if UN_OVERFLOW.match(e["un_number"])]
    return entries, {
        "pages": len(pages_read), "entries": len(entries),
        "overflowing_cells": len(overflow),
        "overflow_examples": overflow[:10],
        "first_page": pages_read[0] if pages_read else None,
        "last_page": pages_read[-1] if pages_read else None,
        "distinct_rule_layouts": len(shapes),
        "most_common_rules": list(shapes[0][0]) if shapes else [],
        "most_common_rules_pages": shapes[0][1] if shapes else 0,
        "pages_without_grid": len(skipped),
        "pages_without_grid_examples": skipped[:10],
    }


# --- Zelfcontrole -------------------------------------------------------------

def load(name: str) -> Any:
    try:
        return json.loads((SEED / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - seed ontbreekt
        return None


def division_matches(found: str, divisions: set[str]) -> bool:
    """Whether the class from the list agrees with what ADR says about this substance.

    Two things make this more than a comparison. A UN number can appear in Table
    A more than once — UN 1950 (aerosols) has a 2.1 and a 2.2 entry — so there is
    not one ADR division but a set. And the IMDG Code simply calls aerosols class
    2 where ADR gives the division; that is not a contradiction but a difference
    in how finely the two schemes classify. A class that is the head of an ADR
    division therefore counts.
    """
    found = found.strip()
    if not found or not divisions:
        return False
    return found in divisions or any(d.startswith(f"{found}.") for d in divisions)


def adr_divisions() -> dict[str, set[str]]:
    """The division per UN number according to ADR Table A.

    The 'class' column gives only '2' for gases and only '1' for explosives; the
    actual division is in the labels column and the classification code
    respectively. The Dangerous Goods List *does* carry that division in full
    ("1.1D", "2.3"), so they have to be brought into line here.

    This is a copy of `parse_hazards()` from
    backend/app/services/dg/enrichment.py. This script runs in GitHub Actions
    with only pymupdf installed and cannot import the application.
    backend/tests/test_imdg_dgl_extraction.py binds the two together, so they
    cannot drift apart.
    """
    divisions: dict[str, set[str]] = {}
    for entry in load("un_numbers.json") or []:
        hazard_class = str(entry.get("class") or "").strip()
        classification = str(entry.get("classification_code") or "").strip().upper()
        # Normalise labels the way the application does: "9A" is class 9, the
        # model letter is not part of it. Without this step UN 1950 gave "2.2"
        # here where the app says "2.1" — exactly the kind of difference that
        # makes a self-check worthless.
        tokens = []
        for raw in str(entry.get("labels") or "").split("+"):
            token = raw.strip().upper()
            if not token:
                continue
            match = re.match(r"^(\d(?:\.\d)?)", token)
            tokens.append(match.group(1) if match else token)

        division = hazard_class
        if hazard_class == "1" and re.match(r"^1\.\d[A-S]$", classification):
            division = classification
        elif tokens and tokens[0].startswith(f"{hazard_class}."):
            division = tokens[0]
        elif not hazard_class and tokens:
            division = tokens[0]
        # Classes 1 and 2 are always divided into divisions; if only "1" or "2"
        # is left here, ADR *has* given no division. That happens with substances
        # forbidden by road (the labels column then says BEFÖRDERUNG VERBOTEN)
        # and with articles referring to 5.2.2.1.12. By sea those are permitted,
        # and the IMDG Code simply names their division. Laying such cases against
        # each other measures nothing: one source simply has no answer to it, and
        # counting them would produce seven false deviations.
        if division and division not in {"1", "2"}:
            divisions.setdefault(str(entry.get("un", "")).strip(), set()).add(division)
    return divisions


def cross_check(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Lay the outcome next to what we already know by other routes.

    Class comes from ADR Table A, EmS from the EmS Guide. Both are independent of
    this PDF — that is the whole point. Earlier the class came from
    card_data.json, but those are the UN cards: an IMDG source too, so that lays
    one IMDG reading next to another. And for UN 2984-2992, 3548 and 3550 those
    cards turned out to carry sequence numbers in the class field instead of
    classes, which produced eleven false deviations that were checked one by one.
    If the column layout is right, they should largely coincide; a shifted column
    shows hundreds of differences here straight away instead of quietly leaking
    into the app.
    """
    adr = adr_divisions()
    ems_seed = (load("ems.json") or {}).get("entries", {})

    checks = {"class": {"same": 0, "differs": 0, "examples": []},
              "ems": {"same": 0, "differs": 0, "examples": []}}

    by_un: dict[str, dict[str, Any]] = {}
    for entry in entries:
        by_un.setdefault(entry["un_number"], entry)

    for un, entry in by_un.items():
        divisions = adr.get(un)
        if divisions:
            found = entry.get("class", "").strip()
            key = "same" if division_matches(found, divisions) else "differs"
            checks["class"][key] += 1
            if key == "differs" and len(checks["class"]["examples"]) < 15:
                checks["class"]["examples"].append(
                    f"UN {un}: list {found!r} vs ADR {sorted(divisions)!r}")

        seeded = ems_seed.get(un)
        if isinstance(seeded, dict) and seeded.get("fire"):
            expected = f"{seeded['fire']} {seeded['spillage']}".replace(" ", "")
            found = entry.get("ems", "").replace(" ", "").replace(",", "")
            key = "same" if found == expected.replace(",", "") else "differs"
            checks["ems"][key] += 1
            if key == "differs" and len(checks["ems"]["examples"]) < 15:
                checks["ems"]["examples"].append(
                    f"UN {un}: list {entry.get('ems')!r} vs EmS Guide {expected!r}")

    for name, result in checks.items():
        total = result["same"] + result["differs"]
        result["agreement"] = round(result["same"] / total, 4) if total else None
    return checks


def diagnose(path: Path, pages: list[int]) -> None:
    """Show what the parser actually finds on a page.

    Making the wrong assumption twice in a row costs more time than measuring
    once. This prints the page size, what drawings are on it, the first words
    with their position and the cells that follow from them.
    """
    import fitz

    with fitz.open(path) as document:
        for number in pages:
            if not 0 < number <= document.page_count:
                continue
            page = document[number - 1]
            print(f"\n===== p{number} =====")
            print(f"  rect {page.rect}, rotatie {page.rotation}")

            drawings = page.get_drawings()
            vertical = [d["rect"] for d in drawings if d["rect"].width <= 2.0]
            print(f"  drawings: {len(drawings)}, of which narrow-and-vertical: {len(vertical)}")
            if vertical:
                tallest = sorted(vertical, key=lambda r: -r.height)[:8]
                print("    hoogste: " + ", ".join(
                    f"x{r.x0:.1f} h{r.height:.1f}" for r in tallest))
            elif drawings:
                sample = [d["rect"] for d in drawings[:8]]
                print("    voorbeeld: " + ", ".join(
                    f"({r.x0:.0f},{r.y0:.0f})-({r.x1:.0f},{r.y1:.0f})" for r in sample))

            words = page.get_text("words")
            ys = [w[1] for w in words]
            print(f"  woorden: {len(words)}, y van {min(ys, default=0):.1f} "
                  f"tot {max(ys, default=0):.1f}")
            print(f"  binnen BODY_TOP..BODY_BOTTOM ({BODY_TOP}..{BODY_BOTTOM}): "
                  f"{sum(1 for y in ys if BODY_TOP <= y <= BODY_BOTTOM)}")

            print("  first 25 words below the header:")
            for word in sorted((w for w in words if w[1] > BODY_TOP),
                               key=lambda w: (w[1], w[0]))[:25]:
                print(f"    x{word[0]:8.1f} y{word[1]:8.1f}  {word[4]!r}")

            horizontals: dict[float, float] = {}
            for drawing in page.get_drawings():
                rect = drawing["rect"]
                if rect.height <= 2.0 and rect.width > 0:
                    key = round((rect.y0 + rect.y1) / 2, 1)
                    horizontals[key] = horizontals.get(key, 0.0) + rect.width
            print(f"  horizontale stukjes op {len(horizontals)} hoogtes; "
                  f"breedste dekking {max(horizontals.values(), default=0):.0f}")
            heights = [d["rect"].height for d in page.get_drawings()
                       if d["rect"].width <= 2.0 and d["rect"].height >= 10.0]
            print(f"  verticale segmenten: {len(heights)}, hoogte "
                  f"{min(heights, default=0):.1f}..{max(heights, default=0):.1f}")
            print(f"  drawn horizontal rules: {len(find_row_rules(page))}")

            rules = find_rules(page)
            markers = column_markers(page)
            print(f"  column numbers in the header: {len(markers)}")
            print("    " + ", ".join(f"({label})@{x:.0f}" for x, label in markers))
            bounds = boundaries(rules, markers)
            if not bounds:
                print("  NO usable column layout; this page is skipped.")
                continue
            print("  columns:")
            for name, left, right in bounds:
                print(f"    {left:7.1f} - {right:7.1f}  {name}")

            starts = un_number_rows(page, bounds)
            row_rules = row_rules_for(page, bounds)
            print(f"  UN numbers in the first column: {len(starts)}; "
                  f"row boundaries after filling in: {len(row_rules)}")

            lines = page_lines(page, bounds, row_rules)
            print(f"  rows after column and row banding: {len(lines)}")
            odd = [ascii(cells.get("un_number", "")) for cells in lines
                   if not UN_CELL.match(cells.get("un_number", "").strip())]
            print(f"  first cells that are not a UN number: {odd}")
            for cells in lines[:5]:
                print(f"    {cells}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=SEED / "imdg_dgl.json")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--pages", help="Only these pages, for a trial run")
    parser.add_argument("--dry-run", action="store_true",
                        help="Read and check, but do not write anything")
    parser.add_argument("--debug", action="store_true",
                        help="Show what the parser actually sees, per trial page")
    parser.add_argument("--min-agreement", type=float, default=0.95,
                        help="Below this agreement nothing is written")
    parser.add_argument("--show-un", default="",
                        help="Show these UN numbers in full, with the page they "
                             "came from — to chase down a discrepancy")
    args = parser.parse_args(argv)

    path = args.pdf or download(SOURCE_URL, Path("/tmp/imdg_42_24.pdf"))
    only = [int(p) for p in (args.pages or "").split(",") if p.strip().isdigit()] or None

    if args.debug and only:
        diagnose(path, only)

    entries, summary = extract(path, only)
    print(f"read: {summary}")
    if not entries:
        print("No entries read.")
        return 1

    print("\n--- first three entries ---")
    for entry in entries[:3]:
        print(json.dumps(entry, ensure_ascii=False, indent=1))

    wanted = {u.strip() for u in args.show_un.split(",") if u.strip()}
    if wanted:
        print("\n--- requested entries ---")
        for entry in entries:
            if entry.get("un_number") in wanted:
                print(json.dumps(entry, ensure_ascii=False, indent=1))

    checks = cross_check(entries)
    print("\n--- self-check against independent sources ---")
    for name, result in checks.items():
        print(f"  {name}: {result['same']} same, {result['differs']} different, "
              f"agreement {result['agreement']}")
        for example in result["examples"]:
            print(f"      {example}")

    weakest = [r["agreement"] for r in checks.values() if r["agreement"] is not None]
    if not weakest:
        print("\nNothing to compare against; nothing is written.")
        return 1
    if min(weakest) < args.min_agreement:
        print(f"\nAgreement {min(weakest)} is below {args.min_agreement}: "
              "the column layout is wrong. Nothing is written.")
        return 1

    payload = {
        "_comment": ("Dangerous Goods List of IMDG Code Amendment 42-24, read by "
                     "machine with scripts/extract_imdg_dgl.py. A compilation of "
                     "facts offered as an aid; the published text of the code "
                     "remains authoritative."),
        "amendment": "42-24",
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "summary": summary,
        "cross_check": checks,
        "entries": [{k: v for k, v in e.items() if k != "_page"} for e in entries],
    }
    document = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    print(f"\n{len(entries)} vermeldingen, {len(document.encode('utf-8'))} bytes")

    if args.dry_run or only:
        print("Dry run; nothing is written.")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document, encoding="utf-8")
    print(f"geschreven: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
