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


class ReminderSettings(BaseModel):
    enabled: bool = False
    lead_minutes: int = 30  # first show this many minutes before the event start
    visible_seconds: int = 60  # how long each pop-up stays on screen
    repeat: bool = True  # re-show in intervals until the event starts
    repeat_interval_minutes: int = 5  # gap between repeated pop-ups
    travel_enabled: bool = False
    home_latitude: float = 52.52
    home_longitude: float = 13.405
    home_place_name: str = ""
    travel_refresh_minutes: int = 5  # how often the travel time is recomputed


class Settings(BaseModel):
    calendar_sources: List[CalendarSource] = Field(default_factory=list)
    calendar_refresh_minutes: int = 15
    weather: WeatherSettings = Field(default_factory=WeatherSettings)
    display: DisplaySettings = Field(default_factory=DisplaySettings)
    reminder: ReminderSettings = Field(default_factory=ReminderSettings)
