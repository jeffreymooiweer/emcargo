"""Geo endpoints: location typeahead (airports/ports/stations) and address autocomplete.

Address autocomplete proxies to a Photon-compatible API (photon.komoot.io by
default, OpenStreetMap data). An administrator can point it elsewhere or switch
it off entirely from the settings screen; ``GEO_ADDRESS_API_URL`` remains the
default when nothing has been saved. It fails softly either way, so the wizard
stays usable without internet access.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.ratelimit import ADDRESS_LOOKUP, limiter
from app.models.user import User
from app.services.geo.locations import LOCATION_TYPES, search_locations
from app.services.settings_store import instance_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geo", tags=["geo"])


@router.get("/locations")
def geo_locations(
    q: str = Query(..., min_length=2, max_length=80),
    type: str | None = Query(default=None, description="Comma-separated: airport,port,station"),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    limit: int = Query(default=10, ge=1, le=25),
    user: User = Depends(get_current_user),
):
    types = None
    if type:
        types = [t.strip() for t in type.split(",") if t.strip() in LOCATION_TYPES]
    return {"results": search_locations(q, types=types, country=country, limit=limit)}


@router.get("/address")
@limiter.limit(ADDRESS_LOOKUP)
def geo_address(
    request: Request,
    q: str = Query(..., min_length=3, max_length=200),
    lang: str = Query(default="en", min_length=2, max_length=2),
    limit: int = Query(default=6, ge=1, le=15),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = instance_settings(db)
    # The one request this app makes to the outside world while somebody is
    # typing. An administrator can switch it off, and then it is not made at
    # all rather than made and discarded.
    if not settings.address_lookup_enabled:
        return {"results": [], "available": False}
    params = {"q": q, "limit": limit, "lang": lang if lang in ("en", "de", "fr") else "en"}
    headers = {"User-Agent": "EMCargo (+https://github.com/jeffreymooiweer/EMCargo)"}
    try:
        with httpx.Client(timeout=settings.address_timeout_seconds, headers=headers) as client:
            response = client.get(settings.address_api_url, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Address API unreachable: %s", exc)
        return {"results": [], "available": False}

    results = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        name = props.get("name") or ""
        street = props.get("street") or (name if props.get("housenumber") else "")
        street_line = " ".join(p for p in (street, props.get("housenumber")) if p)
        label_parts = [name] if name and name != street else []
        label_parts += [street_line, props.get("postcode"), props.get("city"), props.get("country")]
        results.append(
            {
                "label": ", ".join(p for p in label_parts if p),
                "name": name,
                "street": street,
                "housenumber": props.get("housenumber") or "",
                "postcode": props.get("postcode") or "",
                "city": props.get("city") or "",
                "state": props.get("state") or "",
                "country": props.get("country") or "",
                "countrycode": props.get("countrycode") or "",
            }
        )
    return {"results": results, "available": True}
