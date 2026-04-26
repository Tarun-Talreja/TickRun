#!/usr/bin/env python3
"""
scripts/build_dashboard.py — Assemble output/dashboard.json from all sources.

Combines:
  - data/portfolio.json    (holdings + rules)
  - data/watchlist.json    (candidates + verdicts)
  - data/themes.json       (theme definitions)
  - data/quotes_cache.json (current prices/fundamentals)
  - output/alerts.json     (pullback alerts + stale research)
  - output/earnings_calendar.json (upcoming earnings)

Writes output/dashboard.json — the single file the UI reads.
Run after refresh_quotes.py, pullback_alerts.py, earnings_calendar.py.

Usage:
    python3 scripts/build_dashboard.py
"""

import json
import os
from datetime import datetime, timezone

SCRIPT_DIR          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH      = os.path.join(SCRIPT_DIR, "data", "portfolio.json")
WATCHLIST_PATH      = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
THEMES_PATH         = os.path.join(SCRIPT_DIR, "data", "themes.json")
QUOTES_PATH         = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
ALERTS_PATH         = os.path.join(SCRIPT_DIR, "output", "alerts.json")
EARNINGS_PATH       = os.path.join(SCRIPT_DIR, "output", "earnings_calendar.json")
OUTPUT_PATH         = os.path.join(SCRIPT_DIR, "output", "dashboard.json")
os.makedirs(os.path.join(SCRIPT_DIR, "output"), exist_ok=True)


def _load(path: str, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default or {}


def _enrich_holding(holding: dict, quotes: dict) -> dict:
    ticker = holding.get("ticker", "")
    q = quotes.get("tickers", {}).get(ticker, {})
    if not q or q.get("status") != "ok":
        return {**holding, "current_price": None, "market_value": None, "pnl": None, "pnl_pct": None}

    price = q.get("price")
    shares = holding.get("shares", 0)
    cost = holding.get("cost_basis_per_share", 0)
    market_value = round(price * shares, 2) if price and shares else None
    pnl = round((price - cost) * shares, 2) if price and cost and shares else None
    pnl_pct = round((price - cost) / cost * 100, 1) if price and cost and cost > 0 else None

    return {
        **holding,
        "current_price": price,
        "market_value":  market_value,
        "pnl":           pnl,
        "pnl_pct":       pnl_pct,
        "drawdown_from_high": q.get("drawdown_from_high"),
        "pe":            q.get("pe"),
        "forward_pe":    q.get("forward_pe"),
    }


def _enrich_candidate(candidate: dict, quotes: dict) -> dict:
    ticker = candidate.get("ticker", "")
    q = quotes.get("tickers", {}).get(ticker, {})
    if not q or q.get("status") != "ok":
        return {**candidate, "price": None, "drawdown_from_high": None}

    return {
        **candidate,
        "price":             q.get("price"),
        "market_cap":        q.get("market_cap"),
        "drawdown_from_high": q.get("drawdown_from_high"),
        "revenue_growth":    q.get("revenue_growth"),
        "op_margin":         q.get("op_margin"),
        "pe":                q.get("pe"),
        "forward_pe":        q.get("forward_pe"),
    }


def main():
    portfolio = _load(PORTFOLIO_PATH)
    watchlist = _load(WATCHLIST_PATH)
    themes    = _load(THEMES_PATH)
    quotes    = _load(QUOTES_PATH)
    alerts    = _load(ALERTS_PATH)
    earnings  = _load(EARNINGS_PATH)

    # Enrich portfolio holdings with current prices + P&L
    core_enriched = [_enrich_holding(h, quotes) for h in portfolio.get("core", [])]
    thematic_enriched = [_enrich_holding(h, quotes) for h in portfolio.get("thematic", [])]

    # Total portfolio value
    total_value = sum(
        h.get("market_value") or 0
        for h in core_enriched + thematic_enriched
    )

    # Enrich watchlist candidates
    candidates_enriched = [
        _enrich_candidate(c, quotes)
        for c in watchlist.get("candidates", [])
    ]

    # Group watchlist by verdict
    by_verdict = {}
    for c in candidates_enriched:
        v = c.get("verdict", "UNKNOWN")
        by_verdict.setdefault(v, []).append(c)

    # Group watchlist by theme
    by_theme = {}
    for c in candidates_enriched:
        t = c.get("theme", "unknown")
        by_theme.setdefault(t, []).append(c)

    dashboard = {
        "last_built":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quotes_updated": quotes.get("last_updated"),
        "portfolio": {
            "total_value":  total_value,
            "core":         core_enriched,
            "thematic":     thematic_enriched,
            "target_allocation": portfolio.get("target_allocation"),
            "rules":        portfolio.get("rules"),
        },
        "watchlist": {
            "all":       candidates_enriched,
            "by_verdict": by_verdict,
            "by_theme":  by_theme,
            "counts": {
                "total":            len(candidates_enriched),
                "research_worthy":  len(by_verdict.get("RESEARCH-WORTHY", [])),
                "watchlist":        len(by_verdict.get("WATCHLIST", [])),
                "pass":             len(by_verdict.get("PASS", [])),
                "red_flag":         len(by_verdict.get("RED FLAG", [])),
            },
        },
        "themes":          themes.get("themes", {}),
        "signals": {
            "pullback_alerts":    alerts.get("pullback_alerts", []),
            "stale_research":     alerts.get("stale_research", []),
            "upcoming_earnings":  earnings.get("upcoming_earnings", []),
        },
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(dashboard, f, indent=2)

    print(f"✅ Dashboard assembled → {OUTPUT_PATH}")
    print(f"   Portfolio value:  ${total_value:,.0f}")
    print(f"   Watchlist:        {dashboard['watchlist']['counts']['total']} names")
    print(f"   Research-worthy:  {dashboard['watchlist']['counts']['research_worthy']}")
    print(f"   Pullback alerts:  {len(dashboard['signals']['pullback_alerts'])}")
    print(f"   Upcoming earnings: {len(dashboard['signals']['upcoming_earnings'])}")


if __name__ == "__main__":
    main()
