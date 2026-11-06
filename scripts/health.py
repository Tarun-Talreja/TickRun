#!/usr/bin/env python3
"""
scripts/health.py — Did each stage actually work, and when?

Green workflow runs hid a frozen live site for 3 months and failed research for
10 weeks, because "the job finished" is not "the job did its work". The app
reports on itself instead, from the data each stage leaves behind.
"""

from datetime import datetime, timezone

# Hours a stage may go without a fresh result.
MAX_AGE_HOURS = {"Quotes": 30, "Research": 36, "Catalysts": 36, "News": 30,
                 "SEC filings": 30, "Screener": 8 * 24, "Field news": 30}
# Market data stops on Friday night, so allow for the weekend until Monday.
WEEKEND_SLACK_HOURS = 48
MARKET_STAGES = {"Quotes", "News", "SEC filings"}
SATURDAY, SUNDAY, MONDAY = 5, 6, 0


def _stage(name: str, updated_at: str | None, now: datetime, detail: str | None = None) -> dict:
    stage = {"name": name, "updated_at": updated_at, "detail": detail}
    if not updated_at:
        return {**stage, "status": "unknown", "age_hours": None}
    ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    age = (now - ts).total_seconds() / 3600
    limit = MAX_AGE_HOURS[name]
    if name in MARKET_STAGES and now.weekday() in (SATURDAY, SUNDAY, MONDAY):
        limit += WEEKEND_SLACK_HOURS
    return {**stage, "status": "ok" if age <= limit else "stale", "age_hours": round(age, 1)}


def _research_stage(research: dict, now: datetime) -> dict:
    attempted, landed = research.get("attempted"), research.get("landed")
    detail = f"{landed}/{attempted} tickers" if attempted else None
    stage = _stage("Research", research.get("ran_at"), now, detail)
    if attempted and stage["status"] == "ok" and landed * 2 < attempted:
        return {**stage, "status": "failing"}
    return stage


def _ratings_stage(ratings: tuple[int, int] | None) -> dict:
    """How many ratings came from the current logic; old ones re-queue on their own."""
    current, total = ratings or (0, 0)
    return {"name": "Ratings", "updated_at": None, "age_hours": None,
            "detail": f"{current}/{total} on current logic",
            "status": "ok" if ratings and current == total else "stale"}


def _news_stage(updated_at: str | None, now: datetime, coverage: tuple[int, int] | None) -> dict:
    """Fresh isn't enough: the feed once ran daily for five weeks returning nothing."""
    with_news, total = coverage or (0, 0)
    stage = _stage("News", updated_at, now, f"{with_news}/{total} stocks have headlines")
    if stage["status"] == "ok" and with_news * 2 < total:
        return {**stage, "status": "failing"}
    return stage


def build_health(now: datetime, *, quotes, research, catalysts, news, sec, screener,
                 field_news=None, ratings=None, news_coverage=None) -> dict:
    return {"stages": [
        _stage("Quotes", quotes, now),
        _research_stage(research, now),
        _stage("Catalysts", catalysts, now),
        _news_stage(news, now, news_coverage),
        _stage("SEC filings", sec, now),
        _stage("Screener", screener, now),
        _stage("Field news", field_news, now),
        _ratings_stage(ratings),
    ]}
