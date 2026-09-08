#!/usr/bin/env python3
"""Read the per-substance data out of the UN cards into a seed file.

This produced `backend/seed/dg/card_data.json` from the third-party card set
that shipped with EMCargo before v1.129.0. Those source PDFs are no longer
in the repository (EMCargo generates its own cards now, see
docs/un-cards.md), so running this again needs a local `un_cards/` directory
with that set. The cards are laid out as label/value pairs, which made them a
usable source for the fields EMCargo had been missing per substance:

  marine pollutant   column 4 of the Dangerous Goods List
  stowage codes      SW…, column 16a
  segregation codes  SG…, column 16b — until now the app knew only the
                     segregation *groups* and had to point at the DGL itself
  bulk carriage      whether the substance may travel in bulk
  tank type          the IMO tank instruction, where one applies

The EmS code is read too, but only to cross-check `ems.json`, which comes from
the official EmS Guide and stays the authority. A disagreement between two
independent sources is worth knowing about.

    python scripts/extract_un_card_data.py --out backend/seed/dg/card_data.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

REPO = Path(__file__).resolve().parents[1]
CARDS = REPO / "un_cards"
EMS_DATABASE = REPO / "backend" / "seed" / "dg" / "ems.json"

CARD_NAME = re.compile(r"^un_(\d{4})(?:-(\d+))?\.pdf$", re.IGNORECASE)

# Codes as the cards print them: "(SW1)", "(SG27)", "(SGG9". The trailing
# bracket is optional because a list can run "…(SG35). Stow …".
STOWAGE_CODE = re.compile(r"\bSW(\d{1,2})\b")
SEGREGATION_CODE = re.compile(r"\bSG(\d{1,2})\b")
SEGREGATION_GROUP = re.compile(r"\bSGG(\d{1,2}a?)\b")

# Every label that starts a section, in the order the cards use them. Section
# text runs from one label to the next.
SECTIONS = [
    "UN number", "Shipping name", "Class", "Packing group", "Hazard labels",
    "Marine pollutant", "EmS", "Marking", "Tank provisions:", "Transport in bulk",
    "Orange panel", "Stowage and segregation", "Limited quantities (LQ)",
    "Excepted quantities (EQ)", "Packaging", "Mixed packaging", "Remarks",
    "Properties and", "observations", "Stowage", "Segregation",
    "Placarding of the", "transport unit", "Foodstuff", "IMDG - UN card",
]


def lines_of(path: Path) -> list[str]:
    with fitz.open(path) as pdf:
        text = pdf[0].get_text()
    return [line.strip() for line in text.split("\n") if line.strip()]


def value_after(lines: list[str], label: str) -> str:
    """The single value printed under a label."""
    try:
        index = lines.index(label)
    except ValueError:
        return ""
    if index + 1 >= len(lines):
        return ""
    following = lines[index + 1]
    return "" if following in SECTIONS else following


def section_text(lines: list[str], label: str, until: str) -> str:
    """The paragraph between two section labels."""
    try:
        start = lines.index(label)
    except ValueError:
        return ""
    try:
        end = lines.index(until, start + 1)
    except ValueError:
        end = len(lines)
    return " ".join(lines[start + 1:end]).strip()


def prefixed(value: str) -> str:
    """Normalise a free-text yes/no/maybe answer."""
    lowered = value.strip().lower()
    if lowered.startswith("yes"):
        return "yes"
    if lowered.startswith("no"):
        return "no"
    if lowered.startswith("maybe"):
        return "maybe"
    return ""


def parse_card(path: Path) -> dict[str, object] | None:
    lines = lines_of(path)
    if "UN number" not in lines:
        return None

    stowage = section_text(lines, "Stowage", "Segregation")
    segregation = section_text(lines, "Segregation", "Placarding of the")

    record: dict[str, object] = {
        "un": value_after(lines, "UN number").zfill(4),
        "name": value_after(lines, "Shipping name"),
        "marine_pollutant": prefixed(value_after(lines, "Marine pollutant")),
        "ems": value_after(lines, "EmS"),
        "bulk": value_after(lines, "Transport in bulk").strip().lower(),
        "stowage_codes": sorted({f"SW{n}" for n in STOWAGE_CODE.findall(stowage)},
                                key=lambda c: int(c[2:])),
        "segregation_codes": sorted({f"SG{n}" for n in SEGREGATION_CODE.findall(segregation)},
                                    key=lambda c: int(c[2:])),
        "segregation_groups": sorted({f"SGG{n}" for n in SEGREGATION_GROUP.findall(segregation)},
                                     key=lambda c: (int(c[3:].rstrip("a")), c)),
        "stowage_text": stowage,
        "segregation_text": segregation,
    }
    tank = value_after(lines, "Tank provisions:")
    if tank and tank != "–":
        record["tank_provisions"] = tank
    return record


# What a segregation provision tells you to do. The cards spell every code out
# in a fixed sentence, so the meaning is read from the source rather than typed
# from memory — getting a segregation rule wrong is not a harmless bug.
ACTIONS = [
    ("separated longitudinally by an intervening complete compartment or hold from",
     "separated_longitudinally"),
    ("separated by a complete compartment or hold from", "separated_by_compartment"),
    ("separated from", "separated_from"),
    ("away from", "away_from"),
]
AS_FOR_CLASS = re.compile(r"[Ss]egregation as for (?:class\s+)?([\d.]+[A-Z]?)\b")
CLASS_TOKEN = re.compile(r"\b(?:class|classes|division|divisions)\s+([\d.]+[A-Z]?(?:\s*,?\s*(?:and\s+)?[\d.]+[A-Z]?)*)")
GROUP_TOKEN = re.compile(r"\bSGG(\d{1,2}a?)\b")


def parse_provision(code: str, sentence: str) -> dict[str, object]:
    """Turn one card sentence into a rule the compliance check can apply.

    Sentences that name a class or a segregation group become actionable.
    Anything else — foodstuffs, a named substance, a cross-reference to a table
    in the Code — is kept as text and shown to the user without being acted on.
    """
    rule: dict[str, object] = {"code": code, "text": sentence}

    for phrase, action in ACTIONS:
        if f"\u201c{phrase}\u201d" in sentence or f'"{phrase}"' in sentence:
            rule["action"] = action
            break

    as_for = AS_FOR_CLASS.search(sentence)
    if as_for and "action" not in rule:
        rule["action"] = "segregate_as_class"
        rule["as_class"] = as_for.group(1)
        return rule

    # Only look for a target after the action phrase, so "class 1" in
    # "in relation to goods of class 1" is not mistaken for the target.
    tail = sentence
    for phrase, _action in ACTIONS:
        marker = f"\u201c{phrase}\u201d"
        if marker in sentence:
            tail = sentence.split(marker, 1)[1]
            break

    # "class 1 except for division 1.4S" names one target and one exception.
    # Reading the exception as a second target would warn about a load the Code
    # explicitly allows.
    excepted: list[str] = []
    if re.search(r"\bexcept\b", tail, re.IGNORECASE):
        tail, _, exception_tail = re.split(r"\bexcept\b", tail, maxsplit=1, flags=re.IGNORECASE)[0], "except", \
            re.split(r"\bexcept\b", tail, maxsplit=1, flags=re.IGNORECASE)[1]
        for match in CLASS_TOKEN.finditer(exception_tail):
            for token in re.split(r"[,\s]+(?:and\s+)?", match.group(1)):
                token = token.strip(" .,")
                if token and token not in excepted:
                    excepted.append(token)

    classes: list[str] = []
    for match in CLASS_TOKEN.finditer(tail):
        for token in re.split(r"[,\s]+(?:and\s+)?", match.group(1)):
            token = token.strip(" .,")
            if token and token not in classes:
                classes.append(token)
    groups = [f"SGG{n}" for n in GROUP_TOKEN.findall(tail)]

    targets: dict[str, list[str]] = {}
    if classes:
        targets["classes"] = classes
    if groups:
        targets["groups"] = list(dict.fromkeys(groups))
    if targets and rule.get("action"):
        rule["targets"] = targets
        if excepted:
            rule["excepted_classes"] = excepted
    else:
        rule["informational"] = True
    return rule


def collect_provisions(entries: dict[str, object]) -> dict[str, object]:
    """The canonical sentence per SG code, mined from every card that uses it."""
    from collections import defaultdict

    sentences: defaultdict[str, Counter] = defaultdict(Counter)
    for entry in entries.values():
        text = entry.get("segregation_text")  # type: ignore[union-attr]
        if isinstance(text, list):
            text = " ".join(text)
        if not text:
            continue
        for sentence in re.split(r"(?<=\.)\s+", str(text)):
            for number in set(SEGREGATION_CODE.findall(sentence)):
                sentences[f"SG{number}"][sentence.strip()] += 1

    provisions: dict[str, object] = {}
    for code, counter in sentences.items():
        sentence, count = counter.most_common(1)[0]
        rule = parse_provision(code, sentence)
        rule["seen"] = sum(counter.values())
        rule["variants"] = len(counter)
        provisions[code] = rule
    return dict(sorted(provisions.items(), key=lambda kv: int(kv[0][2:])))


def merge(records: list[dict[str, object]]) -> dict[str, object]:
    """Fold the cards of one UN number into a single entry.

    Where the variants agree, one value. Where they differ — a substance whose
    packing groups are stowed differently — keep every value rather than pick
    one, the same rule the rest of the app follows.
    """
    merged: dict[str, object] = {}
    # The class was here too, but has been removed. It was read by nothing in the
    # application — only by the self-check of scripts/extract_imdg_dgl.py, and
    # that thereby laid one IMDG reading next to another instead of against an
    # independent source. Moreover value_after(lines, "Class") read something
    # else on some cards: UN 2984 to 2992, 3548 and 3550 got sequence numbers as
    # their class, and where two variants disagreed merge() kept both ("['10',
    # '9']"). The self-check now uses ADR Table A from un_numbers.json.
    for field in ("marine_pollutant", "ems", "bulk"):
        values = [r[field] for r in records if r.get(field)]
        unique = list(dict.fromkeys(values))
        if len(unique) == 1:
            merged[field] = unique[0]
        elif unique:
            merged[field] = unique  # genuinely differs per variant
    for field in ("stowage_codes", "segregation_codes", "segregation_groups"):
        codes: list[str] = []
        for record in records:
            for code in record[field]:  # type: ignore[index]
                if code not in codes:
                    codes.append(code)
        if codes:
            merged[field] = codes
    for field in ("stowage_text", "segregation_text"):
        texts = list(dict.fromkeys(str(r.get(field) or "") for r in records if r.get(field)))
        if texts:
            merged[field] = texts[0] if len(texts) == 1 else texts
    names = list(dict.fromkeys(r["name"] for r in records if r.get("name")))
    if names:
        merged["name"] = names[0]
    merged["cards"] = len(records)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", default=str(CARDS))
    parser.add_argument("--out", default="backend/seed/dg/card_data.json")
    args = parser.parse_args()

    directory = Path(args.cards)
    files = sorted(p for p in directory.glob("un_*.pdf") if CARD_NAME.match(p.name))
    if not files:
        print(f"No cards in {directory}", file=sys.stderr)
        return 1

    by_un: dict[str, list[dict[str, object]]] = {}
    failed: list[str] = []
    for path in files:
        try:
            record = parse_card(path)
        except Exception as exc:  # noqa: BLE001 - one bad card must not stop 2849
            failed.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        if record is None:
            failed.append(f"{path.name}: no UN number field")
            continue
        filename_un = CARD_NAME.match(path.name).group(1)  # type: ignore[union-attr]
        if record["un"] != filename_un:
            failed.append(f"{path.name}: card says UN {record['un']}")
            continue
        by_un.setdefault(filename_un, []).append(record)

    entries = {un: merge(records) for un, records in sorted(by_un.items())}

    # Cross-check the EmS codes against the official EmS Guide.
    ems_source = json.loads(EMS_DATABASE.read_text(encoding="utf-8"))["entries"]
    agree = differ = only_card = 0
    disagreements: list[str] = []
    for un, entry in entries.items():
        card_ems = entry.get("ems")
        if not isinstance(card_ems, str) or not card_ems:
            continue
        official = ems_source.get(un)
        if not isinstance(official, dict) or "fire" not in official:
            only_card += 1
            continue
        expected = f"{official['fire']}, {official['spillage']}"
        def canonical(value: str) -> str:
            return re.sub(r"[^A-Z]", "", value.upper())

        if canonical(card_ems) == canonical(expected):
            agree += 1
        else:
            differ += 1
            if len(disagreements) < 20:
                disagreements.append(f"UN {un}: card {card_ems!r} vs guide {expected!r}")

    counts = Counter()
    for entry in entries.values():
        counts["marine_pollutant_yes"] += entry.get("marine_pollutant") == "yes"
        counts["with_stowage_codes"] += bool(entry.get("stowage_codes"))
        counts["with_segregation_codes"] += bool(entry.get("segregation_codes"))
        counts["with_segregation_groups"] += bool(entry.get("segregation_groups"))
        # Bulk carriage is spelled as a BK instruction ("bk2", "bk2 / bk3");
        # anything else on these cards is "not allowed".
        counts["bulk_allowed"] += "bk" in str(entry.get("bulk", ""))

    summary = {
        "cards_read": len(files) - len(failed),
        "un_numbers": len(entries),
        "failed": len(failed),
        "ems_cross_check": {"agree": agree, "differ": differ, "not_in_guide": only_card},
        **counts,
    }
    print(json.dumps(summary, indent=2))
    if failed:
        print("\nfailed:", *failed[:20], sep="\n  ")
    if disagreements:
        print("\nEmS disagreements (guide wins):", *disagreements, sep="\n  ")

    provisions = collect_provisions(entries)
    actionable = [c for c, r in provisions.items() if not r.get("informational")]
    summary["segregation_provisions"] = len(provisions)
    summary["segregation_provisions_actionable"] = len(actionable)

    payload = {
        "_comment": (
            "Per-substance data read from the UN cards in un_cards/ by "
            "scripts/extract_un_card_data.py. Marine pollutant, stowage (SW) and "
            "segregation (SG) codes, bulk carriage. The EmS code here is not used: "
            "ems.json, from the official EmS Guide, is the authority."
        ),
        "source": "Cantell IMDG UN cards, 2023 edition (IMDG 41-22)",
        "summary": summary,
        "segregation_provisions": provisions,
        "entries": entries,
    }
    out = Path(args.out)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nWrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
