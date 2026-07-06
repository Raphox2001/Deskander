import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from app.calendar_service import (
    CalendarFetchError,
    build_snapshot,
    fetch_all_events,
    fetch_source_events,
)
from app.models import CalendarSource, DisplaySettings, Settings

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_events.ics"
BERLIN = ZoneInfo("Europe/Berlin")


@pytest.mark.asyncio
async def test_fetch_source_events_resolves_start_and_end():
    ics_bytes = FIXTURE_PATH.read_bytes()
    source = CalendarSource(name="Test", url="https://example.com/test.ics")

    with respx.mock:
        respx.get("https://example.com/test.ics").mock(
            return_value=httpx.Response(200, content=ics_bytes)
        )
        async with httpx.AsyncClient() as client:
            events = await fetch_source_events(
                client, source, dt.date(2026, 7, 1), dt.date(2026, 7, 31), BERLIN
            )

    by_title = {e.title: e for e in events}

    single = by_title["Einzeltermin"]
    assert single.start == dt.datetime(2026, 7, 6, 16, 0, tzinfo=BERLIN)
    assert single.end == dt.datetime(2026, 7, 6, 17, 30, tzinfo=BERLIN)
    assert single.all_day is False
    assert single.location == "Buero"

    recurring = [e for e in events if e.title == "Wiederkehrend"]
    assert len(recurring) == 5
    assert recurring[0].start == dt.datetime(2026, 7, 1, 11, 0, tzinfo=BERLIN)
    assert recurring[1].start == dt.datetime(2026, 7, 8, 11, 0, tzinfo=BERLIN)

    all_day = by_title["Mehrtaegig Ganztags"]
    assert all_day.all_day is True
    # DTEND is exclusive per RFC 5545 (20260712 means "up to end of 07-11")
    assert all_day.start.date() == dt.date(2026, 7, 10)
    assert all_day.end.date() == dt.date(2026, 7, 11)


@pytest.mark.asyncio
async def test_disabled_source_is_skipped():
    source = CalendarSource(name="Test", url="https://example.com/test.ics", enabled=False)
    async with httpx.AsyncClient() as client:
        events = await fetch_source_events(
            client, source, dt.date(2026, 7, 1), dt.date(2026, 7, 31), BERLIN
        )
    assert events == []


@pytest.mark.asyncio
async def test_broken_source_raises_fetch_error():
    source = CalendarSource(name="Broken", url="https://example.com/broken.ics")
    with respx.mock:
        respx.get("https://example.com/broken.ics").mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as client:
            with pytest.raises(CalendarFetchError):
                await fetch_source_events(
                    client, source, dt.date(2026, 7, 1), dt.date(2026, 7, 31), BERLIN
                )


@pytest.mark.asyncio
async def test_fetch_all_events_isolates_broken_source_and_counts_failure():
    ics_bytes = FIXTURE_PATH.read_bytes()
    settings = Settings(
        calendar_sources=[
            CalendarSource(name="Good", url="https://example.com/good.ics"),
            CalendarSource(name="Broken", url="https://example.com/broken.ics"),
        ],
        display=DisplaySettings(timezone="Europe/Berlin"),
    )
    with respx.mock:
        respx.get("https://example.com/good.ics").mock(
            return_value=httpx.Response(200, content=ics_bytes)
        )
        respx.get("https://example.com/broken.ics").mock(return_value=httpx.Response(500))
        result = await fetch_all_events(settings, dt.date(2026, 7, 1), dt.date(2026, 7, 31))

    # The good source's events still come through; the broken one is counted.
    assert result.attempted == 2
    assert result.failed == 1
    assert result.total_failure is False
    assert len(result.events) > 0


@pytest.mark.asyncio
async def test_fetch_all_events_total_failure_when_all_sources_down():
    settings = Settings(
        calendar_sources=[CalendarSource(name="Broken", url="https://example.com/broken.ics")],
        display=DisplaySettings(timezone="Europe/Berlin"),
    )
    with respx.mock:
        respx.get("https://example.com/broken.ics").mock(return_value=httpx.Response(500))
        result = await fetch_all_events(settings, dt.date(2026, 7, 1), dt.date(2026, 7, 31))

    assert result.total_failure is True
    assert result.events == []


@pytest.mark.asyncio
async def test_build_snapshot_agenda_includes_ongoing_multiday_event():
    ics_bytes = FIXTURE_PATH.read_bytes()
    source = CalendarSource(name="Test", url="https://example.com/test.ics")
    with respx.mock:
        respx.get("https://example.com/test.ics").mock(
            return_value=httpx.Response(200, content=ics_bytes)
        )
        async with httpx.AsyncClient() as client:
            events = await fetch_source_events(
                client, source, dt.date(2026, 7, 1), dt.date(2026, 7, 31), BERLIN
            )

    snapshot = build_snapshot(events, today=dt.date(2026, 7, 11), weeks_shown=2)
    agenda_titles = [e["title"] for e in snapshot["agenda"]]
    assert "Mehrtaegig Ganztags" in agenda_titles
    assert len(snapshot["calendar_weeks"]) == 2
    assert len(snapshot["calendar_weeks"][0]["days"]) == 7
    # 2026-07-06 is a Monday, ISO week 28
    assert snapshot["calendar_weeks"][0]["week_number"] == 28
    assert snapshot["show_week_numbers"] is True


def test_build_snapshot_week_numbers_increment_and_toggle_off():
    snapshot = build_snapshot([], today=dt.date(2026, 7, 11), weeks_shown=3, show_week_numbers=False)
    week_numbers = [w["week_number"] for w in snapshot["calendar_weeks"]]
    assert week_numbers == [28, 29, 30]
    assert snapshot["show_week_numbers"] is False
