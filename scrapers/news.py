from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone

from scrapling import Fetcher

from config.settings import settings
from core.models import ScrapedItem, ScrapeResult
from scrapers.base import BaseScraper, RateLimiter

log = logging.getLogger(__name__)

# Per-source extraction config.  Each entry describes how to pull articles
# from a particular news site's HTML.
NEWS_SOURCE_CONFIGS: dict[str, dict] = {
    "hackernews": {
        "url": "https://news.ycombinator.com/",
        "article_selector": ".titleline > a",
        "title_attr": "text",
        "link_attr": "href",
        "base_url": "",
    },
    "reuters": {
        "url": "https://www.reuters.com/",
        "article_selector": "a[data-testid='Heading']",
        "title_attr": "text",
        "link_attr": "href",
        "base_url": "https://www.reuters.com",
    },
    "ap_news": {
        "url": "https://apnews.com/",
        "article_selector": "a.Link[href*='/article/']",
        "title_attr": "text",
        "link_attr": "href",
        "base_url": "https://apnews.com",
    },
}


class NewsScraper(BaseScraper):
    source_name = "news"

    def __init__(self) -> None:
        enabled = [
            s.strip() for s in settings.NEWS_SOURCES.split(",") if s.strip()
        ]
        self._sources = {
            k: v for k, v in NEWS_SOURCE_CONFIGS.items() if k in enabled
        }
        self._limiter = RateLimiter(settings.SCRAPE_REQUEST_DELAY)

    async def scrape(self) -> ScrapeResult:
        items: list[ScrapedItem] = []
        errors: list[str] = []
        start = time.monotonic()

        for name, config in self._sources.items():
            try:
                await self._limiter.wait()
                new_items = await asyncio.to_thread(
                    self._fetch_source, name, config
                )
                items.extend(new_items)
                log.info("Scraped %s: %d articles", name, len(new_items))
            except Exception as e:
                msg = f"{name}: {e}"
                log.warning("News scrape error: %s", msg)
                errors.append(msg)

        return ScrapeResult(
            source="news",
            items=items,
            errors=errors,
            duration_seconds=time.monotonic() - start,
        )

    def _fetch_source(
        self, source_name: str, config: dict
    ) -> list[ScrapedItem]:
        fetcher = Fetcher()
        page = fetcher.get(
            config["url"],
            stealthy_headers=True,
            follow_redirects=True,
        )
        if page.status != 200:
            raise ConnectionError(f"HTTP {page.status}")

        items: list[ScrapedItem] = []
        seen_urls: set[str] = set()

        for el in page.css(config["article_selector"]):
            title = el.text.strip() if el.text else ""
            link = el.attrib.get(config.get("link_attr", "href"), "")

            if not title or len(title) < 15 or " " not in title:
                continue

            if link and not link.startswith("http"):
                base = config.get("base_url", "")
                link = f"{base}{link}" if base else link

            if link in seen_urls:
                continue
            seen_urls.add(link)

            source_id = hashlib.md5(
                (link or title).encode()
            ).hexdigest()[:16]

            items.append(
                ScrapedItem(
                    source="news",
                    source_id=source_id,
                    source_url=link,
                    author=source_name,
                    title=title,
                    body="",
                    score=0,
                    num_comments=0,
                    published_at=datetime.now(timezone.utc),
                    category=source_name,
                )
            )
        return items
