#!/usr/bin/env python3
"""
fetch_weekly.py — TickRun weekly pipeline orchestrator.

Runs the three-stage pipeline:
    1. universe.py     → data/universe.json     (IWR+IWM holdings, ETF/ADR exclusions)
    2. fundamentals.py → data/fundamentals.json (parallel yfinance fetch + cache)
    3. composite.py    → output/weekly_screens.json (hard gates + composite scoring)

This file replaces the prior S&P 500 / 7-screens pipeline. The new
pipeline targets U.S. mid/small-cap equities with indirect AI /
data-center / power / networking exposure.

Usage:
    python3 fetch_weekly.py [--limit N]   # limit fundamentals fetch (debug)
    python3 fetch_weekly.py --skip-universe  # reuse existing data/universe.json
    python3 fetch_weekly.py --skip-fundamentals  # reuse existing data/fundamentals.json

Requirements:
    pip3 install yfinance pandas requests tenacity
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_stage(name: str, args: list[str]) -> None:
    print(f"\n━━━ {name} ━━━")
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, args[0]), *args[1:]],
        check=False,
    )
    if result.returncode != 0:
        print(f"❌ Stage {name!r} exited with code {result.returncode}")
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap on universe size during fundamentals fetch (debug)")
    parser.add_argument("--skip-universe", action="store_true",
                        help="Reuse existing data/universe.json")
    parser.add_argument("--skip-fundamentals", action="store_true",
                        help="Reuse existing data/fundamentals.json")
    parser.add_argument("--top", type=int, default=25,
                        help="Number of conviction picks in output (default 25)")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    print(f"🚀 TickRun weekly pipeline — {started.isoformat()}")

    if not args.skip_universe:
        run_stage("Stage 1: universe", ["universe.py"])
    else:
        print("⏭ Skipping universe (using cached data/universe.json)")

    if not args.skip_fundamentals:
        fa = ["fundamentals.py"]
        if args.limit:
            fa += ["--limit", str(args.limit)]
        run_stage("Stage 2: fundamentals", fa)
    else:
        print("⏭ Skipping fundamentals (using cached data/fundamentals.json)")

    run_stage("Stage 3: composite", ["composite.py", "--top", str(args.top)])

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"\n✅ Pipeline complete in {elapsed:.0f}s")


if __name__ == "__main__":
    main()
