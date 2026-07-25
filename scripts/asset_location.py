#!/usr/bin/env python3
"""
scripts/asset_location.py — Which account should each holding live in?

You hold two accounts: a Roth IRA (growth is never taxed) and a taxable
brokerage. Asset location is the decision of WHICH account holds WHICH asset.
Done well it is free return — same holdings, less tax drag, no extra risk.

The governing principle is tax DRAG, not volatility: put the assets that would
be taxed hardest in the account where tax does not apply.

  ROTH (shelter the tax-inefficient)
    - High-growth individual convictions — the biggest compounder should sit
      where the gain is never taxed.
    - REITs — their distributions are largely NON-qualified, taxed at ordinary
      income rates. The single most tax-inefficient common asset class.
    - High dividend payers — a yield you cannot defer is taxed every year in a
      taxable account whether or not you sell.

  TAXABLE (already tax-efficient, or needed for liquidity)
    - Broad-market index ETFs — low turnover, mostly qualified dividends, and
      they carry their own built-in tax efficiency.
    - Anything you might need to sell before 59.5, since Roth earnings are not
      freely withdrawable.

NOTE ON ONE REFINEMENT: a plain "boring goes taxable" rule would send REITs and
high-yield defensives to the taxable account. That is backwards — those are
boring AND highly tax-inefficient, so the yield gets taxed annually for as long
as it is held. Volatility is not the criterion; taxability is. This script
flags those cases explicitly rather than following the simpler rule.

Output:
  data/asset_location.json   (read by build_dashboard.py)

Usage:
    python3 scripts/asset_location.py
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "data", "asset_location.json")

# Broad-market index funds — tax-efficient by construction, and the natural
# place to hold liquidity you may need before retirement age.
BROAD_MARKET_ETFS = {"VOO", "VTI", "SPY", "QQQ", "IVV", "VXUS", "VEA", "VWO", "SCHD", "DIA", "IWM"}

# Yield above which annual dividend taxation becomes the dominant consideration.
HIGH_YIELD_PCT = 3.0
# Yields above this are treated as bad data rather than trusted.
MAX_PLAUSIBLE_YIELD = 25.0


def _load(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}


def _classify(candidate: dict, quote: dict) -> dict:
    ticker  = candidate.get("ticker", "")
    theme   = candidate.get("theme", "")
    verdict = candidate.get("verdict", "")

    dy = quote.get("div_yield_pct")
    if dy is not None and (dy < 0 or dy > MAX_PLAUSIBLE_YIELD):
        dy = None   # implausible — don't let bad data drive a tax decision

    growth = quote.get("revenue_growth")

    # Rules are ordered by how decisive the tax consequence is.
    if ticker in BROAD_MARKET_ETFS:
        return {
            "account": "TAXABLE", "priority": "high",
            "reason": "Broad-market index fund — low turnover and mostly qualified "
                      "dividends make it tax-efficient on its own. Holding it here "
                      "preserves Roth space for assets that actually need shelter, "
                      "and keeps it available before 59.5.",
        }

    if theme == "real_estate":
        return {
            "account": "ROTH", "priority": "high",
            "reason": "REIT — distributions are largely non-qualified and taxed as "
                      "ordinary income, making this the most tax-inefficient asset "
                      "class you hold. Sheltering it is worth more than sheltering "
                      "an equivalent amount of growth stock.",
        }

    if dy is not None and dy >= HIGH_YIELD_PCT:
        return {
            "account": "ROTH", "priority": "high",
            "reason": f"{dy:.1f}% yield is taxed every year in a taxable account "
                      f"whether or not you sell — there is no deferral. Note this "
                      f"overrides the 'boring goes taxable' instinct: the criterion "
                      f"is taxability, not volatility.",
        }

    if verdict == "RESEARCH-WORTHY":
        g = f" ({growth:.0f}% revenue growth)" if isinstance(growth, (int, float)) else ""
        return {
            "account": "ROTH", "priority": "high",
            "reason": f"Highest-conviction growth pick{g} — the names most likely to "
                      f"compound hardest belong where the gain is never taxed.",
        }

    return {
        "account": "ROTH", "priority": "medium",
        "reason": "Individual stock held for long-term gains — capital gains and any "
                  "dividends go untaxed in the Roth. Default for single-name picks.",
    }


def main():
    wl = _load(WATCHLIST_PATH, {"candidates": []})
    quotes = _load(QUOTES_PATH).get("tickers", {})

    placements = []
    for c in wl.get("candidates", []):
        ticker = c.get("ticker", "")
        if ticker.startswith("^") or c.get("verdict") == "PASS":
            continue
        q = quotes.get(ticker, {})
        cls = _classify(c, q)
        placements.append({
            "ticker": ticker,
            "name": c.get("name", ticker),
            "theme": c.get("theme"),
            "verdict": c.get("verdict"),
            "div_yield_pct": q.get("div_yield_pct"),
            **cls,
        })

    roth    = [p for p in placements if p["account"] == "ROTH"]
    taxable = [p for p in placements if p["account"] == "TAXABLE"]
    # Cases where the tax-driven answer contradicts a naive "boring -> taxable" read
    overrides = [p for p in roth
                 if (p.get("theme") == "real_estate"
                     or (p.get("div_yield_pct") or 0) >= HIGH_YIELD_PCT)]

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rules": {
            "roth": "Highest-growth convictions, REITs, and high-yield payers — "
                    "shelter what is taxed hardest.",
            "taxable": "Broad-market index ETFs and anything you may need before 59.5.",
            "high_yield_threshold_pct": HIGH_YIELD_PCT,
        },
        "counts": {"roth": len(roth), "taxable": len(taxable)},
        "roth": sorted(roth, key=lambda p: (p["priority"] != "high", p["ticker"])),
        "taxable": sorted(taxable, key=lambda p: p["ticker"]),
        "tax_drag_overrides": overrides,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print("🏦 ASSET LOCATION")
    print(f"  ROTH:    {len(roth)} names (shelter the tax-inefficient)")
    print(f"  TAXABLE: {len(taxable)} names -> {', '.join(p['ticker'] for p in taxable) or 'none'}")
    if overrides:
        print(f"\n  ⚠ {len(overrides)} name(s) where tax drag overrides the "
              f"'boring goes taxable' instinct — these belong in the ROTH:")
        for p in overrides:
            dy = p.get("div_yield_pct")
            label = f"{dy:.1f}% yield" if dy else "REIT distributions"
            print(f"      {p['ticker']:6s} {label}")
    print(f"\n✅ Asset location → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
