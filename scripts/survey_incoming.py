"""A first look at whatever the operator put in the incoming directory.

This is reconnaissance, and it deliberately records nothing. Before a
document can be registered, extracted or even named, somebody has to know
what it *is*: which publication, which edition, how many pages, whether
there is a text layer to read or only scanned images, and where the parts
worth extracting sit. This script prints exactly that, for every PDF under
the incoming directory — subfolders included, because a Drive folder
arrives as a tree.

Per document it reports:

* name, size, sha256 — the identity, and what a register pin would hold;
* page count and page size;
* whether pages carry extractable text, measured over a sample, because a
  scanned book without OCR needs a different plan than a born-digital one;
* the first pages' text, where a title page names the edition;
* a probe over well-known section markers (Dangerous Goods List, packing
  instructions, segregation, stowage), with the page they first appear on —
  the map a later extractor starts from.

Usage::

    python scripts/survey_incoming.py /tmp/emcargo-regulations/incoming
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import fitz  # pymupdf

#: What to look for, and why. The IMDG Code's own chapter numbers, plus the
#: generic markers any dangerous-goods publication carries. First occurrence
#: past the table of contents is what an extractor needs.
MARKERS = [
    ("dangerous goods list", re.compile(r"dangerous\s+goods\s+list", re.I)),
    ("3.2 heading", re.compile(r"chapter\s+3\.2\b", re.I)),
    ("packing instruction P", re.compile(r"\bP0\d\d\b")),
    ("segregation", re.compile(r"segregation", re.I)),
    ("stowage and handling", re.compile(r"stowage\s+and\s+handling", re.I)),
    ("7.1.5 heading", re.compile(r"\b7\.1\.5\b")),
    ("EmS", re.compile(r"\bEmS\b")),
    ("limited quantities", re.compile(r"limited\s+quantit", re.I)),
    ("proper shipping name", re.compile(r"proper\s+shipping\s+name", re.I)),
    ("UN number column", re.compile(r"\bUN\s*No\.?\b", re.I)),
    ("amendment 42-24", re.compile(r"42[-–]24")),
    ("IMO/IMDG naming", re.compile(r"\bIMDG\b")),
]

#: Column (16a)/(16b), the DGL's own signature: codes an ADR book never uses.
DGL_CODES = re.compile(r"\bSW\d{1,2}\b|\bSG\d{1,2}\b|\bH\d\b(?=\s|$)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def survey(path: Path) -> None:
    print(f"\n{'=' * 72}")
    print(f"FILE   {path}")
    print(f"SIZE   {path.stat().st_size:,} bytes")
    print(f"SHA256 {sha256(path)}")
    try:
        doc = fitz.open(path)
    except Exception as exc:  # a truncated download, a non-PDF in disguise
        print(f"UNREADABLE: {exc}")
        return
    with doc:
        pages = doc.page_count
        first = doc[0]
        print(f"PAGES  {pages}   page size {first.rect.width:.0f}x{first.rect.height:.0f} pt")
        meta = {k: v for k, v in (doc.metadata or {}).items() if v}
        for key in ("title", "author", "producer", "creationDate"):
            if meta.get(key):
                print(f"META   {key}: {meta[key][:90]}")

        # Text layer: sampled across the book, not only the front matter —
        # a scanned body behind a born-digital cover is a known trap.
        sample = sorted({0, 1, pages // 4, pages // 2, (3 * pages) // 4,
                         pages - 1} & set(range(pages)))
        with_text = 0
        for number in sample:
            if len(doc[number].get_text().strip()) > 80:
                with_text += 1
        print(f"TEXT   {with_text}/{len(sample)} sampled pages carry a text layer")

        print("--- first two pages, first lines ---")
        for number in (0, 1):
            if number >= pages:
                break
            lines = [line.strip() for line in doc[number].get_text().splitlines()
                     if line.strip()][:14]
            for line in lines:
                print(f"  p{number + 1}: {line[:100]}")

        # Where the interesting parts sit. Scan every page once, keep the
        # first and last hit per marker; cheap even on a thousand pages.
        hits: dict[str, list[int]] = {name: [] for name, _ in MARKERS}
        dgl_pages: list[int] = []
        for number in range(pages):
            text = doc[number].get_text()
            for name, pattern in MARKERS:
                if pattern.search(text):
                    hits[name].append(number + 1)
            if len(DGL_CODES.findall(text)) >= 5:
                dgl_pages.append(number + 1)
        print("--- markers (first…last page, count) ---")
        for name, pages_hit in hits.items():
            if pages_hit:
                print(f"  {name:24} p{pages_hit[0]}…p{pages_hit[-1]}  ({len(pages_hit)} pages)")
        if dgl_pages:
            print(f"  DGL code density (SW/SG/H) p{dgl_pages[0]}…p{dgl_pages[-1]}  "
                  f"({len(dgl_pages)} pages)")

        # A UN-number census over the densest stretch says whether the list
        # is complete enough to be worth extracting.
        if dgl_pages:
            numbers: set[str] = set()
            for number in dgl_pages:
                for match in re.finditer(r"\b([0-3]\d{3})\b", doc[number - 1].get_text()):
                    value = int(match.group(1))
                    if 4 <= value <= 3600:
                        numbers.add(match.group(1))
            print(f"  distinct plausible UN numbers on those pages: {len(numbers)}")


def main() -> int:
    incoming = Path(sys.argv[1] if len(sys.argv) > 1
                    else "/tmp/emcargo-regulations/incoming")
    pdfs = sorted(incoming.rglob("*.pdf")) + sorted(incoming.rglob("*.PDF"))
    if not pdfs:
        print(f"nothing under {incoming}")
        return 1
    print(f"{len(pdfs)} PDF(s) under {incoming}")
    for path in pdfs:
        survey(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
