from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, delete, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.models import ScrapedItem
from data.schema import DBPost, DBScrapeRun, DBTrendingTopic

# ── helpers ──────────────────────────────────────────────────────────

# Words to exclude from trending topic extraction
_STOP_WORDS = frozenset(
    "the a an and or but in on at to for of is it this that with from by as "
    "are was were be been has have had do does did will would can could may "
    "might shall should not no so if then than too also just about up its my "
    "your his her our their what which who whom how when where why all each "
    "every both few more most other some such only own same into over after "
    "before between through during above below out off again further once "
    "here there these those am i me we they them he she you".split()
)

_WORD_RE = re.compile(r"[a-zA-Z]{3,}")


def _compute_engagement(score: int, num_comments: int) -> float:
    return score + num_comments * 2.0


def _extract_keywords(text: str) -> list[str]:
    """Pull meaningful keywords from a title/body for trend detection."""
    words = _WORD_RE.findall(text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 3]


# ── PostRepository ───────────────────────────────────────────────────


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert_many(self, items: list[ScrapedItem]) -> int:
        """Insert or ignore scraped items. Returns count of newly inserted rows."""
        if not items:
            return 0

        new_count = 0
        for item in items:
            stmt = (
                sqlite_upsert(DBPost)
                .values(
                    source=item.source,
                    source_id=item.source_id,
                    source_url=item.source_url,
                    author=item.author,
                    title=item.title,
                    body=item.body[:2000],
                    subreddit=item.subreddit,
                    category=item.category,
                    score=item.score,
                    num_comments=item.num_comments,
                    engagement_score=_compute_engagement(item.score, item.num_comments),
                    published_at=item.published_at,
                    scraped_at=datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    index_elements=["source", "source_id"],
                    set_={
                        "score": item.score,
                        "num_comments": item.num_comments,
                        "engagement_score": _compute_engagement(
                            item.score, item.num_comments
                        ),
                        "scraped_at": datetime.now(timezone.utc),
                    },
                )
            )
            result = await self._s.execute(stmt)
            if result.rowcount and result.rowcount > 0:
                new_count += 1
        return new_count

    async def list_posts(
        self,
        *,
        source: str | None = None,
        search: str | None = None,
        subreddit: str | None = None,
        sort: str = "published_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[DBPost]:
        q = select(DBPost)
        if source:
            q = q.where(DBPost.source == source)
        if search:
            pattern = f"%{search}%"
            q = q.where(DBPost.title.ilike(pattern) | DBPost.body.ilike(pattern))
        if subreddit:
            q = q.where(DBPost.subreddit == subreddit)
        if since:
            q = q.where(DBPost.published_at >= since)

        sort_col = getattr(DBPost, sort, DBPost.published_at)
        q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
        q = q.limit(limit).offset(offset)
        result = await self._s.execute(q)
        return list(result.scalars().all())

    async def get_stats(self) -> dict:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        total = await self._s.scalar(select(func.count(DBPost.id))) or 0
        today = (
            await self._s.scalar(
                select(func.count(DBPost.id)).where(
                    DBPost.scraped_at >= today_start
                )
            )
            or 0
        )
        avg_eng = (
            await self._s.scalar(select(func.avg(DBPost.engagement_score))) or 0.0
        )

        # Per-source breakdown
        per_source_q = select(
            DBPost.source, func.count(DBPost.id), func.avg(DBPost.engagement_score)
        ).group_by(DBPost.source)
        rows = (await self._s.execute(per_source_q)).all()
        per_source = {
            row[0]: {"count": row[1], "avg_engagement": round(row[2] or 0, 1)}
            for row in rows
        }

        return {
            "total_posts": total,
            "posts_today": today,
            "avg_engagement": round(avg_eng, 1),
            "per_source": per_source,
        }

    async def get_hourly_activity(self, hours: int = 24) -> list[dict]:
        """Post counts per source per hour for charting."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        q = (
            select(
                DBPost.source,
                func.strftime("%Y-%m-%dT%H:00:00", DBPost.published_at).label(
                    "hour"
                ),
                func.count(DBPost.id).label("count"),
            )
            .where(DBPost.published_at >= since)
            .group_by(DBPost.source, "hour")
            .order_by("hour")
        )
        rows = (await self._s.execute(q)).all()
        return [
            {"source": r[0], "hour": r[1], "count": r[2]} for r in rows
        ]


# ── TrendRepository ──────────────────────────────────────────────────


class TrendRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def compute_trends(self) -> None:
        """Recompute trending topics from recent posts."""
        since = datetime.now(timezone.utc) - timedelta(
            hours=settings.TREND_WINDOW_HOURS
        )
        q = select(DBPost.source, DBPost.title, DBPost.engagement_score).where(
            DBPost.published_at >= since
        )
        rows = (await self._s.execute(q)).all()

        # Count keyword frequencies per source
        source_counters: dict[str, Counter[str]] = {}
        source_engagement: dict[str, dict[str, list[float]]] = {}
        for source, title, eng in rows:
            if source not in source_counters:
                source_counters[source] = Counter()
                source_engagement[source] = {}
            keywords = _extract_keywords(title)
            source_counters[source].update(keywords)
            for kw in keywords:
                source_engagement[source].setdefault(kw, []).append(eng)

        # Mark all existing as inactive, then upsert active ones
        await self._s.execute(
            update(DBTrendingTopic).values(is_active=False)
        )

        now = datetime.now(timezone.utc)
        for source, counter in source_counters.items():
            for topic, count in counter.most_common(20):
                if count < settings.TREND_MIN_MENTIONS:
                    continue
                eng_values = source_engagement[source][topic]
                avg_eng = sum(eng_values) / len(eng_values) if eng_values else 0

                stmt = (
                    sqlite_upsert(DBTrendingTopic)
                    .values(
                        source=source,
                        topic=topic,
                        mention_count=count,
                        avg_engagement=round(avg_eng, 1),
                        first_seen=now,
                        last_seen=now,
                        is_active=True,
                    )
                    .on_conflict_do_update(
                        index_elements=["source", "topic"],
                        set_={
                            "mention_count": count,
                            "avg_engagement": round(avg_eng, 1),
                            "last_seen": now,
                            "is_active": True,
                        },
                    )
                )
                await self._s.execute(stmt)

    async def list_trends(
        self, *, source: str | None = None, limit: int = 30
    ) -> list[DBTrendingTopic]:
        q = (
            select(DBTrendingTopic)
            .where(DBTrendingTopic.is_active.is_(True))
            .order_by(DBTrendingTopic.mention_count.desc())
            .limit(limit)
        )
        if source:
            q = q.where(DBTrendingTopic.source == source)
        result = await self._s.execute(q)
        return list(result.scalars().all())

    async def get_timeline(self, hours: int = 24) -> list[dict]:
        """Trend mention counts over time for charting."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        q = (
            select(DBTrendingTopic)
            .where(DBTrendingTopic.last_seen >= since, DBTrendingTopic.is_active.is_(True))
            .order_by(DBTrendingTopic.mention_count.desc())
            .limit(20)
        )
        result = await self._s.execute(q)
        return [
            {
                "topic": t.topic,
                "source": t.source,
                "mention_count": t.mention_count,
                "avg_engagement": t.avg_engagement,
            }
            for t in result.scalars().all()
        ]


# ── ScrapeLogRepository ──────────────────────────────────────────────


class ScrapeLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def log_run(
        self,
        *,
        source: str,
        status: str,
        items_scraped: int,
        items_new: int,
        error_message: str,
        duration_seconds: float,
        started_at: datetime,
    ) -> None:
        run = DBScrapeRun(
            source=source,
            status=status,
            items_scraped=items_scraped,
            items_new=items_new,
            error_message=error_message,
            duration_seconds=round(duration_seconds, 2),
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
        self._s.add(run)

    async def recent_runs(self, limit: int = 20) -> list[DBScrapeRun]:
        q = (
            select(DBScrapeRun)
            .order_by(DBScrapeRun.started_at.desc())
            .limit(limit)
        )
        result = await self._s.execute(q)
        return list(result.scalars().all())

    async def source_stats(self) -> list[dict]:
        """Per-source: last run time, total runs, success rate."""
        # Get latest run per source
        subq = (
            select(
                DBScrapeRun.source,
                func.count(DBScrapeRun.id).label("total_runs"),
                func.sum(
                    func.cast(DBScrapeRun.status == "success", Integer)
                ).label("success_count"),
                func.max(DBScrapeRun.started_at).label("last_run"),
                func.sum(DBScrapeRun.items_new).label("total_items"),
            )
            .group_by(DBScrapeRun.source)
        )
        rows = (await self._s.execute(subq)).all()
        return [
            {
                "source": r[0],
                "total_runs": r[1],
                "success_rate": round((r[2] or 0) / max(r[1], 1) * 100, 0),
                "last_run": r[3].isoformat() if r[3] else None,
                "total_items": r[4] or 0,
            }
            for r in rows
        ]
