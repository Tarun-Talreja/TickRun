#!/usr/bin/env python3
"""
scripts/move_explainer.py — Detect significant price moves and explain WHY.

Instead of waiting for next-day research, this runs every refresh:
  1. Compares current price vs the last committed snapshot (per ticker).
  2. Flags any name that moved more than MOVE_THRESHOLD since last check
     OR more than DAY_THRESHOLD on the day.
  3. Pulls recent news headlines for each mover (free, via news_feed).
  4. If an LLM key is set, asks for a ONE-SENTENCE likely reason, grounded
     ONLY in those headlines (no hallucinated causes).

Output:
  data/price_snapshot.json — last seen price per ticker (committed, for diffing)
  data/movers.json         — current movers with reason + news (read by dashboard)

Usage:
    python3 scripts/move_explainer.py
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
SNAPSHOT_PATH  = os.path.join(SCRIPT_DIR, "data", "price_snapshot.json")
MOVERS_PATH    = os.path.join(SCRIPT_DIR, "data", "movers.json")

# Thresholds
MOVE_THRESHOLD = 3.0   # % change since last snapshot to flag (intraday spike)
DAY_THRESHOLD  = 5.0   # % change on the day to flag regardless of snapshot

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from news_feed import fetch_news
except Exception:
    def fetch_news(ticker, limit=5):
        return []


def _load(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _verdict_map() -> dict:
    wl = _load(WATCHLIST_PATH, {"candidates": []})
    return {c["ticker"]: c.get("verdict", "") for c in wl.get("candidates", [])}


def _llm_reason(ticker: str, pct: float, headlines: list[str]) -> str | None:
    """One-sentence reason grounded ONLY in the provided headlines."""
    key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key or not headlines:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    direction = "up" if pct > 0 else "down"
    headlines_block = "\n".join(f"- {h}" for h in headlines)
    prompt = (
        f"{ticker} moved {direction} {abs(pct):.1f}% today. Based ONLY on these "
        f"headlines, give the single most likely reason in ONE sentence (max 20 words). "
        f"If the headlines don't explain it, say 'No clear catalyst in current news.'\n\n"
        f"Headlines:\n{headlines_block}"
    )
    try:
        client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=key)
        r = client.chat.completions.create(
            model="meta/llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.2,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return None


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

        # Pull news + reason
        news = fetch_news(ticker, 5)
        headlines = [n["title"] for n in news if n.get("title")]
        reason = _llm_reason(ticker, day_pct or since_pct or 0, headlines)

        movers.append({
            "ticker":     ticker,
            "name":       q.get("name", ticker),
            "verdict":    verdicts.get(ticker, ""),
            "price":      price,
            "pct_day":    day_pct,
            "pct_since":  since_pct,
            "direction":  "up" if (day_pct or since_pct or 0) > 0 else "down",
            "triggers":   triggers,
            "reason":     reason or "Reason pending — see headlines.",
            "news":       news[:3],
        })

    # Sort by absolute daily move, biggest first
    movers.sort(key=lambda m: abs(m.get("pct_day") or m.get("pct_since") or 0), reverse=True)

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
