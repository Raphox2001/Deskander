from __future__ import annotations

import logging
from typing import List, Optional, TypedDict

import httpx

from app.models import WeatherSettings

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 10.0
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Open-Meteo returns WMO weather codes (numeric), not icon names - this table
# maps them to a short description + a simple icon key the frontend renders.
# Ranges per https://open-meteo.com/en/docs (WMO Weather interpretation codes).
WMO_CODE_MAP = {
    0: ("Klar", "sun"),
    1: ("Überwiegend klar", "sun"),
    2: ("Teilweise bewölkt", "cloud-sun"),
    3: ("Bedeckt", "cloud"),
    45: ("Nebel", "fog"),
    48: ("Reifnebel", "fog"),
    51: ("Leichter Nieselregen", "drizzle"),
    53: ("Nieselregen", "drizzle"),
    55: ("Starker Nieselregen", "drizzle"),
    56: ("Gefrierender Nieselregen", "drizzle"),
    57: ("Starker gefrierender Nieselregen", "drizzle"),
    61: ("Leichter Regen", "rain"),
    63: ("Regen", "rain"),
    65: ("Starker Regen", "rain"),
    66: ("Gefrierender Regen", "rain"),
    67: ("Starker gefrierender Regen", "rain"),
    71: ("Leichter Schneefall", "snow"),
    73: ("Schneefall", "snow"),
    75: ("Starker Schneefall", "snow"),
    77: ("Schneegriesel", "snow"),
    80: ("Leichte Regenschauer", "rain"),
    81: ("Regenschauer", "rain"),
    82: ("Heftige Regenschauer", "rain"),
    85: ("Leichte Schneeschauer", "snow"),
    86: ("Starke Schneeschauer", "snow"),
    95: ("Gewitter", "thunderstorm"),
    96: ("Gewitter mit leichtem Hagel", "thunderstorm"),
    99: ("Gewitter mit starkem Hagel", "thunderstorm"),
}
DEFAULT_CODE_INFO = ("Unbekannt", "cloud")


def describe_weather_code(code: int) -> dict:
    description, icon = WMO_CODE_MAP.get(code, DEFAULT_CODE_INFO)
    return {"code": code, "description": description, "icon": icon}


class GeocodingResult(TypedDict):
    name: str
    country: str
    admin1: str
    latitude: float
    longitude: float
    timezone: str


async def fetch_weather(
    client: httpx.AsyncClient,
    settings: WeatherSettings,
    display_timezone: str,
    forecast_days: int = 5,
) -> Optional[dict]:
    """Fetch current conditions + a short forecast from Open-Meteo (no API key).

    Returns None (and logs) on any failure so a weather outage can't crash
    the scheduler - callers should keep serving the last-known-good cache.
    """
    params = {
        "latitude": settings.latitude,
        "longitude": settings.longitude,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
        "timezone": display_timezone,
        "forecast_days": forecast_days,
    }
    try:
        response = await client.get(FORECAST_URL, params=params, timeout=FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except Exception:
        logger.exception("Failed to fetch weather from Open-Meteo")
        return None

    current = data.get("current", {})
    daily = data.get("daily", {})
    daily_days = []
    for i, date in enumerate(daily.get("time", [])):
        daily_days.append(
            {
                "date": date,
                "temperature_max": daily["temperature_2m_max"][i],
                "temperature_min": daily["temperature_2m_min"][i],
                "precipitation_probability_max": daily["precipitation_probability_max"][i],
                **describe_weather_code(daily["weather_code"][i]),
            }
        )

    return {
        "place_name": settings.place_name,
        "current": {
            "temperature": current.get("temperature_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "time": current.get("time"),
            **describe_weather_code(current.get("weather_code", -1)),
        },
        "daily": daily_days,
    }


async def search_place(client: httpx.AsyncClient, query: str, count: int = 5) -> List[GeocodingResult]:
    """Look up candidate places for a typed name via Open-Meteo's free,
    keyless geocoding API - used by the admin GUI's "search place" field so
    the user doesn't have to look up their own lat/lon coordinates."""
    if not query.strip():
        return []
    params = {"name": query, "count": count, "language": "de"}
    try:
        response = await client.get(GEOCODING_URL, params=params, timeout=FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except Exception:
        logger.exception("Failed to search place %r via Open-Meteo geocoding", query)
        return []

    results = []
    for item in data.get("results", []):
        results.append(
            {
                "name": item.get("name", ""),
                "country": item.get("country", ""),
                "admin1": item.get("admin1", ""),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "timezone": item.get("timezone", ""),
            }
        )
    return results
