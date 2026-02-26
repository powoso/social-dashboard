from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/scraper", tags=["scraper"])

# The scheduler reference is injected by app.py at startup
_scheduler = None


def set_scheduler(scheduler) -> None:
    global _scheduler
    _scheduler = scheduler


@router.post("/run/{source}")
async def trigger_scrape(source: str):
    if source not in ("reddit", "news", "twitter"):
        raise HTTPException(400, f"Unknown source: {source}")
    if _scheduler is None:
        raise HTTPException(503, "Scheduler not initialized")

    result = await _scheduler.run_source(source)
    if result is None:
        raise HTTPException(404, f"No scraper for source: {source}")

    return {
        "source": result.source,
        "items": len(result.items),
        "errors": result.errors,
        "duration_seconds": round(result.duration_seconds, 2),
    }


@router.get("/status")
async def scheduler_status():
    if _scheduler is None:
        return {"running": False, "jobs": []}
    return _scheduler.get_status()
