import logging

import httpx

logger = logging.getLogger(__name__)

FREIGHTUTILS_ADR_URL = "https://www.freightutils.com/api/adr"


def _normalize_entry(item: dict) -> dict:
    return {
        "un_number": item.get("un_number"),
        "proper_shipping_name": item.get("proper_shipping_name"),
        "class": item.get("class"),
        "subsidiary_risks": item.get("subsidiary_risks") or item.get("classification_code"),
        "packing_group": item.get("packing_group"),
        "packing_instruction": item.get("packing_instruction"),
        "labels": item.get("labels"),
        "limited_quantity": item.get("limited_quantity"),
        "excepted_quantity": item.get("excepted_quantity"),
        "tunnel_restriction_code": item.get("tunnel_restriction_code"),
        "transport_category": item.get("transport_category"),
        "source": "freightutils.com/api/adr (ADR 2025 / UNECE)",
    }


def lookup_un_number(un_number: str, *, timeout: float = 15.0) -> dict | None:
    digits = "".join(ch for ch in un_number if ch.isdigit())
    if len(digits) != 4:
        return None
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            response = client.get(
                FREIGHTUTILS_ADR_URL,
                params={"un": digits},
                headers={"Accept": "application/json", "User-Agent": "EMCargo/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("ADR lookup failed for UN%s: %s", digits, exc)
        return None
    results = payload.get("results") or []
    if not results:
        return None
    return _normalize_entry(results[0])
