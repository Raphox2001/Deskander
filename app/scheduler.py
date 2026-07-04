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

# If a refresh fails (e.g. network not up yet right after boot), retry
# quickly instead of waiting for the full configured interval to elapse.
RETRY_SECONDS = 60


async def _refresh_calendar(store: SettingsStore) -> None:
    settings = store.load()
    today = dt.date.today()
    window_start = today - dt.timedelta(days=today.weekday())  # Monday of current week
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


def refresh_calendar_job(scheduler: "DashboardScheduler") -> None:
    try:
        asyncio.run(_refresh_calendar(scheduler._store))
    except Exception:
        logger.exception("Calendar refresh job failed, retrying in %ss", RETRY_SECONDS)
        scheduler._schedule_retry(CALENDAR_JOB_ID)


async def _refresh_weather(store: SettingsStore) -> None:
    settings = store.load()
    async with httpx.AsyncClient() as client:
        weather = await fetch_weather(client, settings.weather, settings.display.timezone)
    if weather is not None:
        display_cache.set_weather(weather)


def refresh_weather_job(scheduler: "DashboardScheduler") -> None:
    try:
        asyncio.run(_refresh_weather(scheduler._store))
    except Exception:
        logger.exception("Weather refresh job failed, retrying in %ss", RETRY_SECONDS)
        scheduler._schedule_retry(WEATHER_JOB_ID)


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
            args=[self],
            id=CALENDAR_JOB_ID,
            replace_existing=True,
            next_run_time=now,
        )
        self._scheduler.add_job(
            refresh_weather_job,
            trigger=IntervalTrigger(minutes=settings.weather.refresh_minutes),
            args=[self],
            id=WEATHER_JOB_ID,
            replace_existing=True,
            next_run_time=now,
        )
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    def _schedule_retry(self, job_id: str) -> None:
        retry_time = dt.datetime.now() + dt.timedelta(seconds=RETRY_SECONDS)
        self._scheduler.modify_job(job_id, next_run_time=retry_time)

    def refresh_calendar_now(self) -> None:
        self._scheduler.modify_job(CALENDAR_JOB_ID, next_run_time=dt.datetime.now())

    def refresh_weather_now(self) -> None:
        self._scheduler.modify_job(WEATHER_JOB_ID, next_run_time=dt.datetime.now())

    def reschedule_calendar(self, minutes: int) -> None:
        self._scheduler.reschedule_job(CALENDAR_JOB_ID, trigger=IntervalTrigger(minutes=minutes))

    def reschedule_weather(self, minutes: int) -> None:
        self._scheduler.reschedule_job(WEATHER_JOB_ID, trigger=IntervalTrigger(minutes=minutes))
