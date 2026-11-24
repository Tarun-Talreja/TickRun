#!/usr/bin/env python3
"""
scripts/market_tick.py — Make sure the price loop is running, whatever GitHub's timer does.

Each run is held 30 minutes by the environment's wait timer (no machine is used while
waiting), does this check, and starts the next run. See .github/workflows/market_tick.yml.

Usage (needs GH_TOKEN with actions: write):  python3 scripts/market_tick.py
"""
import json
import subprocess
from datetime import datetime, timedelta, timezone

from market_loop import dispatch, window

LEAD = timedelta(minutes=65)   # two checks fall inside this before the open


def needs_loop(now: datetime) -> bool:
    span = window(now)
    return span is not None and span[0] - LEAD <= now <= span[1]


def active(runs: list[dict]) -> bool:
    return any(r["status"] != "completed" for r in runs)


def _loop_runs() -> list[dict]:
    result = subprocess.run(["gh", "run", "list", "--workflow", "market_loop.yml", "-L", "10", "--json", "status"],
                            capture_output=True, text=True)
    return json.loads(result.stdout) if result.returncode == 0 else []


def main() -> None:
    now = datetime.now(timezone.utc)
    if not needs_loop(now):
        print("Market shut: nothing to start.")
    elif active(_loop_runs()):
        print("The price loop is running.")
    else:
        print("Starting the price loop.")
        dispatch("market_loop.yml")


if __name__ == "__main__":
    main()
