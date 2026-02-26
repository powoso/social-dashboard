from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from core.models import ScrapeResult


class BaseScraper(ABC):
    source_name: str

    @abstractmethod
    async def scrape(self) -> ScrapeResult:
        """Execute a full scrape cycle."""
        ...


class RateLimiter:
    """Simple token-bucket style rate limiter."""

    def __init__(self, delay_seconds: float = 2.0) -> None:
        self._delay = delay_seconds
        self._lock = asyncio.Lock()
        self._last_request: float = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request
            if elapsed < self._delay:
                await asyncio.sleep(self._delay - elapsed)
            self._last_request = asyncio.get_event_loop().time()
