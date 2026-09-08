#!/usr/bin/env python3
"""Read which substances carry the shunting models 13 and 15 in RID table A.

The column (5) explanation of RID 3.2.1 (English edition, page 258; German,
page 280 — they agree) says the shunting labels of 5.3.4 are "indicated in
brackets for some substances" and are only ever affixed in two cases: Class 1
on both sides of full-load wagons, Class 2 on both sides of tank-type wagons.
EMCargo has applied those two cases since v1.121.0 as a *class-level*
condition, because its table A is the ADR's, whose column (5) carries neither
model. This script reads the per-substance half out of the RID's own table.

It is deliberately not a full table A parser. The question is narrow — which
rows print a bracketed 13 or 15 in the labels column — so the reading is
narrow too: every word of every page is scanned for the bracketed tokens, and
a hit is attributed to the row whose UN number governs its vertical band. The
label column's x-range is confirmed per page from the column (5) hits
themselves, and a bracketed 13/15 outside every table page pattern is
reported rather than counted.

Two independent readings, per the rule for regulatory tables here:

``--pdf rid.pdf``     the OTIF English edition (from the CI cache).
``--pdf rid_de.pdf``  the German edition, read the same way.

Both run on the runner via the extract workflow, print their rows to the log
(the development container cannot reach the artifact store), and the two logs
are compared in the development container before anything becomes a seed.

``--probe``       report, per page with hits, the token, its coordinates and
                  the attributed UN — the mode to look at before believing.
``--probe-page``  dump every word of one page with coordinates.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - runner installs it
    fitz = None

STORE = Path(
    os.environ.get("EMCARGO_REGULATIONS_DIR")
    or ("/data/regulations" if Path("/data").is_dir()
        else "/tmp/emcargo-regulations"))

#: The bracketed shunting models as table A prints them in the cells: with a
#: plus sign — ``(+13)`` after label model 1 on UN 0027's row. The plus is the
#: discriminator the first probe run found: the plain ``(13)`` and ``(15)``
#: are the table's own column numbers, printed in the header of every page,
#: and part 2 prints plain ``(13)`` in running text as well.
TOKEN = re.compile(r"^\(\+(1[35])\)$")

#: A UN number is a bare four-digit word in the leftmost column. The x
#: threshold is generous; the probe mode exists to check it against the book.
UN_WORD = re.compile(r"^\d{4}$")


def rows_of(page) -> list[tuple[float, float, str, float]]:
    """Every word on the page as (x0, y0, text, y1)."""
    return [(w[0], w[1], w[4], w[3]) for w in page.get_text("words")]


def un_bands(words, un_max_x: float) -> list[tuple[float, str]]:
    """The y positions where a table row starts: a four-digit word at the left
    margin. Sorted top to bottom; each governs down to the next one."""
    bands = sorted(
        (y0, text) for x0, y0, text, _y1 in words
        if x0 <= un_max_x and UN_WORD.match(text))
    return bands


def attribute(y: float, bands: list[tuple[float, str]]) -> str | None:
    """The UN number whose band a y coordinate falls in."""
    owner = None
    for band_y, un in bands:
        if band_y <= y + 2.0:
            owner = un
        else:
            break
    return owner


def scan(pdf_path: Path, un_max_x: float, probe: bool) -> dict:
    doc = fitz.open(pdf_path)
    hits: dict[str, set[str]] = {}
    pages_with_hits: list[int] = []
    orphans: list[dict] = []
    for number in range(doc.page_count):
        page = doc[number]
        words = rows_of(page)
        tokens = [(x0, y0, TOKEN.match(t).group(1))
                  for x0, y0, t, _y1 in words if TOKEN.match(t)]
        if not tokens:
            continue
        bands = un_bands(words, un_max_x)
        page_report = []
        for x0, y0, model in tokens:
            un = attribute(y0, bands)
            if un is None:
                orphans.append({"page": number + 1, "x": round(x0, 1),
                                "y": round(y0, 1), "model": model})
                continue
            hits.setdefault(un, set()).add(model)
            page_report.append((un, model, round(x0, 1), round(y0, 1)))
        pages_with_hits.append(number + 1)
        if probe and page_report:
            print(f"page {number + 1}:")
            for un, model, x, y in page_report:
                print(f"  UN {un}  ({model})  at x={x} y={y}")
    doc.close()
    return {
        "rows": {un: sorted(models) for un, models in sorted(hits.items())},
        "pages": pages_with_hits,
        "orphans": orphans,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default="rid.pdf",
                        help="file name in the document store")
    parser.add_argument("--un-max-x", type=float, default=120.0,
                        help="right edge of the UN column, in PDF points")
    parser.add_argument("--probe", action="store_true",
                        help="print every hit with its coordinates")
    parser.add_argument("--probe-page", type=int, default=0,
                        help="dump every word of this page and stop")
    args = parser.parse_args()

    if fitz is None:
        print("PyMuPDF is not installed", file=sys.stderr)
        return 2
    pdf_path = STORE / args.pdf
    if not pdf_path.exists():
        print(f"not in the store: {pdf_path}", file=sys.stderr)
        return 2

    if args.probe_page:
        doc = fitz.open(pdf_path)
        page = doc[args.probe_page - 1]
        for x0, y0, text, _y1 in rows_of(page):
            print(f"{x0:7.1f} {y0:7.1f}  {text}")
        doc.close()
        return 0

    result = scan(pdf_path, args.un_max_x, args.probe)
    print("=== shunting models per UN number ===")
    print(json.dumps(result["rows"], indent=1, sort_keys=True))
    print(f"=== {len(result['rows'])} UN numbers, "
          f"{len(result['pages'])} pages with hits ===")
    if result["orphans"]:
        print("=== bracketed 13/15 with no UN row above them — look at these ===")
        for orphan in result["orphans"]:
            print(f"  page {orphan['page']} x={orphan['x']} y={orphan['y']} "
                  f"({orphan['model']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
