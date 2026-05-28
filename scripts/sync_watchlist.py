#!/usr/bin/env python3
"""
scripts/sync_watchlist.py — Sync watchlist.md tickers into data/watchlist.json.

watchlist.md is the source of truth for WHICH tickers to track.
This script reads it, adds stubs for new tickers, and removes entries
for tickers you've deleted from the file.

Existing entries in data/watchlist.json keep their hand-curated
thesis, verdict, and buy_target intact — only new tickers get stubs.

Run this first in the pipeline so refresh_quotes.py and build_dashboard.py
pick up all tickers.

Usage:
    python3 scripts/sync_watchlist.py
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_MD   = os.path.join(SCRIPT_DIR, "watchlist.md")
WATCHLIST_JSON = os.path.join(SCRIPT_DIR, "data", "watchlist.json")


def parse_watchlist_md(path: str) -> list[str]:
    """Extract ticker symbols from watchlist.md, ignoring headers and comments."""
    tickers = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Valid ticker: 1-5 uppercase letters, optionally ^TICKER or with dots
            if re.match(r"^[\^]?[A-Z][A-Z0-9.\-]{0,9}$", line):
                tickers.append(line)
    return tickers


def infer_theme(ticker: str) -> str:
    """Rough theme guess from ticker — can be corrected in watchlist.json."""
    mega_cap = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"}
    power    = {"NEE", "AES", "ETN", "POWL", "EATON"}
    nuclear  = {"BWXT", "CEG", "VST", "NRG"}
    ai_semi  = {"AMD", "AVGO", "ALAB", "ONTO", "ASML", "TSM", "QCOM", "MRVL", "ARM"}
    cyber    = {"CRWD", "PANW", "FTNT", "ZS", "QLYS", "S", "OKTA"}
    platform = {"UBER", "ABNB", "LYFT", "SHOP", "SQ", "PYPL"}
    if ticker in mega_cap:
        return "mega_cap_ai"
    if ticker in ai_semi:
        return "edge_ai_silicon"
    if ticker in cyber:
        return "cybersecurity"
    if ticker in nuclear:
        return "nuclear_smr"
    if ticker in power:
        return "power_grid"
    if ticker in platform:
        return "platform_network"
    return "uncategorized"


def make_stub(ticker: str) -> dict:
    return {
        "ticker":         ticker,
        "name":           ticker,
        "theme":          infer_theme(ticker),
        "status":         "monitoring",
        "thesis":         "",
        "added":          datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "verdict":        "WATCHLIST",
        "buy_target":     None,
        "current_price":  None,
        "next_action":    "Run research_ticker.py to generate thesis and verdict.",
        "research_file":  None,
        "last_researched": None,
    }


def main():
    if not os.path.exists(WATCHLIST_MD):
        print(f"No watchlist.md found at {WATCHLIST_MD}")
        sys.exit(1)

    md_tickers = parse_watchlist_md(WATCHLIST_MD)
    if not md_tickers:
        print("watchlist.md has no valid tickers.")
        sys.exit(0)

    # Load existing watchlist.json
    if os.path.exists(WATCHLIST_JSON):
        with open(WATCHLIST_JSON) as f:
            wl = json.load(f)
    else:
        wl = {"last_updated": None, "candidates": []}

    existing = {c["ticker"]: c for c in wl.get("candidates", [])}
    md_set   = set(md_tickers)

    # Add stubs for tickers in watchlist.md but not in watchlist.json
    added = []
    for ticker in md_tickers:
        if ticker not in existing:
            existing[ticker] = make_stub(ticker)
            added.append(ticker)

    # Remove tickers no longer in watchlist.md
    removed = [t for t in list(existing.keys()) if t not in md_set]
    for t in removed:
        del existing[t]

    # Preserve original order from watchlist.md, then any extras
    ordered = [existing[t] for t in md_tickers if t in existing]

    wl["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    wl["candidates"]   = ordered

    with open(WATCHLIST_JSON, "w") as f:
        json.dump(wl, f, indent=2)

    print(f"✅ Synced watchlist.md → data/watchlist.json")
    print(f"   Tickers tracked: {len(ordered)}")
    if added:
        print(f"   Added stubs:     {', '.join(added)}")
    if removed:
        print(f"   Removed:         {', '.join(removed)}")
    if not added and not removed:
        print("   No changes.")


if __name__ == "__main__":
    main()
