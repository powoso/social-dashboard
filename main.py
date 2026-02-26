"""Social Dashboard — entry point."""

from __future__ import annotations

import logging
import os

import certifi
import uvicorn

# Fix SSL cert resolution for curl_cffi (used by Scrapling)
os.environ.setdefault("CURL_CA_BUNDLE", certifi.where())
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from api.app import create_app  # noqa: E402
from api.routers.scraper_control import set_scheduler  # noqa: E402
from config.settings import settings  # noqa: E402
from data.database import init_db  # noqa: E402
from scrapers.scheduler import ScrapeScheduler  # noqa: E402

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

app = create_app()


@app.on_event("startup")
async def on_startup() -> None:
    log.info("Initialising database…")
    await init_db()

    log.info("Starting scrape scheduler…")
    scheduler = ScrapeScheduler(broadcast_fn=app.state.broadcaster.broadcast)
    app.state.scheduler = scheduler
    set_scheduler(scheduler)
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.stop()
        log.info("Scrape scheduler stopped.")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.DASHBOARD_PORT,
        reload=False,
    )
