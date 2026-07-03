from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import admin, display
from app.scheduler import DashboardScheduler
from app.settings_store import settings_store

logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = DashboardScheduler(settings_store)
    scheduler.start()
    app.state.scheduler = scheduler
    app.state.settings_store = settings_store
    yield
    scheduler.shutdown()


app = FastAPI(title="Bildschirmprogramm", lifespan=lifespan)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(display.router)
app.include_router(admin.router)
