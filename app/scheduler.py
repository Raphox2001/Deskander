from __future__ import annotations

import asyncio
import datetime as dt
import logging

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.cache import display_cache
from app.calendar_service import build_snapshot, fetch_all_events
from app.settings_store import SettingsStore
from app.weather_service import fetch_weather

logger = logging.getLogger(__name__)

CALENDAR_JOB_ID = "refresh_calendar"
WEATHER_JOB_ID = "refresh_weather"


async def _refresh_calendar(store: SettingsStore) -> None:
    settings = store.load()
    today = dt.date.today()
    window_start = today - dt.timedelta(days=1)
    window_end = today + dt.timedelta(weeks=settings.display.calendar_weeks_shown)
    events = await fetch_all_events(settings, window_start, window_end)
    snapshot = build_snapshot(
        events,
        today,
        settings.display.calendar_weeks_shown,
        settings.display.agenda_days_ahead,
        settings.display.show_week_numbers,
    )
    display_cache.set_calendar(snapshot)


def refresh_calendar_job(store: SettingsStore) -> None:
    try:
        asyncio.run(_refresh_calendar(store))
    except Exception:
        logger.exception("Calendar refresh job failed")


async def _refresh_weather(store: SettingsStore) -> None:
    settings = store.load()
    async with httpx.AsyncClient() as client:
        weather = await fetch_weather(client, settings.weather, settings.display.timezone)
    if weather is not None:
        display_cache.set_weather(weather)


def refresh_weather_job(store: SettingsStore) -> None:
    try:
        asyncio.run(_refresh_weather(store))
    except Exception:
        logger.exception("Weather refresh job failed")


class DashboardScheduler:
    """Owns the two background refresh jobs.

    Both jobs re-read the settings store on every run (not once at startup),
    so changing an interval or a calendar source via the admin GUI takes
    effect on the next tick without restarting the process. Interval changes
    additionally call reschedule_*() so they apply immediately rather than
    waiting for the old interval to elapse.
    """

    def __init__(self, store: SettingsStore) -> None:
        self._store = store
        self._scheduler = BackgroundScheduler()

    def start(self) -> None:
        settings = self._store.load()
        now = dt.datetime.now()
        self._scheduler.add_job(
            refresh_calendar_job,
            trigger=IntervalTrigger(minutes=settings.calendar_refresh_minutes),
            args=[self._store],
            id=CALENDAR_JOB_ID,
            replace_existing=True,
            next_run_time=now,
        )
        self._scheduler.add_job(
            refresh_weather_job,
            trigger=IntervalTrigger(minutes=settings.weather.refresh_minutes),
            args=[self._store],
            id=WEATHER_JOB_ID,
            replace_existing=True,
            next_run_time=now,
        )
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    def refresh_calendar_now(self) -> None:
        self._scheduler.modify_job(CALENDAR_JOB_ID, next_run_time=dt.datetime.now())

    def refresh_weather_now(self) -> None:
        self._scheduler.modify_job(WEATHER_JOB_ID, next_run_time=dt.datetime.now())

    def reschedule_calendar(self, minutes: int) -> None:
        self._scheduler.reschedule_job(CALENDAR_JOB_ID, trigger=IntervalTrigger(minutes=minutes))

    def reschedule_weather(self, minutes: int) -> None:
        self._scheduler.reschedule_job(WEATHER_JOB_ID, trigger=IntervalTrigger(minutes=minutes))
