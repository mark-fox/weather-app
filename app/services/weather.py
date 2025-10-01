from datetime import date, datetime
from typing import Optional, List, Dict
import httpx

# Minimal mapping for Open-Meteo weather codes.
WEATHER_CODE_DESC = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ slight hail",
    99: "Thunderstorm w/ heavy hail",
}

def _c_to_f(c: Optional[float]) -> Optional[float]:
    if c is None:
        return None
    return c * 9 / 5 + 32

def _mm_to_in(mm: Optional[float]) -> Optional[float]:
    if mm is None:
        return None
    return mm / 25.4


async def get_current_weather(lat: float, lon: float):
    """
    Fetch current weather from Open-Meteo.
    Returns dict or None:
    {
      temperature_c, temperature_f,
      apparent_c, apparent_f,
      wind_speed, precipitation,
      weather_code, weather_desc
    }
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "timezone": "auto",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    cur = data.get("current") or {}
    code = cur.get("weather_code")
    desc = WEATHER_CODE_DESC.get(code, f"Code {code}")

    temp_c = cur.get("temperature_2m")
    feels_c = cur.get("apparent_temperature")

    return {
        "temperature_c": temp_c,
        "temperature_f": _c_to_f(temp_c),
        "apparent_c": feels_c,
        "apparent_f": _c_to_f(feels_c),
        "wind_speed": cur.get("wind_speed_10m"),   # m/s
        "precipitation": cur.get("precipitation"), # mm
        "weather_code": code,
        "weather_desc": desc,
    }


async def get_forecast_5d(lat: float, lon: float) -> Optional[List[Dict]]:
    """
    Fetch a 5-day daily forecast from Open-Meteo.
    Returns a list of dicts (len up to 5), or None:
    [
      {
        "date": "2025-09-30",
        "tmax_c": 23.1, "tmax_f": 73.6,
        "tmin_c": 12.4, "tmin_f": 54.3,
        "precip_mm": 3.2, "precip_in": 0.13,
        "weather_code": 63,
        "weather_desc": "Moderate rain",
      },
      ...
    ]
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
        "forecast_days": 5,          # ask for exactly 5
        "timezone": "auto",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    daily = data.get("daily") or {}
    times = daily.get("time") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []
    codes = daily.get("weather_code") or []

    out: List[Dict] = []
    for i in range(min(5, len(times))):
        code = codes[i] if i < len(codes) else None
        desc = WEATHER_CODE_DESC.get(code, f"Code {code}") if code is not None else "—"

        tmax_c = tmax[i] if i < len(tmax) else None
        tmin_c = tmin[i] if i < len(tmin) else None
        prec_mm = precip[i] if i < len(precip) else None

        out.append({
            "date": times[i],
            "tmax_c": tmax_c,
            "tmax_f": _c_to_f(tmax_c),
            "tmin_c": tmin_c,
            "tmin_f": _c_to_f(tmin_c),
            "precip_mm": prec_mm,
            "precip_in": _mm_to_in(prec_mm),
            "weather_code": code,
            "weather_desc": desc,
        })

    return out

async def _daily_rows_from_open_meteo(url: str, params: dict) -> Optional[List[Dict]]:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    daily = data.get("daily") or {}
    times = daily.get("time") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []
    codes = daily.get("weather_code") or []

    out: List[Dict] = []
    n = len(times)
    for i in range(n):
        code = codes[i] if i < len(codes) else None
        desc = WEATHER_CODE_DESC.get(code, f"Code {code}") if code is not None else "—"
        tmax_c = tmax[i] if i < len(tmax) else None
        tmin_c = tmin[i] if i < len(tmin) else None
        prec_mm = precip[i] if i < len(precip) else None
        out.append({
            "date": times[i],
            "tmax_c": tmax_c, "tmax_f": _c_to_f(tmax_c),
            "tmin_c": tmin_c, "tmin_f": _c_to_f(tmin_c),
            "precip_mm": prec_mm, "precip_in": _mm_to_in(prec_mm),
            "weather_code": code, "weather_desc": desc,
        })
    return out

async def get_daily_range(lat: float, lon: float, start: date, end: date) -> Optional[List[Dict]]:
    # Return daily rows for [start, end] inclusive, merging archive + forecast if needed.
    today = date.today()

    # Entirely past >> archive
    if end < today:
        return await _daily_rows_from_open_meteo(
            "https://archive-api.open-meteo.com/v1/era5",
            {
                "latitude": lat, "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                "timezone": "auto",
            },
        )

    # Entirely future >> forecast (Open-Meteo can go up to ~16 days ahead)
    if start > today:
        return await _daily_rows_from_open_meteo(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": lat, "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                "timezone": "auto",
            },
        )

    # Crossing today >> split into [start, today] archive and [today, end] forecast; merge
    past = await _daily_rows_from_open_meteo(
        "https://archive-api.open-meteo.com/v1/era5",
        {
            "latitude": lat, "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": today.isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
            "timezone": "auto",
        },
    )

    future = await _daily_rows_from_open_meteo(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": lat, "longitude": lon,
            "start_date": today.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
            "timezone": "auto",
        },
    )

    if past is None and future is None:
        return None
    return (past or []) + (future or [])