#!/usr/bin/env python3
"""
scripts/track_record.py — Did the app's calls actually work?

Records the price at the time each verdict was assigned, then measures the
return since. Over weeks/months this answers the trust question:
"Are RESEARCH-WORTHY calls actually going up?"

State:
  data/verdict_history.json  — committed log of {ticker, verdict, date, entry_price}

Output:
  output/track_record.json   — per-call returns + aggregate scoreboard

Note: history starts accumulating from the first run. Early numbers are sparse —
that's honest. The scoreboard gets meaningful after a few weeks.

Usage:
    python3 scripts/track_record.py
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
HISTORY_PATH   = os.path.join(SCRIPT_DIR, "data", "verdict_history.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "output", "track_record.json")

TRACK_VERDICTS = ("RESEARCH-WORTHY", "WATCHLIST")


def _load(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}


def main():
    wl      = _load(WATCHLIST_PATH, {"candidates": []})
    quotes  = _load(QUOTES_PATH).get("tickers", {})
    history = _load(HISTORY_PATH, {"entries": []})
    entries = history.get("entries", [])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Index existing entries by (ticker, verdict, date_assigned)
    seen = {(e["ticker"], e["verdict"], e["date"]) for e in entries}

    # Record a new entry when a ticker carries a tracked verdict and its
    # last_researched date isn't already logged.
    for c in wl.get("candidates", []):
        ticker  = c.get("ticker", "")
        verdict = c.get("verdict", "")
        researched = c.get("last_researched")
        if verdict not in TRACK_VERDICTS or not researched:
            continue
        q = quotes.get(ticker, {})
        price = q.get("price")
        if not price:
            continue
        key = (ticker, verdict, researched)
        if key not in seen:
            entries.append({
                "ticker":      ticker,
                "verdict":     verdict,
                "date":        researched,
                "entry_price": price,
                "confidence":  c.get("confidence"),
            })
            seen.add(key)

    # Compute return since entry for each logged call
    scored = []
    for e in entries:
        q = quotes.get(e["ticker"], {})
        cur = q.get("price")
        if not cur or not e.get("entry_price"):
            continue
        ret = round((cur - e["entry_price"]) / e["entry_price"] * 100, 1)
        scored.append({**e, "current_price": cur, "return_pct": ret})

    # Aggregate scoreboard by verdict
    def _agg(verdict):
        rows = [s for s in scored if s["verdict"] == verdict]
        if not rows:
            return {"count": 0, "avg_return": None, "win_rate": None}
        avg = round(sum(r["return_pct"] for r in rows) / len(rows), 1)
        wins = sum(1 for r in rows if r["return_pct"] > 0)
        return {
            "count": len(rows),
            "avg_return": avg,
            "win_rate": round(wins / len(rows) * 100),
            "best": max(rows, key=lambda r: r["return_pct"]),
            "worst": min(rows, key=lambda r: r["return_pct"]),
        }

    scoreboard = {v: _agg(v) for v in TRACK_VERDICTS}

    # Persist history (committed) + output scoreboard
    with open(HISTORY_PATH, "w") as f:
        json.dump({"updated": today, "entries": entries}, f, indent=2)

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tracked_since": min((e["date"] for e in entries), default=today),
        "scoreboard":   scoreboard,
        "calls":        sorted(scored, key=lambda s: s["return_pct"], reverse=True),
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print("📈 TRACK RECORD")
    for v in TRACK_VERDICTS:
        s = scoreboard[v]
        if s["count"]:
            print(f"  {v}: {s['count']} calls, avg {s['avg_return']:+.1f}%, win rate {s['win_rate']}%")
        else:
            print(f"  {v}: no calls logged yet")
    print(f"  Tracked since: {out['tracked_since']}")
    print(f"\n✅ Track record → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
