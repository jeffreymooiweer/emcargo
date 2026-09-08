"""The dangerous goods notification: IFTDGN, UN/EDIFACT D.16A.

The message a party responsible for declaring dangerous goods sends to the
one that checks them — a port authority, a terminal, a carrier's agent —
about one conveyance of one means of transport. Port community systems
speak it; a forwarder that gets one re-keys nothing. The structure is that
of the UN/EDIFACT D.16A directory, revision 8 of the message, which
``config/iftdgn_d16a.json`` holds and this module writes to.

**What is filled in, and from where.** The same parts the structured export
is built from — the document fields, the goods lines, the dangerous goods
entries — and nothing else: BGM with the shipment reference, DTM with the
issue moment, TDT with the mode and the vehicle, NAD for the consignor,
the carrier and the forwarder, EQD for a container, one CNI consignment
with its place of loading and of discharge, and per dangerous product a
GID goods item with a DGS segment carrying the regulation, the class, the
UN number, the packing group, the hazard identification number, the
labels, the tunnel code and the EmS, the technical name in FTX, the mass in
MEA and the container in SGP.

**What is not invented.** A field the user left empty is absent from the
message. The consignee is not among the parties IFTDGN names for a
consignment (the specification lists the consignor and either the carrier's
agent or the forwarder) and is left out rather than squeezed in under a
function the message did not mean. The interchange envelope (UNB/UNZ)
names the consignor as sender and the carrier or forwarder as recipient
where those are known, and a marked placeholder where they are not: the EDI
gateway that sends the message owns those identifiers, not this
application. Package types travel as text (7064), not as a Recommendation
21 code, until that Recommendation has been read.

**What is checked.** Before a message is handed out it is parsed back and
checked against the segment table: every mandatory segment and group
present, no repeat count exceeded, nothing out of order. A message that
fails is not written — a notification that is malformed is worse than one
that is missing, because the receiver will act on what it can parse.
"""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.edifact.syntax import Segment, parse, validate, write
from app.services.quantities import positive_number

_CONFIG = Path(__file__).resolve().parents[2] / "config" / "iftdgn_d16a.json"
_lock = threading.Lock()
_cache: dict[str, Any] = {}

#: The dangerous goods regulations code (8273) per EMCargo profile. The
#: D.16A list has no code for ADN — ADNR's is a different agreement — so ADN
#: travels as "mutually defined" and says so in the additional information.
REGULATION_CODES = {"ADR": "ADR", "RID": "RID", "IMDG": "IMD", "IATA": "ICA", "ADN": "ZZZ"}

#: UN/ECE Recommendation 19 mode codes, per EMCargo modality.
MODE_CODES = {"road": "3", "rail": "2", "sea": "1", "inland": "8", "air": "4"}

#: Which regime a modality's DGS segment reports when several profiles apply.
MODALITY_REGIME = {"road": "ADR", "rail": "RID", "sea": "IMDG", "inland": "ADN", "air": "IATA"}

PACKING_GROUP_CODES = {"I": "1", "II": "2", "III": "3"}

#: What the sender and recipient identifiers say when nothing is known.
#: Marked, so that a gateway operator sees at once what is theirs to fill.
PLACEHOLDER_SENDER = "SENDER"
PLACEHOLDER_RECIPIENT = "RECIPIENT"


def config() -> dict[str, Any]:
    with _lock:
        if "config" not in _cache:
            _cache["config"] = json.loads(_CONFIG.read_text(encoding="utf-8"))
        return _cache["config"]


class NothingToNotify(ValueError):
    """A shipment without dangerous goods has no IFTDGN."""


# --- helpers -------------------------------------------------------------------


def _s(value: Any, limit: int | None = None) -> str:
    """A value as the message can carry it: one line, ISO 8859-1.

    UNOC is ISO 8859-1. A character outside it is replaced *here*, before
    the syntax layer releases the service characters — replacing it after,
    as the first release did, turned an emoji into a bare ``?``, which is
    the release character itself, and the segment read back wrong.
    """
    text = "" if value is None else str(value).strip()
    text = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", text))
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text[:limit] if limit else text


def _lines(block: str, width: int, count: int) -> list[str]:
    """A free-text address block as up to ``count`` lines of ``width``."""
    out: list[str] = []
    for line in re.split(r"[\r\n]+|,\s*", str(block or "")):
        line = _s(line)
        while line and len(out) < count:
            out.append(line[:width])
            line = line[width:]
    return out[:count]


def _number(value: Any) -> float | None:
    """The quantity in a string ("800 kg", "1.250,5 L") when it is one and
    greater than zero. What is not — "abc", "-5 L", "1.2.3" — is left out of
    the message and named by :func:`problems`, never written as a guess."""
    return positive_number(value)


def _un(value: Any) -> str:
    """The UN number as four digits, or nothing when it is not one.

    "UN 1203", "1203" and "un1203" are 1203; "abc" and "12" are nothing.
    The first release padded whatever digits it found to four, which made
    "abc" into UN 0000 — a number that does not exist, sent as fact.
    """
    text = re.sub(r"^\s*UN\s*", "", _s(value), flags=re.IGNORECASE)
    return text if re.fullmatch(r"\d{4}", text) else ""


def _unit(value: Any) -> str:
    text = _s(value).lower()
    if re.search(r"\b(l|ltr|liter|litre|liters|litres)\b", text):
        return "LTR"
    if re.search(r"\b(kg|kilo|kilogram|kilograms)\b", text):
        return "KGM"
    return ""


def _measure(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.3f}".rstrip("0").rstrip(".")


def _codes(value: Any) -> list[str]:
    return [c for c in re.split(r"[+,/;\s]+", _s(value)) if c]


def _flashpoint(value: Any) -> str:
    """The flashpoint as a whole number of degrees, n3, or nothing."""
    m = re.search(r"-?\d+", _s(value))
    if not m:
        return ""
    degrees = int(m.group(0))
    return str(degrees) if -99 <= degrees <= 999 else ""


def _reference(values: dict[str, Any]) -> str:
    return _s(values.get("shipment_reference") or values.get("reference"), 70)


# --- the message ---------------------------------------------------------------


def build_segments(values: dict[str, Any], lines: list[dict[str, Any]],
                   dangerous_goods: list[dict[str, Any]] | None, *,
                   profiles: list[str] | None = None, modality: str | None = None,
                   now: datetime | None = None, reference: str = "1") -> list[Segment]:
    """The message UNH..UNT as segments, from the shipment's parts."""
    products = [(entry, product) for entry in (dangerous_goods or [])
                for product in (entry.get("products") or [])]
    if not products:
        raise NothingToNotify("The shipment carries no dangerous goods; there is nothing to notify.")

    regimes = [str(p).strip().upper() for p in (profiles or []) if str(p).strip()]
    regime = MODALITY_REGIME.get(modality or "", "")
    if regime not in regimes:
        regime = regimes[0] if regimes else ""
    moment = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M")
    ref = _reference(values)

    segments: list[Segment] = [
        Segment("UNH", [reference, ["IFTDGN", "D", "16A", "UN"]]),
        Segment("BGM", [["890"], [ref], "9"]),
        Segment("DTM", [["137", moment, "203"]]),
    ]

    # SG2: the main carriage, when the mode or the vehicle is known.
    vehicle = _s(values.get("vessel_name") or values.get("vehicle_registration")
                 or values.get("wagon_number") or values.get("vessel_flight"), 70)
    mode = MODE_CODES.get(modality or "", "")
    if mode or vehicle:
        segments.append(Segment("TDT", ["20", "", [mode], "", "", "", "", ["", "", "", vehicle]]))

    # SG4: the parties relevant to the whole message — the carrier and the
    # forwarder, who receive the notification or send it on.
    for function, name_key, address_key in (("CA", "carrier_name", "carrier_address"),
                                            ("FW", "freight_forwarder", "")):
        segments.extend(_party(function, values.get(name_key), values.get(address_key)))

    # SG6: the equipment the goods travel in.
    container = _s(values.get("container_number"), 17)
    if container:
        segments.append(Segment("EQD", ["CN", [container]]))

    # SG7: the one consignment.
    segments.append(Segment("CNI", ["1", [ref]]))
    for qualifier, key in (("9", "loading_point"), ("11", "discharge_point")):
        place = _s(values.get(key), 256)
        if place:
            segments.append(Segment("LOC", [qualifier, ["", "", "", place]]))
    # SG10: the consignor, as the specification names for the consignment.
    segments.extend(_party("CZ", values.get("consignor_name"), values.get("consignor_address")))

    # SG12: one goods item per dangerous product.
    for index, (entry, product) in enumerate(products, start=1):
        segments.extend(_goods_item(index, entry, product, regime, container))

    segments.append(Segment("UNT", [str(len(segments) + 1), reference]))
    return segments


def _party(function: str, name: Any, address: Any) -> list[Segment]:
    name = _s(name, 70)
    if not name:
        return []
    address_lines = _lines(str(address or ""), 35, 5)
    return [Segment("NAD", [function, "", address_lines, [name]])]


def _goods_item(index: int, entry: dict[str, Any], product: dict[str, Any],
                regime: str, container: str) -> list[Segment]:
    packages = _number(product.get("quantity_packages"))
    package_type = _s(product.get("type_of_package"), 35)
    quantity = _measure(packages) if packages is not None else ""
    segments = [Segment("GID", [str(index), [quantity, "", "", "", package_type]])]

    description = _s(product.get("chosen_name") or product.get("proper_shipping_name"), 512)
    if description:
        segments.append(Segment("FTX", ["AAA", "", "", [description]]))

    segments.append(_dgs(product, regime))

    technical = _s(product.get("technical_name") or product.get("chosen_name")
                   or product.get("proper_shipping_name") or f"UN {_un(product.get('un_number'))}", 512)
    segments.append(Segment("FTX", ["AAD", "", "", [technical]]))
    additional = _additional(product, regime)
    if additional:
        segments.append(Segment("FTX", ["AAC", "", "", additional[:5]]))

    segments.extend(_masses(product))

    item_container = _s(product.get("container_number"), 17) or container
    if item_container:
        segments.append(Segment("SGP", [[item_container], quantity]))
    return segments


def _dgs(product: dict[str, Any], regime: str) -> Segment:
    subsidiary = _codes(product.get("subsidiary_risks"))
    un = _un(product.get("un_number"))
    flash = _flashpoint(product.get("flashpoint"))
    labels = _codes(product.get("labels"))[:4]
    tunnel = _s(product.get("tunnel_code")).strip("()")[:6]
    hin = _s(product.get("hazard_number"), 4)
    return Segment("DGS", [
        REGULATION_CODES.get(regime, "ZZZ") if regime else "",
        [_s(product.get("class"), 7), subsidiary[0][:7] if subsidiary else ""],
        [un],
        [flash, "CEL" if flash else ""],
        PACKING_GROUP_CODES.get(_s(product.get("packing_group")).upper(), ""),
        _s(product.get("ems_code"), 8).replace(" ", ""),
        "",
        "",
        [hin, un if hin else ""],
        [label[:4] for label in labels],
        "",
        "",
        "",
        [tunnel],
    ])


def _additional(product: dict[str, Any], regime: str) -> list[str]:
    """What the receiver must know beyond the codes, as short statements."""
    notes: list[str] = []
    if regime == "ADN":
        notes.append("ADN")
    if _s(product.get("marine_pollutant")).lower() in ("yes", "ja", "true", "1", "oui"):
        notes.append("MARINE POLLUTANT")
    # No LIMITED QUANTITY statement: the ``limited_quantity`` field holds
    # column 7a of Table A — the quantity per package *up to which* 3.4
    # applies — not whether this consignment travels under it. The first
    # release wrote the statement whenever the column was filled, which
    # declared nearly every consignment a limited quantity one.
    if _s(product.get("empty_uncleaned")).lower() in ("yes", "ja", "true", "1", "oui"):
        notes.append("EMPTY UNCLEANED")
    if _s(product.get("is_waste")).lower() in ("yes", "ja", "true", "1", "oui"):
        notes.append("WASTE")
    control = _s(product.get("control_temperature"))
    if control:
        notes.append(f"CONTROL TEMPERATURE {control}"[:512])
    extra = _s(product.get("additional_information"), 512)
    if extra:
        notes.append(extra)
    return notes


#: The fields a quantity is read from, with the name the problem list uses.
QUANTITY_FIELDS = ("quantity_packages", "gross_mass_per_package",
                   "adr_total_quantity", "net_mass_liters_per_package")


def _masses(product: dict[str, Any]) -> list[Segment]:
    """Gross and net, as far as they are known; the message wants at least one.

    The gross is per package times the packages. The net is the ADR total
    quantity as given; failing that, the net per package times the packages
    — a per-package figure written as the item's total, as the first
    release did, understated the consignment by the number of packages.
    """
    segments: list[Segment] = []
    packages = _number(product.get("quantity_packages"))
    gross_each = _number(product.get("gross_mass_per_package"))
    if gross_each is not None and packages is not None:
        segments.append(Segment("MEA", ["AAE", ["AAB"], ["KGM", _measure(gross_each * packages)]]))
    total = product.get("adr_total_quantity")
    net, unit = _number(total), _unit(total)
    if net is None or not unit:
        each = product.get("net_mass_liters_per_package")
        net_each, unit = _number(each), _unit(each)
        net = net_each * packages if net_each is not None and packages is not None else None
    if net is not None and unit:
        segments.append(Segment("MEA", ["AAE", ["AAF"], [unit, _measure(net)]]))
    return segments


# --- the interchange -----------------------------------------------------------


def _party_id(value: Any, fallback: str) -> str:
    return _s(value, 35) or fallback


def build_interchange(values: dict[str, Any], lines: list[dict[str, Any]],
                      dangerous_goods: list[dict[str, Any]] | None, *,
                      profiles: list[str] | None = None, modality: str | None = None,
                      now: datetime | None = None) -> str:
    """The whole interchange as text: UNA, UNB, the message, UNZ."""
    moment = now or datetime.now(timezone.utc)
    message = build_segments(values, lines, dangerous_goods, profiles=profiles,
                             modality=modality, now=moment, reference="1")
    problems = validate(message, config()["structure"])
    if problems:  # pragma: no cover - the builder is written to the table
        raise ValueError("The IFTDGN message does not conform: " + "; ".join(problems))
    control = moment.strftime("%Y%m%d%H%M%S")
    sender = _party_id(values.get("consignor_name"), PLACEHOLDER_SENDER)
    recipient = _party_id(values.get("carrier_name") or values.get("freight_forwarder"),
                          PLACEHOLDER_RECIPIENT)
    interchange = [
        Segment("UNB", [["UNOC", "3"], [sender], [recipient],
                        [moment.strftime("%y%m%d"), moment.strftime("%H%M")], control]),
        *message,
        Segment("UNZ", ["1", control]),
    ]
    return write(interchange)


def problems(values: dict[str, Any], dangerous_goods: list[dict[str, Any]] | None,
             language: str = "nl") -> list[str]:
    """What keeps a shipment from being notified, in the user's language.

    Called by the document validation before the export: the message needs a
    UN number and a class per product and at least one mass or quantity, and
    a shipment without dangerous goods has nothing to notify.
    """
    lang = language if language in _TEXTS["no_dangerous_goods"] else "en"
    products = [(entry, product) for entry in (dangerous_goods or [])
                for product in (entry.get("products") or [])]
    if not products:
        return [_TEXTS["no_dangerous_goods"][lang]]
    found: list[str] = []
    for index, (_entry, product) in enumerate(products, start=1):
        given, un = _s(product.get("un_number")), _un(product.get("un_number"))
        label = f"UN {un}" if un else f"#{index}"
        if not given:
            found.append(_TEXTS["no_un_number"][lang].format(item=label))
        elif not un:
            found.append(_TEXTS["bad_un_number"][lang].format(item=label, value=given))
        if not _s(product.get("class")):
            found.append(_TEXTS["no_class"][lang].format(item=label))
        for field in QUANTITY_FIELDS:
            value = _s(product.get(field))
            if value and _number(value) is None:
                found.append(_TEXTS["bad_quantity"][lang].format(item=label, value=value))
        if not _masses(product):
            found.append(_TEXTS["no_mass"][lang].format(item=label))
    return found


_TEXTS = {
    "no_dangerous_goods": {
        "nl": "De zending bevat geen gevaarlijke stoffen; er is niets te melden met een IFTDGN.",
        "en": "The shipment carries no dangerous goods; there is nothing to notify with an IFTDGN.",
        "de": "Die Sendung enthält keine gefährlichen Güter; mit einer IFTDGN gibt es nichts zu melden.",
        "fr": "L'expédition ne contient pas de marchandises dangereuses ; il n'y a rien à notifier par IFTDGN.",
    },
    "no_un_number": {
        "nl": "IFTDGN: positie {item} heeft geen UN-nummer.",
        "en": "IFTDGN: item {item} has no UN number.",
        "de": "IFTDGN: Position {item} hat keine UN-Nummer.",
        "fr": "IFTDGN : la position {item} n'a pas de numéro ONU.",
    },
    "bad_un_number": {
        "nl": "IFTDGN: positie {item} heeft een UN-nummer dat geen vier cijfers is ({value}).",
        "en": "IFTDGN: item {item} has a UN number that is not four digits ({value}).",
        "de": "IFTDGN: Position {item} hat eine UN-Nummer, die nicht aus vier Ziffern besteht ({value}).",
        "fr": "IFTDGN : la position {item} a un numéro ONU qui n'est pas à quatre chiffres ({value}).",
    },
    "bad_quantity": {
        "nl": "IFTDGN: {item} heeft een hoeveelheid die geen getal groter dan nul is ({value}).",
        "en": "IFTDGN: {item} has a quantity that is not a number greater than zero ({value}).",
        "de": "IFTDGN: {item} hat eine Menge, die keine Zahl größer als null ist ({value}).",
        "fr": "IFTDGN : {item} a une quantité qui n'est pas un nombre supérieur à zéro ({value}).",
    },
    "no_class": {
        "nl": "IFTDGN: {item} heeft geen klasse.",
        "en": "IFTDGN: {item} has no class.",
        "de": "IFTDGN: {item} hat keine Klasse.",
        "fr": "IFTDGN : {item} n'a pas de classe.",
    },
    "no_mass": {
        "nl": "IFTDGN: {item} heeft geen massa of hoeveelheid (bruto per collo en aantal colli, of de totale hoeveelheid met eenheid).",
        "en": "IFTDGN: {item} has no mass or quantity (gross per package and number of packages, or the total quantity with its unit).",
        "de": "IFTDGN: {item} hat keine Masse oder Menge (brutto je Versandstück und Anzahl, oder die Gesamtmenge mit Einheit).",
        "fr": "IFTDGN : {item} n'a ni masse ni quantité (brut par colis et nombre de colis, ou la quantité totale avec son unité).",
    },
}


def read_back(text: str) -> list[Segment]:
    """The segments of a written interchange, for whoever checks one."""
    return parse(text)
