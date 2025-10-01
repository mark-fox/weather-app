import logging
import re
import httpx

logger = logging.getLogger(__name__)

# Accepts "lat,lon" or "lat lon" with optional spaces
LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$")


def _try_parse_latlon(q: str):
    # Return dict {name, lat, lon} if q looks like coordinates.
    m = LATLON_RE.match(q or "")
    if not m:
        return None
    try:
        lat = float(m.group(1))
        lon = float(m.group(2))
    except ValueError:
        return None
    return {"name": f"{lat:.4f},{lon:.4f}", "lat": lat, "lon": lon}


async def _geocode_open_meteo(query: str):
    # Primary geocoder: Open-Meteo.
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": query, "count": 1, "language": "en", "format": "json"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("Open-Meteo geocoding error: %s", e)
        return None

    results = data.get("results") or []
    if not results:
        return None

    top = results[0]
    parts = [top.get("name")]
    admin1 = top.get("admin1")
    country = top.get("country")
    if admin1:
        parts.append(admin1)
    if country:
        parts.append(country)

    return {
        "name": ", ".join([p for p in parts if p]),
        "lat": top.get("latitude"),
        "lon": top.get("longitude"),
        "country_code": top.get("country_code"),
        "source": "open-meteo",
    }


async def _geocode_nominatim(query: str):
    # Fallback geocoder: Nominatim (OpenStreetMap). Requires a User-Agent.
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "jsonv2", "limit": 1}
    headers = {"User-Agent": "markfox-weather-app/1.0 (learning project)"}
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("Nominatim geocoding error: %s", e)
        return None

    if not data:
        return None

    top = data[0]
    display_name = top.get("display_name") or query
    try:
        lat = float(top.get("lat"))
        lon = float(top.get("lon"))
    except (TypeError, ValueError):
        return None

    return {
        "name": display_name,
        "lat": lat,
        "lon": lon,
        "country_code": None,
        "source": "nominatim",
    }


async def geocode_one(query: str):
    """
    Resolve free-form text to a single lat/lon.
    Strategy:
      - If it's coordinates, return directly.
      - Else try Open-Meteo, then fall back to Nominatim.
    """
    latlon = _try_parse_latlon(query)
    if latlon:
        return latlon

    # Primary: Open-Meteo
    result = await _geocode_open_meteo(query)
    if result:
        return result

    # Fallback: Nominatim
    result = await _geocode_nominatim(query)
    if result:
        return result

    logger.info("Geocoding failed for query=%r", query)
    return None
