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
INSIDER_PATH        = os.path.join(SCRIPT_DIR, "data", "insider_signals.json")
HEDGE_FUND_PATH     = os.path.join(SCRIPT_DIR, "data", "hedge_fund_signals.json")
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


def _cap_tier(market_cap) -> str:
    """Classify by market cap: mega >$100B, large $10-100B, mid $1-10B, small <$1B."""
    if market_cap is None:
        return "unknown"
    if market_cap >= 100e9:
        return "mega"
    if market_cap >= 10e9:
        return "large"
    if market_cap >= 1e9:
        return "mid"
    return "small"


def _enrich_candidate(candidate: dict, quotes: dict, insider_signals: dict, hedge_fund_signals: dict) -> dict:
    ticker = candidate.get("ticker", "")
    q = quotes.get("tickers", {}).get(ticker, {})
    insider = insider_signals.get("tickers", {}).get(ticker, {})
    hf = hedge_fund_signals.get("tickers", {}).get(ticker, {})

    enriched = {**candidate}

    if q and q.get("status") == "ok":
        mcap     = q.get("market_cap")
        drawdown = q.get("drawdown_from_high")
        tier     = _cap_tier(mcap)

        enriched.update({
            "price":               q.get("price"),
            "market_cap":          mcap,
            "cap_tier":            tier,
            "drawdown_from_high":  drawdown,
            "revenue_growth":      q.get("revenue_growth"),
            "op_margin":           q.get("op_margin"),
            "pe":                  q.get("pe"),
            "forward_pe":          q.get("forward_pe"),
            "short_percent_float": q.get("short_percent_float"),
            "short_ratio":         q.get("short_ratio"),
        })

        # Tiered 52-week high gate thresholds
        # Mega-caps get a more lenient gate (-15%) because they're stable businesses
        # that rarely fall >15% — when they do it's a genuine sale event.
        gate_pct = -15 if tier == "mega" else -10
        soft_pct = -25 if tier == "mega" else -20

        if drawdown is not None and drawdown > gate_pct and enriched.get("verdict") == "RESEARCH-WORTHY":
            enriched["verdict"] = "WATCHLIST"
            enriched["high_proximity_warning"] = True
            enriched["high_proximity_note"] = (
                f"Within {abs(drawdown):.1f}% of 52-week high — WAIT for pullback"
            )
        elif drawdown is not None and drawdown > soft_pct:
            enriched["high_proximity_warning"] = True
            enriched["high_proximity_note"] = (
                f"Only {abs(drawdown):.1f}% from 52-week high — entry timing risk"
            )
        else:
            enriched["high_proximity_warning"] = False
    else:
        enriched.update({
            "price": None, "drawdown_from_high": None, "cap_tier": "unknown",
            "short_percent_float": None, "short_ratio": None,
            "high_proximity_warning": False,
        })

    # Insider signals
    if insider and insider.get("signal") not in ("NO_DATA", "ERROR", None):
        enriched.update({
            "insider_signal": insider.get("signal"),
            "insider_note":   insider.get("note"),
            "insider_buys":   insider.get("buys"),
            "insider_sells":  insider.get("sells"),
        })

    # Hedge fund signals
    if hf and hf.get("status") == "ok":
        enriched.update({
            "conviction_holders": hf.get("conviction_holders", []),
            "hf_new_positions":   hf.get("new_positions", []),
        })

    return enriched


def main():
    portfolio = _load(PORTFOLIO_PATH)
    watchlist = _load(WATCHLIST_PATH)
    themes    = _load(THEMES_PATH)
    quotes    = _load(QUOTES_PATH)
    insider    = _load(INSIDER_PATH)
    hedge_fund = _load(HEDGE_FUND_PATH)
    alerts     = _load(ALERTS_PATH)
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
        _enrich_candidate(c, quotes, insider, hedge_fund)
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
            "insider_alerts": [
                {
                    "ticker":  c["ticker"],
                    "name":    c.get("name", c["ticker"]),
                    "signal":  c.get("insider_signal"),
                    "note":    c.get("insider_note"),
                    "buys":    c.get("insider_buys", 0),
                    "sells":   c.get("insider_sells", 0),
                    "verdict": c.get("verdict"),
                }
                for c in candidates_enriched
                if c.get("insider_signal") in ("RED_FLAG", "BEARISH")
            ],
            "short_interest_alerts": [
                {
                    "ticker":       c["ticker"],
                    "name":         c.get("name", c["ticker"]),
                    "short_pct":    c.get("short_percent_float"),
                    "short_ratio":  c.get("short_ratio"),
                    "verdict":      c.get("verdict"),
                }
                for c in candidates_enriched
                if c.get("short_percent_float") and c["short_percent_float"] > 10
            ],
            "hedge_fund_alerts": [
                {
                    "ticker":         c["ticker"],
                    "name":           c.get("name", c["ticker"]),
                    "verdict":        c.get("verdict"),
                    "new_positions":  c.get("hf_new_positions", []),
                    "all_conviction": c.get("conviction_holders", []),
                }
                for c in candidates_enriched
                if c.get("hf_new_positions") or c.get("conviction_holders")
            ],
            "mega_cap_on_sale": [
                {
                    "ticker":       c["ticker"],
                    "name":         c.get("name", c["ticker"]),
                    "drawdown_pct": c.get("drawdown_from_high"),
                    "price":        c.get("price"),
                    "pe":           c.get("pe"),
                    "forward_pe":   c.get("forward_pe"),
                    "verdict":      c.get("verdict"),
                    "next_action":  c.get("next_action"),
                }
                for c in candidates_enriched
                if c.get("cap_tier") == "mega"
                and c.get("drawdown_from_high") is not None
                and c["drawdown_from_high"] <= -15
            ],
        },
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(dashboard, f, indent=2)

    print(f"✅ Dashboard assembled → {OUTPUT_PATH}")
    print(f"   Portfolio value:  ${total_value:,.0f}")
    print(f"   Watchlist:        {dashboard['watchlist']['counts']['total']} names")
    print(f"   Research-worthy:  {dashboard['watchlist']['counts']['research_worthy']}")
    print(f"   Pullback alerts:   {len(dashboard['signals']['pullback_alerts'])}")
    print(f"   Upcoming earnings: {len(dashboard['signals']['upcoming_earnings'])}")
    print(f"   Mega-cap on sale:  {len(dashboard['signals']['mega_cap_on_sale'])}")


if __name__ == "__main__":
    main()
