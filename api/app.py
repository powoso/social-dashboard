from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from api.routers import posts, scraper_control, sources, trends

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"


class Broadcaster:
    """Simple in-memory SSE broadcaster."""

    def __init__(self) -> None:
        self._listeners: list[asyncio.Queue] = []

    async def broadcast(self, data: dict) -> None:
        for q in list(self._listeners):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._listeners:
            self._listeners.remove(q)


def create_app() -> FastAPI:
    app = FastAPI(title="Social Dashboard", version="0.1.0")
    broadcaster = Broadcaster()
    app.state.broadcaster = broadcaster

    # Mount static files
    app.mount(
        "/static",
        StaticFiles(directory=str(DASHBOARD_DIR / "static")),
        name="static",
    )
    templates = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))

    # Register API routers
    app.include_router(posts.router)
    app.include_router(trends.router)
    app.include_router(sources.router)
    app.include_router(scraper_control.router)

    # SSE endpoint
    @app.get("/api/events")
    async def sse_events(request: Request):
        q = broadcaster.subscribe()

        async def event_generator():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        data = await asyncio.wait_for(q.get(), timeout=30.0)
                        yield {"event": "message", "data": json.dumps(data)}
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": ""}
                    except Exception:
                        break
            finally:
                broadcaster.unsubscribe(q)

        return EventSourceResponse(event_generator())

    # Dashboard route
    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
