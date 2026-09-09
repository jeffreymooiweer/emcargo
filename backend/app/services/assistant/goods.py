"""What the goods themselves still leave open, and how a spoken answer to it
is read.

The assistant was a dangerous goods assistant: every question it asked came
from `dg/prepare` or the document registry, and a consignment of sand-lime
brick — no UN number, no regulation, just goods — was carried from the first
sentence straight to the consignor's name with the weight and the volume left
empty. The pipeline had already said what was wrong ("dimensions_missing")
and the catalogue had already supplied the density; nobody asked the one
question that turns both into a weight.

This module names those questions. Like every other question source it only
reports what the calculation itself raised: nothing here decides anything
about the goods, and an unanswered question leaves the line exactly as the
pipeline left it.
"""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.assistant.understanding import (ALTERNATIVE, NEGATED, NUMBER, unsure, number, stated_number)

_INSTRUCTIONS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "goods_instructions.json"
)


@lru_cache(maxsize=1)
def goods_fields() -> dict[str, Any]:
    try:
        payload = json.loads(_INSTRUCTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - config missing
        return {}
    return payload.get("goods_fields", {})


def _known(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def open_questions_for_line(line: dict[str, Any]) -> list[dict[str, Any]]:
    """The questions this calculated goods line leaves open.

    Two of them, both optional, and never both at once: the dimensions of one
    item, which with a known density give the weight and the loading volume;
    or, for goods the catalogue does not know, the weight of one item, which
    is the only thing that still helps.
    """
    if not _known(line.get("quantity")):
        return []
    has_dimensions = all(_known(line.get(key))
                         for key in ("length_cm", "width_cm", "height_cm"))
    if has_dimensions:
        return []
    weight_known = _known(line.get("weight_total_kg")) or _known(line.get("weight_each_kg"))
    volume_known = _known(line.get("transport_volume_m3"))
    if weight_known and volume_known:
        return []
    if not _known(line.get("material_density")):
        if weight_known:
            return []
        # Without a density in the catalogue no measurement produces a weight;
        # the weight itself is the only answer that completes the line.
        return [{"field": "goods_weight_each", "required": False,
                 "reason": "weight_unknown_material"}]
    reason = "dimensions_complete_the_picture" if not weight_known else "dimensions_complete_the_volume"
    return [{"field": "goods_dimensions", "required": False, "reason": reason}]


# --- reading the answers ---------------------------------------------------

_NUMBER = r"\d+(?:[.,]\d+)?"
#: "120 x 80 x 100", "120 bij 80 bij 100 cm", "1,2 x 0,8 x 1 m" — the ways
#: three measurements get written down, with the unit stated once or not at
#: all. Centimetres are the assumption the wizard's own columns make.
_DIMENSIONS = re.compile(
    rf"({_NUMBER})\s*(mm|cm|m)?\s*(?:x|×|\*|bij|by|par|auf)\s*"
    rf"({_NUMBER})\s*(mm|cm|m)?\s*(?:x|×|\*|bij|by|par|auf)\s*"
    rf"({_NUMBER})\s*(mm|cm|m)?",
    re.IGNORECASE,
)

_TO_CM = {"mm": 0.1, "cm": 1.0, "m": 100.0}

_WEIGHT = re.compile(rf"({_NUMBER})\s*(kg|kilo|kilogram|kilogramme[s]?|t|ton|tonne[s]?|tonnen)?\b",
                     re.IGNORECASE)
_TO_KG = {"kg": 1.0, "kilo": 1.0, "kilogram": 1.0, "kilogramme": 1.0,
          "kilogrammes": 1.0, "t": 1000.0, "ton": 1000.0, "tonne": 1000.0,
          "tonnes": 1000.0, "tonnen": 1000.0, "g": 0.001, "gram": 0.001, "grams": 0.001, "gramme": 0.001, "grammes": 0.001}


def parse_dimensions(text: str) -> dict[str, float] | None:
    """Three measurements out of a spoken answer, in centimetres.

    A unit named once counts for all three ("1,2 x 0,8 x 1 m"); a unit named
    per measurement counts for that one. Without any unit the numbers are
    centimetres, the same as the wizard's own columns.
    """
    if unsure(text) or NEGATED.search(text) or re.search(r"-\s*\d", text):
        return None
    matches = list(_DIMENSIONS.finditer(text or ""))
    match = matches[0] if len(matches) == 1 else None
    if not match:
        return None
    numbers = [match.group(1), match.group(3), match.group(5)]
    units = [match.group(2), match.group(4), match.group(6)]
    stated = [unit for unit in units if unit]
    common = stated[-1].lower() if stated else "cm"
    values: list[float] = []
    for number, unit in zip(numbers, units):
        factor = _TO_CM[(unit or common).lower()]
        try:
            value = float(number.replace(",", ".")) * factor
        except ValueError:  # pragma: no cover - the regex only matches numbers
            return None
        if not math.isfinite(value) or not 0 < value <= 100_000:
            return None
        values.append(round(value, 2))
    return {"length_cm": values[0], "width_cm": values[1], "height_cm": values[2]}


def parse_weight_kg(text: str) -> float | None:
    """One weight out of a spoken answer, in kilograms. A bare number is
    kilograms; tonnes are converted."""
    if unsure(text) or NEGATED.search(text) or ALTERNATIVE.search(text) or re.search(r"-\s*\d", text):
        return None
    if _DIMENSIONS.search(text):
        return None
    # Prefer the number carrying a mass unit; a package count is not mass.
    pattern = re.compile(rf"({NUMBER})\s*(kilogrammes?|kilograms?|kilogram|kilo|kg|grams?|grammes?|g|tonnes?|tonnen|ton|t)\b", re.I)
    matches = list(pattern.finditer(text))
    if len(matches) == 1:
        match = matches[0]
        value = number(match.group(1))
        factor = _TO_KG.get(match.group(2).lower(), 1.0)
    elif not matches:
        value, factor = number(text.strip()), 1.0
    else:
        return None
    weight = value * factor if value is not None else 0
    return round(weight, 3) if math.isfinite(weight) and 0 < weight <= 1e9 else None



#: What the model may say about a measurement, and nothing else: three
#: numbers in centimetres. It never sees a regulation and never decides one.
DIMENSIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "length_cm": {"type": "number"},
        "width_cm": {"type": "number"},
        "height_cm": {"type": "number"},
    },
    "required": ["length_cm", "width_cm", "height_cm"],
}

DIMENSIONS_PROMPT = (
    "The user describes how big one item or one package is. Convert their "
    "answer into three measurements in centimetres: length, width and "
    "height. Convert metres and millimetres to centimetres. The message may "
    "be in Dutch, English, German or French. Report only what they stated."
)


def dimensions_from_model(text: str) -> dict[str, float] | None:
    """A measurement the regular expressions could not read, through the
    model. Every number it returns is validated here: three positive
    measurements or nothing."""
    from app.services.assistant import runtime

    if unsure(text) or len(re.findall(NUMBER, text)) < 3 or not runtime.installed():
        return None
    result = runtime.extract_json(DIMENSIONS_PROMPT, text, DIMENSIONS_SCHEMA)
    if not result:
        return None
    values: dict[str, float] = {}
    for key in ("length_cm", "width_cm", "height_cm"):
        try:
            value = float(result.get(key))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or not 0 < value <= 100_000:
            return None
        # A vague comparison such as "chest high" supplies no measurement.
        # Conversions are accepted only when the corresponding source number
        # is explicit. The model cannot turn an estimate into measured fact.
        if not any(stated_number(text, value / factor) for factor in (0.1, 1, 100)):
            return None
        values[key] = round(value, 2)
    return values
