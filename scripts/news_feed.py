#!/usr/bin/env python3
"""
scripts/news_feed.py — Recent headlines for each stock, from Google News (no API key).

Research reads these so its notes reflect what actually happened, not what the model
remembers. This used Yahoo's news call until it began failing on 2026-10-01; the
failure read as "no news", so five weeks of ratings had no headlines and nothing
said so. A feed failure now raises NewsUnavailable, which is not the same as a quiet
stock: research stops, and System Check shows how many stocks have headlines.

Two uses:
  1. Standalone: writes data/news_cache.json for all watchlist tickers.
  2. Import: get_recent_news(ticker) returns a formatted string for prompts.

Usage:
    python3 scripts/news_feed.py            # cache news for whole watchlist
    python3 scripts/news_feed.py VST        # print recent VST headlines
"""

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import quote

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from field_news import FEED_URL, HEADERS, best_headlines, parse_feed
from io_utils import load_json

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "data", "news_cache.json")

DEFAULT_LIMIT = 6
RESEARCH_LIMIT = 10
# Long enough to reach the last earnings report, which is what explains most moves.
WINDOW_DAYS = 45
ATTEMPTS = 3
RETRY_WAIT_SECONDS = 5
WORKERS = 4
MAX_CANDIDATES = 60
NO_NEWS = "No recent news found."

# What headlines call the company, where that differs from its legal name.
# The first entry is also the search term.
ALIASES = {
    "TSM": ["TSMC", "Taiwan Semiconductor"], "AMD": ["AMD"], "IBM": ["IBM"],
    "GOOGL": ["Alphabet", "Google"], "GOOG": ["Alphabet", "Google"],
    "META": ["Meta"], "LLY": ["Eli Lilly", "Lilly"], "GEV": ["GE Vernova"],
    "GEHC": ["GE HealthCare", "GE Healthcare"], "UNH": ["UnitedHealth"],
    "BWXT": ["BWXT", "BWX"], "LPLA": ["LPL Financial", "LPL"], "EIX": ["Edison International"],
    "ADP": ["ADP"], "NVDA": ["Nvidia"], "AAPL": ["Apple"], "NFLX": ["Netflix"],
    "CMCSA": ["Comcast"], "PAYX": ["Paychex"], "ISRG": ["Intuitive Surgical"],
}
_SUFFIX_RE = re.compile(
    r"[,\s]+(?:inc|incorporated|corp|corporation|co|company|plc|ltd|limited|n\.?v|"
    r"holdings?|holding|group|\(the\))\.?$", re.IGNORECASE)
# Headlines that say something happened, rather than filler about the stock.
_MATERIAL_RE = re.compile(
    r"\b(?:earnings|results?|q[1-4]|quarter\w*|guidance|outlook|forecasts?|beats?|miss(?:es)?|"
    r"revenue|sales|profit|loss|settlement|lawsuit|sued?|probe|investigation|antitrust|"
    r"acqui\w+|merger|deal|contract|layoffs?|ceo|cfo|recall|fda|downgrades?|upgrades?|"
    r"plunge\w*|sinks?|sank|tumbl\w+|slump\w*|slides?|soar\w*|surge\w*|jumps?|falls?|fell|"
    r"drops?|cuts?|raises?)\b", re.IGNORECASE)


class NewsUnavailable(RuntimeError):
    """The feed itself failed, as opposed to having nothing on this stock."""


def short_name(name: str) -> str:
    """'Vertiv Holdings Co' -> 'Vertiv'. Headlines don't use legal suffixes."""
    previous = None
    while name != previous:
        previous, name = name, _SUFFIX_RE.sub("", name).strip()
    return name


def company_terms(ticker: str, name: str | None) -> list[str]:
    """What a headline about this company contains; the first is the search term."""
    terms = list(ALIASES.get(ticker, []))
    if name and name != ticker:
        terms.append(short_name(name))
    if len(ticker) >= 3:
        terms.append(ticker)
    return list(dict.fromkeys(terms)) or [ticker]


def _mentions(title: str, terms: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", title) for term in terms)


def pick_news(items: list[dict], terms: list[str], limit: int) -> list[dict]:
    """Headlines about the company, what-happened stories first, shown newest first."""
    about = [h for h in best_headlines(items, MAX_CANDIDATES) if _mentions(h["title"], terms)]
    # Stable sort: best_headlines already put trusted sources first.
    ranked = sorted(about, key=lambda h: bool(_MATERIAL_RE.search(h["title"])), reverse=True)
    chosen = sorted(ranked[:limit], key=lambda h: h["date"], reverse=True)
    return [{"title": h["title"], "publisher": h["source"], "date": h["date"], "url": h["link"]}
            for h in chosen]


def _search(query: str) -> list[dict]:
    """Raw feed items. Raises NewsUnavailable once the retries run out."""
    url = FEED_URL.format(query=quote(query), days=WINDOW_DAYS)
    problem = ""
    for attempt in range(ATTEMPTS):
        if attempt:
            time.sleep(RETRY_WAIT_SECONDS * attempt)
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            problem = str(exc)[:120]
            continue
        if b"<rss" in response.content[:500]:
            return parse_feed(response.content)
        problem = "response was not a news feed"
    raise NewsUnavailable(f"news feed failed: {problem}")


@lru_cache(maxsize=1)
def _quotes() -> dict:
    return load_json(QUOTES_PATH).get("tickers", {})


def _company_news(ticker: str, limit: int, name: str | None) -> list[dict]:
    name = name or _quotes().get(ticker, {}).get("name")
    terms = company_terms(ticker, name)
    return pick_news(_search(f'"{terms[0]}" ({ticker} OR stock OR earnings OR shares)'),
                     terms, limit)


def fetch_news(ticker: str, limit: int = DEFAULT_LIMIT, name: str | None = None) -> list[dict]:
    """For display, where a gap is acceptable. Research uses get_recent_news."""
    try:
        return _company_news(ticker, limit, name)
    except NewsUnavailable as exc:
        print(f"⚠ no news for {ticker}: {exc}")
        return []


def get_recent_news(ticker: str, limit: int = RESEARCH_LIMIT, name: str | None = None) -> str:
    """Formatted string for an LLM prompt. Raises NewsUnavailable if the feed is down."""
    items = _company_news(ticker, limit, name)
    if not items:
        return NO_NEWS
    return "\n".join(f"- [{n['date']}] {n['title']} ({n['publisher']})" for n in items)


def _load_watchlist_tickers() -> list[str]:
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)
    return [
        c["ticker"] for c in wl.get("candidates", [])
        if not c.get("ticker", "").startswith("^") and c.get("verdict") != "PASS"
    ]


def main():
    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
        print(f"📰 Recent news for {ticker}:\n")
        print(get_recent_news(ticker, 8))
        return

    tickers = _load_watchlist_tickers()
    print(f"📰 Caching news for {len(tickers)} tickers...")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        cache = dict(zip(tickers, pool.map(fetch_news, tickers)))
    print(f"  {sum(1 for items in cache.values() if items)}/{len(cache)} have headlines")

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "news": cache,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n✅ News cache → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
