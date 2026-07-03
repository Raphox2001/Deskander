from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import update_service
from app.calendar_service import validate_ical_url
from app.models import CalendarSource
from app.weather_service import search_place

router = APIRouter(prefix="/admin")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _store(request: Request):
    return request.app.state.settings_store


def _scheduler(request: Request):
    return request.app.state.scheduler


@router.get("/")
async def dashboard(request: Request):
    settings = _store(request).load()
    return templates.TemplateResponse(request, "admin/dashboard.html", {"settings": settings})


@router.get("/sources/new")
async def new_source_form(request: Request):
    return templates.TemplateResponse(
        request, "admin/source_form.html", {"source": None, "error": None}
    )


@router.post("/sources/new")
async def create_source(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    color: str = Form("#4a90d9"),
    enabled: Optional[str] = Form(None),
):
    error = await validate_ical_url(url)
    if error:
        return templates.TemplateResponse(
            request,
            "admin/source_form.html",
            {"source": {"name": name, "url": url, "color": color, "enabled": bool(enabled)}, "error": error},
            status_code=400,
        )

    settings = _store(request).load()
    settings.calendar_sources.append(
        CalendarSource(name=name, url=url, color=color, enabled=bool(enabled))
    )
    _store(request).save(settings)
    _scheduler(request).refresh_calendar_now()
    return RedirectResponse("/admin", status_code=303)


@router.get("/sources/{source_id}/edit")
async def edit_source_form(request: Request, source_id: str):
    settings = _store(request).load()
    source = next((s for s in settings.calendar_sources if s.id == source_id), None)
    if source is None:
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request, "admin/source_form.html", {"source": source, "error": None}
    )


@router.post("/sources/{source_id}/edit")
async def update_source(
    request: Request,
    source_id: str,
    name: str = Form(...),
    url: str = Form(...),
    color: str = Form("#4a90d9"),
    enabled: Optional[str] = Form(None),
):
    error = await validate_ical_url(url)
    if error:
        return templates.TemplateResponse(
            request,
            "admin/source_form.html",
            {
                "source": {"id": source_id, "name": name, "url": url, "color": color, "enabled": bool(enabled)},
                "error": error,
            },
            status_code=400,
        )

    settings = _store(request).load()
    for source in settings.calendar_sources:
        if source.id == source_id:
            source.name = name
            source.url = url
            source.color = color
            source.enabled = bool(enabled)
            break
    _store(request).save(settings)
    _scheduler(request).refresh_calendar_now()
    return RedirectResponse("/admin", status_code=303)


@router.post("/sources/{source_id}/delete")
async def delete_source(request: Request, source_id: str):
    settings = _store(request).load()
    settings.calendar_sources = [s for s in settings.calendar_sources if s.id != source_id]
    _store(request).save(settings)
    _scheduler(request).refresh_calendar_now()
    return RedirectResponse("/admin", status_code=303)


@router.post("/calendar-settings")
async def update_calendar_settings(request: Request, calendar_refresh_minutes: int = Form(...)):
    settings = _store(request).load()
    settings.calendar_refresh_minutes = calendar_refresh_minutes
    _store(request).save(settings)
    _scheduler(request).reschedule_calendar(calendar_refresh_minutes)
    return RedirectResponse("/admin", status_code=303)


@router.get("/weather")
async def weather_form(request: Request):
    settings = _store(request).load()
    return templates.TemplateResponse(
        request, "admin/weather_form.html", {"weather": settings.weather, "places": []}
    )


@router.post("/weather")
async def update_weather(
    request: Request,
    place_name: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    refresh_minutes: int = Form(...),
):
    settings = _store(request).load()
    settings.weather.place_name = place_name
    settings.weather.latitude = latitude
    settings.weather.longitude = longitude
    settings.weather.refresh_minutes = refresh_minutes
    _store(request).save(settings)
    _scheduler(request).reschedule_weather(refresh_minutes)
    _scheduler(request).refresh_weather_now()
    return RedirectResponse("/admin", status_code=303)


@router.get("/api/search-place")
async def api_search_place(request: Request, q: str = ""):
    async with httpx.AsyncClient() as client:
        results = await search_place(client, q)
    return results


@router.get("/display")
async def display_form(request: Request):
    settings = _store(request).load()
    return templates.TemplateResponse(request, "admin/display_form.html", {"display": settings.display})


@router.post("/display")
async def update_display(
    request: Request,
    calendar_weeks_shown: int = Form(...),
    agenda_days_ahead: int = Form(...),
    timezone: str = Form(...),
    show_week_numbers: Optional[str] = Form(None),
):
    settings = _store(request).load()
    settings.display.calendar_weeks_shown = calendar_weeks_shown
    settings.display.agenda_days_ahead = agenda_days_ahead
    settings.display.timezone = timezone
    settings.display.show_week_numbers = bool(show_week_numbers)
    _store(request).save(settings)
    _scheduler(request).refresh_calendar_now()
    return RedirectResponse("/admin", status_code=303)


@router.post("/api/refresh/calendar")
async def api_refresh_calendar(request: Request):
    _scheduler(request).refresh_calendar_now()
    return {"status": "ok"}


@router.post("/api/refresh/weather")
async def api_refresh_weather(request: Request):
    _scheduler(request).refresh_weather_now()
    return {"status": "ok"}


@router.get("/update")
async def update_page(request: Request):
    return templates.TemplateResponse(request, "admin/update.html", {})


@router.get("/api/update/check")
async def api_update_check(request: Request):
    return update_service.check_for_updates()


@router.post("/api/update/apply")
async def api_update_apply(request: Request, background_tasks: BackgroundTasks):
    background_tasks.add_task(update_service.apply_update)
    return {"status": "started"}
