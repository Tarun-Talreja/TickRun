#!/usr/bin/env python3
"""
scripts/portfolio_analytics.py — Live P&L, allocation drift, concentration, dividends.

Reads data/portfolio.json (your holdings) + data/quotes_cache.json (live prices)
and computes everything you need AFTER you buy:

  - Per-holding P&L (market value, gain/loss $ and %)
  - Total portfolio value + total P&L
  - Allocation vs your 60/35/5 target (core/thematic/intl) with drift
  - Concentration by theme — warns when one theme exceeds CONCENTRATION_WARN
  - Projected annual dividend income (Roth = tax-free)

Output:
  output/portfolio_analytics.json  (read by build_dashboard.py / app)

Usage:
    python3 scripts/portfolio_analytics.py
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(SCRIPT_DIR, "data", "portfolio.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "output", "portfolio_analytics.json")

CONCENTRATION_WARN = 40.0   # % of invested value in one theme triggers a warning
MAX_DIV_YIELD      = 25.0   # yields above this are treated as bad data (yfinance bug)


def _load(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}


def _theme_map() -> dict:
    wl = _load(WATCHLIST_PATH, {"candidates": []})
    return {c["ticker"]: c.get("theme", "unknown") for c in wl.get("candidates", [])}


def _enrich(holding: dict, quotes: dict, themes: dict) -> dict:
    ticker = holding.get("ticker", "")
    q = quotes.get(ticker, {})
    price  = q.get("price")
    shares = holding.get("shares", 0) or 0
    cost   = holding.get("cost_basis_per_share", 0) or 0

    market_value = round(price * shares, 2) if price and shares else 0.0
    invested     = round(cost * shares, 2) if cost and shares else 0.0
    pnl          = round(market_value - invested, 2) if market_value and invested else 0.0
    pnl_pct      = round((price - cost) / cost * 100, 1) if price and cost else None

    # Dividend (guard the yfinance yield bug)
    dy = q.get("div_yield_pct")
    if dy and dy > MAX_DIV_YIELD:
        dy = None
    annual_div = round(market_value * dy / 100, 2) if dy and market_value else 0.0

    return {
        "ticker":         ticker,
        "name":           holding.get("name", ticker),
        "shares":         shares,
        "cost_basis":     cost,
        "current_price":  price,
        "market_value":   market_value,
        "invested":       invested,
        "pnl":            pnl,
        "pnl_pct":        pnl_pct,
        "pct_change_1d":  q.get("pct_change_1d"),
        "theme":          themes.get(ticker, "core"),
        "div_yield_pct":  dy,
        "annual_dividend": annual_div,
    }


def main():
    portfolio = _load(PORTFOLIO_PATH)
    quotes    = _load(QUOTES_PATH).get("tickers", {})
    themes    = _theme_map()

    core     = [_enrich(h, quotes, themes) for h in portfolio.get("core", [])]
    thematic = [_enrich(h, quotes, themes) for h in portfolio.get("thematic", [])]
    holdings = core + thematic

    invested_holdings = [h for h in holdings if h["shares"] > 0]

    total_value    = round(sum(h["market_value"] for h in holdings), 2)
    total_invested = round(sum(h["invested"] for h in holdings), 2)
    total_pnl      = round(total_value - total_invested, 2)
    total_pnl_pct  = round(total_pnl / total_invested * 100, 1) if total_invested else None
    annual_dividends = round(sum(h["annual_dividend"] for h in holdings), 2)

    # Allocation: core vs thematic (by current market value)
    core_val     = sum(h["market_value"] for h in core)
    thematic_val = sum(h["market_value"] for h in thematic)
    target = portfolio.get("target_allocation", {})
    allocation = {
        "core_pct_actual":     round(core_val / total_value * 100, 1) if total_value else 0,
        "thematic_pct_actual": round(thematic_val / total_value * 100, 1) if total_value else 0,
        "core_pct_target":     target.get("core_pct", 60),
        "thematic_pct_target": target.get("thematic_pct", 35),
    }
    allocation["core_drift"]     = round(allocation["core_pct_actual"] - allocation["core_pct_target"], 1)
    allocation["thematic_drift"] = round(allocation["thematic_pct_actual"] - allocation["thematic_pct_target"], 1)

    # Concentration by theme (only invested positions)
    theme_values = {}
    for h in invested_holdings:
        theme_values[h["theme"]] = theme_values.get(h["theme"], 0) + h["market_value"]
    concentration = []
    for theme, val in sorted(theme_values.items(), key=lambda x: -x[1]):
        pct = round(val / total_value * 100, 1) if total_value else 0
        concentration.append({
            "theme": theme, "value": round(val, 2), "pct": pct,
            "warn": pct > CONCENTRATION_WARN,
        })
    concentration_warnings = [c for c in concentration if c["warn"]]

    output = {
        "generated_at":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "funded":           total_invested > 0,
        "total_value":      total_value,
        "total_invested":   total_invested,
        "total_pnl":        total_pnl,
        "total_pnl_pct":    total_pnl_pct,
        "annual_dividends": annual_dividends,
        "cash_target":      portfolio.get("total_cash"),
        "holdings":         holdings,
        "allocation":       allocation,
        "concentration":    concentration,
        "concentration_warnings": concentration_warnings,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print("💼 PORTFOLIO ANALYTICS")
    if total_invested == 0:
        print("  No funded positions yet (shares = 0). Add real holdings to portfolio.json.")
    else:
        print(f"  Value: ${total_value:,.0f}  |  Invested: ${total_invested:,.0f}  |  P&L: ${total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)")
        print(f"  Allocation: core {allocation['core_pct_actual']}% (target {allocation['core_pct_target']}%), thematic {allocation['thematic_pct_actual']}%")
        print(f"  Projected annual dividends: ${annual_dividends:,.0f} (tax-free in Roth)")
        for w in concentration_warnings:
            print(f"  ⚠ Concentration: {w['theme']} is {w['pct']}% of portfolio (>{CONCENTRATION_WARN}%)")
    print(f"\n✅ Analytics → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
