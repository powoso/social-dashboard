from __future__ import annotations

from fastapi import APIRouter, Query

from data.database import get_session
from data.repositories import TrendRepository

router = APIRouter(prefix="/api/trends", tags=["trends"])


def _trend_to_dict(t) -> dict:
    return {
        "id": t.id,
        "source": t.source,
        "topic": t.topic,
        "mention_count": t.mention_count,
        "avg_engagement": t.avg_engagement,
        "first_seen": t.first_seen.isoformat() if t.first_seen else None,
        "last_seen": t.last_seen.isoformat() if t.last_seen else None,
    }


@router.get("")
async def list_trends(
    source: str | None = None,
    limit: int = Query(30, ge=1, le=100),
):
    async with get_session() as session:
        repo = TrendRepository(session)
        trends = await repo.list_trends(source=source, limit=limit)
        return [_trend_to_dict(t) for t in trends]


@router.get("/timeline")
async def trend_timeline(hours: int = Query(24, ge=1, le=168)):
    async with get_session() as session:
        repo = TrendRepository(session)
        return await repo.get_timeline(hours)
