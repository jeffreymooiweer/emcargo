#!/usr/bin/env python3
"""Find the four-page model of the instructions in writing inside a volume.

ADR 5.4.3.4 and ADN 5.4.3.4 do not describe the instructions in writing, they
*print* them: "the instructions in writing shall correspond in form and content
to the following four-page model". So the document a driver or a boatmaster has
to carry is a reproduction of those pages, and the honest way for EMCargo to
hand one over is to serve the pages themselves rather than a paraphrase of them.

The publishers do not offer those four pages as a standalone file that this
project can reach — unece.org answers a runner behind Cloudflare with 403 for
its pages, the web archive with 498 — but the volumes are in the document store
already. This reports where the model sits in a volume, so a page range can be
*measured* into ``backend/seed/dg/sources.json`` instead of guessed at, and the
application can cut those pages out of the operator's own copy.

    python scripts/find_instructions_pages.py store/adn.pdf [more.pdf ...]
    python scripts/find_instructions_pages.py --provision 8.6.3 store/adn.pdf

The instructions are not the only model a regime prints rather than describes.
ADN 8.6.3 prints the checklist for loading and unloading a tank vessel and
8.6.4 the one for degassing, and they are found the same way: the provision's
own page, the model's title, and the page the next provision starts on.

What it prints per volume: the pages that carry 5.4.3, the page the model
starts on (the model opens with a title that names the regime, and its pages
are the ones carrying the label pictograms as images), the page 5.4.4 starts
on, and the first line of every page in between — enough to see whether the
range is clean or whether the last page of the model shares a sheet with what
follows it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

#: Each model this script can find: the provision that prints it, the
#: provision that follows it, and the model's own title in the four languages
#: the editions are published in. The title is the first line of the model's
#: first page and is what tells the model apart from a cross-reference to it.
MODELS: dict[str, dict[str, object]] = {
    "5.4.3": {
        "next": "5.4.4",
        "title": re.compile(
            r"INSTRUCTIONS? IN WRITING|CONSIGNES ÉCRITES|SCHRIFTELIJKE INSTRUCTIES"
            r"|SCHRIFTLICHE WEISUNGEN", re.IGNORECASE),
        "span": 20,
    },
    "8.6.3": {
        "next": "8.6.4",
        "title": re.compile(
            r"ADN CHECK ?LIST|LISTE DE CONTRÔLE ADN|CONTROLELIJST ADN"
            r"|ADN[- ]KONTROLLISTE|PRÜFLISTE ADN", re.IGNORECASE),
        "span": 20,
    },
    "8.6.4": {
        # What follows 8.6.4 is not another provision but a whole part, and
        # asking for "9.1" found the contents pages instead: the run reported a
        # twenty-page model. The part's own heading is what ends this one.
        "next": r"(?:PART|PARTIE|TEIL|DEEL)\s+9\b",
        "title": re.compile(
            r"CHECK ?LIST DEGASSING|LISTE DE CONTRÔLE DÉGAZAGE"
            r"|CONTROLELIJST ONTGASSING|PRÜFLISTE ENTGASUNG", re.IGNORECASE),
        "span": 20,
    },
}


def look(path: Path, provision: str = "5.4.3") -> None:
    import fitz

    model = MODELS[provision]
    title_pattern = model["title"]
    section = re.compile(
        rf"^\s*(?:{re.escape(provision)}|{model['next']})\b", re.MULTILINE)
    here = re.compile(rf"^\s*{re.escape(provision)}\b", re.MULTILINE)

    with fitz.open(path) as document:
        print(f"=== {path.name}: {document.page_count} pages")
        # Which edition this is, in the file's own words. An operator-supplied
        # volume arrives without provenance, and the title page is the only
        # place it says who published it.
        meta = document.metadata or {}
        print("  metadata: "
              + ", ".join(f"{key}={meta.get(key)!r}" for key in
                          ("title", "author", "producer", "creationDate")
                          if meta.get(key)))
        first = [line.strip() for line in
                 document[0].get_text("text").strip().split("\n") if line.strip()]
        print("  title page: " + " / ".join(line[:50] for line in first[:5]))
        # The table of contents names 5.4.3 and 5.4.4 on one page and would
        # end the search in the front matter, so every candidate is collected
        # and the *last* run is the body. The model's own title decides where
        # it starts: a page that carries it and the pictograms is a model page.
        heads_543: list[int] = []
        heads_544: list[int] = []
        titles: list[int] = []
        for index in range(document.page_count):
            text = document[index].get_text("text")
            for found in section.finditer(text):
                (heads_543 if here.match(found.group(0)) else heads_544).append(index)
            if title_pattern.search(text):
                titles.append(index)
        print(f"  pages naming {provision}: {heads_543[:8]}")
        print(f"  pages naming the next provision: {heads_544[:8]}")
        print(f"  pages carrying the model's title: {titles[:8]}")
        # The section's own page is the last one naming 5.4.3 that has 5.4.4
        # within a model's length of it. In the table of contents the two names
        # sit on one page and the model does not follow, which rules it out;
        # elsewhere in the book "instructions in writing" is only ever
        # mentioned (1.4.3, 8.1.2), never printed.
        span = int(model["span"])
        pairs = [(a, b) for a in dict.fromkeys(heads_543)
                 for b in heads_544 if 0 < b - a <= span]
        if not pairs:
            print("  the model is not in this volume")
            return
        first_543, first_544 = pairs[-1]
        stop = (first_544 + 1) if first_544 is not None else first_543 + 6
        print(f"  the model sits on pages {first_543 + 1}..{first_544} "
              f"(one-based, 5.4.3's own page first, 5.4.4's page excluded)")
        for index in range(max(0, first_543 - 1), min(stop + 1, document.page_count)):
            page = document[index]
            # The running head and the copyright line are on every page and say
            # nothing about which page this is; the first lines that are not
            # those are what identifies the model.
            lines = [line.strip() for line in
                     page.get_text("text").strip().split("\n")
                     if line.strip() and not re.fullmatch(r"-\s*[\dxvi]+\s*-", line.strip())
                     and not line.strip().startswith(("Copyright", "©"))]
            print(f"  p{index + 1}: images {len(page.get_images())}, "
                  + " / ".join(line[:44] for line in lines[:3]))


def main() -> int:
    arguments = sys.argv[1:]
    provision = "5.4.3"
    if arguments and arguments[0] == "--provision":
        provision = arguments[1]
        arguments = arguments[2:]
    if provision not in MODELS:
        print(f"no model registered for {provision}", file=sys.stderr)
        return 2
    if not arguments:
        print("give one or more PDF paths", file=sys.stderr)
        return 2
    for name in arguments:
        path = Path(name)
        if not path.is_file():
            print(f"=== {path}: not in the store")
            continue
        look(path, provision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
