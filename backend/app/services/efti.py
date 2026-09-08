"""The eFTI common data set, and where EMCargo's shipment lands in it.

Regulation (EU) 2020/1056 has the authorities accept freight transport
information electronically from 9 July 2027, through certified eFTI
platforms, and Commission Delegated Regulation (EU) 2024/2024 establishes
the data set those platforms exchange: 681 data objects with an identifier
each (``eFTIxxx``), and per legal provision a subset saying which of them
the provision asks for. The seed under ``backend/seed/efti`` is that Annex,
read from the Official Journal by ``scripts/build_efti_seed.py``.

EMCargo is not an eFTI platform and does not become one — that is a
certification regime for platform providers. What it can be is connectable
to one, and the first half of that is knowing, element by element, which
eFTI data element each field of the structured shipment export answers,
and which elements a provision asks for that this application does not
hold. ``backend/app/config/efti_mapping.json`` is that correspondence,
written by hand against the definitions in Table 1; this module reads it
and measures it against the subsets: for the road transport document
(EU01) and the ADR, RID and ADN transport documents (EU05a, EU05b, EU05c),
how many of the elements a provision asks for the export can answer, and
which it cannot. ``docs/efti-mapping.md`` is the account of it.

A mapping entry has a ``kind``:

* ``field`` — a value the export carries as such (a registry field, a
  goods line field, a dangerous goods product field);
* ``derived`` — a value EMCargo works out (a tunnel code from Table A,
  the 1.1.3.6 points, a country read off a route field);
* ``translated`` — a value the export carries in its own vocabulary that
  has to be translated into the element's code list first (a modality into
  a mode code, a packing group into a danger level code).

Nothing here produces an eFTI message. That needs the platform's own
schema and the party model the mapping names as missing; this is the
inventory that comes first.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.core.config import get_settings

#: The subsets this application's documents answer to, and what each is.
SUBSETS = {
    "EU01": "Article 6(1) of Regulation No 11 — the road transport document",
    "EU05a": "Directive 2008/68/EC Annex I — ADR, the road dangerous goods transport document",
    "EU05b": "Directive 2008/68/EC Annex II — RID, the rail dangerous goods transport document",
    "EU05c": "Directive 2008/68/EC Annex III — ADN, the inland waterway dangerous goods transport document",
}

#: The statuses under which a subset asks for an element: mandatory,
#: conditional, optional. ``D*`` marks a supplementary component that
#: follows its element; ``SI`` a class present for structure.
ASKED = ("M", "C", "O", "M C")

_lock = threading.Lock()
_cache: dict[str, Any] = {}


def _seed_dir() -> Path:
    return get_settings().seed_dir / "efti"


def _load(name: str) -> dict[str, Any]:
    with _lock:
        if name not in _cache:
            _cache[name] = json.loads((_seed_dir() / f"{name}.json").read_text(encoding="utf-8"))
    return _cache[name]


def source() -> dict[str, Any]:
    """Which text the seed was read from: title, ELI, file, checksum."""
    return dict(_load("common_data_set")["source"])


def elements() -> list[dict[str, Any]]:
    """Table 1: every data object of the common data set, in the Annex's order."""
    return list(_load("common_data_set")["elements"])


def element(identifier: str) -> dict[str, Any] | None:
    index = _cache.get("_by_id")
    if index is None:
        index = {e["id"]: e for e in elements()}
        _cache["_by_id"] = index
    return index.get(identifier)


def subset_rows() -> dict[str, dict[str, Any]]:
    """Table 2: per identifier, the status under each EU subset."""
    return _load("subsets")["rows"]


def code_list(reference: str) -> dict[str, str] | None:
    return _load("code_lists")["lists"].get(reference)


def business_rule(reference: str) -> dict[str, Any] | None:
    return _load("business_rules")["rules"].get(reference)


def asked_by(subset: str) -> list[dict[str, Any]]:
    """The data elements (not classes) a subset asks for, with their status."""
    out = []
    for identifier, row in subset_rows().items():
        status = row.get(subset, {}).get("status", "")
        if row["type"] in ("BBIE", "SC") and status in ASKED:
            found = element(identifier) or {}
            out.append({**found, "status": status, "rule": row[subset].get("rule", ""),
                        "codes": row[subset].get("codes", "")})
    return out


def mapping() -> list[dict[str, Any]]:
    """The hand-written correspondence, export field by eFTI element."""
    with _lock:
        if "_mapping" not in _cache:
            path = Path(__file__).resolve().parents[1] / "config" / "efti_mapping.json"
            _cache["_mapping"] = json.loads(path.read_text(encoding="utf-8"))["mapping"]
    return list(_cache["_mapping"])


def coverage(subset: str) -> dict[str, Any]:
    """How much of what a subset asks for the export can answer.

    Counted over the data elements with status M, C or O; supplementary
    components (``D*``) follow their element and are not counted twice.
    """
    mapped = {m["efti"]: m for m in mapping()}
    asked = asked_by(subset)
    answered = [e for e in asked if e["id"] in mapped]
    missing = [e for e in asked if e["id"] not in mapped]
    by_status = {}
    for status in ("M", "C", "O"):
        total = [e for e in asked if e["status"].startswith(status)]
        by_status[status] = {"asked": len(total), "answered": sum(1 for e in total if e["id"] in mapped)}
    return {
        "subset": subset,
        "provision": SUBSETS.get(subset, subset),
        "asked": len(asked),
        "answered": len(answered),
        "by_status": by_status,
        "answered_elements": [{"id": e["id"], "name": e["name"], "status": e["status"],
                               "kind": mapped[e["id"]]["kind"], "source": mapped[e["id"]]["source"]}
                              for e in answered],
        "missing_elements": [{"id": e["id"], "name": e["name"], "status": e["status"],
                              "definition": e.get("definition", "")} for e in missing],
    }
