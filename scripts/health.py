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
                 "SEC filings": 30, "Screener": 8 * 24, "Field news": 30,
                 "Prices": 30, "Company figures": 30, "Insider data": 9 * 24,
                 "Hedge funds": 100 * 24, "Movers": 30, "Radar": 30, "AI summary": 36,
                 "Self-test": 3 * 24}
# Running on time proves nothing: the news job did that for five weeks and returned
# nothing. So each part also has to produce real data. A share is the part of the list
# that must have data; a count is how many results there must be at least.
MIN_SHARE = {"News": 0.5, "Prices": 0.9, "Company figures": 0.8, "Insider data": 0.5,
             "Hedge funds": 0.5, "Field news": 0.75, "Movers": 0.5}
MIN_COUNT = {"Screener": 300, "Radar": 1, "AI summary": 1}
# What goes wrong for you when a part is down, shown on Home and in the alert.
AFFECTS = {
    "Quotes": "Prices and buy targets may be out of date",
    "Prices": "Prices and buy targets may be missing",
    "Company figures": "Ratings can't check the numbers",
    "Research": "Ratings aren't being updated",
    "Ratings": "Some ratings still use older logic",
    "Catalysts": "Upcoming earnings dates may be missing",
    "News": "Ratings and mover reasons can miss recent news",
    "SEC filings": "New SEC filings won't show",
    "Screener": "New stock ideas may be out of date",
    "Field news": "The field briefing may be out of date",
    "Insider data": "Insider buying won't show on stocks or the radar",
    "Hedge funds": "Hedge fund holdings may be out of date",
    "Movers": "Big moves may have no explanation",
    "Radar": "The radar may be out of date",
    "AI summary": "The AI summary may be out of date",
    "Self-test": "One of the data sources failed its daily test",
}
# Market data stops on Friday night, so allow for the weekend until Monday.
WEEKEND_SLACK_HOURS = 48
MARKET_STAGES = {"Quotes", "News", "SEC filings", "Movers"}
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
    # Nothing due is a healthy run: every rating is current.
    detail = f"{landed}/{attempted} tickers" if attempted else "nothing due"
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


def _content_stage(name: str, updated_at: str | None, now: datetime, have: int,
                   total: int | None = None) -> dict:
    """On time AND holding real data. Movers can be genuinely empty on a calm day."""
    detail = f"{have}/{total} have data" if total is not None else f"{have} found"
    stage = _stage(name, updated_at, now, detail)
    if total is None:
        enough = have >= MIN_COUNT[name]
    else:
        enough = have >= total * MIN_SHARE[name] and (total > 0 or name == "Movers")
    return stage if enough or stage["status"] != "ok" else {**stage, "status": "failing"}


def _self_test_stage(result: dict | None, now: datetime) -> dict:
    checks = (result or {}).get("checks", [])
    failed = [c["name"] for c in checks if not c["ok"]]
    detail = f"failed: {', '.join(failed)}" if failed else f"{len(checks)} sources passed"
    stage = _stage("Self-test", (result or {}).get("ran_at"), now, detail)
    return {**stage, "status": "failing"} if failed else stage


def build_health(now: datetime, *, quotes, research, catalysts, sec, ratings=None,
                 content=None, self_test=None) -> dict:
    """content: {part name: (updated_at, how many have data, out of how many or None)}."""
    stages = [
        _stage("Quotes", quotes, now),
        _research_stage(research, now),
        _stage("Catalysts", catalysts, now),
        _stage("SEC filings", sec, now),
        *[_content_stage(name, counts[0], now, *counts[1:]) for name, counts in (content or {}).items()],
        _self_test_stage(self_test, now),
        _ratings_stage(ratings),
    ]
    return {"stages": [{**s, "affects": AFFECTS.get(s["name"])} for s in stages]}
