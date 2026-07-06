"""Regression tests for the boot-time refresh retry.

The subtle bug these guard: fetch_source_events used to swallow network errors
and return [], so a failed refresh looked "successful", never triggered the
60s retry, and left the display empty until the next full interval. The jobs
must now retry on a real fetch failure and must not overwrite good cache with
an empty snapshot on a total failure.
"""

from __future__ import annotations

import pytest

from app import scheduler as scheduler_module
from app.calendar_service import CalendarFetchResult
from app.models import Settings
from app.scheduler import (
    CALENDAR_JOB_ID,
    WEATHER_JOB_ID,
    refresh_calendar_job,
    refresh_weather_job,
)


class _StoreStub:
    def load(self) -> Settings:
        return Settings()


class _SchedulerStub:
    def __init__(self) -> None:
        self._store = _StoreStub()
        self.retried: list[str] = []

    def _schedule_retry(self, job_id: str) -> None:
        self.retried.append(job_id)


def test_calendar_total_failure_retries_and_keeps_cache(monkeypatch):
    async def _fake_fetch(*args, **kwargs):
        return CalendarFetchResult(events=[], attempted=2, failed=2)

    set_calls: list = []
    monkeypatch.setattr(scheduler_module, "fetch_all_events", _fake_fetch)
    monkeypatch.setattr(
        scheduler_module.display_cache, "set_calendar", lambda snap: set_calls.append(snap)
    )

    sched = _SchedulerStub()
    refresh_calendar_job(sched)

    assert sched.retried == [CALENDAR_JOB_ID]  # retry scheduled
    assert set_calls == []  # cache left untouched on total failure


def test_calendar_partial_failure_caches_but_still_retries(monkeypatch):
    async def _fake_fetch(*args, **kwargs):
        return CalendarFetchResult(events=[], attempted=2, failed=1)

    set_calls: list = []
    monkeypatch.setattr(scheduler_module, "fetch_all_events", _fake_fetch)
    monkeypatch.setattr(
        scheduler_module.display_cache, "set_calendar", lambda snap: set_calls.append(snap)
    )

    sched = _SchedulerStub()
    refresh_calendar_job(sched)

    assert sched.retried == [CALENDAR_JOB_ID]  # still retry to fill the missing source
    assert len(set_calls) == 1  # but the reachable source's data is cached


def test_calendar_full_success_does_not_retry(monkeypatch):
    async def _fake_fetch(*args, **kwargs):
        return CalendarFetchResult(events=[], attempted=1, failed=0)

    monkeypatch.setattr(scheduler_module, "fetch_all_events", _fake_fetch)
    monkeypatch.setattr(scheduler_module.display_cache, "set_calendar", lambda snap: None)

    sched = _SchedulerStub()
    refresh_calendar_job(sched)

    assert sched.retried == []


def test_weather_failure_retries_without_touching_cache(monkeypatch):
    async def _fake_weather(*args, **kwargs):
        return None

    set_calls: list = []
    monkeypatch.setattr(scheduler_module, "fetch_weather", _fake_weather)
    monkeypatch.setattr(
        scheduler_module.display_cache, "set_weather", lambda w: set_calls.append(w)
    )

    sched = _SchedulerStub()
    refresh_weather_job(sched)

    assert sched.retried == [WEATHER_JOB_ID]
    assert set_calls == []
