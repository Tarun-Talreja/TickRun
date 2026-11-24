#!/usr/bin/env python3
"""
scripts/weekly_digest.py — Plain-English summary for the home screen, rebuilt daily.

Reads the assembled dashboard.json and produces a short, readable digest:
  - Biggest movers and why
  - New buy-ready (RESEARCH-WORTHY) names at or below buy target
  - Upcoming earnings to watch
  - Any data warnings to be aware of
  - SEC ownership stakes (early smart-money)

The narrative is built in code; no model is involved.

Output:
  output/weekly_digest.json  — structured + narrative (read by dashboard/app)

Usage:
    python3 scripts/weekly_digest.py
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import load_json as _load
from market_time import session_date
from summary_history import load_days, save_days, with_summary

SCRIPT_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PATH = os.path.join(SCRIPT_DIR, "output", "dashboard.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "output", "weekly_digest.json")
QUOTES_PATH   = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
INDEX_FUNDS = ("SPY", "QQQ")
TOP_MOVERS = 4
EARNINGS_DAYS = 10


def _day(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{d:%a %b} {d.day}"


def _moved(pct: float) -> str:
    return f"{'rose' if pct >= 0 else 'fell'} {abs(pct):.1f}%"


def market_line(quotes: dict, prices_as_of: str | None) -> str | None:
    spy = quotes.get("SPY", {}).get("pct_change_1d")
    qqq = quotes.get("QQQ", {}).get("pct_change_1d")
    if spy is None or qqq is None or not prices_as_of:
        return None
    day = session_date(datetime.fromisoformat(prices_as_of.replace("Z", "+00:00")))
    return f"{_day(day.isoformat())}: the S&P 500 {_moved(spy)} and the Nasdaq 100 {_moved(qqq)}."


def movers_line(movers: list[dict] | None) -> str | None:
    stocks = [m for m in movers or [] if m["ticker"] not in INDEX_FUNDS and m.get("pct") is not None]
    if not stocks:
        return None
    listed = ", ".join(f"{m['ticker']} {m['pct']:+.1f}%" for m in stocks[:TOP_MOVERS])
    lead = next((m for m in stocks if "headline:" in (m.get("reason") or "")), None)
    quote = f" {lead['ticker']}, {lead['reason'].split(' The whole market')[0]}" if lead else ""
    return f"Biggest moves you follow: {listed}.{quote}"


def earnings_line(earnings: list[dict]) -> str | None:
    soon = [f"{e['ticker']} {_day(e['date'])}" for e in earnings
            if e.get("date") and (e.get("days_until") or 0) <= EARNINGS_DAYS]
    return f"Earnings next: {', '.join(soon)}." if soon else None


def summary(quotes: dict, prices_as_of: str | None, movers: list[dict] | None,
            earnings: list[dict]) -> str | None:
    """Built in code from saved data. A model wrote this until 2026-11-23, when it said
    no company headline explained any move on the day NVDA's CEO came back."""
    lines = [market_line(quotes, prices_as_of), movers_line(movers), earnings_line(earnings)]
    return " ".join(line for line in lines if line) or None


def current_movers(sig: dict, prices_as_of: str | None) -> list[dict] | None:
    """Movers worked out from these prices, or None when they predate them: on 2026-11-23,
    after a 5% rally, the summary still led with Friday's falls."""
    if not prices_as_of or (sig.get("movers_updated") or "") < prices_as_of:
        return None
    return [{"ticker": m["ticker"], "pct": m.get("pct_day"), "reason": m.get("reason")}
            for m in sig.get("price_movers", [])[:6]]


def main():
    if not os.path.exists(DASHBOARD_PATH):
        print("No dashboard.json. Run build_dashboard.py first.")
        sys.exit(0)

    d = _load(DASHBOARD_PATH)
    sig = d.get("signals", {})
    prices_as_of = d.get("prices_as_of")
    wl  = d.get("watchlist", {})

    # Buy-ready: RESEARCH-WORTHY at or below buy target
    buy_ready = []
    for c in wl.get("by_verdict", {}).get("RESEARCH-WORTHY", []):
        price = c.get("current_price") or c.get("price")
        target = c.get("buy_target")
        at_target = (price and target and price <= target * 1.03)
        buy_ready.append({
            "ticker": c["ticker"], "name": c.get("name"),
            "price": price, "buy_target": target,
            "at_or_below_target": bool(at_target),
            "confidence": c.get("confidence"),
            "theme": c.get("theme"),
        })
    buy_ready.sort(key=lambda x: not x["at_or_below_target"])

    movers = current_movers(sig, prices_as_of)
    if movers is None:
        print("⚠ movers predate the prices, left out of the summary")
    earnings = [
        {"ticker": e["ticker"], "date": e.get("date"), "days_until": e.get("days_until")}
        for e in sig.get("upcoming_earnings", [])
    ]
    stakes = [
        {"ticker": s["ticker"], "form": s.get("form"), "filed": s.get("filed_date")}
        for s in sig.get("sec_ownership_stakes", [])
    ]
    data_warnings = [
        c["ticker"] for c in wl.get("all", []) if c.get("data_ok") is False
    ]

    narrative = summary(_load(QUOTES_PATH).get("tickers", {}), prices_as_of, movers, earnings)

    digest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "narrative":    narrative,
        "buy_ready":    buy_ready,
        "movers":       movers or [],
        "prices_as_of": None if movers is None else prices_as_of,
        "upcoming_earnings": earnings,
        "sec_stakes":   stakes,
        "data_warnings": data_warnings,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(digest, f, indent=2)

    if narrative and digest["prices_as_of"]:
        day = session_date(datetime.fromisoformat(prices_as_of.replace("Z", "+00:00"))).isoformat()
        save_days(with_summary(load_days(), day, narrative, prices_as_of))

    print("📋 WEEKLY DIGEST")
    if narrative:
        print(f"\n{narrative}\n")
    print(f"Movers: {', '.join(m['ticker'] for m in movers or []) or 'none'}")
    print(f"Earnings ahead: {', '.join(e['ticker'] for e in earnings) or 'none'}")
    if data_warnings:
        print(f"⚠ Data warnings: {', '.join(data_warnings)}")
    print(f"\n✅ Digest → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
