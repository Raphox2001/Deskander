from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx
import recurring_ical_events
from icalendar import Calendar

from app.models import CalendarSource, Settings

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 10.0


class CalendarFetchError(Exception):
    """Raised by fetch_source_events when a source can't be fetched/parsed.

    fetch_all_events catches these so one broken source can't take the others
    down, but it counts them so the scheduler knows the refresh was only
    partial (or a total failure) and can retry soon instead of leaving a stale
    or empty display until the next full interval.
    """


@dataclass
class CalendarFetchResult:
    events: List["CalendarEvent"]
    attempted: int  # enabled sources we tried to fetch
    failed: int  # of those, how many could not be fetched/parsed

    @property
    def total_failure(self) -> bool:
        """All configured sources failed (e.g. network down right after boot)."""
        return self.attempted > 0 and self.failed == self.attempted


@dataclass
class CalendarEvent:
    source_id: str
    source_name: str
    color: str
    title: str
    location: str
    start: dt.datetime
    end: dt.datetime
    all_day: bool

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "color": self.color,
            "title": self.title,
            "location": self.location,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "all_day": self.all_day,
        }


def _localize(value: dt.datetime, tzinfo: ZoneInfo) -> dt.datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=tzinfo)
    return value.astimezone(tzinfo)


def _resolve_start_end(
    raw_start, raw_end, tzinfo: ZoneInfo
) -> tuple[dt.datetime, dt.datetime, bool]:
    """Turn icalendar's raw DTSTART/DTEND values into aware start/end datetimes.

    All-day events arrive as `datetime.date` (not `datetime.datetime`), and
    per RFC 5545 their DTEND is *exclusive* (the day after the event's last
    day) - both need explicit handling so an all-day event isn't shown as a
    bogus "00:00-00:00" range or as spanning one day too many.
    """
    is_all_day = isinstance(raw_start, dt.date) and not isinstance(raw_start, dt.datetime)
    if is_all_day:
        last_day = raw_end - dt.timedelta(days=1) if raw_end > raw_start else raw_start
        start = dt.datetime.combine(raw_start, dt.time.min, tzinfo=tzinfo)
        end = dt.datetime.combine(last_day, dt.time(23, 59, 59), tzinfo=tzinfo)
        return start, end, True
    return _localize(raw_start, tzinfo), _localize(raw_end, tzinfo), False


async def _fetch_ics_text(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True)
    response.raise_for_status()
    return response.text


async def validate_ical_url(url: str) -> Optional[str]:
    """Fetch+parse a candidate iCal URL to catch a mistyped/invalid URL at
    save time in the admin GUI. Returns an error message, or None if OK."""
    try:
        async with httpx.AsyncClient() as client:
            ics_text = await _fetch_ics_text(client, url)
        Calendar.from_ical(ics_text)
    except httpx.HTTPStatusError as exc:
        return f"URL antwortete mit Status {exc.response.status_code}"
    except httpx.HTTPError:
        return "URL konnte nicht erreicht werden"
    except Exception:
        return "Antwort ist kein gültiges iCal-Format"
    return None


async def fetch_source_events(
    client: httpx.AsyncClient,
    source: CalendarSource,
    window_start: dt.date,
    window_end: dt.date,
    tzinfo: ZoneInfo,
) -> List[CalendarEvent]:
    """Fetch, parse and expand one calendar source.

    Raises CalendarFetchError if the source can't be fetched/parsed (e.g.
    network not up yet). fetch_all_events catches that to isolate the source
    from the others *and* to count it as a failure - important so a boot-time
    network outage triggers a retry instead of silently caching an empty
    calendar. (A single malformed occurrence is still skipped individually,
    not treated as a whole-source failure.)
    """
    if not source.enabled:
        return []
    try:
        ics_text = await _fetch_ics_text(client, source.url)
        calendar = Calendar.from_ical(ics_text)
        occurrences = recurring_ical_events.of(calendar).between(window_start, window_end)
    except Exception as exc:
        logger.exception("Failed to fetch/parse calendar source %s (%s)", source.name, source.url)
        raise CalendarFetchError(source.name) from exc

    events: List[CalendarEvent] = []
    for occurrence in occurrences:
        try:
            raw_start = occurrence["DTSTART"].dt
            dtend_prop = occurrence.get("DTEND")
            raw_end = dtend_prop.dt if dtend_prop is not None else raw_start
            start, end, all_day = _resolve_start_end(raw_start, raw_end, tzinfo)
            title = str(occurrence.get("SUMMARY", "(ohne Titel)"))
            location = str(occurrence.get("LOCATION", "") or "")
        except Exception:
            logger.exception("Skipping malformed occurrence in source %s", source.name)
            continue
        events.append(
            CalendarEvent(
                source_id=source.id,
                source_name=source.name,
                color=source.color,
                title=title,
                location=location,
                start=start,
                end=end,
                all_day=all_day,
            )
        )
    return events


async def fetch_all_events(
    settings: Settings,
    window_start: dt.date,
    window_end: dt.date,
    client: Optional[httpx.AsyncClient] = None,
) -> CalendarFetchResult:
    """Fetch every configured source, isolating failures.

    Uses return_exceptions=True so one unreachable source can't abort the
    gather; failed sources are counted (not silently dropped) so the caller
    can tell "no events" apart from "couldn't reach anything" and retry.
    """
    tzinfo = ZoneInfo(settings.display.timezone)
    attempted = sum(1 for source in settings.calendar_sources if source.enabled)

    async def _run(active_client: httpx.AsyncClient) -> tuple[List[CalendarEvent], int]:
        results = await asyncio.gather(
            *(
                fetch_source_events(active_client, source, window_start, window_end, tzinfo)
                for source in settings.calendar_sources
            ),
            return_exceptions=True,
        )
        events: List[CalendarEvent] = []
        failed = 0
        for result in results:
            if isinstance(result, CalendarFetchError):
                failed += 1
            elif isinstance(result, BaseException):
                raise result  # unexpected error - don't swallow programming bugs
            else:
                events.extend(result)
        return events, failed

    if client is not None:
        events, failed = await _run(client)
    else:
        async with httpx.AsyncClient() as owned_client:
            events, failed = await _run(owned_client)

    events.sort(key=lambda e: e.start)
    return CalendarFetchResult(events=events, attempted=attempted, failed=failed)


def build_snapshot(
    events: List[CalendarEvent],
    today: dt.date,
    weeks_shown: int,
    agenda_days_ahead: int = 1,
    show_week_numbers: bool = True,
) -> dict:
    """Build the /display/data payload shape: agenda (today .. +agenda_days_ahead-1) + a week-bucketed grid."""
    agenda_end = today + dt.timedelta(days=max(agenda_days_ahead, 1) - 1)
    agenda = [e.to_dict() for e in events if e.start.date() <= agenda_end and e.end.date() >= today]

    grid_start = today - dt.timedelta(days=today.weekday())  # Monday of current week
    grid_end = grid_start + dt.timedelta(days=weeks_shown * 7)  # exclusive

    events_by_date: Dict[dt.date, List[dict]] = {
        grid_start + dt.timedelta(days=offset): [] for offset in range(weeks_shown * 7)
    }

    for e in events:
        day = max(e.start.date(), grid_start)
        last_day = min(e.end.date(), grid_end - dt.timedelta(days=1))
        while day <= last_day:
            if day in events_by_date:
                events_by_date[day].append(e.to_dict())
            day += dt.timedelta(days=1)

    weeks = []
    current_day = grid_start
    for _ in range(weeks_shown):
        week_monday = current_day
        days = []
        for _ in range(7):
            days.append(
                {"date": current_day.isoformat(), "events": events_by_date.get(current_day, [])}
            )
            current_day += dt.timedelta(days=1)
        weeks.append({"week_number": week_monday.isocalendar()[1], "days": days})

    return {
        "agenda": agenda,
        "calendar_weeks": weeks,
        "show_week_numbers": show_week_numbers,
    }
