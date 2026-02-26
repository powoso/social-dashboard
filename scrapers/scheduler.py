from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import settings
from core.models import ScrapeResult
from data.database import get_session
from data.repositories import PostRepository, ScrapeLogRepository, TrendRepository
from scrapers.base import BaseScraper
from scrapers.news import NewsScraper
from scrapers.reddit import RedditScraper
from scrapers.twitter import TwitterScraper

log = logging.getLogger(__name__)


class ScrapeScheduler:
    """Orchestrates periodic scraping and persistence."""

    def __init__(self, broadcast_fn=None) -> None:
        self._broadcast = broadcast_fn
        self._scheduler = AsyncIOScheduler()
        self._scrapers: dict[str, BaseScraper] = {
            "reddit": RedditScraper(),
            "news": NewsScraper(),
            "twitter": TwitterScraper(),
        }

    def start(self) -> None:
        intervals = {
            "reddit": settings.REDDIT_INTERVAL_MINUTES,
            "news": settings.NEWS_INTERVAL_MINUTES,
            "twitter": settings.TWITTER_INTERVAL_MINUTES,
        }
        for name, scraper in self._scrapers.items():
            minutes = intervals.get(name, 15)
            self._scheduler.add_job(
                self._run_scraper,
                "interval",
                minutes=minutes,
                args=[scraper],
                id=f"scrape_{name}",
                replace_existing=True,
            )
            # Also run once at startup (after a short delay to let server boot)
            self._scheduler.add_job(
                self._run_scraper,
                "date",
                run_date=datetime.now(timezone.utc),
                args=[scraper],
                id=f"scrape_{name}_init",
            )
        self._scheduler.start()
        log.info("Scrape scheduler started with intervals: %s", intervals)

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    async def run_source(self, source: str) -> ScrapeResult | None:
        """Manually trigger a single source scrape."""
        scraper = self._scrapers.get(source)
        if not scraper:
            return None
        return await self._run_scraper(scraper)

    def get_status(self) -> dict:
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "next_run": job.next_run_time.isoformat()
                    if job.next_run_time
                    else None,
                }
            )
        return {"running": self._scheduler.running, "jobs": jobs}

    async def _run_scraper(self, scraper: BaseScraper) -> ScrapeResult:
        started_at = datetime.now(timezone.utc)
        log.info("Starting scrape: %s", scraper.source_name)

        result = await scraper.scrape()

        # Persist results
        new_count = 0
        try:
            async with get_session() as session:
                post_repo = PostRepository(session)
                new_count = await post_repo.upsert_many(result.items)

                # Recompute trends after new data
                trend_repo = TrendRepository(session)
                await trend_repo.compute_trends()

                # Log the run
                log_repo = ScrapeLogRepository(session)
                status = "success" if not result.errors else "partial"
                if not result.items and result.errors:
                    status = "failed"
                await log_repo.log_run(
                    source=scraper.source_name,
                    status=status,
                    items_scraped=len(result.items),
                    items_new=new_count,
                    error_message="; ".join(result.errors)[:500],
                    duration_seconds=result.duration_seconds,
                    started_at=started_at,
                )
        except Exception as e:
            log.error("Failed to persist scrape results for %s: %s", scraper.source_name, e)

        log.info(
            "Finished scrape: %s | %d items (%d new) | %.1fs | %d errors",
            scraper.source_name,
            len(result.items),
            new_count,
            result.duration_seconds,
            len(result.errors),
        )

        # Broadcast SSE event
        if self._broadcast:
            await self._broadcast(
                {
                    "event": "scrape_complete",
                    "source": scraper.source_name,
                    "items": len(result.items),
                    "new": new_count,
                    "errors": len(result.errors),
                }
            )

        return result
