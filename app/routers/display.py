from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.cache import display_cache

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/")
async def kiosk_page(request: Request):
    return templates.TemplateResponse(request, "kiosk.html", {})


@router.get("/display/data")
async def display_data():
    return JSONResponse(display_cache.get())
