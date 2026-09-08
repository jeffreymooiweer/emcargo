import logging
import re
from dataclasses import dataclass

import httpx

from app.services.catalog_sync.materials import MaterialRecord

logger = logging.getLogger(__name__)

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_MATERIAL_SOURCE = "wikidata.org (P2054 density)"

# Wikidata item → EMCargo canonical material mapping
WIKIDATA_MATERIAL_MAP: dict[str, dict] = {
    "Q11424": {
        "canonical_name": "steel",
        "category": "metal",
        "aliases": ["staal", "carbon steel", "construction steel"],
        "language_labels": {"nl": "Staal", "en": "Steel", "de": "Stahl", "fr": 'Acier'},
    },
    "Q663": {
        "canonical_name": "aluminium",
        "category": "metal",
        "aliases": ["aluminum", "alu"],
        "language_labels": {"nl": "Aluminium", "en": "Aluminium", "de": "Aluminium", "fr": 'Aluminium'},
    },
    "Q11466": {
        "canonical_name": "copper",
        "category": "metal",
        "aliases": ["koper", "copper"],
        "language_labels": {"nl": "Koper", "en": "Copper", "de": "Kupfer", "fr": 'Cuivre'},
    },
    "Q34095": {
        "canonical_name": "brass",
        "category": "metal",
        "aliases": ["messing", "brass", "bronze"],
        "language_labels": {"nl": "Messing", "en": "Brass", "de": "Messing", "fr": 'Laiton'},
    },
    "Q1090": {
        "canonical_name": "silver",
        "category": "metal",
        "aliases": ["zilver", "silver"],
        "language_labels": {"nl": "Zilver", "en": "Silver", "de": "Silber", "fr": 'Argent'},
    },
    "Q1096": {
        "canonical_name": "cast_iron",
        "category": "metal",
        "aliases": ["gietijzer", "cast iron", "ijzer"],
        "language_labels": {"nl": "Gietijzer", "en": "Cast iron", "de": "Gusseisen", "fr": 'Fonte'},
    },
    "Q11427": {
        "canonical_name": "lead",
        "category": "metal",
        "aliases": ["lood", "lead"],
        "language_labels": {"nl": "Lood", "en": "Lead", "de": "Blei", "fr": 'Plomb'},
    },
    "Q11428": {
        "canonical_name": "tin",
        "category": "metal",
        "aliases": ["tin", "tin metal"],
        "language_labels": {"nl": "Tin", "en": "Tin", "de": "Zinn", "fr": 'Étain'},
    },
    "Q11429": {
        "canonical_name": "zinc",
        "category": "metal",
        "aliases": ["zink", "zinc", "verzinkt"],
        "language_labels": {"nl": "Zink", "en": "Zinc", "de": "Zink", "fr": 'Zinc'},
    },
    "Q22731": {
        "canonical_name": "stone",
        "category": "bulk_material",
        "aliases": ["steen", "stone", "natuursteen"],
        "language_labels": {"nl": "Steen", "en": "Stone", "de": "Stein", "fr": 'Pierre'},
    },
    "Q184190": {
        "canonical_name": "glass",
        "category": "other",
        "aliases": ["glas", "glass"],
        "language_labels": {"nl": "Glas", "en": "Glass", "de": "Glas", "fr": 'Verre'},
    },
}


@dataclass
class WikidataDensity:
    item_id: str
    label: str
    density: float
    unit_label: str | None


def _to_kg_m3(amount: float, unit_label: str | None) -> float:
    if unit_label and re.search(r"gram per cubic centimetre", unit_label, re.I):
        return amount * 1000
    return amount


def _sparql_query(item_ids: list[str]) -> str:
    values = " ".join(f"wd:{item_id}" for item_id in item_ids)
    return f"""
SELECT ?item ?itemLabel ?density ?unitLabel WHERE {{
  VALUES ?item {{ {values} }}
  ?item p:P2054 ?stmt.
  ?stmt psv:P2054 ?val.
  ?val wikibase:quantityAmount ?density.
  OPTIONAL {{
    ?val wikibase:quantityUnit ?unit.
    ?unit rdfs:label ?unitLabel.
    FILTER(LANG(?unitLabel) = "en")
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def fetch_wikidata_densities(
    client: httpx.Client, item_ids: list[str], timeout: float
) -> list[WikidataDensity]:
    if not item_ids:
        return []
    query = _sparql_query(item_ids)
    try:
        response = client.get(
            WIKIDATA_SPARQL_URL,
            params={"query": query},
            headers={"Accept": "application/sparql-results+json", "User-Agent": "EMCargo/1.0"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Wikidata fetch failed: %s", exc)
        return []

    results: list[WikidataDensity] = []
    for row in payload.get("results", {}).get("bindings", []):
        item_uri = row.get("item", {}).get("value", "")
        item_id = item_uri.rsplit("/", 1)[-1]
        try:
            density = float(row.get("density", {}).get("value", ""))
        except ValueError:
            continue
        unit_label = row.get("unitLabel", {}).get("value")
        label = row.get("itemLabel", {}).get("value", item_id)
        results.append(
            WikidataDensity(
                item_id=item_id,
                label=label,
                density=_to_kg_m3(density, unit_label),
                unit_label=unit_label,
            )
        )
    return results


def enrich_from_wikidata(records: list[MaterialRecord], densities: list[WikidataDensity]) -> list[MaterialRecord]:
    by_name = {r.canonical_name: r for r in records}
    for entry in densities:
        mapping = WIKIDATA_MATERIAL_MAP.get(entry.item_id)
        if not mapping:
            continue
        canonical = mapping["canonical_name"]
        if canonical in by_name:
            record = by_name[canonical]
            record.density_kg_m3 = entry.density
            record.source = WIKIDATA_MATERIAL_SOURCE
            record.aliases = list(dict.fromkeys([*(record.aliases or []), *mapping.get("aliases", [])]))
            labels = mapping.get("language_labels") or {}
            record.language_labels = {**(record.language_labels or {}), **labels}
        else:
            new_record = MaterialRecord(
                canonical_name=canonical,
                category=mapping["category"],
                density_kg_m3=entry.density,
                aliases=mapping.get("aliases", []),
                language_labels=mapping.get("language_labels", {}),
                source=WIKIDATA_MATERIAL_SOURCE,
                notes=f"Wikidata {entry.item_id} ({entry.label})",
            )
            records.append(new_record)
            by_name[canonical] = new_record
    return records
