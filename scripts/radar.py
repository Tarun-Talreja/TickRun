#!/usr/bin/env python3
"""
scripts/radar.py — Which stocks should you know about, and why?

The weekly screener ranks companies. The radar adds what the ranking can't see:
this week's field news, price falls and insider buying. A stock surfaces when at
least two separate reasons line up, and each card lists those reasons plus what
to watch out for. Reasons are built by code from real data, so the model can't
invent one.

These are leads to research, not buy calls. Every first appearance is logged so
the radar can be scored against SPY.

Usage:
    python3 scripts/radar.py
"""

import json
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import load_json
from screener import MAX_PER_SECTOR, company_key

SCRIPT_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR      = os.path.join(SCRIPT_DIR, "data")
UNIVERSE_PATH = os.path.join(DATA_DIR, "screen_universe.json")
FIELD_PATH    = os.path.join(DATA_DIR, "field_news.json")
WATCHLIST_PATH = os.path.join(DATA_DIR, "watchlist.json")
QUOTES_PATH   = os.path.join(DATA_DIR, "quotes_cache.json")
LOG_PATH      = os.path.join(DATA_DIR, "radar_log.json")
OUTPUT_PATH   = os.path.join(DATA_DIR, "radar.json")

MAX_CARDS       = 12
MAX_ON_SALE     = 10
MIN_REASONS     = 2
STRONG_SCORE    = 70       # of 100, the screener's blended score
SALE_DRAWDOWN   = -25.0    # % below the 52-week high
SALE_QUALITY    = 20.0     # of 35; a cheap bad business isn't on sale
MIN_NAME_CHARS  = 4        # shorter names match too much by accident
PEAK_GROWTH     = 1.0      # revenue doubling
PEAK_FORWARD_PE = 8.0
HIGH_DEBT_EQUITY = 200.0   # Yahoo reports this as a percent
DEEP_DRAWDOWN   = -50.0
INSIDER_FINALISTS = 30     # one Yahoo call each, so only the likely cards
NEW_DAYS        = 7
SCORE_WINDOWS   = {"4w": 28, "12w": 84}


def match_company(name: str, universe: list[dict]) -> str | None:
    """Ticker for a company named in the news, or None unless the match is unique."""
    key = company_key(name)
    if len(key) < MIN_NAME_CHARS:
        return None
    keys = {s["ticker"]: company_key(s.get("name") or "") for s in universe}
    exact = [t for t, k in keys.items() if k == key]
    if exact:
        return exact[0]
    partial = [t for t, k in keys.items() if k.startswith(f"{key} ")]
    return partial[0] if len(partial) == 1 else None


def tracked_tickers(candidates: list[dict], universe: list[dict]) -> set[str]:
    """Watchlist tickers, plus other share classes of those companies (GOOG for GOOGL)."""
    names = {company_key(c.get("name") or c["ticker"]) for c in candidates}
    twins = {s["ticker"] for s in universe if company_key(s.get("name") or "") in names}
    return {c["ticker"] for c in candidates} | twins


def on_sale(s: dict) -> bool:
    drawdown, quality = s.get("drawdown_pct"), s.get("quality")
    return (drawdown is not None and quality is not None
            and drawdown <= SALE_DRAWDOWN and quality >= SALE_QUALITY)


def watch_outs(s: dict) -> list[str]:
    growth, forward_pe = s.get("rev_growth"), s.get("forward_pe")
    fcf, debt, drawdown = s.get("fcf"), s.get("debt_equity"), s.get("drawdown_pct")
    notes = []
    if growth is not None and growth >= PEAK_GROWTH:
        notes.append(f"Possible peak earnings: revenue up {growth * 100:.0f}% in a quarter may not last")
    elif forward_pe is not None and 0 < forward_pe < PEAK_FORWARD_PE:
        notes.append(f"Possible peak earnings: {forward_pe:.1f}x forward earnings can mean profits are expected to fall")
    if fcf is not None and fcf < 0:
        notes.append("Burning cash over the last year")
    if debt is not None and debt > HIGH_DEBT_EQUITY:
        notes.append(f"High debt: debt/equity {debt / 100:.1f}x")
    if drawdown is not None and drawdown <= DEEP_DRAWDOWN:
        notes.append(f"Down {abs(drawdown):.0f}% from its high, so find out why first")
    return notes


def news_reasons(fields: dict, universe: list[dict]) -> dict:
    """Ticker -> reasons, for every company in the news that maps to one stock."""
    reasons = {}
    for field in fields.values():
        sources = field.get("sources", [])
        for company in field.get("companies", []):
            ticker = match_company(company, universe)
            if not ticker:
                continue
            story = next((h for h in sources if company.lower() in h["title"].lower()),
                         sources[0] if sources else {})
            reason = {"kind": "field_news", "link": story.get("link"),
                      "text": f"In {field['name']} news: {story.get('title', company)}"}
            reasons = {**reasons, ticker: [*reasons.get(ticker, []), reason]}
    return reasons


def _is_new(entry: dict | None, today: str | None) -> bool:
    if entry is None:
        return True
    if not today:
        return False
    age = date.fromisoformat(today) - date.fromisoformat(entry["first_seen"])
    return age.days < NEW_DAYS


def build_card(s: dict, news: dict, log: dict, insiders: dict, tracked: set, ratings: dict,
               today: str | None = None) -> dict:
    ticker = s["ticker"]
    seen = log.get(ticker, {})
    new = _is_new(log.get(ticker), today)
    reasons = list(news.get(ticker, []))
    if s.get("score", 0) >= STRONG_SCORE:
        reasons.append({"kind": "fundamentals", "text": f"Strong fundamentals: scores {s['score']:.0f}/100"})
    if on_sale(s):
        reasons.append({"kind": "on_sale", "text": f"Quality business {abs(s['drawdown_pct']):.0f}% below its high"})
    insider = insiders.get(ticker, {})
    if insider.get("buys", 0) > insider.get("sells", 0) and insider.get("buy_value"):
        reasons.append({"kind": "insider", "text": f"Insiders bought: {insider['buys']} buys, {insider['sells']} sells in 6 months"})
    if new and reasons:
        reasons.append({"kind": "new", "text": "New to the radar"})
    return {
        "ticker": ticker, "name": s.get("name"), "sector": s.get("sector"), "price": s.get("price"),
        "drawdown_pct": s.get("drawdown_pct"), "score": s.get("score"), "new": new,
        "tracked": ticker in tracked, "rating": ratings.get(ticker) or seen.get("rating"),
        "reasons": reasons, "watch_outs": watch_outs(s),
    }


def _capped(cards: list[dict], limit: int) -> list[dict]:
    picks, per_sector = [], {}
    for c in cards:
        if per_sector.get(c["sector"], 0) >= MAX_PER_SECTOR:
            continue
        per_sector[c["sector"]] = per_sector.get(c["sector"], 0) + 1
        picks.append(c)
        if len(picks) == limit:
            break
    return picks


def build_radar(universe: list[dict], news: dict, log: dict, insiders: dict,
                tracked: set, ratings: dict, today: str | None = None) -> dict:
    mentions = news_reasons(news.get("fields", {}), universe)
    cards = [build_card(s, mentions, log, insiders, tracked, ratings, today) for s in universe]
    # The "new" label says nothing about the stock, so it can't qualify or rank one.
    def strength(card: dict) -> int:
        return sum(r["kind"] != "new" for r in card["reasons"])
    ranked = sorted((c for c in cards if strength(c) >= MIN_REASONS),
                    key=lambda c: (strength(c), c["score"] or 0), reverse=True)
    sale = sorted((c for c, s in zip(cards, universe) if on_sale(s) and not c["tracked"]),
                  key=lambda c: (c["score"] or 0), reverse=True)
    return {"cards": _capped(ranked, MAX_CARDS), "on_sale": _capped(sale, MAX_ON_SALE)}


def updated_log(log: dict, cards: list[dict], today: str, spy: float | None) -> dict:
    """New log with each card's first appearance added; old entries never change."""
    fresh = {c["ticker"]: {"first_seen": today, "price": c.get("price"), "spy": spy,
                           "signals": [r["kind"] for r in c["reasons"]]}
             for c in cards if c["ticker"] not in log}
    return {**log, **fresh}


def scorecard(log: dict, prices: dict, spy_now: float | None, today: str) -> dict:
    """Average return minus SPY for picks old enough to judge, per time window."""
    now = date.fromisoformat(today)
    out = {}
    for label, days in SCORE_WINDOWS.items():
        excess = []
        for ticker, entry in log.items():
            price, first, spy = prices.get(ticker), entry.get("price"), entry.get("spy")
            old_enough = (now - date.fromisoformat(entry["first_seen"])).days >= days
            if old_enough and price and first and spy and spy_now:
                excess.append((price / first - spy_now / spy) * 100)
        average = round(sum(excess) / len(excess), 1) if excess else None
        out[label] = {"count": len(excess), "avg_excess_pct": average}
    return out


def _finalists(universe: list[dict], news: dict, log: dict, tracked: set) -> list[str]:
    """Stocks one reason away from a card, so insider data can only add to them."""
    mentions = news_reasons(news.get("fields", {}), universe)
    near = [s for s in universe
            if any(r["kind"] != "new" for r in build_card(s, mentions, log, {}, tracked, {})["reasons"])]
    near.sort(key=lambda s: s.get("score", 0), reverse=True)
    return [s["ticker"] for s in near[:INSIDER_FINALISTS]]


def _insiders(tickers: list[str]) -> dict:
    from insider_check import _fetch_one
    return {t: _fetch_one(t) for t in tickers}


def main() -> None:
    universe = load_json(UNIVERSE_PATH).get("stocks", [])
    if not universe:
        print("❌ No screen_universe.json yet. Run scripts/screener.py first.")
        sys.exit(1)
    news, log = load_json(FIELD_PATH), load_json(LOG_PATH)
    candidates = load_json(WATCHLIST_PATH).get("candidates", [])
    tracked = tracked_tickers(candidates, universe)
    ratings = {c["ticker"]: c.get("verdict") for c in candidates}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    spy = load_json(QUOTES_PATH).get("tickers", {}).get("SPY", {}).get("price")

    insiders = _insiders(_finalists(universe, news, log, tracked))
    radar = build_radar(universe, news, log, insiders, tracked, ratings, today)
    new_log = updated_log(log, radar["cards"], today, spy)
    prices = {s["ticker"]: s.get("price") for s in universe}

    with open(LOG_PATH, "w") as f:
        json.dump(new_log, f, indent=2, sort_keys=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "universe_as_of": load_json(UNIVERSE_PATH).get("generated_at"),
                   **radar, "scorecard": scorecard(new_log, prices, spy, today)}, f, indent=2)
    print(f"📡 Radar: {len(radar['cards'])} cards, {len(radar['on_sale'])} on sale")
    for c in radar["cards"]:
        print(f"  {c['ticker']:6s} {' + '.join(r['kind'] for r in c['reasons'])}")


if __name__ == "__main__":
    main()
