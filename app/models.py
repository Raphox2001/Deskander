from __future__ import annotations

import uuid
from typing import List

from pydantic import BaseModel, Field


class CalendarSource(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    url: str
    color: str = "#4a90d9"
    enabled: bool = True


class WeatherSettings(BaseModel):
    latitude: float = 52.52
    longitude: float = 13.405
    place_name: str = "Berlin"
    refresh_minutes: int = 20
    units: str = "metric"


class DisplaySettings(BaseModel):
    calendar_weeks_shown: int = 4
    agenda_days_ahead: int = 1
    timezone: str = "Europe/Berlin"
    show_week_numbers: bool = True
    show_admin_url: bool = True


class Settings(BaseModel):
    calendar_sources: List[CalendarSource] = Field(default_factory=list)
    calendar_refresh_minutes: int = 15
    weather: WeatherSettings = Field(default_factory=WeatherSettings)
    display: DisplaySettings = Field(default_factory=DisplaySettings)
