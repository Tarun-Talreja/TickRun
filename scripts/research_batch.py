#!/usr/bin/env python3
"""
scripts/research_batch.py — Run daily LLM research on the highest-priority names.

Re-researches RESEARCH-WORTHY and WATCHLIST candidates that are either:
  - Stale (last_researched > STALE_DAYS ago), OR
  - Showing a fresh pullback alert (drawdown <= ALERT_THRESHOLD)

Uses research_ticker.py's provider logic (NVIDIA NIM free by default).
Skips PASS verdicts and index benchmarks. Caps the run to MAX_PER_RUN
tickers so the daily job stays within free-tier rate limits.

Usage:
    export NVIDIA_API_KEY=nvapi-...
    python3 scripts/research_batch.py
    python3 scripts/research_batch.py --max 5
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
RESEARCH_SCRIPT = os.path.join(SCRIPT_DIR, "scripts", "research_ticker.py")

STALE_DAYS      = 7      # re-research if older than this
ALERT_THRESHOLD = -20.0  # drawdown that forces a re-research
MAX_PER_RUN     = 6      # cap per daily run to respect free-tier limits


def _days_since(date_str: str | None) -> int:
    if not date_str:
        return 9999
    try:
        d = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days
    except ValueError:
        return 9999


def _select_tickers(max_n: int) -> list[str]:
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)
    quotes = {}
    if os.path.exists(QUOTES_PATH):
        with open(QUOTES_PATH) as f:
            quotes = json.load(f).get("tickers", {})

    scored = []
    for c in wl.get("candidates", []):
        ticker = c.get("ticker", "")
        verdict = c.get("verdict", "")
        if ticker.startswith("^") or verdict == "PASS":
            continue
        if verdict not in ("RESEARCH-WORTHY", "WATCHLIST"):
            continue

        drawdown = quotes.get(ticker, {}).get("drawdown_from_high")
        stale_days = _days_since(c.get("last_researched"))

        # Priority score: bigger = more urgent
        score = 0
        if verdict == "RESEARCH-WORTHY":
            score += 100
        if drawdown is not None and drawdown <= ALERT_THRESHOLD:
            score += 50
        score += min(stale_days, 30)   # staleness adds up to 30

        # Only include if stale OR freshly dipping
        if stale_days >= STALE_DAYS or (drawdown is not None and drawdown <= ALERT_THRESHOLD):
            scored.append((score, ticker))

    scored.sort(reverse=True)
    return [t for _, t in scored[:max_n]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=MAX_PER_RUN,
                        help=f"Max tickers to research (default {MAX_PER_RUN})")
    args = parser.parse_args()

    if not (os.environ.get("NVIDIA_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        print("⚠ No NVIDIA_API_KEY or ANTHROPIC_API_KEY set — skipping daily research.")
        sys.exit(0)   # exit 0 so the workflow doesn't fail

    tickers = _select_tickers(args.max)
    if not tickers:
        print("✅ No tickers need re-research today.")
        sys.exit(0)

    print(f"🔬 Daily research queue ({len(tickers)}): {', '.join(tickers)}\n")
    failures = []
    for ticker in tickers:
        print(f"── {ticker} " + "─" * 40)
        result = subprocess.run(
            [sys.executable, RESEARCH_SCRIPT, ticker],
            cwd=SCRIPT_DIR,
        )
        if result.returncode != 0:
            failures.append(ticker)

    print(f"\n✅ Researched {len(tickers) - len(failures)}/{len(tickers)} tickers.")
    if failures:
        print(f"⚠ Failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
