"""Match named establishments against the configured address provider.

Results are proposals, not an exhaustive business register. A single match
still needs confirmation; a map result is not evidence of a delivery entrance.
"""
import re
import unicodedata


def words(value: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return set(re.findall(r"[^\W_]+", "".join(c for c in folded if not unicodedata.combining(c))))


GENERIC = words("supermarkt supermarket supermarche supermarché supermarkt bedrijf company firma magasin winkel shop factory fabriek usine warehouse magazijn entrepot entrepôt restaurant hotel bv nv gmbh ltd sa sas sarl ag de het the der die das le la les")


def business_name(value: str) -> str:
    """Remove category words, while keeping the source spelling of the name."""
    return " ".join(w for w in value.split() if not words(w).issubset(GENERIC))


def match_businesses(results: list[dict], name: str, city: str) -> list[dict]:
    wanted = words(business_name(name))
    place = words(city)
    if not wanted or not place:
        return []
    matches, seen = [], set()
    for item in results:
        if not isinstance(item, dict):
            continue
        if not wanted.issubset(words(str(item.get("name") or ""))):
            continue
        found_city = words(str(item.get("city") or ""))
        if not found_city or not found_city.issubset(place):
            continue
        if not all(item.get(k) for k in ("street", "housenumber", "city", "country")):
            continue
        address = "\n".join([
            f"{item['street']} {item['housenumber']}",
            " ".join(p for p in (item.get("postcode"), item["city"]) if p),
            item["country"],
        ])
        key = " ".join(sorted(words(address)))
        if key in seen:
            continue
        seen.add(key)
        matches.append({"name": item["name"], "address": address})
    return matches


def split_business_place(text: str) -> tuple[str, str] | None:
    """Read an explicit named endpoint, without guessing a business from a town."""
    match = re.fullmatch(r"(.+?)\s+(?:in|te|à|bei)\s+([^,;\n]+)", text.strip(), re.I)
    if not match:
        return None
    name, city = match.groups()
    if words(name) & words("haven port hafen luchthaven airport flughafen aeroport aéroport station bahnhof gare"):
        return None
    name = re.sub(r"^(?:de|het|the|der|die|das|le|la|les)\s+", "", name, flags=re.I)
    if not business_name(name) or len(city) > 100 or any(c.isdigit() for c in city):
        return None
    return name, city.strip(" .")
