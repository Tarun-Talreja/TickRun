#!/usr/bin/env python3
"""
scripts/hedge_fund_signal.py — Track name-brand hedge fund positions in watchlist tickers.

Uses yfinance institutional_holders (Yahoo Finance / 13F proxy).
On each run, diffs against the previous snapshot to surface NEW positions
by conviction funds — the most actionable signal.

Output:
  data/hedge_fund_signals.json  — current signals (read by build_dashboard.py)
  data/hedge_fund_snapshot.json — previous-run holder set (for new-position diffing)

Schedule: Quarterly — ~45 days after each quarter end.
    Q4 → Feb 15 | Q1 → May 15 | Q2 → Aug 15 | Q3 → Nov 15

Usage:
    python3 scripts/hedge_fund_signal.py
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Missing dependency: pip install yfinance")
    sys.exit(1)

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "data", "hedge_fund_signals.json")
SNAPSHOT_PATH  = os.path.join(SCRIPT_DIR, "data", "hedge_fund_snapshot.json")

# Name-brand conviction funds (substring match, case-insensitive)
CONVICTION_FUNDS = {
    "Pershing Square":  "Bill Ackman",
    "Duquesne":         "Stanley Druckenmiller",
    "Greenlight":       "David Einhorn",
    "Berkshire":        "Warren Buffett",
    "Third Point":      "Dan Loeb",
    "Baupost":          "Seth Klarman",
    "Coatue":           "Philippe Laffont",
    "Viking Global":    "Andreas Halvorsen",
    "Appaloosa":        "David Tepper",
    "Tiger Global":     "Chase Coleman",
    "ValueAct":         "Jeff Ubben",
    "Starboard Value":  "Jeff Smith (activist)",
    "Elliott":          "Paul Singer (activist)",
    "Soros Fund":       "George Soros",
    "Lone Pine":        "Steve Mandel",
    "Maverick":         "Lee Ainslie",
    "Dragoneer":        "Marc Stad",
    "Altimeter":        "Brad Gerstner",
}


def _match_fund(holder_name: str) -> str | None:
    """Return manager name if holder matches a conviction fund, else None."""
    hn = holder_name.upper()
    for key, manager in CONVICTION_FUNDS.items():
        if key.upper() in hn:
            return manager
    return None


def _fetch_one(ticker: str) -> dict:
    base = {
        "ticker":            ticker,
        "status":            "no_data",
        "top_holders":       [],
        "conviction_holders": [],
        "fetched_at":        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        t = yf.Ticker(ticker)
        df = t.institutional_holders
        if df is None or (hasattr(df, "empty") and df.empty):
            return base

        holders = []
        for _, row in df.iterrows():
            holder  = str(row.get("Holder",       row.get("holder", "")))
            shares  = row.get("Shares",            row.get("shares", None))
            pct     = row.get("% Out",             row.get("pctOut", row.get("pct_out", None)))
            value   = row.get("Value",             row.get("value", None))
            date_r  = str(row.get("Date Reported", row.get("dateReported", "")))

            manager = _match_fund(holder)

            holders.append({
                "holder":              holder,
                "shares":              int(shares) if shares is not None and pd.notna(shares) else None,
                "pct_out":             float(pct) if pct is not None and pd.notna(pct) else None,
                "value_usd":           float(value) if value is not None and pd.notna(value) else None,
                "date_reported":       date_r,
                "is_conviction_fund":  manager is not None,
                "manager":             manager,
            })

        conviction = [h for h in holders if h["is_conviction_fund"]]

        return {
            "ticker":            ticker,
            "status":            "ok",
            "top_holders":       holders[:10],
            "conviction_holders": conviction,
            "fetched_at":        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except Exception as exc:
        return {**base, "status": "error", "error": str(exc)}


def _load_snapshot() -> dict:
    if os.path.exists(SNAPSHOT_PATH):
        with open(SNAPSHOT_PATH) as f:
            return json.load(f)
    return {}


def _save_snapshot(results: dict):
    snapshot = {
        ticker: {
            "conviction_fund_names": [h["holder"] for h in data.get("conviction_holders", [])]
        }
        for ticker, data in results.items()
    }
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)


def _detect_new_positions(ticker: str, conviction_holders: list, snapshot: dict) -> list:
    """Return conviction holders that are NEW vs last snapshot. Empty on first run."""
    if not snapshot:
        return []
    prev_names = set(snapshot.get(ticker, {}).get("conviction_fund_names", []))
    return [h for h in conviction_holders if h["holder"] not in prev_names]


def main():
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)

    tickers = [c["ticker"] for c in wl.get("candidates", []) if c.get("verdict") != "PASS"]
    if not tickers:
        print("No active tickers in watchlist.")
        sys.exit(0)

    snapshot = _load_snapshot()
    is_first_run = not snapshot

    print(f"Fetching institutional holders for {len(tickers)} tickers: {', '.join(tickers)}")
    results = {}

    for i, ticker in enumerate(tickers, 1):
        rec = _fetch_one(ticker)
        n_conviction = len(rec.get("conviction_holders", []))
        new_pos = _detect_new_positions(ticker, rec.get("conviction_holders", []), snapshot)
        rec["new_positions"] = new_pos
        results[ticker] = rec

        icon = "🟢" if new_pos else ("⭐" if n_conviction > 0 else "—")
        detail = f"{n_conviction} conviction fund(s)"
        if new_pos:
            detail += f" | NEW: {', '.join(h['holder'][:30] for h in new_pos)}"
        print(f"  [{i:2d}/{len(tickers)}] {ticker:8s} {icon}  {detail}")
        time.sleep(0.5)

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "first_run":    is_first_run,
        "tickers":      results,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    _save_snapshot(results)

    all_conviction = [(t, h) for t, r in results.items() for h in r.get("conviction_holders", [])]
    new_positions  = [(t, h) for t, r in results.items() for h in r.get("new_positions", [])]

    print(f"\n✅ Hedge fund signals → {OUTPUT_PATH}")
    if is_first_run:
        print("   (First run — snapshot saved; new-position detection starts next quarter)")
    if new_positions:
        print("   🟢 NEW positions detected:")
        for ticker, h in new_positions:
            print(f"      {ticker}: {h['holder']} ({h.get('manager', '?')}) — {h.get('shares', '?'):,} shares")
    if all_conviction:
        print("   ⭐ Conviction fund holders:")
        for ticker, h in all_conviction:
            print(f"      {ticker}: {h['manager']} ({h['holder']})")
    if not all_conviction:
        print("   No name-brand fund holdings found in current watchlist.")


if __name__ == "__main__":
    main()
