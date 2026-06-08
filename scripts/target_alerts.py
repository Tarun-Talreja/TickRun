#!/usr/bin/env python3
"""
scripts/target_alerts.py — Flag watchlist names that hit your buy_target.

You've set buy_target on each candidate. This checks live prices and surfaces
any name now trading at or below its target (within a small tolerance), so you
get told "VST hit $148" instead of watching prices yourself.

Output:
  data/target_alerts.json  (read by build_dashboard.py)

Usage:
    python3 scripts/target_alerts.py
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "data", "target_alerts.json")

TOLERANCE = 0.03   # within 3% of target counts as "hit"


def _load(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}


def main():
    wl     = _load(WATCHLIST_PATH, {"candidates": []})
    quotes = _load(QUOTES_PATH).get("tickers", {})

    hits = []
    approaching = []
    for c in wl.get("candidates", []):
        ticker = c.get("ticker", "")
        target = c.get("buy_target")
        verdict = c.get("verdict", "")
        if not target or verdict in ("PASS", "RED FLAG"):
            continue
        q = quotes.get(ticker, {})
        price = q.get("price")
        if not price:
            continue

        gap_pct = round((price - target) / target * 100, 1)
        rec = {
            "ticker":     ticker,
            "name":       c.get("name", ticker),
            "verdict":    verdict,
            "confidence": c.get("confidence"),
            "theme":      c.get("theme"),
            "price":      price,
            "buy_target": target,
            "gap_pct":    gap_pct,
            "next_action": c.get("next_action", ""),
        }
        if price <= target * (1 + TOLERANCE):
            hits.append(rec)
        elif price <= target * 1.10:   # within 10% above target
            approaching.append(rec)

    hits.sort(key=lambda x: x["gap_pct"])
    approaching.sort(key=lambda x: x["gap_pct"])

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hits":         hits,
        "approaching":  approaching,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    if hits:
        print(f"🎯 {len(hits)} name(s) AT or BELOW buy target:")
        for h in hits:
            print(f"  {h['ticker']} ${h['price']} (target ${h['buy_target']}, {h['gap_pct']:+.1f}%) [{h['verdict']}]")
    else:
        print("No names at buy target right now.")
    if approaching:
        print(f"\n👀 {len(approaching)} approaching (within 10%): {', '.join(a['ticker'] for a in approaching)}")
    print(f"\n✅ Target alerts → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
