#!/usr/bin/env python3
"""
scripts/move_explainer.py — Detect significant price moves and explain WHY.

Instead of waiting for next-day research, this runs every refresh:
  1. Compares current price vs the last committed snapshot (per ticker).
  2. Flags any name that moved more than MOVE_THRESHOLD since last check
     OR more than DAY_THRESHOLD on the day.
  3. Pulls recent news headlines for each mover (free, via news_feed).
  4. Quotes the day's company headline and the market's move. No model is involved.

Output:
  data/price_snapshot.json — last seen price per ticker (committed, for diffing)
  data/movers.json         — current movers with reason + news (read by dashboard)

Usage:
    python3 scripts/move_explainer.py
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from io_utils import load_json as _load

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
SNAPSHOT_PATH  = os.path.join(SCRIPT_DIR, "data", "price_snapshot.json")
MOVERS_PATH    = os.path.join(SCRIPT_DIR, "data", "movers.json")

# Thresholds
MOVE_THRESHOLD = 3.0   # % change since last snapshot to flag (intraday spike)
DAY_THRESHOLD  = 5.0   # % change on the day to flag regardless of snapshot
MARKET_MOVE_PCT = 2.0  # an index move this big can explain a stock's move by itself

NEWS_WORKERS = 4
NEWS_LIMIT = 15   # enough to reach the day's own headlines past the older ones
NO_HEADLINE = "No clear company headline found for this move."
_UP_RE = re.compile(r"\b(?:up|jump\w*|surg\w*|soar\w*|rall(?:y|ies|ied)|skyrocket\w*|rise[sn]?|rising|rose|"
                    r"climb\w*|gain(?:s|ed)?|rebound\w*|upgrade[sd]?|pops?|spikes?)\b", re.IGNORECASE)
_DOWN_RE = re.compile(r"\b(?:down|fall(?:s|ing|en)?|fell|drop(?:s|ped)?|plung\w*|plummet\w*|sinks?|sank|slid\w*|"
                      r"slump\w*|tumbl\w*|crush\w*|crash\w*|lowered|cuts?|trims?|downgrade[sd]?|rout|"
                      r"sell-?off|selloff|retreats?|loses?|lost)\b", re.IGNORECASE)
# Opinion pieces and quote pages, not something that happened.
_OPINION_RE = re.compile(r"\?|\((?:NYSE|NASDAQ):|stock forecasts?|price prediction|history says|"
                         r"stock outlook|analyst ratings|is it time|here's why|valued\b|gf scor|earnings preview", re.IGNORECASE)
_EARNINGS_RE = re.compile(r"\b(?:earnings|results|q[1-4]|quarter\w*|guidance)\b", re.IGNORECASE)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_time import previous_session, prices_as_of, session_date
from news_feed import _MATERIAL_RE, fetch_news


def _verdict_map() -> dict:
    wl = _load(WATCHLIST_PATH, {"candidates": []})
    return {c["ticker"]: c.get("verdict", "") for c in wl.get("candidates", [])}


def _market_note(quotes: dict) -> str:
    spy = quotes.get("SPY", {}).get("pct_change_1d")
    qqq = quotes.get("QQQ", {}).get("pct_change_1d")
    if spy is None or qqq is None:
        return ""
    return f"Nasdaq 100 {qqq:+.1f}%, S&P 500 {spy:+.1f}%"


def _market_reason(pct: float, quotes: dict) -> str | None:
    """The market itself, when it moved hard the same way as the stock.

    Headlines for a single ticker rarely mention the index, so on 2026-11-05,
    with the Nasdaq 100 down 6.5%, every top faller read "No clear catalyst".
    """
    qqq = quotes.get("QQQ", {}).get("pct_change_1d")
    if qqq is None or abs(qqq) < MARKET_MOVE_PCT or qqq * pct <= 0:
        return None
    return f"The whole market moved the same way ({_market_note(quotes)})."


def _contradicts(title: str, pct: float) -> bool:
    """A headline about the opposite move, such as Friday's fall on a Monday rally."""
    same, opposite = (_UP_RE, _DOWN_RE) if pct > 0 else (_DOWN_RE, _UP_RE)
    return bool(opposite.search(title)) and not same.search(title)


def pick_headline(news: list[dict], pct: float, session: str, previous: str) -> dict | None:
    """The day's headline, else earnings from the session before (often released after its close)."""
    usable = [n for n in news if n.get("title") and not _OPINION_RE.search(n["title"])
              and _MATERIAL_RE.search(n["title"]) and not _contradicts(n["title"], pct)]
    return next((n for n in usable if n["date"] == session), None) or next(
        (n for n in usable if previous <= n["date"] < session and _EARNINGS_RE.search(n["title"])), None)


def _lead_first(news: list[dict], pct: float, session: str, previous: str) -> list[dict]:
    """The quoted headline leads, so the card links to it."""
    lead = pick_headline(news, pct, session, previous)
    return [lead, *(n for n in news if n is not lead)] if lead else news


def explain(pct: float, news: list[dict], quotes: dict, session: str, previous: str) -> str:
    """The headline itself, quoted and dated. Nothing here is written by a model, and
    nothing claims the headline caused the move: on 2026-11-23 NVDA rose 31% on its CEO's
    return and the app said "no company-specific news found"."""
    headline = pick_headline(news, pct, session, previous)
    market = _market_reason(pct, quotes)
    if headline:
        day = date.fromisoformat(headline["date"])
        source = f" ({headline['publisher']})" if headline.get("publisher") else ""
        told = f"{day:%b} {day.day} headline: \u201c{headline['title']}\u201d{source}."
        return f"{told} {market}" if market else told
    return f"{market} {NO_HEADLINE}" if market else NO_HEADLINE


def main():
    quotes = _load(QUOTES_PATH, {}).get("tickers", {})
    if not quotes:
        print("No quotes cache. Run refresh_quotes.py first.")
        sys.exit(0)

    prev = _load(SNAPSHOT_PATH, {}).get("prices", {})
    verdicts = _verdict_map()

    movers = []
    new_snapshot = {}

    for ticker, q in quotes.items():
        if q.get("status") != "ok":
            continue
        price = q.get("price")
        if not price:
            continue
        new_snapshot[ticker] = price

        day_pct = q.get("pct_change_1d")
        prev_price = prev.get(ticker)
        since_pct = round((price - prev_price) / prev_price * 100, 2) if prev_price else None

        # Decide if this is a mover
        triggers = []
        if since_pct is not None and abs(since_pct) >= MOVE_THRESHOLD:
            triggers.append(f"{since_pct:+.1f}% since last check")
        if day_pct is not None and abs(day_pct) >= DAY_THRESHOLD:
            triggers.append(f"{day_pct:+.1f}% on the day")
        if not triggers:
            continue

        # The move that actually tripped the alert is the one to report. Using
        # whichever value is larger in magnitude keeps direction, the displayed
        # %, and the trigger text consistent — day and since can disagree in
        # sign (e.g. up on the day but sharply down since the last check).
        primary_pct = max(
            [p for p in (day_pct, since_pct) if p is not None],
            key=abs,
            default=0,
        )

        movers.append({
            "ticker":      ticker,
            "name":        q.get("name", ticker),
            "verdict":     verdicts.get(ticker, ""),
            "price":       price,
            "pct_day":     day_pct,
            "pct_since":   since_pct,
            "primary_pct": primary_pct,
            "direction":   "up" if primary_pct > 0 else "down",
            "triggers":    triggers,
            "reason":      None,
            "news":        [],
        })

    # Sort by the size of the move that triggered the alert, biggest first
    movers.sort(key=lambda m: abs(m.get("primary_pct") or 0), reverse=True)

    as_of = prices_as_of(quotes)
    now = datetime.fromisoformat(as_of.replace("Z", "+00:00")) if as_of else datetime.now(timezone.utc)
    session = session_date(now)
    days = (session.isoformat(), previous_session(session).isoformat())
    with ThreadPoolExecutor(max_workers=NEWS_WORKERS) as pool:
        found = list(pool.map(lambda m: fetch_news(m["ticker"], NEWS_LIMIT), movers))
    movers = [{**m, "news": _lead_first(news, m["primary_pct"] or 0, *days)[:3],
               "reason": explain(m["primary_pct"] or 0, news, quotes, *days)}
              for m, news in zip(movers, found)]

    with open(MOVERS_PATH, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "movers": movers,
        }, f, indent=2)

    with open(SNAPSHOT_PATH, "w") as f:
        json.dump({
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prices": new_snapshot,
        }, f, indent=2)

    if movers:
        print(f"\n📊 {len(movers)} significant mover(s):")
        for m in movers:
            arrow = "🟢▲" if m["direction"] == "up" else "🔴▼"
            print(f"  {arrow} {m['ticker']} ({', '.join(m['triggers'])})")
            print(f"      → {m['reason']}")
    else:
        print("No significant movers since last check.")
    print(f"\n✅ Movers → {MOVERS_PATH}")


if __name__ == "__main__":
    main()
