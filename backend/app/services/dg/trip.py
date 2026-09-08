"""Several consignments on one vehicle, judged as one load.

Everything else in EMCargo reasons about a consignment, because a consignment
is what somebody fills in. The ADR does not look at anybody's administration; it
looks at what is physically on the vehicle. Three rules are therefore decided
over the whole load and cannot be decided per consignment, however carefully
each one is filled in:

* **1.1.3.6** counts points per transport unit. Two consignments that each stay
  under the 1000 can pass it together — and the moment they do, the whole load
  needs orange plates, a driver with an ADR certificate and the equipment of
  8.1.5. Each consignment on its own reports "exempt"; the vehicle is not.
* **7.5.2** forbids certain classes from travelling together. Within one
  consignment that is already checked. Between two consignments from different
  customers nobody was checking it at all.
* **3.4.13/3.4.14** put the limited-quantities mark on the transport unit, and
  both of their conditions are about the unit rather than the consignment.

So this module adds exactly one thing: the level above the consignment. It
computes nothing regulatory of its own — it hands the *union* of the entries to
the checks that already exist, because that is what those checks were always
measuring. What it adds is the comparison: what each consignment said alone,
beside what they say together.

**A trip is not stored.** An installation without a shipment history keeps
nothing about shipments, so a trip that landed in the database would break the
promise the rest of the application keeps. It is assembled from what the caller
sends, judged, and forgotten. That is also why there is no trip id, no history
and nothing to retrieve: this module is a calculation, not an entity. Whether
an installation that does keep its shipments keeps the trip as well is that
phase's question, not this module's.
"""
from __future__ import annotations

import copy
from typing import Any

from app.core.languages import pick
from app.services.dg.compliance import (
    check_adr_mixed_loading,
    check_adr_points,
    check_lq_eq,
)

#: The 1.1.3.6 statuses that mean the load is *not* travelling under the
#: exemption, and therefore carries orange plates under 5.3.2. Named here
#: because two provisions turn on it: whether the exemption was lost by
#: combining, and whether 3.4.13's orange-plate exception applies.
_NOT_EXEMPT_STATUSES = frozenset({
    "above_threshold", "not_exempt", "not_available_for_mode"})

#: ADR 3.4.13: the marking is required on transport units whose **maximum mass**
#: exceeds this. It is a property of the vehicle, not of the cargo — which is
#: why a consignment on its own can never decide it and this module asks.
UNIT_MAX_MASS_TRIGGER_T = 12.0

#: ADR 3.4.14: the marking of 3.4.13 may be dispensed with while the total gross
#: mass of the limited-quantity packages carried stays at or under this, per
#: transport unit. A property of the cargo, and therefore the one number that
#: only becomes true over the whole load.
LQ_DISPENSATION_T = 8.0


def _labelled(consignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every consignment's entries, tagged with the consignment they came from.

    The tag is what makes a trip-level warning actionable. Two customers both
    shipping UN 1263 produce two identically named positions, and "these two may
    not travel together" is useless if the reader cannot tell which pallet to
    take off. ``_product_label`` picks the tag up when it is there and is
    unchanged without it, so a single consignment reads exactly as before.
    """
    flat: list[dict[str, Any]] = []
    for index, consignment in enumerate(consignments):
        name = str(consignment.get("name") or "").strip() or f"#{index + 1}"
        for entry in consignment.get("entries") or []:
            # Copied, because tagging is this module's business and the caller's
            # consignment must come back out of it exactly as it went in.
            tagged = copy.deepcopy(entry)
            tagged["consignment"] = name
            flat.append(tagged)
    return flat


def _points_total(result: dict[str, Any]) -> float | None:
    value = result.get("total_points")
    return float(value) if isinstance(value, (int, float)) else None


def _exempt(result: dict[str, Any]) -> bool | None:
    """Whether 1.1.3.6 is available, read from the status the check reports.

    Three-valued on purpose. ``incomplete`` is not "no": it is "you have not
    told me enough yet", and rendering that as a refusal would send somebody
    fitting orange plates they may not need.

    With one exception, and it matters on a trip more than anywhere else. A
    total already past the threshold is past it whatever is still missing —
    unstated quantities can only add points, never remove them. Reading that
    as "unknown" is how a load of 1500 points on three consignments, one of
    which has a blank field, comes back as undecided.
    """
    status = str(result.get("status") or "")
    if status in _NOT_EXEMPT_STATUSES:
        return False
    total = result.get("total_points")
    threshold = result.get("threshold")
    if isinstance(total, (int, float)) and isinstance(threshold, (int, float)) \
            and total > threshold:
        return False
    if status == "exempt_possible":
        return True
    return None


def check_trip(
    consignments: list[dict[str, Any]],
    profiles: list[str] | None = None,
    language: str = "nl",
    unit_max_mass_tonnes: float | None = None,
) -> dict[str, Any]:
    """Judge the whole load, and say what changed by combining it.

    ``consignments`` is a list of ``{"name": str, "entries": [...]}``. The
    entries are the same dangerous goods entries every other check receives.
    """
    profiles = list(profiles or [])
    flat = _labelled(consignments)

    together_points = check_adr_points(flat, language, profiles)
    mixed_loading = check_adr_mixed_loading(flat, language, profiles)
    lq = check_lq_eq(flat, language, profiles)

    # What each consignment said on its own, so the screen can show the step.
    # This is the finding, not a detail: "each one exempt, the load not" is the
    # sentence somebody loads a vehicle wrongly for want of.
    apart: list[dict[str, Any]] = []
    for index, consignment in enumerate(consignments):
        name = str(consignment.get("name") or "").strip() or f"#{index + 1}"
        alone = check_adr_points(consignment.get("entries") or [], language, profiles)
        apart.append({
            "name": name,
            "points": _points_total(alone),
            "exempt": _exempt(alone),
            "status": alone.get("status"),
        })

    return {
        "consignments": apart,
        "adr_points": together_points,
        "mixed_loading": mixed_loading,
        "lq_eq": lq,
        "lq_marking": _lq_marking(lq, together_points, unit_max_mass_tonnes, language),
        "exemption_lost": _exemption_lost(apart, together_points, language),
    }


def _exemption_lost(
    apart: list[dict[str, Any]], together: dict[str, Any], language: str
) -> dict[str, Any] | None:
    """The one finding a per-consignment check can never produce.

    Every consignment exempt under 1.1.3.6, the load not. Reported separately
    from the points table because it is the reason this screen exists, and
    because the table alone states a total without saying what it costs.
    """
    if _exempt(together) is not False:
        return None
    exempt_apart = [c for c in apart if c.get("exempt") is True]
    if len(exempt_apart) < 2 or len(exempt_apart) != len(apart):
        return None
    return {
        "severity": "warning",
        "rule": "ADR 1.1.3.6",
        "consignments": [c["name"] for c in exempt_apart],
        "message": pick(
            {
                "nl": "Elke zending blijft afzonderlijk onder de 1000 punten, maar "
                      "samen op één transporteenheid niet ({total}). De vrijstelling "
                      "van 1.1.3.6 vervalt daarmee voor de hele lading: oranje borden, "
                      "een ADR-gecertificeerde chauffeur en de uitrusting van 8.1.5 "
                      "gelden dan voor alles wat er op staat.",
                "en": "Each consignment stays under the 1000 points on its own, but "
                      "not together on one transport unit ({total}). The 1.1.3.6 "
                      "exemption falls away for the whole load: orange plates, an "
                      "ADR-certified driver and the equipment of 8.1.5 then apply to "
                      "everything on board.",
                "de": "Jede Sendung bleibt für sich unter den 1000 Punkten, zusammen "
                      "auf einer Beförderungseinheit jedoch nicht ({total}). Die "
                      "Freistellung nach 1.1.3.6 entfällt damit für die gesamte "
                      "Ladung: orangefarbene Tafeln, ein ADR-bescheinigter Fahrer und "
                      "die Ausrüstung nach 8.1.5 gelten dann für alles an Bord.",
                "fr": "Chaque envoi reste seul sous les 1000 points, mais pas "
                      "ensemble sur une même unité de transport ({total}). "
                      "L'exemption du 1.1.3.6 disparaît alors pour tout le "
                      "chargement : panneaux orange, conducteur titulaire du "
                      "certificat ADR et équipement du 8.1.5 s'appliquent à tout ce "
                      "qui est à bord.",
            },
            language,
        ).format(total=_fmt(together.get("total_points"))),
    }


def _fmt(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "?"
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _lq_marking(
    lq: dict[str, Any],
    points: dict[str, Any],
    unit_max_mass_tonnes: float | None,
    language: str,
) -> dict[str, Any]:
    """ADR 3.4.13 and 3.4.14, which only a whole load can answer.

    Three separate quantities, and they are easy to run together — the
    consignment-level check did exactly that until this phase:

    * **12 tonnes** is the *maximum mass of the transport unit* (3.4.13). It is
      a property of the vehicle. Below it the marking is not required at all,
      whatever the cargo weighs, and no consignment carries that number.
    * **8 tonnes** is the *total gross mass of the limited-quantity packages*
      (3.4.14). Above it the dispensation stops; it never creates a
      requirement by itself.
    * **The orange plates** of 5.3.2 are an exception in their own right: a unit
      already displaying them because of other dangerous goods need not carry
      the limited-quantities mark. In groupage that is the common case, and it
      is decidable only over the whole load — which is the point of this
      module.
    """
    gross_kg = float(lq.get("lq_gross_total_kg") or 0.0)
    over_dispensation = gross_kg > LQ_DISPENSATION_T * 1000.0
    # Three-valued: the load carries orange plates when 1.1.3.6 is lost, does
    # not when it holds, and is undecided while the points check is still
    # missing quantities.
    plates = _exempt(points)
    plates = None if plates is None else not plates

    if unit_max_mass_tonnes is None:
        decided, reason = None, "unit_mass_unknown"
    elif unit_max_mass_tonnes <= UNIT_MAX_MASS_TRIGGER_T:
        decided, reason = False, "unit_at_or_below_12t"
    elif not over_dispensation:
        decided, reason = False, "within_8t_dispensation"
    elif plates is True:
        decided, reason = False, "orange_plates_instead"
    elif plates is None:
        # Both conditions of 3.4.13 are met, and the one thing that could still
        # excuse the mark cannot be settled. Saying "required" flatly would be
        # a certainty this does not have; saying nothing would leave the load
        # unmarked. So it says: required unless the plates turn out to be there.
        decided, reason = None, "required_unless_plates"
    else:
        decided, reason = True, "required"

    return {
        "rule": "ADR 3.4.13/3.4.14",
        "lq_gross_kg": gross_kg,
        "over_dispensation": over_dispensation,
        "unit_max_mass_tonnes": unit_max_mass_tonnes,
        "orange_plates_required": plates,
        "required": decided,
        "reason": reason,
        "message": _lq_message(reason, gross_kg, language),
    }


def _lq_message(reason: str, gross_kg: float, language: str) -> str:
    texts = {
        "unit_mass_unknown": {
            "nl": "De LQ-colli wegen samen {kg} kg bruto. Of de LQ-kenmerking van "
                  "3.4.15 verplicht is hangt af van de toegestane maximummassa van de "
                  "transporteenheid: 3.4.13 geldt pas boven 12 ton. Vul die massa in "
                  "om dit te laten beoordelen.",
            "en": "The LQ packages weigh {kg} kg gross together. Whether the mark of "
                  "3.4.15 is required depends on the permitted maximum mass of the "
                  "transport unit: 3.4.13 applies only above 12 tonnes. Fill in that "
                  "mass to have this assessed.",
            "de": "Die LQ-Versandstücke wiegen zusammen {kg} kg brutto. Ob die "
                  "Kennzeichnung nach 3.4.15 vorgeschrieben ist, hängt von der "
                  "zulässigen Höchstmasse der Beförderungseinheit ab: 3.4.13 gilt erst "
                  "über 12 Tonnen. Tragen Sie diese Masse ein, damit dies beurteilt "
                  "werden kann.",
            "fr": "Les colis QL pèsent ensemble {kg} kg bruts. Le caractère "
                  "obligatoire de la marque du 3.4.15 dépend de la masse maximale "
                  "admissible de l'unité de transport : le 3.4.13 ne s'applique "
                  "qu'au-dessus de 12 tonnes. Renseignez cette masse pour que cela "
                  "soit apprécié.",
        },
        "unit_at_or_below_12t": {
            "nl": "De transporteenheid blijft op of onder 12 ton toegestane "
                  "maximummassa, dus 3.4.13 geldt niet en de LQ-kenmerking op de "
                  "eenheid is niet vereist.",
            "en": "The transport unit stays at or below 12 tonnes permitted maximum "
                  "mass, so 3.4.13 does not apply and the mark on the unit is not "
                  "required.",
            "de": "Die Beförderungseinheit bleibt bei oder unter 12 Tonnen zulässiger "
                  "Höchstmasse, daher gilt 3.4.13 nicht und die Kennzeichnung an der "
                  "Einheit ist nicht vorgeschrieben.",
            "fr": "L'unité de transport reste à 12 tonnes de masse maximale "
                  "admissible ou en dessous ; le 3.4.13 ne s'applique donc pas et la "
                  "marque sur l'unité n'est pas exigée.",
        },
        "within_8t_dispensation": {
            "nl": "De LQ-colli wegen samen {kg} kg bruto en blijven daarmee onder de "
                  "8 ton per transporteenheid: de kenmerking van 3.4.13 mag op grond "
                  "van 3.4.14 achterwege blijven.",
            "en": "The LQ packages total {kg} kg gross and so stay under the 8 tonnes "
                  "per transport unit: the marking of 3.4.13 may be dispensed with "
                  "under 3.4.14.",
            "de": "Die LQ-Versandstücke wiegen zusammen {kg} kg brutto und bleiben "
                  "damit unter den 8 Tonnen je Beförderungseinheit: die Kennzeichnung "
                  "nach 3.4.13 darf nach 3.4.14 entfallen.",
            "fr": "Les colis QL totalisent {kg} kg bruts et restent donc sous les "
                  "8 tonnes par unité de transport : la marque du 3.4.13 peut être "
                  "omise en vertu du 3.4.14.",
        },
        "orange_plates_instead": {
            "nl": "De LQ-colli wegen samen {kg} kg bruto, boven de 8 ton van 3.4.14. "
                  "De eenheid voert echter al oranje borden voor de overige "
                  "gevaarlijke goederen, en dan hoeft de LQ-kenmerking volgens 3.4.13 "
                  "niet: de borden alleen mag, beide mag ook.",
            "en": "The LQ packages total {kg} kg gross, above the 8 tonnes of 3.4.14. "
                  "The unit already carries orange plates for the other dangerous "
                  "goods, and 3.4.13 then does not require the LQ mark: the plates "
                  "alone are permitted, as are both.",
            "de": "Die LQ-Versandstücke wiegen zusammen {kg} kg brutto, über den "
                  "8 Tonnen des 3.4.14. Die Einheit führt jedoch bereits "
                  "orangefarbene Tafeln für die übrigen gefährlichen Güter; dann "
                  "verlangt 3.4.13 die LQ-Kennzeichnung nicht: die Tafeln allein sind "
                  "zulässig, beides ebenfalls.",
            "fr": "Les colis QL totalisent {kg} kg bruts, au-delà des 8 tonnes du "
                  "3.4.14. L'unité porte cependant déjà des panneaux orange pour les "
                  "autres marchandises dangereuses ; le 3.4.13 n'exige alors pas la "
                  "marque QL : les panneaux seuls sont admis, les deux également.",
        },
        "required_unless_plates": {
            "nl": "De LQ-colli wegen samen {kg} kg bruto, boven de 8 ton van 3.4.14, "
                  "op een transporteenheid van meer dan 12 ton: de LQ-kenmerking van "
                  "3.4.15 is vereist, tenzij de eenheid al oranje borden voert voor "
                  "andere gevaarlijke goederen. Of dat zo is, is nu niet vast te "
                  "stellen — de puntentelling van 1.1.3.6 mist nog hoeveelheden. Vul "
                  "die aan, of ga uit van het merk.",
            "en": "The LQ packages total {kg} kg gross, above the 8 tonnes of 3.4.14, "
                  "on a transport unit over 12 tonnes: the mark of 3.4.15 is "
                  "required, unless the unit already carries orange plates for other "
                  "dangerous goods. Whether it does cannot be settled here — the "
                  "1.1.3.6 points calculation is still missing quantities. Complete "
                  "them, or assume the mark.",
            "de": "Die LQ-Versandstücke wiegen zusammen {kg} kg brutto, über den "
                  "8 Tonnen des 3.4.14, auf einer Beförderungseinheit über 12 Tonnen: "
                  "die Kennzeichnung nach 3.4.15 ist vorgeschrieben, es sei denn, die "
                  "Einheit führt bereits orangefarbene Tafeln für andere gefährliche "
                  "Güter. Ob das der Fall ist, lässt sich hier nicht feststellen — "
                  "der Punkteberechnung nach 1.1.3.6 fehlen noch Mengen. Ergänzen Sie "
                  "diese, oder gehen Sie vom Kennzeichen aus.",
            "fr": "Les colis QL totalisent {kg} kg bruts, au-delà des 8 tonnes du "
                  "3.4.14, sur une unité de transport de plus de 12 tonnes : la "
                  "marque du 3.4.15 est exigée, sauf si l'unité porte déjà des "
                  "panneaux orange pour d'autres marchandises dangereuses. Cela ne "
                  "peut être établi ici — il manque encore des quantités au calcul "
                  "des points du 1.1.3.6. Complétez-les, ou retenez la marque.",
        },
        "required": {
            "nl": "De LQ-colli wegen samen {kg} kg bruto, boven de 8 ton van 3.4.14, "
                  "op een transporteenheid van meer dan 12 ton die geen oranje borden "
                  "voert. De LQ-kenmerking van 3.4.15 (250 × 250 mm) is dan voor en "
                  "achter vereist; op een container op alle vier de zijden.",
            "en": "The LQ packages total {kg} kg gross, above the 8 tonnes of 3.4.14, "
                  "on a transport unit over 12 tonnes that carries no orange plates. "
                  "The mark of 3.4.15 (250 × 250 mm) is then required at the front "
                  "and rear; on a container, on all four sides.",
            "de": "Die LQ-Versandstücke wiegen zusammen {kg} kg brutto, über den "
                  "8 Tonnen des 3.4.14, auf einer Beförderungseinheit über 12 Tonnen "
                  "ohne orangefarbene Tafeln. Die Kennzeichnung nach 3.4.15 "
                  "(250 × 250 mm) ist dann vorn und hinten vorgeschrieben; an einem "
                  "Container an allen vier Seiten.",
            "fr": "Les colis QL totalisent {kg} kg bruts, au-delà des 8 tonnes du "
                  "3.4.14, sur une unité de transport de plus de 12 tonnes sans "
                  "panneaux orange. La marque du 3.4.15 (250 × 250 mm) est alors "
                  "exigée à l'avant et à l'arrière ; sur un conteneur, sur les quatre "
                  "faces.",
        },
    }
    return pick(texts[reason], language).format(kg=_fmt(gross_kg))
