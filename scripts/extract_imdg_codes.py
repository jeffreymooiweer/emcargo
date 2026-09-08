"""Stowage, handling and segregation codes from IMDG Code Amendment 42-24.

The app knows the codes of columns 16a and 16b per substance — SW1, H2, SG35 —
but until now only with the fragments of text that could be scraped off the UN
cards. A bare code says nothing to a user, and half a quotation is worse than no
quotation.

This script reads the definitions from their own chapters:

- 7.1.5  stowage codes SW1 to SW31
- 7.1.6  handling codes H1 to H5
- 7.2.8  segregation codes SG1 to SG78

Source: resolution MSC.556(108), adopted on 23 May 2024, in force on 1 January
2026 — the instrument by which Amendment 42-24 was adopted. It runs via GitHub
Actions, because the development environment has no outbound network.

What is written out is a factual code table: code, description and where it came
from. The same line as the rest of the data in this repo. The published text of
the Code remains authoritative.

Usage::

    python scripts/extract_imdg_codes.py --out backend/seed/dg/imdg_codes.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

SOURCE_URL = "https://www.cepa.be/wp-content/uploads/IMDG_Code-amdt_42_24.pdf"
SOURCE_NAME = ("IMO-resolutie MSC.556(108), aangenomen 23 mei 2024 — Amendments to the "
               "International Maritime Dangerous Goods (IMDG) Code, Amendment 42-24, "
               "in werking sinds 1 januari 2026")
UA = {"User-Agent": "EMCargo data extraction (github.com/jeffreymooiweer/emcargo)"}

# Each series with the heading the section starts on and the pattern of its codes.
SECTIONS = [
    {
        "key": "stowage_codes",
        "section": "7.1.5",
        "heading": re.compile(r"^7\.1\.5(?![\d.])"),
        "intro": "stowage codes given in column 16a",
        "code": re.compile(r"^(SW\d{1,2})(?!\d)\s*(.*)$"),
        "stop": re.compile(r"^7\.1\.6(?![\d.])"),
    },
    {
        "key": "handling_codes",
        "section": "7.1.6",
        "heading": re.compile(r"^7\.1\.6(?![\d.])"),
        "intro": "handling codes given in column 16a",
        "code": re.compile(r"^(H\d{1,2})(?!\d)\s*(.*)$"),
        "stop": re.compile(r"^Chapter 7\.2(?![\d.])"),
    },
    {
        "key": "segregation_codes",
        "section": "7.2.8",
        "heading": re.compile(r"^7\.2\.8(?![\d.])"),
        "intro": "segregation codes given in column 16b",
        "code": re.compile(r"^(SG\d{1,2})(?!\d)\s*(.*)$"),
        "stop": re.compile(r"^Annex\s*$"),
    },
]

# Headers and footers of the publication. Those sit in the middle of the codes
# and would otherwise be taken along as a description.
NOISE = re.compile(
    r"^(?:"
    r"MSC \d+/\d+/Add\.\d+"
    r"|Annex \d+, page \d+"
    r"|IMDG Code \(Amendment [\d-]+\)\s*\d{4} EDITION"
    r"|Part \d+ [–-] .*"
    r"|Chapter [\d.]+ [–-] .*"
    r"|(?:Stowage|Handling|Segregation)\s*$"
    r"|code\s*$"
    r"|Description\s*$"
    r"|\d{1,4}\s*$"
    r"|■\s*"
    r")$"
)

# "[Reserved]" is not a provision but a gap the Code keeps open.
RESERVED = re.compile(r"^\[\s*reserved\s*\]\.?$", re.I)


def download(url: str, target: Path, timeout: int = 600) -> Path:
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        target.write_bytes(response.read())
    return target


def clean_lines(document, first: int, last: int) -> list[str]:
    """Readable lines from a page range, without headers and footers."""
    out: list[str] = []
    for index in range(first, min(last, document.page_count)):
        for raw in document[index].get_text().splitlines():
            line = raw.replace("\t", " ").replace("\xa0", " ").strip()
            if line and not NOISE.match(line):
                out.append(line)
    return out


def find_section(document, spec: dict[str, Any]) -> int:
    """The page number a section starts on, found by its introductory sentence.

    Searching on the section number yields the table of contents and every
    cross-reference — 7.1.5 occurs in five places. The introductory sentence
    ("The stowage codes given in column 16a …") occurs in only one.
    """
    for index in range(document.page_count):
        if spec["intro"] in document[index].get_text():
            return index
    raise LookupError(f"sectie {spec['section']} niet gevonden: "
                      f"de zin {spec['intro']!r} komt nergens voor")


def parse_codes(lines: list[str], spec: dict[str, Any]) -> dict[str, str]:
    """Codes and their description out of a run of lines.

    The layout is a two-column table that comes out of the PDF as separate
    lines: first the code alone on a line, then the description over one or more
    lines. Everything up to the next code belongs to the previous one.
    """
    codes: dict[str, list[str]] = {}
    current: str | None = None
    started = False

    for line in lines:
        if not started:
            if spec["heading"].match(line):
                started = True
            continue
        if spec["stop"].match(line):
            break
        match = spec["code"].match(line)
        if match:
            current = match.group(1)
            codes.setdefault(current, [])
            # Usually the code stands alone on its line, but the PDF sometimes
            # contracts columns; then the description already begins here.
            if match.group(2).strip():
                codes[current].append(match.group(2).strip())
            continue
        if current is not None:
            codes[current].append(line)

    return {code: " ".join(parts).strip() for code, parts in codes.items() if parts}


def sort_key(code: str) -> tuple[str, int]:
    match = re.match(r"^([A-Z]+)(\d+)$", code)
    return (match.group(1), int(match.group(2))) if match else (code, 0)


def extract(path: Path) -> dict[str, Any]:
    import fitz

    result: dict[str, Any] = {
        "_comment": (
            "Stowage codes (16a), handling codes (16a) and segregation codes (16b) with "
            "their descriptions, taken from chapters 7.1.5, 7.1.6 and 7.2.8 of the IMDG "
            "Code. A compilation of facts offered as an aid; the published text of the "
            "code remains authoritative. Read by machine with "
            "scripts/extract_imdg_codes.py."
        ),
        "amendment": "42-24",
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
    }

    with fitz.open(path) as document:
        for spec in SECTIONS:
            start = find_section(document, spec)
            lines = clean_lines(document, start, start + 6)
            codes = parse_codes(lines, spec)
            if not codes:
                raise LookupError(f"geen codes gelezen in {spec['section']}")
            # Reserved codes have no meaning. Putting them apart stops the
            # interface showing "[Reserved]" as a provision.
            reserved = sorted((c for c, t in codes.items() if RESERVED.match(t)), key=sort_key)
            active = {c: t for c, t in codes.items() if not RESERVED.match(t)}
            result[spec["key"]] = {
                "section": spec["section"],
                "codes": {code: active[code] for code in sorted(active, key=sort_key)},
                "reserved": reserved,
            }
            print(f"{spec['section']}: {len(active)} codes "
                  f"({min(codes, key=sort_key)}..{max(codes, key=sort_key)}), "
                  f"{len(reserved)} gereserveerd {reserved}, vanaf PDF-pagina {start + 1}")
    return result


def sanity_check(data: dict[str, Any]) -> list[str]:
    """What can go wrong when reading a PDF table, made explicit.

    A parser that quietly misses half is more dangerous than one that fails, so
    this reports incompleteness instead of letting it pass.
    """
    problems: list[str] = []
    expected = {"stowage_codes": ("SW", 31), "handling_codes": ("H", 5),
                "segregation_codes": ("SG", 78)}
    for key, (prefix, highest) in expected.items():
        entry = data[key]
        codes = entry["codes"]
        numbers = {int(c[len(prefix):]) for c in list(codes) + entry.get("reserved", [])}
        if highest not in numbers:
            problems.append(f"{key}: hoogste code {prefix}{highest} ontbreekt")
        # Gaps may exist — SG64, SG66 and SG73 are reserved, SG75 lapsed with
        # 41-22 — but a gap of more than three in a row points to a reading error
        # rather than to the Code.
        missing = sorted(set(range(1, highest + 1)) - numbers)
        run: list[int] = []
        for number in missing + [None]:
            if run and number == run[-1] + 1:
                run.append(number)
                continue
            if len(run) > 3:
                problems.append(f"{key}: {prefix}{run[0]}..{prefix}{run[-1]} ontbreken")
            run = [number] if number is not None else []
        for code, text in codes.items():
            if len(text) < 5:
                problems.append(f"{key}: {code} heeft een verdacht korte omschrijving")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("backend/seed/dg/imdg_codes.json"))
    parser.add_argument("--pdf", type=Path, help="Al gedownload bestand hergebruiken")
    args = parser.parse_args(argv)

    path = args.pdf or download(SOURCE_URL, Path("/tmp/imdg_42_24.pdf"))
    print(f"bron: {path} ({path.stat().st_size} bytes)")

    data = extract(path)
    problems = sanity_check(data)
    for problem in problems:
        print(f"LET OP: {problem}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"geschreven: {args.out}")

    print("\n--- wat er gelezen is ---")
    for key in ("stowage_codes", "handling_codes", "segregation_codes"):
        for code, text in data[key]["codes"].items():
            print(f"{code:<6} {text}")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
