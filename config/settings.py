from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./social_dashboard.db"

    # Server
    DASHBOARD_PORT: int = 8001
    LOG_LEVEL: str = "INFO"

    # Reddit
    REDDIT_SUBREDDITS: str = "technology,worldnews,science,programming,stocks,wallstreetbets,cryptocurrency,economics"
    REDDIT_SORT: str = "hot"
    REDDIT_LIMIT: int = 25
    REDDIT_INTERVAL_MINUTES: int = 10

    # Twitter
    TWITTER_QUERIES: str = "breaking news,AI,technology,crypto"
    TWITTER_NITTER_INSTANCES: str = "https://nitter.privacydev.net,https://nitter.poast.org"
    TWITTER_INTERVAL_MINUTES: int = 30

    # News
    NEWS_SOURCES: str = "hackernews,reuters,ap_news"
    NEWS_INTERVAL_MINUTES: int = 15

    # Scraping behaviour
    SCRAPE_REQUEST_DELAY: float = 2.0

    # Trending
    TREND_WINDOW_HOURS: int = 24
    TREND_MIN_MENTIONS: int = 2

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
