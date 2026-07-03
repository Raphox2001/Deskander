import httpx
import pytest
import respx

from app.models import WeatherSettings
from app.weather_service import describe_weather_code, fetch_weather, search_place

FORECAST_RESPONSE = {
    "current": {
        "time": "2026-07-03T13:30",
        "temperature_2m": 20.8,
        "weather_code": 3,
        "wind_speed_10m": 21.8,
    },
    "daily": {
        "time": ["2026-07-03", "2026-07-04"],
        "temperature_2m_max": [21.8, 23.2],
        "temperature_2m_min": [14.8, 12.8],
        "weather_code": [3, 61],
        "precipitation_probability_max": [0, 25],
    },
}

GEOCODING_RESPONSE = {
    "results": [
        {
            "name": "Berlin",
            "country": "Deutschland",
            "admin1": "Berlin",
            "latitude": 52.52437,
            "longitude": 13.41053,
            "timezone": "Europe/Berlin",
        }
    ]
}


def test_describe_weather_code_known_and_unknown():
    assert describe_weather_code(0) == {"code": 0, "description": "Klar", "icon": "sun"}
    assert describe_weather_code(95)["icon"] == "thunderstorm"
    unknown = describe_weather_code(-1)
    assert unknown["description"] == "Unbekannt"


@pytest.mark.asyncio
async def test_fetch_weather_maps_response_to_normalized_shape():
    with respx.mock:
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=FORECAST_RESPONSE)
        )
        async with httpx.AsyncClient() as client:
            result = await fetch_weather(
                client,
                WeatherSettings(latitude=52.52, longitude=13.405, place_name="Berlin"),
                "Europe/Berlin",
            )

    assert result["place_name"] == "Berlin"
    assert result["current"]["temperature"] == 20.8
    assert result["current"]["description"] == "Bedeckt"
    assert len(result["daily"]) == 2
    assert result["daily"][1]["description"] == "Leichter Regen"


@pytest.mark.asyncio
async def test_fetch_weather_returns_none_on_failure():
    with respx.mock:
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            result = await fetch_weather(
                client, WeatherSettings(), "Europe/Berlin"
            )
    assert result is None


@pytest.mark.asyncio
async def test_search_place_returns_candidates():
    with respx.mock:
        respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
            return_value=httpx.Response(200, json=GEOCODING_RESPONSE)
        )
        async with httpx.AsyncClient() as client:
            results = await search_place(client, "Berlin")

    assert len(results) == 1
    assert results[0]["name"] == "Berlin"
    assert results[0]["latitude"] == 52.52437


@pytest.mark.asyncio
async def test_search_place_empty_query_short_circuits_without_request():
    async with httpx.AsyncClient() as client:
        results = await search_place(client, "   ")
    assert results == []
