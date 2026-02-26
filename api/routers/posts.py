from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from data.database import get_session
from data.repositories import PostRepository

router = APIRouter(prefix="/api/posts", tags=["posts"])


def _post_to_dict(p) -> dict:
    return {
        "id": p.id,
        "source": p.source,
        "source_id": p.source_id,
        "source_url": p.source_url,
        "author": p.author,
        "title": p.title,
        "body": p.body[:300],
        "subreddit": p.subreddit,
        "category": p.category,
        "score": p.score,
        "num_comments": p.num_comments,
        "engagement_score": p.engagement_score,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "scraped_at": p.scraped_at.isoformat() if p.scraped_at else None,
    }


@router.get("")
async def list_posts(
    source: str | None = None,
    search: str | None = None,
    subreddit: str | None = None,
    sort: str = Query("published_at", pattern="^(published_at|score|engagement_score)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    since: datetime | None = None,
):
    async with get_session() as session:
        repo = PostRepository(session)
        posts = await repo.list_posts(
            source=source,
            search=search,
            subreddit=subreddit,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
            since=since,
        )
        return [_post_to_dict(p) for p in posts]


@router.get("/stats")
async def post_stats():
    async with get_session() as session:
        repo = PostRepository(session)
        return await repo.get_stats()


@router.get("/activity")
async def hourly_activity(hours: int = Query(24, ge=1, le=168)):
    async with get_session() as session:
        repo = PostRepository(session)
        return await repo.get_hourly_activity(hours)
