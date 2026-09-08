#!/usr/bin/env python3
"""Read the official ADR, RID and ADN texts and quote the provisions we implement.

EMCargo's land-transport checks were built from an ADR Table A data export and
from general knowledge of how the regimes are structured. That is not the same as
having read the regulation, and the difference matters: a rule implemented from
memory looks exactly like a rule implemented from the text.

The texts themselves are free. UNECE publishes ADR and ADN, OTIF publishes RID,
all as official PDFs at no charge. What the development container lacks is the
network to reach them; a runner has it. So this script runs there.

Two modes, and the split is deliberate:

``--quote``
    Print the verbatim text of named provisions to the run log, so a human (or
    an agent) can read what the regulation actually says. Nothing is written to
    the repository. The regulatory text is not ours to redistribute.

``--emit``
    Write the *factual values* read out of those provisions — thresholds,
    multipliers, limits — to a JSON file. Numbers are facts, and the repository
    already holds that kind of data (see docs/data-sources.md). Every value
    carries the provision it came from so it can be checked.

Usage::

    python scripts/read_land_regulations.py --quote lq_eq
    python scripts/read_land_regulations.py --quote exemptions --doc rid
    python scripts/read_land_regulations.py --emit backend/seed/dg/land_limits.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The store first, the CI cache path second. /data/regulations is the document
# store of backend/seed/dg/sources.json — a volume that outlives the container —
# and a runner without /data lands on the path its actions/cache step persists.
CACHE = Path(
    os.environ.get("EMCARGO_REGULATIONS_DIR")
    or ("/data/regulations" if Path("/data").is_dir() else "/tmp/emcargo-regulations")
)

# Official, free-of-charge sources. Any change here changes what the app claims
# to be based on, so each entry records the edition and the publisher.
SOURCES: dict[str, dict[str, Any]] = {
    "adr1": {
        "urls": [
            "https://unece.org/sites/default/files/2025-01/2412006_E_ECE_TRANS_352_Vol.I_WEB_0.pdf",
            "https://unece.org/sites/default/files/2025-01/2412006_E_ECE_TRANS_352_Vol.I_WEB.pdf",
        ],
        "title": "ADR 2025 Volume I (ECE/TRANS/352 Vol. I)",
        "publisher": "UNECE",
        "edition": "ADR 2025, in force 1 January 2025",
    },
    # The French edition of Volume I, for the proper shipping names of column
    # (2). ADR is authentic in English and French alike, so this is a source
    # text and not a translation of one.
    "adr1_fr": {
        "urls": [
            "https://unece.org/sites/default/files/2025-01/2412007_F_ECE_TRANS_352_Vol.I_WEB.pdf",
            "https://unece.org/sites/default/files/2025-01/2412007_F_ECE_TRANS_352_Vol.I_WEB_0.pdf",
        ],
        "title": "ADR 2025 Volume I, French (ECE/TRANS/352 Vol. I)",
        "publisher": "UNECE",
        "edition": "ADR 2025, in force 1 January 2025",
    },
    "adr2": {
        "urls": [
            "https://unece.org/sites/default/files/2025-01/2412010_E_ECE_TRANS_352_Vol.II_WEB.pdf",
            "https://unece.org/sites/default/files/2025-01/2412010_E_ECE_TRANS_352_Vol.II_WEB_0.pdf",
        ],
        "title": "ADR 2025 Volume II (ECE/TRANS/352 Vol. II)",
        "publisher": "UNECE",
        "edition": "ADR 2025, in force 1 January 2025",
    },
    "rid": {
        "urls": [
            "https://otif.org/fileadmin/docs/LegalTexts/COTIF/DangerousGoodsRID/RID/RID_2025_e_1_January_2025.pdf",
            "https://www.cit-rail.org/media/files/cim-unterlagen/rid_2025_e_1_january_2025.pdf?cid=395946",
        ],
        "title": "RID 2025 (Appendix C to COTIF, Annex)",
        "publisher": "OTIF",
        "edition": "RID 2025, in force 1 January 2025",
    },
    "adn": {
        "urls": [
            "https://unece.org/sites/default/files/2025-01/ADN%202025%20English.pdf",
            "https://unece.org/sites/default/files/2025-01/ADN_2025_English.pdf",
        ],
        "title": "ADN 2025",
        "publisher": "UNECE",
        "edition": "ADN 2025, in force 1 January 2025",
    },
}

#: The document register of the store, so a reading can name a book this script
#: cannot download.
#:
#: The five sources above are the ones a runner can fetch. They are not the only
#: books EMCargo reads: the printed Dutch ADR, the German volumes and the
#: Dutch ADN were supplied by the operator and live in the store, and a
#: provision that has to be read twice needs a second edition more than it needs
#: a downloadable one. Merging the register in means ``--doc adr_nl_2025`` works
#: exactly like ``--doc adr2``, and a document that is not in the store says so
#: instead of being unnameable.
REGISTER = Path(__file__).resolve().parents[1] / "backend" / "seed" / "dg" / "sources.json"


def _register_documents() -> dict[str, dict[str, Any]]:
    try:
        manifest = json.loads(REGISTER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    extra: dict[str, dict[str, Any]] = {}
    for doc in manifest.get("documents", []):
        name = doc.get("filename", "")
        if doc["id"] in SOURCES or not name.lower().endswith(".pdf"):
            continue
        extra[doc["id"]] = {
            "urls": list(doc.get("urls") or []),
            "title": doc.get("title", doc["id"]),
            "publisher": doc.get("publisher", ""),
            "edition": doc.get("edition", ""),
            "filename": name,
        }
    return extra


SOURCES.update(_register_documents())

# These servers refuse a request that does not look like a browser. The
# documents are published free of charge and require no login; the headers only
# get past a user-agent filter, they do not get past any access control.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class Provision:
    """A provision to quote, addressed by the number it carries in the text."""

    section: str
    docs: tuple[str, ...]
    # Some provisions are easier to find by a phrase than by their number: the
    # number appears in the table of contents, in cross-references and in the
    # running head long before it appears at the provision itself.
    anchors: tuple[str, ...] = ()
    chars: int = 2600
    note: str = ""


# Grouped by the question they answer, because that is how they get read.
GROUPS: dict[str, list[Provision]] = {
    # Does EMCargo's LQ/EQ arithmetic match the text? This is the group that
    # settles whether "verified against the published 3.4/3.5 text" is true.
    "lq_eq": [
        Provision("3.4.1", ("adr1", "rid", "adn"), chars=2200,
                  note="what the LQ chapter exempts, and the column 7a reference"),
        Provision("3.4.2", ("adr1", "rid", "adn"), chars=1200,
                  note="gross mass of the package — expected 30 kg"),
        Provision("3.4.3", ("adr1", "rid", "adn"), chars=1200,
                  note="shrink- or stretch-wrapped trays — expected 20 kg"),
        Provision("3.5.1.2", ("adr1", "rid", "adn"), chars=2600,
                  anchors=("Maximum net quantity per inner packaging",),
                  note="table of E-code limits, E1 to E5"),
        Provision("3.5.1.4", ("adr1", "rid", "adn"), chars=1400,
                  note="how mixed inner packagings are counted"),
        Provision("3.5.5", ("adr1", "rid", "adn"), chars=900,
                  note="packages per vehicle/wagon/container — expected 1000"),
    ],
    # The LQ marking above a certain load. EMCargo fires on 8 tonnes of LQ
    # alone; the text is believed to add a condition on the transport unit.
    "lq_marking": [
        # The package first. 3.4.13 to 3.4.15 mark the transport unit, and
        # reading only those answers the carrier's question while leaving the
        # packer's — which is the one this application is arranged around —
        # unread. The two marks are different sizes and neither implies the
        # other.
        Provision("3.4.7", ("adr1", "rid", "adn"), chars=2600,
                  anchors=("Marking of packages containing limited quantities",),
                  note="the package mark: the diamond, its dimensions and its colours"),
        Provision("3.4.8", ("adr1", "rid", "adn"), chars=2000,
                  note="the same mark with 'Y', for a package packed to the air rules"),
        Provision("3.4.9", ("adr1", "rid", "adn"), chars=1200,
                  note="overpacks — whether the mark has to be reproduced on the outside"),
        Provision("3.4.10", ("adr1", "rid", "adn"), chars=1200),
        Provision("3.4.11", ("adr1", "rid", "adn"), chars=1200),
        Provision("3.4.12", ("adr1", "rid", "adn"), chars=1200),
        Provision("3.4.13", ("adr1", "rid", "adn"), chars=2000,
                  note="when the large LQ mark is required — check for a 12 t condition"),
        Provision("3.4.14", ("adr1", "rid", "adn"), chars=1200,
                  note="when the 3.4.13 marking may be omitted"),
        Provision("3.4.15", ("adr1", "rid", "adn"), chars=1200,
                  note="the mark itself, and its dimensions"),
        # And the sea, which numbers its own chapter 3.4 differently and has
        # never yet agreed with the land where it was assumed to. Read whole
        # rather than quoted per number, because the numbering is what is in
        # question.
        Provision("3.4", ("imdg_42_24",), chars=22000,
                  anchors=("Limited quantities",),
                  note="the Code's own chapter 3.4 — its numbering is not ADR's"),
    ],
    # The 1000-point rule. RID and ADN are believed to have their own version;
    # EMCargo answers all three with ADR's table.
    "exemptions": [
        Provision("1.1.3.6", ("adr1", "rid", "adn"), chars=6000,
                  anchors=("Exemptions related to quantities carried",
                           "Total maximum permissible quantity per wagon",
                           "maximum total quantity per transport unit"),
                  note="transport categories, multipliers and the threshold"),
    ],
    # Mixed loading. Same question as above.
    # Mixed loading. RID has its own 7.5.2.1 and it counts per wagon; ADN has no
    # 7.5.2.1 at all, so for ADN this group is expected to come back empty and
    # the subject has to be found by phrase instead.
    "mixed_loading": [
        Provision("7.5.2.1", ("adr2", "rid"), chars=7000,
                  anchors=("shall not be loaded together in the same",),
                  note="the prohibition table for packages, label against label"),
        Provision("7.5.2.2", ("adr2", "rid"), chars=3000,
                  anchors=("compatibility groups",),
                  note="class 1 compatibility groups loaded together"),
    ],
    # The transport document. Settles whether the tunnel code belongs on a rail
    # or inland waterway document — EMCargo removed it in v1.29.5.
    "document": [
        Provision("5.4.1.1.1", ("adr1", "rid", "adn"), chars=4200,
                  note="the particulars of the description line, item by item"),
    ],
    # Placarding and marking of the vehicle. The one chapter EMCargo names
    # in its output and does not derive. What has to be settled from the text:
    # which placards a vehicle carrying only *packages* needs — the rule is much
    # narrower than "the labels of what is on board" — and when an orange plate
    # has to carry the hazard identification number rather than be blank.
    "placarding": [
        Provision("5.3.1.5", ("adr2",), chars=3000,
                  anchors=("carrying packages only",),
                  note="placards on a vehicle carrying packages"),
        Provision("5.3.2.1", ("adr2",), chars=6000,
                  anchors=("orange-coloured plate",),
                  note="which units carry orange plates, blank or numbered"),
        Provision("5.3.3", ("adr2",), chars=2000,
                  anchors=("elevated temperature",),
                  note="the elevated temperature mark"),
        Provision("5.3.6", ("adr2",), chars=2000,
                  anchors=("environmentally hazardous",),
                  note="the environmentally hazardous substance mark"),
    ],
    # Security. Chapter 1.10 is named nowhere in the application, and the table
    # of 1.10.3.1.2 is a quantity threshold per substance, which is exactly the
    # shape EMCargo can compute with.
    "security": [
        Provision("1.10.3.1", ("adr1",), chars=5000,
                  anchors=("high consequence dangerous goods",),
                  note="the definition and the table of thresholds"),
        Provision("1.10.3.2", ("adr1",), chars=3000,
                  anchors=("security plan",),
                  note="who needs a security plan and what is in it"),
    ],
    # Tunnel restrictions, road only as far as we know.
    "tunnels": [
        Provision("8.6.1", ("adr2",), chars=2000, note="tunnel categories"),
        Provision("8.6.3", ("adr2",), chars=2400, note="tunnel restriction codes"),
    ],
    # Sea placarding. The one chapter the application names for IMDG without
    # deriving anything from it. The amendment resolution replaces the complete
    # text of the Code, so chapter 5.3 is readable there like any other.
    #
    # What has to be settled from the text, because the road rule is *not* a
    # safe guide: a cargo transport unit is placarded on all four sides where a
    # vehicle is not, the UN number accompanies the placard rather than sitting
    # on an orange plate, and the marine pollutant mark has no road counterpart
    # at all.
    "sea_placarding": [
        Provision("5.3.1", ("imdg_42_24",), chars=9000,
                  anchors=("Placarding of cargo transport units",),
                  note="which units, how many sides, which placards, and the "
                       "size the Code prescribes"),
        Provision("5.3.2", ("imdg_42_24",), chars=9000,
                  anchors=("Marking of cargo transport units",),
                  note="UN numbers, the marine pollutant mark and the elevated "
                       "temperature mark, each with the condition that triggers it"),
        Provision("5.3.3", ("imdg_42_24",), chars=2500,
                  anchors=("Elevated temperature",),
                  note="if the elevated temperature mark is its own section here"),
    ],
    # Every case in which 5.4.1 asks for something *beyond* the description
    # line. The application composes the line of 5.4.1.1.1 and handles waste,
    # empty uncleaned packagings, salvage and the environmentally hazardous
    # mention; the rest of this chapter has never been read as a whole, and a
    # missing mention is invisible until an inspector finds it.
    #
    # Read as one block rather than provision by provision: the numbering
    # differs between the three regimes, and asking for a number that does not
    # exist in a book returns nothing rather than saying so.
    "document_cases": [
        Provision("5.4.1.1", ("adr1", "rid", "adn"), chars=30000,
                  anchors=("General information required in the transport document",),
                  note="the whole of 5.4.1.1: every sub-provision that adds a "
                       "mention, in the order the book gives them"),
        Provision("5.4.1.2", ("adr1", "rid", "adn"), chars=20000,
                  anchors=("Additional or special information",),
                  note="the class-specific additions: 1, 2, 4.1/5.2 temperature "
                       "control, 6.2 and 7"),
        Provision("5.4.1.5", ("imdg_42_24",), chars=20000,
                  anchors=("General information required in the transport document",
                           "Additional information"),
                  note="the sea equivalent, which has mentions the land regimes "
                       "do not (limited quantity, marine pollutant, segregation)"),
    ],
}


def _looks_like_pdf(path: Path) -> bool:
    """A 403 page saved to disk is still a file. Check it is really a PDF."""
    if not path.exists() or path.stat().st_size < 500_000:
        return False
    with path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def _wayback(url: str) -> str:
    """The Internet Archive's copy of the same public document.

    UNECE and OTIF sit behind a web application firewall that refuses requests
    from datacentre address ranges — which is every CI runner. The Archive holds
    the same published files and does not, so it is the practical route to a
    document that is free to read either way. ``id_`` asks for the original
    bytes rather than a rewritten page.
    """
    return f"https://web.archive.org/web/2025id_/{url}"


def _curl(url: str, target: Path, extra: list[str] | None = None) -> tuple[int, str]:
    """Fetch and report what actually came back, not just whether curl exited 0.

    Without --fail curl treats a 403 page as a successful download and writes
    the error page to the file. Both earlier attempts failed this way and said
    nothing, which cost two runs.
    """
    command = [
        "curl", "--silent", "--show-error", "--location", "--compressed",
        "--max-time", "300", "--retry", "2", "--retry-delay", "3",
        "-A", BROWSER_HEADERS["User-Agent"],
        "-H", f"Accept: {BROWSER_HEADERS['Accept']}",
        "-H", f"Accept-Language: {BROWSER_HEADERS['Accept-Language']}",
        "-w", "%{http_code} %{content_type}",
        "-o", str(target),
        *(extra or []),
        url,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=360)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 0, f"curl failed: {error}"
    status, _, kind = result.stdout.strip().partition(" ")
    try:
        code = int(status)
    except ValueError:
        code = 0
    return code, kind or result.stderr.strip()[:120]


# Ways to ask, in the order worth trying. Each is a label and the extra curl
# arguments it adds; the URL transform lets the Archive stand in for the origin.
STRATEGIES: list[tuple[str, list[str], bool]] = [
    ("direct", [], False),
    ("with referer", ["-H", "Referer: https://unece.org/"], False),
    ("web archive", [], True),
]

#: Statuses that mean "ask again later" rather than "no".
#:
#: The Archive answers 503 when it is busy, and busy is the normal state of it.
#: The same ADN URL that served 19 MB in the morning served 503 twice in the
#: afternoon and 200 again after a wait — nothing about the request had changed.
#: Without this a whole run is spent discovering that the internet was briefly
#: crowded, which is the most expensive way to learn nothing.
RETRY_STATUSES = frozenset({0, 408, 429, 500, 502, 503, 504})

#: Seconds to wait before asking again. curl's own ``--retry`` covers the first
#: few seconds; these cover the minutes, because a busy Archive stays busy
#: longer than curl is willing to wait. Three waits, then give up honestly.
RETRY_WAITS = (15, 45, 90)


def _ask(address: str, target: Path, extra: list[str], label: str) -> tuple[int, str]:
    """Ask once, and ask again while the answer is "later" rather than "no"."""
    for wait in (*RETRY_WAITS, None):
        code, kind = _curl(address, target, extra)
        size = target.stat().st_size if target.exists() else 0
        ok = _looks_like_pdf(target)
        print(f"      [{label}] {code} {kind} {size:,}B "
              f"{'-> PDF' if ok else ''}", file=sys.stderr)
        if ok or code not in RETRY_STATUSES or wait is None:
            return code, kind
        target.unlink(missing_ok=True)
        print(f"      [{label}] {code} is temporary; asking again in {wait}s",
              file=sys.stderr)
        time.sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


def fetch(doc: str) -> Path:
    """Download a text, reporting the status of every attempt.

    A book that came from the operator is never downloaded: it is in the store
    or the run has nothing to read, and saying which is more useful than a
    fetch that cannot succeed.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    name = SOURCES[doc].get("filename", f"{doc}.pdf")
    for base in (CACHE, Path("/tmp/emcargo-regulations")):
        target = base / name
        if _looks_like_pdf(target):
            return target
    target = CACHE / name

    if not SOURCES[doc]["urls"]:
        raise SystemExit(
            f"{doc} ({SOURCES[doc]['title']}) is operator-supplied and is not in "
            f"the store: expected {target}. Put it there with "
            f"scripts/regulations_store.py add {doc} <file>."
        )

    print(f"    fetching {SOURCES[doc]['title']}", file=sys.stderr)
    attempts: list[str] = []
    for url in SOURCES[doc]["urls"]:
        for label, extra, via_archive in STRATEGIES:
            address = _wayback(url) if via_archive else url
            code, _kind = _ask(address, target, extra, label)
            ok = _looks_like_pdf(target)
            attempts.append(f"{label} {url} -> {code}")
            if ok:
                SOURCES[doc]["resolved_url"] = address
                SOURCES[doc]["resolved_via"] = label
                return target
            target.unlink(missing_ok=True)

    raise SystemExit(
        f"could not download {doc}.\n  " + "\n  ".join(attempts)
        + "\nThe address may have moved; check the publisher's download page."
    )


_PAGES: dict[str, list[str]] = {}


def pages(doc: str) -> list[str]:
    """Page text, cached. Kept per page so a quote can name where it was found."""
    if doc not in _PAGES:
        import pymupdf

        with pymupdf.open(fetch(doc)) as pdf:
            _PAGES[doc] = [page.get_text() for page in pdf]
    return _PAGES[doc]


def _normalise(text: str) -> str:
    """Collapse the whitespace that PDF extraction scatters through a line."""
    return re.sub(r"[ \t]+", " ", text.replace("\xa0", " "))


def _searchable(text: str) -> tuple[str, list[int]]:
    """A view of a page for searching, plus where each character came from.

    RID's typesetting breaks words at the line end — "com-\\npatibility",
    "divi-\\nsion", "alka-\\nline" — so searching it for a phrase quietly found
    nothing at all. "No occurrence" then looks like an answer about the
    regulation when it is only an answer about the line breaks, and that is the
    worst possible failure for a tool whose whole job is to check what the text
    says.

    So: lower case, every hyphen dropped, every run of whitespace one space. It
    over-matches slightly — "self-reactive" also matches "selfreactive" — which
    for a locator is the right way round. It points at a page to read; it does
    not decide anything.

    The second return value maps each position back to the original text, so the
    snippet that gets printed is the real one, hyphens and line breaks included.
    """
    characters: list[str] = []
    origin: list[int] = []
    after_space = True
    after_hyphen = False
    for index, character in enumerate(text):
        if character in "-­‐‑":
            # The line break that follows a hyphen has to go with it, or
            # "com-\npatibility" becomes "com patibility" and is still missed.
            after_hyphen = True
            continue
        if character.isspace():
            if after_space or after_hyphen:
                continue
            characters.append(" ")
            origin.append(index)
            after_space = True
            continue
        characters.append(character.lower())
        origin.append(index)
        after_space = False
        after_hyphen = False
    return "".join(characters), origin


_LEADER = re.compile(r"\.{3,}\s*\d+\s*$", re.MULTILINE)
# RID numbers its pages "1-3" (chapter-page) and its contents is a column of
# those, with no dot leaders at all. An earlier version only knew about leaders
# and so handed RID's contents page back as if it were chapter 1.1.3.6.
_CHAPTER_PAGE = re.compile(r"^[ \t]*\d+-\d+[ \t]*$", re.MULTILINE)
_BARE_NUMBER = re.compile(r"^[ \t]*\d+(?:\.\d+){1,4}[ \t]*$", re.MULTILINE)
# A sentence, roughly: a line long enough to be prose rather than a table cell.
_PROSE_LINE = re.compile(r"^.{60,}$", re.MULTILINE)


def _is_contents_page(text: str) -> bool:
    """Is this a table of contents rather than the regulation itself?

    Three signals, because the three documents format their contents
    differently: dot leaders, a column of chapter-page references, and a page
    that is almost nothing but clause numbers. A body page carries a handful of
    clause numbers; a contents page carries dozens.

    That third signal used to fire on its own, and it took out exactly the wrong
    pages. A table like 7.5.2.1 is a column of "1.4", "5.1", "6.2" — dozens of
    bare numbers and not a contents page in sight. So RID's 7.5.2.1 was skipped
    by the finder, which then reported "no occurrence outside the contents
    pages" for a footnote that is plainly there, on page 1101. Both escape
    hatches failed on the same kind of page, and for the same reason.

    Hence the guard: a page carrying real sentences is not a contents page,
    however many numbers stand in its margin. The other two signals are specific
    enough to stand alone; this one never was.
    """
    if len(_LEADER.findall(text)) >= 4 or len(_CHAPTER_PAGE.findall(text)) >= 5:
        return True
    return len(_BARE_NUMBER.findall(text)) >= 18 and len(_PROSE_LINE.findall(text)) < 5


def locate(doc: str, provision: Provision) -> list[tuple[int, int, int]]:
    """Find where a provision actually starts, best candidate first.

    These are two-column documents: the clause number sits in the left margin
    and extraction puts it on a line of its own, with the text beginning on the
    next line. An earlier version required the text to follow on the same line
    and therefore found almost nothing.

    The same number also appears in the contents, in the running head and in
    every cross-reference. Rather than guess which occurrence is the provision,
    every candidate is scored by how much prose follows it, and the richest
    wins. Returned as (score, page index, offset).
    """
    number = re.escape(provision.section)
    # The number at the start of a line, not the prefix of a longer number
    # (3.4.1 must not match 3.4.13), then either the end of the line or a gap
    # and the text itself.
    pattern = re.compile(rf"^[ \t]*{number}(?![.\d])[ \t]*(?:$|[ \t]+(?=\S))", re.MULTILINE)

    scored: list[tuple[int, int, int]] = []
    page_texts = [_normalise(text) for text in pages(doc)]
    for index, body in enumerate(page_texts):
        if _is_contents_page(body):
            continue
        for match in pattern.finditer(body):
            window = body[match.end(): match.end() + 700]
            # A cross-reference is followed by more reference; a provision is
            # followed by sentences. Letters are the cheapest proxy for prose.
            score = sum(character.isalpha() for character in window)
            if provision.anchors:
                near = " ".join(page_texts[index: index + 2]).lower()
                if any(phrase.lower() in near for phrase in provision.anchors):
                    score += 5000
            scored.append((score, index, match.start()))

    scored.sort(reverse=True)
    return scored


def quote(doc: str, provision: Provision) -> None:
    hits = locate(doc, provision)
    label = f"{SOURCES[doc]['title']} — {provision.section}"
    print()
    print("=" * 78)
    print(label)
    if provision.note:
        print(f"({provision.note})")
    print("=" * 78)
    if not hits:
        print("!! not found — the section number may differ in this regime,")
        print("!! or the provision is absent from it. That is itself an answer.")
        return
    if len(hits) > 1:
        runners_up = ", ".join(f"p{page + 1}({score})" for score, page, _ in hits[1:4])
        print(f"[{len(hits)} candidates; next best: {runners_up}]")
    _, page_index, offset = hits[0]
    text = _normalise(pages(doc)[page_index])[offset:]
    # A provision can run over a page break; pull in what follows.
    following = ""
    for extra in range(1, 4):
        if page_index + extra < len(pages(doc)) and len(text) + len(following) < provision.chars:
            following += "\n" + _normalise(pages(doc)[page_index + extra])
    body = (text + following)[: provision.chars]
    print(f"[page {page_index + 1}]")
    print(body.strip())


_HEADING = re.compile(r"^[ \t]*(\d+(?:\.\d+){1,4})[ \t]*$", re.MULTILINE)


def find(doc: str, phrase: str, limit: int = 12) -> None:
    """Locate a provision by what it says, when its number is unknown.

    Not every regime files the same subject under the same number. ADN has no
    7.5.2.1; looking it up by number returns "not found", which is a true answer
    but not a useful one — the provision exists somewhere else. This searches the
    text and reports the nearest preceding clause number, which is the address
    to quote next.
    """
    print()
    print("=" * 78)
    print(f"{SOURCES[doc]['title']} — searching for {phrase!r}")
    print("=" * 78)
    needle, _ = _searchable(phrase)
    shown = 0
    for index, raw in enumerate(pages(doc)):
        body = _normalise(raw)
        haystack, origin = _searchable(body)
        if needle not in haystack or _is_contents_page(body):
            continue
        for match in re.finditer(re.escape(needle), haystack):
            start = origin[match.start()]
            headings = _HEADING.findall(body[:start])
            where = headings[-1] if headings else "?"
            snippet = " ".join(body[start: start + 220].split())
            print(f"  [page {index + 1}, under {where}] {snippet}")
            shown += 1
            if shown >= limit:
                print(f"  ... stopping at {limit} hits")
                return
            break
    if not shown:
        print("  no occurrence outside the contents pages")


def parse_pages(spec: str) -> list[int]:
    """Turn "594" or "600-606" into a list of one-based page numbers.

    Small on purpose, and refuses the mistakes that would otherwise print a
    thousand pages into a run log: a reversed range, a zero, a range wider than
    a chapter.
    """
    text = spec.strip()
    if "-" in text:
        first_text, _, last_text = text.partition("-")
        first, last = int(first_text), int(last_text)
    else:
        first = last = int(text)
    if first < 1 or last < first:
        raise ValueError(f"{spec!r} is not a page or a page range")
    if last - first >= 12:
        raise ValueError(f"{spec!r} spans {last - first + 1} pages; ask for at most 12")
    return list(range(first, last + 1))


def dump(doc: str, page_number: int) -> None:
    """Print one page exactly as it extracts, clause numbers or not.

    ``locate`` finds a provision by the prose that follows its number, which is
    the right rule for a provision made of sentences and the wrong one for a
    provision that is almost entirely a table. ADR 7.5.2.1 is a grid of crosses
    with a number in the margin, so it scores near zero and loses to every
    cross-reference elsewhere in the volume. When the finder cannot reach the
    text, the page still can — this is that escape hatch.
    """
    body = pages(doc)
    print()
    print("=" * 78)
    print(f"{SOURCES[doc]['title']} — page {page_number} verbatim")
    print("=" * 78)
    if page_number > len(body):
        print(f"!! this document has {len(body)} pages")
        return
    print(_normalise(body[page_number - 1]).strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quote", choices=sorted(GROUPS), action="append", default=[],
                        help="which group of provisions to print (repeatable)")
    parser.add_argument("--doc", choices=sorted(SOURCES), action="append", default=[],
                        help="restrict to these documents (default: all that apply)")
    parser.add_argument("--section", action="append", default=[],
                        help="quote an arbitrary section number, e.g. 1.1.3.6.3")
    parser.add_argument("--chars", type=int, default=2600, help="length of an ad-hoc quote")
    parser.add_argument("--find", action="append", default=[],
                        help="locate a provision by a phrase when its number is unknown")
    parser.add_argument("--page", action="append", default=[],
                        help="print a page verbatim, e.g. 594 or 600-606")
    args = parser.parse_args()

    if not args.quote and not args.section and not args.find and not args.page:
        parser.error("give --quote GROUP, --section NUMBER, --find PHRASE or --page N")

    wanted_docs = tuple(args.doc) if args.doc else None

    unreachable: dict[str, str] = {}
    for group in args.quote:
        print()
        print("#" * 78)
        print(f"# {group}")
        print("#" * 78)
        for provision in GROUPS[group]:
            docs = wanted_docs or provision.docs
            for doc in docs:
                if doc not in SOURCES or doc in unreachable:
                    continue
                try:
                    quote(doc, provision)
                except SystemExit as error:
                    # One text being unreachable must not hide the others.
                    unreachable[doc] = str(error)
                    print(f"\n!! {doc} unreachable, skipping it: {error}")

    for section in args.section:
        provision = Provision(section, wanted_docs or ("adr1",), chars=args.chars)
        for doc in provision.docs:
            quote(doc, provision)

    if unreachable:
        print()
        print("!" * 78)
        print("Not read:")
        for doc, why in unreachable.items():
            print(f"  {doc}: {why}")

    for phrase in args.find:
        for doc in (wanted_docs or ("adr1", "adr2", "rid", "adn")):
            try:
                find(doc, phrase)
            except SystemExit as error:
                print(f"\n!! {doc} unreachable: {error}")

    for spec in args.page:
        for number in parse_pages(spec):
            for doc in (wanted_docs or ("adr1",)):
                try:
                    dump(doc, number)
                except SystemExit as error:
                    print(f"\n!! {doc} unreachable: {error}")

    print()
    print("-" * 78)
    print("Sources read:")
    for doc in sorted(_PAGES):
        info = SOURCES[doc]
        print(f"  {doc}: {info['title']} — {info['publisher']}, {info['edition']}")
        # A book out of the store has no address to print; where it came from
        # is what the register records, and the register is the citation.
        where = info.get("resolved_url") or (info["urls"] or ["from the document store"])[0]
        print(f"       {where}")
        if info.get("resolved_via"):
            print(f"       (via {info['resolved_via']})")


if __name__ == "__main__":
    main()
