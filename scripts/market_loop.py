#!/usr/bin/env python3
"""
scripts/market_loop.py — Keep prices fresh all session without GitHub's timer.

GitHub delivers scheduled runs hours late or drops them: on 2026-11-24 none of the
half-hourly refreshes ran in the first hour and a half of trading. One run of this
waits for the open, then starts a price refresh every few minutes until the close.
Runs end before GitHub's six-hour limit and start their own replacement.

Usage (needs GH_TOKEN with actions: write):  python3 scripts/market_loop.py
"""
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from market_time import _SESSION, NEW_YORK, OPEN, _close

EVERY = timedelta(minutes=15)
FIRST_AFTER_OPEN = timedelta(minutes=2)
LAST_AFTER_CLOSE = timedelta(minutes=12)   # so the last refresh has the closing price
RUN_LIMIT = timedelta(hours=5, minutes=30)
STOP_AFTER_FAILURES = 4


def window(now: datetime) -> tuple[datetime, datetime] | None:
    """First and last refresh of today's session, or None when the market is shut today."""
    day = now.astimezone(NEW_YORK).date()
    if not _SESSION.is_on_offset(pd.Timestamp(day)):
        return None
    return (datetime.combine(day, OPEN, NEW_YORK) + FIRST_AFTER_OPEN,
            datetime.combine(day, _close(day), NEW_YORK) + LAST_AFTER_CLOSE)


def step(now: datetime, started: datetime) -> tuple[str, float]:
    """What to do now: refresh, wait, hand over to a new run, or stop. Seconds apply to wait."""
    span = window(now)
    if span is None or now > span[1]:
        return "stop", 0.0
    first, last = span
    if now < first:
        wait = (first - now).total_seconds()
        # An early run that can't last until the open leaves it to a later one.
        return ("wait", wait) if now + timedelta(seconds=wait) < started + RUN_LIMIT else ("stop", 0.0)
    if now >= started + RUN_LIMIT:
        return "hand_over", 0.0
    return "refresh", min(EVERY.total_seconds(), max((last - now).total_seconds(), 60.0))


def dispatch(workflow: str) -> bool:
    result = subprocess.run(["gh", "workflow", "run", workflow, "--ref", "main"], capture_output=True, text=True)
    if result.returncode:
        print(f"⚠ could not start {workflow}: {result.stderr.strip()[:200]}", flush=True)
    return result.returncode == 0


def main() -> None:
    started, failures = datetime.now(timezone.utc), 0
    while True:
        action, seconds = step(datetime.now(timezone.utc), started)
        print(f"{datetime.now(NEW_YORK):%H:%M} {action}", flush=True)
        if action == "stop":
            return
        if action == "hand_over":
            sys.exit(0 if dispatch("market_loop.yml") else 1)
        if action == "refresh":
            failures = 0 if dispatch("daily.yml") else failures + 1
            if failures >= STOP_AFTER_FAILURES:
                sys.exit("Refreshes can't be started.")
        time.sleep(seconds)


if __name__ == "__main__":
    main()
