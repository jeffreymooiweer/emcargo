"""Conservative readers for shipment facts, shared by intake and follow-ups.

Understanding has an explicit failure path. Ambiguity, negation and a request
for help must never silently become a party name, a quantity or a DG choice.
"""
from __future__ import annotations

import math
import re

UNKNOWN = re.compile(
    r"\b(?:weet\s+(?:ik\s+)?(?:het\s+)?niet|ik\s+weet\s+(?:het\s+)?niet|geen\s+idee|"
    r"onbekend|weet\s+ik\s+nog\s+niet|hoe\s+bedoel|wat\s+betekent|help|"
    r"don.t\s+know|not\s+sure|unknown|what\s+does|not\s+understand|"
    r"weiß\s+(?:ich\s+)?nicht|weiss\s+(?:ich\s+)?nicht|keine\s+ahnung|unbekannt|"
    r"sais\s+pas|aucune\s+idée|inconnu|ne\s+comprends\s+pas)\b", re.I,
)
UNCERTAIN = re.compile(
    r"\b(?:misschien|ongeveer|ofzo|wellicht|vermoedelijk|ik\s+denk|"
    r"maybe|perhaps|approximately|about|roughly|probably|"
    r"vielleicht|ungefähr|etwa|vermutlich|peut-être|environ|probablement)\b|\?", re.I,
)
NEGATED = re.compile(r"\b(?:geen|niet|nee|not|no|neither|kein\w*|nicht|nein|pas|non|sans)\b", re.I)
ALTERNATIVE = re.compile(r"\b(?:of|or|oder|ou)\b|\d\s*[-–/]\s*\d", re.I)
NUMBER = r"(?<![\w.,+\-])\d+(?:[.,]\d+)?(?![\d.,])"
NUMBER_WORDS = {
    "een": 1, "één": 1, "one": 1, "ein": 1, "eine": 1, "un": 1, "une": 1,
    "twee": 2, "two": 2, "zwei": 2, "deux": 2,
    "drie": 3, "three": 3, "drei": 3, "trois": 3,
    "vier": 4, "four": 4, "quatre": 4, "vijf": 5, "five": 5, "fünf": 5, "cinq": 5,
    "zes": 6, "six": 6, "sechs": 6, "zeven": 7, "seven": 7, "sieben": 7, "sept": 7,
    "acht": 8, "eight": 8, "huit": 8, "negen": 9, "nine": 9, "neun": 9, "neuf": 9,
    "tien": 10, "ten": 10, "zehn": 10, "dix": 10,
    "honderd": 100, "hundred": 100, "hundert": 100, "cent": 100,
    "duizend": 1000, "thousand": 1000, "tausend": 1000, "mille": 1000,
}


def unsure(text: str) -> bool:
    return bool(UNKNOWN.search(text) or UNCERTAIN.search(text))


def number(value: str) -> float | None:
    """One unambiguous decimal, without guessing thousands separators."""
    if not re.fullmatch(r"\d+(?:[.,]\d+)?", value.strip()):
        return None
    if re.fullmatch(r"[1-9]\d*[.,]\d{3}", value.strip()):
        return None
    result = float(value.replace(",", "."))
    return result if math.isfinite(result) else None


def stated_number(text: str, value: float) -> bool:
    """The model cannot add a number that no source token actually states."""
    values = [number(m.group()) for m in re.finditer(NUMBER, text)]
    values += [v for w, v in NUMBER_WORDS.items() if re.search(rf"\b{re.escape(w)}\b", text, re.I)]
    return value in values


def grounded(text: str, value: str) -> bool:
    """Every word and digit must appear, in order, in one source span.

    Punctuation and whitespace may change; a shared company word does not
    license a fabricated address or a different reference number.
    """
    tokens = lambda s: re.findall(r"\w+", s.casefold())
    source, candidate = tokens(text), tokens(value)
    return bool(candidate) and any(source[i:i + len(candidate)] == candidate
                                   for i in range(len(source) - len(candidate) + 1))


FIELD_ALIASES = {
    "consignor_address": "adres afzender|afzenderadres|sender address|consignor address|absenderadresse|adresse expéditeur",
    "consignee_address": "adres ontvanger|ontvangeradres|receiver address|consignee address|empfängeradresse|adresse destinataire",
    "consignor_name": "afzender|verzender|sender|consignor|absender|expéditeur",
    "consignee_name": "ontvanger|geadresseerde|receiver|consignee|empfänger|destinataire",
    "carrier_name": "vervoerder|carrier|frachtführer|transporteur",
    "loading_point": "laadplaats|ophalen in|laden in|loading point|pickup|ladeort|lieu de chargement",
    "discharge_point": "losplaats|afleveren in|lossen in|discharge point|delivery|entladeort|lieu de déchargement",
    "loading_date": "laaddatum|loading date|ladedatum|date de chargement",
    "shipment_reference": "referentie|reference|referenz|référence",
    "booking_number": "boekingsnummer|booking number|buchungsnummer|numéro de réservation",
    "purchase_order": "ordernummer|purchase order|bestellnummer|numéro de commande",
}
_ALIAS_FIELD = {alias: field for field, aliases in FIELD_ALIASES.items() for alias in aliases.split("|")}
_FACT_START = re.compile(
    r"(?<!\w)(?:(?:de|the|der|die|le|la)\s+)?(?P<label>" + "|".join(re.escape(k) for k in sorted(_ALIAS_FIELD, key=len, reverse=True))
    + r")\s*(?::|=|\bis\b|\bist\b|\best\b)\s*", re.I,
)


def labelled_facts(text: str) -> tuple[dict[str, str], str]:
    """Several explicitly named fields, with the unused prefix returned.

    A comma inside an address is not a separator. Labels provide the field
    identity; a bare company or town remains the current question's answer.
    """
    matches = list(_FACT_START.finditer(text))
    if not matches:
        return {}, text
    fields: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[match.end():end].strip(" ;,\n.")
        value = re.sub(r"\s+(?:en|and|und|et)$", "", value, flags=re.I).strip(" ;,\n")
        field = _ALIAS_FIELD[match.group("label").casefold()]
        if not value or field in fields or UNKNOWN.search(value):
            return {}, text
        fields[field] = value
    prefix = text[:matches[0].start()].strip(" ;,\n.")
    prefix = re.sub(r"^(?:correctie|correction|wijzig|verander|change|korrektur)\s*:?\s*", "", prefix, flags=re.I)
    return fields, prefix
