from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ScrapedItem:
    """A single piece of content normalised from any source."""

    source: str  # "twitter", "reddit", "news"
    source_id: str  # unique id within that source
    source_url: str
    author: str
    title: str
    body: str
    score: int
    num_comments: int
    published_at: datetime
    category: str = ""
    subreddit: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScrapeResult:
    """Outcome of a single scraper run."""

    source: str
    items: list[ScrapedItem]
    errors: list[str]
    duration_seconds: float
