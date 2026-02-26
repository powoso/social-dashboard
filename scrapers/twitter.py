from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

from scrapling import Fetcher

from config.settings import settings
from core.models import ScrapedItem, ScrapeResult
from scrapers.base import BaseScraper, RateLimiter

log = logging.getLogger(__name__)

class TwitterScraper(BaseScraper):
    """Scrapes Twitter/X content via Nitter instances (public HTML frontends).

    Nitter instances can go down, so we rotate through a configured list.
    If all Nitter instances fail for a query, that query is skipped with an
    error logged.
    """

    source_name = "twitter"

    def __init__(self) -> None:
        self._queries = [
            q.strip() for q in settings.TWITTER_QUERIES.split(",") if q.strip()
        ]
        self._instances = [
            u.strip()
            for u in settings.TWITTER_NITTER_INSTANCES.split(",")
            if u.strip()
        ]
        self._limiter = RateLimiter(max(settings.SCRAPE_REQUEST_DELAY, 3.0))

    async def scrape(self) -> ScrapeResult:
        items: list[ScrapedItem] = []
        errors: list[str] = []
        start = time.monotonic()

        for query in self._queries:
            try:
                await self._limiter.wait()
                new_items = await asyncio.to_thread(
                    self._fetch_query, query
                )
                items.extend(new_items)
                log.info(
                    "Scraped twitter query '%s': %d tweets", query, len(new_items)
                )
            except Exception as e:
                msg = f"twitter/{query}: {e}"
                log.warning("Twitter scrape error: %s", msg)
                errors.append(msg)

        return ScrapeResult(
            source="twitter",
            items=items,
            errors=errors,
            duration_seconds=time.monotonic() - start,
        )

    def _fetch_query(self, query: str) -> list[ScrapedItem]:
        """Try each Nitter instance until one works."""
        last_error: Exception | None = None
        for instance in self._instances:
            try:
                return self._scrape_nitter(instance, query)
            except Exception as e:
                last_error = e
                log.debug(
                    "Nitter instance %s failed for '%s': %s",
                    instance, query, e,
                )
                continue
        raise ConnectionError(
            f"All Nitter instances failed for '{query}': {last_error}"
        )

    def _scrape_nitter(
        self, instance: str, query: str
    ) -> list[ScrapedItem]:
        url = f"{instance.rstrip('/')}/search?f=tweets&q={quote_plus(query)}"
        fetcher = Fetcher()
        page = fetcher.get(url, stealthy_headers=True, follow_redirects=True)

        if page.status != 200:
            raise ConnectionError(f"HTTP {page.status} from {instance}")

        items: list[ScrapedItem] = []
        # Nitter uses .timeline-item for each tweet
        for tweet_el in page.css(".timeline-item"):
            try:
                username_el = tweet_el.css(".username")
                username = username_el[0].text.strip() if username_el else "unknown"

                content_el = tweet_el.css(".tweet-content")
                content = content_el[0].text.strip() if content_el else ""

                if not content:
                    continue

                # Try to get the tweet link for a stable ID
                link_el = tweet_el.css(".tweet-link")
                tweet_path = ""
                if link_el:
                    tweet_path = link_el[0].attrib.get("href", "")

                source_id = hashlib.md5(
                    (tweet_path or f"{username}:{content[:80]}").encode()
                ).hexdigest()[:16]

                # Try to extract stats
                stat_els = tweet_el.css(".tweet-stat .icon-container")
                comments = 0
                likes = 0
                for stat in stat_els:
                    txt = stat.text.strip().replace(",", "")
                    if txt.isdigit():
                        if comments == 0:
                            comments = int(txt)
                        else:
                            likes = int(txt)

                items.append(
                    ScrapedItem(
                        source="twitter",
                        source_id=source_id,
                        source_url=f"https://x.com{tweet_path}" if tweet_path else "",
                        author=username,
                        title=content[:200],
                        body=content,
                        score=likes,
                        num_comments=comments,
                        published_at=datetime.now(timezone.utc),
                        category=query,
                    )
                )
            except Exception:
                continue  # skip malformed tweet elements

        return items
