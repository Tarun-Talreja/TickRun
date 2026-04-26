#!/usr/bin/env python3
"""
scripts/earnings_calendar.py — Next earnings dates for portfolio + watchlist.

Reads data/quotes_cache.json and surfaces earnings reports due in the
next LOOKAHEAD_DAYS days. Before earnings, you should:
  1. Re-read your thesis — does the upcoming quarter prove or disprove it?
  2. Decide if you're holding through (recommended for long-term) or trimming
  3. After earnings, re-run research_ticker.py to update the verdict

Usage:
    python3 scripts/earnings_calendar.py

Outputs:
    Writes to output/earnings_calendar.json
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "output", "earnings_calendar.json")
os.makedirs(os.path.join(SCRIPT_DIR, "output"), exist_ok=True)

LOOKAHEAD_DAYS = 30


def main():
    if not os.path.exists(QUOTES_PATH):
        print("No quotes cache. Run: python3 scripts/refresh_quotes.py first.")
        sys.exit(1)

    with open(QUOTES_PATH) as f:
        quotes = json.load(f)
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)

    today = datetime.now(timezone.utc)
    deadline = today + timedelta(days=LOOKAHEAD_DAYS)
    candidates = {c["ticker"]: c for c in wl.get("candidates", [])}
    tickers_data = quotes.get("tickers", {})

    upcoming = []
    for ticker, q in tickers_data.items():
        ts = q.get("next_earnings")
        if not ts:
            continue
        try:
            # yfinance returns Unix timestamp
            if isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                dt = datetime.fromisoformat(str(ts)).replace(tzinfo=timezone.utc)
        except (ValueError, OSError):
            continue

        if today <= dt <= deadline:
            days_until = (dt - today).days
            candidate = candidates.get(ticker, {})
            upcoming.append({
                "ticker":      ticker,
                "name":        q.get("name", ticker),
                "date":        dt.strftime("%Y-%m-%d"),
                "days_until":  days_until,
                "theme":       candidate.get("theme", "unknown"),
                "verdict":     candidate.get("verdict", "UNKNOWN"),
                "thesis":      candidate.get("thesis", ""),
                "action":      f"Review thesis before earnings. Re-run research_ticker.py {ticker} after.",
            })

    upcoming.sort(key=lambda x: x["days_until"])

    output = {
        "generated_at":    today.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookahead_days":  LOOKAHEAD_DAYS,
        "upcoming_earnings": upcoming,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    if upcoming:
        print(f"\n📅 {len(upcoming)} earnings in next {LOOKAHEAD_DAYS} days:")
        for e in upcoming:
            print(f"  {e['date']} ({e['days_until']}d) — {e['ticker']} [{e['verdict']}]")
    else:
        print(f"No earnings in next {LOOKAHEAD_DAYS} days for your watchlist.")

    print(f"\n✅ Calendar → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
