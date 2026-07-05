from __future__ import annotations

import datetime as dt
import threading
from typing import Optional


class DisplayCache:
    """In-memory cache the kiosk page reads from.

    The kiosk display never talks to iCal/Open-Meteo directly - it only
    polls this cache via /display/data, so a flaky external service can't
    hang the display; it just serves the last-known-good data.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calendar_snapshot: Optional[dict] = None
        self._calendar_updated_at: Optional[str] = None
        self._weather: Optional[dict] = None
        self._weather_updated_at: Optional[str] = None
        self._update_available: bool = False
        self._update_info: Optional[dict] = None

    def set_update_status(self, available: bool, info: Optional[dict]) -> None:
        with self._lock:
            self._update_available = available
            self._update_info = info

    def set_calendar(self, snapshot: dict) -> None:
        with self._lock:
            self._calendar_snapshot = snapshot
            self._calendar_updated_at = dt.datetime.now(dt.timezone.utc).isoformat()

    def set_weather(self, weather: Optional[dict]) -> None:
        with self._lock:
            self._weather = weather
            self._weather_updated_at = dt.datetime.now(dt.timezone.utc).isoformat()

    def get(self) -> dict:
        with self._lock:
            snapshot = self._calendar_snapshot or {}
            return {
                "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "calendar_updated_at": self._calendar_updated_at,
                "weather_updated_at": self._weather_updated_at,
                "agenda": snapshot.get("agenda", []),
                "calendar_weeks": snapshot.get("calendar_weeks", []),
                "show_week_numbers": snapshot.get("show_week_numbers", True),
                "weather": self._weather,
                "update_available": self._update_available,
                "update_info": self._update_info,
            }


display_cache = DisplayCache()
