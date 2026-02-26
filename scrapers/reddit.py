"""Reddit scraper using httpx (JSON API)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from config.settings import settings
from core.models import ScrapedItem, ScrapeResult
from scrapers.base import BaseScraper, RateLimiter

log = logging.getLogger(__name__)


class RedditScraper(BaseScraper):
    source_name = "reddit"

    def __init__(self) -> None:
        self._limiter = RateLimiter(delay_seconds=settings.SCRAPE_REQUEST_DELAY)

    async def scrape(self) -> ScrapeResult:
        items: list[ScrapedItem] = []
        errors: list[str] = []
        t0 = time.monotonic()

        subreddits = [s.strip() for s in settings.REDDIT_SUBREDDITS.split(",") if s.strip()]

        async with httpx.AsyncClient(
            headers={
                "User-Agent": "SocialDashboard/1.0 (research project; github.com)",
            },
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            for sub in subreddits:
                await self._limiter.wait()
                try:
                    url = (
                        f"https://www.reddit.com/r/{sub}/{settings.REDDIT_SORT}.json"
                        f"?limit={settings.REDDIT_LIMIT}&raw_json=1"
                    )
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                    for child in data.get("data", {}).get("children", []):
                        post = child.get("data", {})
                        if not post.get("title"):
                            continue

                        items.append(
                            ScrapedItem(
                                source="reddit",
                                source_id=post.get("id", ""),
                                source_url=f"https://www.reddit.com{post.get('permalink', '')}",
                                author=post.get("author", "[deleted]"),
                                title=post.get("title", ""),
                                body=post.get("selftext", "")[:2000],
                                score=post.get("score", 0),
                                num_comments=post.get("num_comments", 0),
                                published_at=datetime.fromtimestamp(
                                    post.get("created_utc", 0), tz=timezone.utc
                                ),
                                subreddit=sub,
                            )
                        )
                    log.info("r/%s: %d posts fetched (status %d)", sub, len(data.get("data", {}).get("children", [])), resp.status_code)

                except Exception as exc:
                    msg = f"r/{sub}: {exc}"
                    log.warning(msg)
                    errors.append(msg)

        elapsed = time.monotonic() - t0
        return ScrapeResult(
            source="reddit",
            items=items,
            errors=errors,
            duration_seconds=elapsed,
        )
