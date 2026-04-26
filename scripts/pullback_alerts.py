#!/usr/bin/env python3
"""
scripts/pullback_alerts.py — Flag watchlist names with significant pullbacks.

Reads data/quotes_cache.json and data/watchlist.json, identifies candidates
whose price has dropped >ALERT_THRESHOLD% from their 52-week high, and
writes deployment-opportunity alerts to output/dashboard.json (alerts section).

Logic: A pullback on a RESEARCH-WORTHY or WATCHLIST name = potential entry point.
A pullback on a PASS name = irrelevant. A pullback on RED FLAG = do not deploy.

Usage:
    python3 scripts/pullback_alerts.py

Outputs:
    Writes alerts to output/alerts.json (merged into dashboard.json by build_dashboard.py)
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "output", "alerts.json")
os.makedirs(os.path.join(SCRIPT_DIR, "output"), exist_ok=True)

ALERT_THRESHOLD   = -20.0   # % drawdown from 52-week high to trigger alert
EXTREME_THRESHOLD = -35.0   # deeper drawdown = "strong opportunity" signal
STALE_RESEARCH_DAYS = 90    # flag names not researched in this many days


def main():
    if not os.path.exists(QUOTES_PATH):
        print("No quotes cache. Run: python3 scripts/refresh_quotes.py first.")
        sys.exit(1)

    with open(QUOTES_PATH) as f:
        quotes = json.load(f)
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)

    today = datetime.now(timezone.utc)
    tickers_data = quotes.get("tickers", {})
    candidates = {c["ticker"]: c for c in wl.get("candidates", [])}

    pullback_alerts = []
    stale_research  = []

    for ticker, q in tickers_data.items():
        if q.get("status") != "ok":
            continue

        candidate = candidates.get(ticker, {})
        verdict = candidate.get("verdict", "UNKNOWN")

        # Skip PASS and unknown names for pullback alerts
        if verdict in ("PASS", "UNKNOWN"):
            continue

        drawdown = q.get("drawdown_from_high")
        if drawdown is None:
            continue

        if drawdown <= ALERT_THRESHOLD:
            severity = "STRONG" if drawdown <= EXTREME_THRESHOLD else "MODERATE"
            pullback_alerts.append({
                "ticker":       ticker,
                "name":         q.get("name", ticker),
                "theme":        candidate.get("theme", "unknown"),
                "verdict":      verdict,
                "price":        q.get("price"),
                "high_52w":     q.get("high_52w"),
                "drawdown_pct": drawdown,
                "severity":     severity,
                "thesis":       candidate.get("thesis", ""),
                "action":       "Consider deploying if thesis intact. Verify with research_ticker.py first.",
            })

        # Flag stale research (> STALE_RESEARCH_DAYS without a re-run)
        last_researched = candidate.get("last_researched")
        if last_researched and verdict in ("RESEARCH-WORTHY", "WATCHLIST"):
            try:
                last_dt = datetime.fromisoformat(last_researched)
                days_since = (today - last_dt.replace(tzinfo=timezone.utc)).days
                if days_since > STALE_RESEARCH_DAYS:
                    stale_research.append({
                        "ticker":       ticker,
                        "last_researched": last_researched,
                        "days_since":   days_since,
                        "verdict":      verdict,
                        "action":       f"Re-run: python3 scripts/research_ticker.py {ticker}",
                    })
            except ValueError:
                pass

    # Sort by severity and then deepest drawdown
    pullback_alerts.sort(key=lambda x: (x["severity"] != "STRONG", x["drawdown_pct"]))

    output = {
        "generated_at":   today.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pullback_alerts": pullback_alerts,
        "stale_research":  stale_research,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    if pullback_alerts:
        print(f"\n🔔 {len(pullback_alerts)} pullback alert(s):")
        for a in pullback_alerts:
            print(f"  [{a['severity']}] {a['ticker']} — {a['drawdown_pct']:.1f}% from 52w high (verdict: {a['verdict']})")
    else:
        print("No pullback alerts today.")

    if stale_research:
        print(f"\n⏰ {len(stale_research)} name(s) need re-research (>{STALE_RESEARCH_DAYS} days):")
        for s in stale_research:
            print(f"  {s['ticker']} — last researched {s['last_researched']} ({s['days_since']} days ago)")

    print(f"\n✅ Alerts → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
