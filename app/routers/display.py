from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.cache import display_cache
from app.network_info import get_lan_ip

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Generated once per process start. The kiosk page compares this on every
# poll and reloads itself when it changes, so a backend restart (deploy,
# self-update, crash-restart) always picks up fresh HTML/CSS/JS without
# needing to manually reload/restart the kiosk browser tab.
BOOT_ID = str(uuid.uuid4())


@router.get("/")
async def kiosk_page(request: Request):
    return templates.TemplateResponse(request, "kiosk.html", {})


@router.get("/display/data")
async def display_data(request: Request):
    data = display_cache.get()
    settings = request.app.state.settings_store.load()
    if settings.display.show_admin_url:
        port = request.url.port or 8000
        data["admin_url"] = f"http://{get_lan_ip()}:{port}/admin"
    data["backend_boot_id"] = BOOT_ID
    return JSONResponse(data)
