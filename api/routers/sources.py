from __future__ import annotations

from fastapi import APIRouter, Query

from data.database import get_session
from data.repositories import ScrapeLogRepository

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("/stats")
async def source_stats():
    async with get_session() as session:
        repo = ScrapeLogRepository(session)
        return await repo.source_stats()


@router.get("/runs")
async def recent_runs(limit: int = Query(20, ge=1, le=100)):
    async with get_session() as session:
        repo = ScrapeLogRepository(session)
        runs = await repo.recent_runs(limit=limit)
        return [
            {
                "id": r.id,
                "source": r.source,
                "status": r.status,
                "items_scraped": r.items_scraped,
                "items_new": r.items_new,
                "error_message": r.error_message,
                "duration_seconds": r.duration_seconds,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in runs
        ]
