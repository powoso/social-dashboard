# Social Dashboard

Real-time dashboard that scrapes Reddit, Twitter/X, and news sites, then displays trending topics, engagement stats, and a live post feed.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)

## What it does

- **Reddit** — Scrapes 8 subreddits (technology, worldnews, science, programming, stocks, wallstreetbets, cryptocurrency, economics)
- **News** — Scrapes Hacker News, AP News, and Reuters
- **Twitter/X** — Scrapes via Nitter instances (best-effort, depends on instance availability)
- **Dashboard** — Dark-themed UI with stats cards, activity chart, trending topics, search, and source filtering
- **Live updates** — Server-Sent Events push new data to the browser automatically

## Quick Start

```bash
# Clone
git clone https://github.com/powoso/social-dashboard.git
cd social-dashboard

# Set up Python environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install "scrapling[all]" fastapi "uvicorn[standard]" jinja2 sse-starlette \
    "sqlalchemy[asyncio]" aiosqlite pydantic pydantic-settings apscheduler \
    python-dotenv structlog certifi httpx

# Run
python main.py
```

Open **http://localhost:8001** in your browser.

## How it works

Scrapers run automatically on a schedule:

| Source  | Interval | Method                        |
|---------|----------|-------------------------------|
| Reddit  | 10 min   | JSON API via httpx            |
| News    | 15 min   | HTML scraping via Scrapling   |
| Twitter | 30 min   | Nitter HTML via Scrapling     |

Data is stored in a local SQLite database (`social_dashboard.db`) that creates itself on first run. No API keys required.

## Dashboard Features

- **Search** — Filter posts by keyword (searches titles and body text)
- **Source tabs** — Switch between All Sources, Reddit, Twitter, or News
- **Stats cards** — Total posts, posts today, average engagement, active sources, trending topics
- **Activity chart** — Posts per hour over the last 24 hours
- **Trending topics** — Most mentioned keywords ranked by frequency
- **Source health** — Per-source status with manual "Run" buttons to trigger scrapes
- **Live indicator** — Green dot shows real-time SSE connection

## Configuration

Optionally create a `.env` file to override defaults:

```env
DASHBOARD_PORT=8001
REDDIT_SUBREDDITS=technology,worldnews,science,programming
REDDIT_INTERVAL_MINUTES=10
NEWS_INTERVAL_MINUTES=15
SCRAPE_REQUEST_DELAY=2.0
```

See `config/settings.py` for all available options.

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy 2.0 (async), APScheduler
- **Scrapers**: Scrapling, httpx
- **Frontend**: Alpine.js, Tailwind CSS, Chart.js (no build step)
- **Database**: SQLite with WAL mode
- **Live updates**: Server-Sent Events (SSE)
