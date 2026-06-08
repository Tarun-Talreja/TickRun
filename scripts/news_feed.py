#!/usr/bin/env python3
"""
scripts/news_feed.py — Free per-ticker news via yfinance (no API key needed).

Provides recent headlines so the LLM research grounds its analysis in REAL
current news instead of hallucinating from stale training data.

Two uses:
  1. Standalone: writes data/news_cache.json for all watchlist tickers.
  2. Import: get_recent_news(ticker, limit) returns a formatted string for prompts.

Usage:
    python3 scripts/news_feed.py            # cache news for whole watchlist
    python3 scripts/news_feed.py VST        # print recent VST headlines
"""

import json
import os
import sys
from datetime import datetime, timezone

try:
    import yfinance as yf
except ImportError:
    print("Missing dependency: pip install yfinance")
    sys.exit(1)

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "data", "news_cache.json")

DEFAULT_LIMIT = 6


def _parse_item(item: dict) -> dict | None:
    """yfinance news schema changed over versions — handle both shapes."""
    content = item.get("content", item)
    title = content.get("title") or item.get("title")
    if not title:
        return None

    provider = content.get("provider")
    if isinstance(provider, dict):
        publisher = provider.get("displayName", "")
    else:
        publisher = item.get("publisher", "")

    pub = (
        content.get("pubDate")
        or content.get("displayTime")
        or item.get("providerPublishTime")
        or ""
    )
    # Normalize unix timestamp → ISO
    if isinstance(pub, (int, float)):
        pub = datetime.fromtimestamp(pub, tz=timezone.utc).strftime("%Y-%m-%d")
    elif isinstance(pub, str) and "T" in pub:
        pub = pub.split("T")[0]

    link = ""
    cu = content.get("canonicalUrl") or content.get("clickThroughUrl")
    if isinstance(cu, dict):
        link = cu.get("url", "")
    elif item.get("link"):
        link = item["link"]

    return {"title": title, "publisher": publisher, "date": pub, "url": link}


def fetch_news(ticker: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        return []
    items = []
    for it in raw:
        parsed = _parse_item(it)
        if parsed:
            items.append(parsed)
        if len(items) >= limit:
            break
    return items


def get_recent_news(ticker: str, limit: int = DEFAULT_LIMIT) -> str:
    """Formatted string for injecting into an LLM prompt."""
    items = fetch_news(ticker, limit)
    if not items:
        return "No recent news found."
    lines = []
    for n in items:
        lines.append(f"- [{n['date']}] {n['title']} ({n['publisher']})")
    return "\n".join(lines)


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
    cache = {}
    for t in tickers:
        cache[t] = fetch_news(t, DEFAULT_LIMIT)
        print(f"  {t}: {len(cache[t])} items")

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "news": cache,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n✅ News cache → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
