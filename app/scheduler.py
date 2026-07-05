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
from app.update_service import check_for_updates
from app.weather_service import fetch_weather

logger = logging.getLogger(__name__)

CALENDAR_JOB_ID = "refresh_calendar"
WEATHER_JOB_ID = "refresh_weather"
UPDATE_JOB_ID = "check_update"

# If a refresh fails (e.g. network not up yet right after boot), retry
# quickly instead of waiting for the full configured interval to elapse.
RETRY_SECONDS = 60

# When to look for a new version: a short delay after start (so we don't run
# git fetch during boot/right after a self-update restart), then once a day.
UPDATE_CHECK_FIRST_DELAY_MINUTES = 20
UPDATE_CHECK_INTERVAL_HOURS = 24


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


def check_update_job(scheduler: "DashboardScheduler") -> None:
    """Look for a newer version and stash the result so the kiosk can show a
    small "update available" hint. Best-effort: check_for_updates() never
    raises, and a failed check just leaves the last-known status untouched."""
    try:
        result = check_for_updates()
        if "error" in result:
            logger.warning("Update check failed: %s", result["error"])
            return
        available = not result.get("up_to_date", True)
        display_cache.set_update_status(available, result if available else None)
    except Exception:
        logger.exception("Update check job failed")


class DashboardScheduler:
    """Owns the background refresh jobs (calendar, weather, update check).

    The calendar/weather jobs re-read the settings store on every run (not once at startup),
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
            # APScheduler's default (1s) skips a run entirely if the process
            # was busy for even a few seconds past its due time - on a Pi
            # under load that silently doubles (or worse) the configured
            # interval. None = always run, however late, instead of skipping.
            misfire_grace_time=None,
        )
        self._scheduler.add_job(
            refresh_weather_job,
            trigger=IntervalTrigger(minutes=settings.weather.refresh_minutes),
            args=[self],
            id=WEATHER_JOB_ID,
            replace_existing=True,
            next_run_time=now,
            misfire_grace_time=None,
        )
        self._scheduler.add_job(
            check_update_job,
            trigger=IntervalTrigger(hours=UPDATE_CHECK_INTERVAL_HOURS),
            args=[self],
            id=UPDATE_JOB_ID,
            replace_existing=True,
            next_run_time=now + dt.timedelta(minutes=UPDATE_CHECK_FIRST_DELAY_MINUTES),
            misfire_grace_time=None,
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
        # A fresh IntervalTrigger without start_date fires the first time only
        # after a full interval (see apscheduler IntervalTrigger.__init__), so
        # rescheduling would otherwise push the next refresh out by the whole
        # (possibly long) interval. Force an immediate run so a changed interval
        # takes effect right away instead of leaving a stale display for minutes.
        self.refresh_calendar_now()

    def reschedule_weather(self, minutes: int) -> None:
        self._scheduler.reschedule_job(WEATHER_JOB_ID, trigger=IntervalTrigger(minutes=minutes))
        self.refresh_weather_now()
