#!/usr/bin/env python3
"""Read table A of RID 3.2.1 out of the editions in the regulations store.

The UN cards fail honestly for rail because EMCargo's table A is the
ADR's: generating a RID card from a road row would relabel road data as
rail data (columns (12) to (20) are the rail's own — tank codes, transport
category, the W/VC/CW/CE provisions, the hazard number can all differ).
This script reads the RID's own table, the way
``extract_rid_shunting_labels.py`` read its column (5): geometrically, from
the word positions of the official editions in the store.

## What the probe measured (run 2026-08-20, both editions)

Both books print the table as one contiguous run of pages — OTIF English
262-523, Dutch 304-515 — each page carrying the full column-number band
``(1) (2) (3a) (3b) (4) (5) (6) (7a) (7b) (8) (9a) (9b) (10) (11) (12)
(13) (15) (16) (17) (18) (19) (20)`` (there is no column (14) in the RID)
at page-constant x positions. The English edition centres each cell under
its number; the Dutch edition left-aligns cells on it. Assignment therefore
scores a chunk against both its left edge and its centre and takes the
nearest column, with everything left of column (3a) belonging to the name.

## The two readings

The Dutch and the English edition are two independent typesettings of the
same table (212 pages against 262, different column positions, different
alignment). Both are parsed by the same code and compared row by row on
every coded column — the names differ by language and are kept per
edition. A systematic parser error does not produce the same wrong value
under two different layouts, so agreement is the check. On top of that the
result is cross-checked against two seeds this repository already trusts:
the ADR table A (columns (1)-(4) are harmonised between the regimes) and
the v1.123.0 shunting-label reading of column (5).

    python scripts/extract_rid_table_a.py --pdf rid.pdf --probe
    python scripts/extract_rid_table_a.py --build --out backend/seed/dg/rid_table_a.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - runner installs it
    fitz = None

STORE = Path(
    os.environ.get("EMCARGO_REGULATIONS_DIR")
    or ("/data/regulations" if Path("/data").is_dir()
        else "/tmp/emcargo-regulations"))

SEED = Path(__file__).resolve().parents[1] / "backend" / "seed" / "dg"

MARKER = re.compile(r"^\((\d{1,2}[ab]?)\)$")
UN_WORD = re.compile(r"^\d{4}$")

#: The columns of RID table A in printed order. No (14): that column is the
#: ADR's (vehicle for tank carriage) and the RID does not print it.
COLS = ["1", "2", "3a", "3b", "4", "5", "6", "7a", "7b", "8", "9a", "9b",
        "10", "11", "12", "13", "15", "16", "17", "18", "19", "20"]

FIELDS = {
    "1": "un", "2": "name", "3a": "class", "3b": "classification_code",
    "4": "packing_group", "5": "labels", "6": "special_provisions",
    "7a": "limited_quantity", "7b": "excepted_quantity",
    "8": "packing_instructions", "9a": "packing_provisions",
    "9b": "mixed_packing_provisions", "10": "portable_tank_instructions",
    "11": "portable_tank_provisions", "12": "tank_code",
    "13": "tank_provisions", "15": "transport_category",
    "16": "packages_provisions", "17": "bulk_provisions",
    "18": "loading_provisions", "19": "express_parcels",
    "20": "hazard_number",
}

#: Coded columns compared between the two editions. The name is per
#: language; everything else must be printed identically in both books.
COMPARED = [c for c in COLS if c not in ("2",)]

#: A footer line: the running page number or edition line at the bottom.
#: The OTIF edition numbers its pages "3.2-A-12"; the Dutch edition adds
#: page lines of its own.
FOOTER = re.compile(
    r"^(RID\s*\d{4}.*|-?\s*\d+\s*-?|\d+\s*/\s*\d+|.*OTIF.*|3\.2-[A-C]-\d+.*"
    r"|(Page|Pagina)\s*\d*)$")

#: The Dutch PDF carries stray "Page N" words in its text layer, at
#: positions that land inside the table's right-hand columns. They are
#: artefacts of the file, not content of the book, and are dropped as
#: chunks wherever they stand.
NOISE_CHUNK = re.compile(r"^((Page|Pagina)( \d+)?|[.,;:·|-]|3\.2-[A-C]-\d+)$")

#: Both editions replace a whole row's cells with a banner where carriage
#: is prohibited by rail, and with another where the entry is not subject
#: to the RID at all. The Dutch banner is set wide enough that its halves
#: land in different columns, so the fragments are matched separately.
PROHIBITED = ("CARRIAGE PROHIBITED", "VERVOER VERBODEN")
NOT_SUBJECT = (("NOT SUBJECT TO RID",), ("NIET ONDERWORPEN", "AAN HET RID"))


def probe(pdf_path: Path, sample_pages: int) -> int:
    doc = fitz.open(str(pdf_path))
    print(f"== {pdf_path.name}: {doc.page_count} pages, "
          f"first page rect {doc[0].rect} ==")
    header_pages: list[tuple[int, tuple[str, ...]]] = []
    for number in range(doc.page_count):
        words = doc[number].get_text("words")
        markers = sorted(
            ((w[0], MARKER.match(w[4]).group(1)) for w in words
             if MARKER.match(w[4])), key=lambda m: m[0])
        codes = tuple(code for _x, code in markers)
        if len(codes) >= 10:
            header_pages.append((number + 1, codes))

    if not header_pages:
        print("no pages with a 10+ column-number band found")
        return 1

    runs: list[list[tuple[int, tuple[str, ...]]]] = []
    for page, codes in header_pages:
        if runs and page - runs[-1][-1][0] <= 2:
            runs[-1].append((page, codes))
        else:
            runs.append([(page, codes)])
    print(f"{len(header_pages)} header pages in {len(runs)} runs:")
    for run in runs:
        print(f"  pages {run[0][0]}-{run[-1][0]} ({len(run)} pages)")
    shapes = Counter(codes for _page, codes in header_pages)
    for codes, count in shapes.most_common(4):
        print(f"  {count} pages with markers: {' '.join(codes)}")

    main_run = max(runs, key=len)
    for page_number in [main_run[0][0], main_run[len(main_run) // 2][0]][:sample_pages]:
        page = doc[page_number - 1]
        words = page.get_text("words")
        markers = sorted(((w[0], w[1], w[4]) for w in words
                          if MARKER.match(w[4])), key=lambda m: m[0])
        print(f"\n-- page {page_number}: marker positions --")
        print("  " + "  ".join(f"{t}@x{x:.0f}/y{y:.0f}" for x, y, t in markers))
        un_rows = sorted((w[1], w[0], w[4]) for w in words
                         if UN_WORD.match(w[4]) and w[0] < page.rect.width * 0.2)
        print(f"  {len(un_rows)} UN-number words at the left margin; first five:")
        for y, x, text in un_rows[:5]:
            print(f"    UN {text} at x{x:.0f} y{y:.0f}")
    return 0


def full_header(page) -> tuple[float, dict[str, float]] | None:
    """The column-number band: y position and each column's x, when whole."""
    markers: dict[str, list[tuple[float, float]]] = {}
    for x0, y0, _x1, _y1, text, *_ in page.get_text("words"):
        match = MARKER.match(text)
        if match:
            markers.setdefault(match.group(1), []).append((x0, y0))
    if not all(code in markers for code in COLS):
        return None
    # Part 2 cites bracketed numbers in running text; the band is the row of
    # markers that share one y. Take, per column, the occurrence at the most
    # common y.
    ys = Counter(round(y) for hits in markers.values() for _x, y in hits)
    band_y = ys.most_common(1)[0][0]
    xs: dict[str, float] = {}
    for code in COLS:
        at_band = [x for x, y in markers[code] if abs(y - band_y) <= 2]
        if not at_band:
            return None
        xs[code] = min(at_band)
    ordered = [xs[code] for code in COLS]
    if ordered != sorted(ordered):
        return None
    return float(band_y), xs


def chunks_of(line_words: list[tuple[float, float, float, str]],
              xs: dict[str, float], gap: float = 6.0) -> list[tuple[float, float, str]]:
    """Adjacent words merged into cell chunks: (x0, x1, text).

    A word that starts on a column's own x begins a new chunk even when the
    gap is small: the narrow columns — (9a)/(9b), (3a) beside a long name —
    print neighbouring cells closer together than the words inside one
    cell, and a gap rule alone glued "PP54 MP20" into column (9a) and a
    class 1 into the end of a name.
    """
    boundaries = [xs[code] for code in COLS[2:]]
    out: list[tuple[float, float, str]] = []
    for x0, x1, _y, text in sorted(line_words):
        on_boundary = any(abs(x0 - mx) <= 3 for mx in boundaries)
        if out and x0 - out[-1][1] <= gap and not on_boundary:
            prev = out[-1]
            out[-1] = (prev[0], x1, f"{prev[2]} {text}")
        else:
            out.append((x0, x1, text))
    return out


def assign(chunk: tuple[float, float, str], xs: dict[str, float]) -> str:
    """The column a chunk belongs to, scored on left edge and centre both."""
    x0, x1, _text = chunk
    if x0 < xs["3a"] - 12:
        return "2" if x0 > xs["1"] + 10 else "1"
    center = (x0 + x1) / 2
    best, best_score = "3a", float("inf")
    for code in COLS[2:]:
        mx = xs[code]
        score = min(abs(x0 - mx), abs(center - mx))
        if score < best_score:
            best, best_score = code, score
    return best


def rules_of(page, below_y: float) -> list[float]:
    """The y positions of the table's printed horizontal rules.

    Both editions draw a rule between every two rows. Banding on the rules
    instead of on the UN-number lines matters because a tall row prints its
    UN number vertically centred: banding on the anchor line handed the
    row's first printed line to the previous row (1002's TA4 TT9 landed one
    row up, 1012's held its neighbour's copy too).
    """
    ys: set[float] = set()
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 0.6 and abs(p2.x - p1.x) > 250:
                    ys.add(round((p1.y + p2.y) / 2, 1))
            elif item[0] == "re":
                rect = item[1]
                if rect.height < 1.6 and rect.width > 250:
                    ys.add(round(rect.y0, 1))
    merged: list[float] = []
    for y in sorted(y for y in ys if y > below_y):
        if not merged or y - merged[-1] > 2.5:
            merged.append(y)
    return merged


def parse(pdf_path: Path) -> tuple[list[dict], dict]:
    """Every row of the main table run, page by page, top to bottom."""
    doc = fitz.open(str(pdf_path))
    headers: dict[int, tuple[float, dict[str, float]]] = {}
    for number in range(doc.page_count):
        header = full_header(doc[number])
        if header:
            headers[number] = header
    runs: list[list[int]] = []
    for number in sorted(headers):
        if runs and number - runs[-1][-1] <= 2:
            runs[-1].append(number)
        else:
            runs.append([number])
    main_run = max(runs, key=len)

    rows: list[dict] = []
    stats = {"ruled_pages": 0, "anchor_banded_pages": 0,
             "bands_without_anchor": 0, "bands_with_extra_anchors": []}
    for number in main_run:
        page = doc[number]
        band_y, xs = headers[number]
        body: list[tuple[float, float, float, str]] = []
        for x0, y0, x1, _y1, text, *_ in page.get_text("words"):
            if y0 <= band_y + 4:
                continue
            body.append((x0, x1, y0, text))

        rules = rules_of(page, band_y + 4)
        if len(rules) >= 3:
            stats["ruled_pages"] += 1
            # The zone above the first rule is a band of its own: on most
            # pages it continues the previous page's last row, but on the
            # table's first page it holds the first row outright — UN 0004
            # was silently dropped when this zone was treated as carry-only.
            boundaries = [band_y + 4] + rules + [page.rect.height]
        else:
            # No printed rules on this page: fall back to the UN lines.
            stats["anchor_banded_pages"] += 1
            anchor_ys = sorted(y0 for x0, _x1, y0, text in body
                               if UN_WORD.match(text) and x0 <= xs["1"] + 10)
            boundaries = [y - 2 for y in anchor_ys] + [page.rect.height]

        bands: list[list[tuple[float, float, float, str]]] = [
            [] for _ in range(max(len(boundaries) - 1, 0))]
        for word in body:
            _x0, _x1, y0, text = word
            for index in range(len(boundaries) - 1):
                if boundaries[index] <= y0 + 1 < boundaries[index + 1]:
                    bands[index].append(word)
                    break

        for band in bands:
            if not band:
                continue
            band_text = " ".join(w[3] for w in sorted(band, key=lambda w: w[0]))
            if FOOTER.match(band_text.strip()):
                continue
            anchors = sorted((w for w in band
                              if UN_WORD.match(w[3]) and w[0] <= xs["1"] + 10),
                             key=lambda w: w[2])
            # A band holding two anchors is a missing rule between two rows
            # (the English edition drops one now and then): split it on the
            # second anchor's line, the way anchor banding always did.
            if len(anchors) > 1:
                stats["bands_with_extra_anchors"].append(
                    (number + 1, [a[3] for a in anchors]))
                sub_bands = []
                cuts = [a[2] - 2 for a in anchors[1:]]
                edges = [min(w[2] for w in band) - 1] + cuts + [
                    max(w[2] for w in band) + 1]
                for index in range(len(edges) - 1):
                    sub_bands.append([w for w in band
                                      if edges[index] <= w[2] < edges[index + 1]])
            else:
                sub_bands = [band]

            for sub in sub_bands:
                if not sub:
                    continue
                sub_anchors = [w for w in sub
                               if UN_WORD.match(w[3]) and w[0] <= xs["1"] + 10]
                if sub_anchors:
                    target = {"page": number + 1, "cells": {}}
                    rows.append(target)
                else:
                    stats["bands_without_anchor"] += 1
                    if not rows:
                        continue
                    target = rows[-1]
                for anchor in sub_anchors[:1]:
                    target["cells"].setdefault("1", []).append(anchor[3])
                others = [w for w in sub if w not in sub_anchors]
                # Line by line inside the band, so cell text keeps order.
                lines: dict[int, list] = {}
                for word in others:
                    lines.setdefault(round(word[2] / 3), []).append(word)
                for key in sorted(lines):
                    line = lines[key]
                    # The last band of a page runs to the page edge and can
                    # swallow the running foot ("3.2-A-262", a bare page
                    # number) — a footer line inside a band is still a
                    # footer.
                    line_text = " ".join(w[3] for w in sorted(line))
                    if (min(w[2] for w in line) > page.rect.height - 40
                            and FOOTER.match(line_text.strip())):
                        continue
                    for chunk in chunks_of(line, xs):
                        if NOISE_CHUNK.match(chunk[2]):
                            continue
                        code = assign(chunk, xs)
                        target["cells"].setdefault(code, []).append(chunk[2])

    out: list[dict] = []
    for row in rows:
        fields = {FIELDS[code]: " ".join(row["cells"].get(code, [])).strip()
                  for code in COLS}
        fields["_page"] = row["page"]
        # A banner row prints its message across the cell area instead of
        # values; whichever columns caught the fragments — the centred
        # banner can land in the name as easily as in a code column — the
        # row's meaning is the banner, and the fragments are not data.
        joined = " ".join(" ".join(
            fields[FIELDS[code]] for code in COLS if code != "1").split())
        fields["carriage_prohibited"] = any(b in joined for b in PROHIBITED)
        fields["not_subject"] = any(
            all(fragment in joined for fragment in variant)
            for variant in NOT_SUBJECT)
        if fields["carriage_prohibited"] or fields["not_subject"]:
            for code in COLS[5:]:
                fields[FIELDS[code]] = ""
            for fragment in PROHIBITED + tuple(
                    f for variant in NOT_SUBJECT for f in variant):
                fields["name"] = fields["name"].replace(fragment, "").strip()
        out.append(fields)
    return out, stats


#: The columns whose value is an unordered list of codes. Their cells wrap
#: over several printed lines, and the two editions break the lines in
#: different places, so the tokens are compared as sets.
LIST_COLS = {"6", "8", "9a", "9b", "10", "11", "13", "16", "17", "18", "19"}


def _norm_tokens(code: str, value: str) -> list[str]:
    """What must agree between the editions: the content, not the comma or
    footnote style. The Dutch book writes "P114(b)", "L1,5BN", "P22DH(M )"
    and appends printed footnote digits where the OTIF book writes
    "P114b", "L1.5BN" and "P22DH(M)" plain; column (7a) writes decimals
    with a comma."""
    if code in ("7a", "12"):
        value = value.replace(",", ".")
    value = value.replace(",", " ").replace("( ", "(").replace(" )", ")")
    tokens = []
    for token in value.split():
        token = token.strip("'’")
        match = re.fullmatch(r"(P\d+)\(([a-z])\)", token)
        if match:                                     # P114(b) -> P114b
            token = match.group(1) + match.group(2)
        token = token.replace("+(", "(+")             # +(13) -> (+13)
        if code == "8" and re.fullmatch(r"\d{1,2}", token):
            continue  # a printed footnote index, not a packing instruction
        # Cross-reference cells are printed in each edition's own language
        # ("see 1.7" / "zie 1.7" / "siehe 1.7", "SP" / "SV"): the reference
        # is the content, the language is not.
        prefix = token[:len(token) - len(token.lstrip("("))]
        suffix = token[len(token.rstrip(")")):]
        core = token.strip("()")
        if core.lower() in _LANGUAGE:
            token = prefix + _LANGUAGE[core.lower()] + suffix
        match = re.fullmatch(r"(SP|SV)(\d+)", token)
        if match:                                     # SP340 -> SP 340
            tokens.extend(["SP", match.group(2)])
            continue
        if token == "SV":
            token = "SP"
        if token:
            # A section number the typesetting broke apart ("5.2.2.1. 12",
            # "1.7.1.5 .1") is glued back to its start.
            if (tokens and re.search(r"\d\.?$", tokens[-1])
                    and re.fullmatch(r"\.?\d[\d.]*\)?", token)):
                tokens[-1] = tokens[-1] + token
                continue
            tokens.append(token)
    return tokens


#: Language-bound words of the cross-reference cells, mapped to one form
#: for the comparison only — the seed keeps the English edition's text.
_LANGUAGE = {
    "see": "see", "zie": "see", "siehe": "see",
    "and": "and", "en": "and", "und": "and",
    "or": "or", "of": "or", "oder": "or",
    "none": "NONE", "geen": "NONE", "keine": "NONE",
}


def _norm(code: str, value: str) -> str:
    tokens = _norm_tokens(code, value)
    if code in LIST_COLS:
        tokens = sorted(tokens)
    if code in ("3a", "3b", "4", "5", "12", "15", "20"):
        # Single-value columns whose token the Dutch edition sometimes
        # breaks with a space: "1.2 G", "2TO C", "5.1+6.1 +8", "S2.65AN (+)".
        return "".join(tokens)
    return " ".join(tokens)


def _dump(label: str, row: dict) -> None:
    print(f"    {label} page {row['_page']}: " + " | ".join(
        f"({code}){row[FIELDS[code]]}" for code in COLS
        if row[FIELDS[code]]) + (" [PROHIBITED]" if row["carriage_prohibited"] else ""))


def build(out_path: Path | None, lenient: bool) -> int:
    import difflib

    en, en_stats = parse(STORE / "rid.pdf")
    nl, nl_stats = parse(STORE / "RID-2025-NL.pdf")
    print(f"rows: en {len(en)}, nl {len(nl)}")
    print(f"banding: en {en_stats}, nl {nl_stats}")

    problems: list[str] = []

    def groups(rows: list[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["un"], []).append(row)
        return grouped

    en_groups, nl_groups = groups(en), groups(nl)
    if list(en_groups) != list(nl_groups):
        matcher = difflib.SequenceMatcher(
            a=list(en_groups), b=list(nl_groups), autojunk=False)
        for tag, a0, a1, b0, b1 in matcher.get_opcodes():
            if tag == "equal":
                continue
            problems.append(
                f"UN order differs: en {list(en_groups)[a0:a1][:6]} "
                f"nl {list(nl_groups)[b0:b1][:6]}")
        for un in list(en_groups.keys() - nl_groups.keys())[:4]:
            for row in en_groups[un]:
                _dump("en only", row)
        for un in list(nl_groups.keys() - en_groups.keys())[:4]:
            for row in nl_groups[un]:
                _dump("nl only", row)

    mismatches: Counter = Counter()
    samples: list[str] = []
    union_compared: list[str] = []
    conflicts: list[tuple[str, int, str, dict, dict]] = []
    for un in en_groups:
        rows_en = en_groups[un]
        rows_nl = nl_groups.get(un, [])
        if not rows_nl:
            continue
        flags_en = {(r["carriage_prohibited"], r["not_subject"]) for r in rows_en}
        flags_nl = {(r["carriage_prohibited"], r["not_subject"]) for r in rows_nl}
        if flags_en != flags_nl:
            mismatches["banner"] += 1
            samples.append(f"UN {un}: banner flags differ")
            for row in rows_en:
                _dump("en", row)
            for row in rows_nl:
                _dump("nl", row)
            continue
        if any(flag for pair in flags_en for flag in pair):
            continue
        if len(rows_en) == len(rows_nl):
            for index, (row_en, row_nl) in enumerate(zip(rows_en, rows_nl)):
                for code in COMPARED:
                    field = FIELDS[code]
                    a, b = _norm(code, row_en[field]), _norm(code, row_nl[field])
                    if a != b:
                        conflicts.append((un, index, code, row_en, row_nl))
        else:
            # One edition prints this UN number's variants as one row where
            # the other prints several (the 3381-3390 inhalation entries).
            # What must then agree is the union of every coded column over
            # the group; the seed carries the English edition's row shape.
            union_compared.append(f"{un} (en {len(rows_en)}, nl {len(rows_nl)})")
            for code in COMPARED:
                field = FIELDS[code]
                # "T1 or T4" on the one edition's single row IS the union
                # {T1, T4} of the other's two rows: the connective carries
                # no content once the values are a set.
                a = sorted({t for r in rows_en for t in _norm_tokens(code, r[field])}
                           - {"or", "and"})
                b = sorted({t for r in rows_nl for t in _norm_tokens(code, r[field])}
                           - {"or", "and"})
                if a != b:
                    mismatches[code] += 1
                    if len(samples) < 60:
                        samples.append(
                            f"UN {un} col ({code}) as union: en {a} != nl {b}")
    if union_compared:
        print(f"  union-compared UN groups: {', '.join(union_compared)}")

    # Where the two editions genuinely print different values — the Dutch
    # book drops special provision 386 across the gas entries, prints MP7
    # where the OTIF book prints MP8 — a third independently typeset
    # edition arbitrates: the OTIF German book, read by the same parser.
    overrides: dict[tuple[str, int, str], str] = {}
    if conflicts:
        de, de_stats = parse(STORE / "rid_de.pdf")
        print(f"arbitration: German edition parsed, {len(de)} rows, {de_stats}")
        de_groups = groups(de)
        for un, index, code, row_en, row_nl in conflicts:
            field = FIELDS[code]
            rows_de = de_groups.get(un, [])
            row_de = rows_de[min(index, len(rows_de) - 1)] if rows_de else None
            a, b = _norm(code, row_en[field]), _norm(code, row_nl[field])
            d = _norm(code, row_de[field]) if row_de else None
            if d == a:
                verdict = "en (German agrees)"
            elif d == b:
                verdict = "nl (German agrees)"
                overrides[(un, index, field)] = row_nl[field]
            else:
                verdict = "unresolved"
                mismatches[code] += 1
            if verdict == "unresolved" or len(samples) < 80:
                samples.append(
                    f"UN {un} col ({code}): en {row_en[field]!r} nl "
                    f"{row_nl[field]!r} de "
                    f"{(row_de[field] if row_de else None)!r} -> {verdict}")

    if mismatches:
        problems.append("unresolved mismatches after arbitration: "
                        + ", ".join(f"({c})x{n}" for c, n in mismatches.most_common()))
    for line in samples:
        print("  " + line)

    # Cross-check 1: the shunting models of column (5), already read twice
    # in v1.123.0, must reappear on exactly the same UN numbers.
    shunting = json.loads((SEED / "rid_shunting_labels.json").read_text(encoding="utf-8"))
    expected = {(un, model) for un, models in shunting["rows"].items()
                for model in models}
    found = set()
    for row in en:
        for model in re.findall(r"\(\+(1[35])\)", row["labels"]):
            found.add((row["un"], model))
    if found != expected:
        problems.append(
            f"shunting models disagree with rid_shunting_labels.json: "
            f"missing {sorted(expected - found)[:8]}, "
            f"extra {sorted(found - expected)[:8]}")

    # Cross-check 2: the harmonised identity columns against the ADR table.
    adr = json.loads((SEED / "adr_table_a.json").read_text(encoding="utf-8"))
    adr_ids: dict[str, set] = {}
    for entry in adr["entries"]:
        adr_ids.setdefault(entry["un"], set()).add(
            (entry.get("class") or "", entry.get("classification_code") or "",
             entry.get("packing_group") or ""))
    rid_ids: dict[str, set] = {}
    for row in en:
        rid_ids.setdefault(row["un"], set()).add(
            (row["class"], row["classification_code"], row["packing_group"]))
    shared = set(adr_ids) & set(rid_ids)
    disagree = [un for un in shared if adr_ids[un] != rid_ids[un]]
    print(f"ADR cross-check: {len(shared)} shared UN numbers, "
          f"{len(disagree)} with a different identity set")
    for un in disagree[:15]:
        print(f"  UN {un}: adr {sorted(adr_ids[un])} rid {sorted(rid_ids[un])}")

    for problem in problems:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    if problems and not lenient:
        return 1

    if out_path:
        entries = []
        seen: Counter = Counter()
        for row_en in en:
            un = row_en["un"]
            variants = nl_groups.get(un, [])
            group_index = seen[un]
            index = min(group_index, len(variants) - 1) if variants else -1
            seen[un] += 1
            entry = {FIELDS[code]: row_en[FIELDS[code]] for code in COLS
                     if code != "2"}
            for code in COLS:
                key = (un, group_index, FIELDS[code])
                if key in overrides:
                    entry[FIELDS[code]] = overrides[key]
            entry["name_en"] = row_en["name"]
            entry["name_nl"] = variants[index]["name"] if variants else ""
            entry["carriage_prohibited"] = row_en["carriage_prohibited"]
            entry["not_subject"] = row_en["not_subject"]
            entries.append(entry)
        payload = {
            "_comment": (
                "RID 3.2.1 table A, read geometrically from the word "
                "positions of two independently typeset editions by "
                "scripts/extract_rid_table_a.py; every coded column agreed "
                "between the two before this file was written. A "
                "compilation offered as an aid; the published text of the "
                "RID remains authoritative."),
            "edition": "RID 2025",
            "source": ("RID 2025 — the OTIF English edition and the Dutch "
                       "edition, table A of chapter 3.2, each read as an "
                       "independent typesetting of the same table, with the "
                       "OTIF German edition arbitrating the cells where the "
                       "two disagreed"),
            "readings": 3 if conflicts else 2,
            "arbitrated_cells": len(conflicts),
            "arbitrated_to_nl": len(overrides),
            "row_count": len(entries),
            "problems": problems,
            "cross_checks": {
                "shunting_labels": "agreed" if found == expected else "disagreed",
                "adr_identity_shared": len(shared),
                "adr_identity_disagreements": len(disagree),
                "adr_identity_disagreeing_un": sorted(disagree),
            },
            "entries": entries,
        }
        out_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        print(f"wrote {out_path} ({len(entries)} rows)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", help="filename in the regulations store, or a path")
    parser.add_argument("--probe", action="store_true",
                        help="report the table's printed structure and exit")
    parser.add_argument("--probe-page", type=int,
                        help="dump one page's words at the left margin, its "
                             "rules and its anchors — the mode to look at "
                             "when a page parses strangely")
    parser.add_argument("--sample-pages", type=int, default=2)
    parser.add_argument("--build", action="store_true",
                        help="parse both editions, cross-check, write the seed")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--lenient", action="store_true",
                        help="report problems without failing (diagnosis runs)")
    args = parser.parse_args()

    if args.build:
        return build(args.out, args.lenient)

    if not args.pdf:
        print("--pdf or --build is required", file=sys.stderr)
        return 2
    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        pdf_path = STORE / args.pdf
    if not pdf_path.is_file():
        print(f"not in the store: {args.pdf}", file=sys.stderr)
        return 1
    if args.probe_page:
        doc = fitz.open(str(pdf_path))
        page = doc[args.probe_page - 1]
        header = full_header(page)
        print(f"== {pdf_path.name} page {args.probe_page} ==")
        print(f"header: {header[0] if header else None}")
        rules = rules_of(page, (header[0] + 4) if header else 0)
        print(f"rules at y: {[round(y, 1) for y in rules]}")
        for x0, y0, x1, y1, text, *_ in sorted(page.get_text("words"),
                                               key=lambda w: (w[1], w[0])):
            if x0 <= 60:
                print(f"  x{x0:6.1f} y{y0:6.1f} {text!r}")
        return 0
    if args.probe:
        return probe(pdf_path, args.sample_pages)
    print("nothing to do: pass --probe or --build", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
