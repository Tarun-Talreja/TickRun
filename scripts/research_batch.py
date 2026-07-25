#!/usr/bin/env python3
"""
scripts/research_batch.py — Run daily LLM research on the highest-priority names.

Re-researches RESEARCH-WORTHY and WATCHLIST candidates that are either:
  - Stale (last_researched > STALE_DAYS ago), OR
  - Showing a fresh pullback alert (drawdown <= ALERT_THRESHOLD)

Uses research_ticker.py's provider logic (NVIDIA NIM free by default).
Skips PASS verdicts and index benchmarks. Caps the run to MAX_PER_RUN
tickers so the daily job stays within free-tier rate limits.

Usage:
    export NVIDIA_API_KEY=nvapi-...
    python3 scripts/research_batch.py
    python3 scripts/research_batch.py --max 5
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
RESEARCH_SCRIPT = os.path.join(SCRIPT_DIR, "scripts", "research_ticker.py")

STALE_DAYS      = 7      # re-research if older than this
ALERT_THRESHOLD = -20.0  # drawdown that forces a re-research
MAX_PER_RUN     = 8      # cap per run to respect free-tier limits

# Index/benchmark ETFs are tracked for context, not as buy candidates —
# spending a research slot on them starves real names in the queue.
SKIP_TICKERS = {"SPY", "QQQ", "VTI", "VOO", "DIA", "IWM"}


def _days_since(date_str: str | None) -> int:
    if not date_str:
        return 9999
    try:
        d = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days
    except ValueError:
        return 9999


def _select_tickers(max_n: int) -> list[str]:
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)
    quotes = {}
    if os.path.exists(QUOTES_PATH):
        with open(QUOTES_PATH) as f:
            quotes = json.load(f).get("tickers", {})

    scored = []
    for c in wl.get("candidates", []):
        ticker = c.get("ticker", "")
        verdict = c.get("verdict", "")
        if ticker.startswith("^") or verdict == "PASS" or ticker in SKIP_TICKERS:
            continue
        if verdict not in ("RESEARCH-WORTHY", "WATCHLIST"):
            continue

        drawdown = quotes.get(ticker, {}).get("drawdown_from_high")
        stale_days = _days_since(c.get("last_researched"))

        # A candidate can carry a last_researched date + thesis that were
        # written by hand (in conversation) rather than by this pipeline —
        # those have no research_file and were never actually grounded in
        # live fundamentals/news. Without this check, +100 for RESEARCH-WORTHY
        # let the same handful of names win every run forever, starving the
        # 32 names that had never been through research_ticker.py at all.
        never_pipeline_researched = not c.get("research_file")

        # Priority score: bigger = more urgent. Never-researched names always
        # outrank everything else so the backlog actually drains.
        score = 0
        if never_pipeline_researched:
            score += 1000
        if verdict == "RESEARCH-WORTHY":
            score += 100
        if drawdown is not None and drawdown <= ALERT_THRESHOLD:
            score += 50
        score += min(stale_days, 30)   # staleness adds up to 30

        # Include if: never actually researched, OR stale, OR freshly dipping
        if (never_pipeline_researched
                or stale_days >= STALE_DAYS
                or (drawdown is not None and drawdown <= ALERT_THRESHOLD)):
            scored.append((score, ticker))

    scored.sort(reverse=True)
    return [t for _, t in scored[:max_n]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=MAX_PER_RUN,
                        help=f"Max tickers to research (default {MAX_PER_RUN})")
    args = parser.parse_args()

    if not (os.environ.get("NVIDIA_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        print("⚠ No NVIDIA_API_KEY or ANTHROPIC_API_KEY set — skipping daily research.")
        sys.exit(0)   # exit 0 so the workflow doesn't fail

    tickers = _select_tickers(args.max)
    if not tickers:
        print("✅ No tickers need re-research today.")
        sys.exit(0)

    print(f"🔬 Daily research queue ({len(tickers)}): {', '.join(tickers)}\n")
    failures = []
    for ticker in tickers:
        print(f"── {ticker} " + "─" * 40)
        result = subprocess.run(
            [sys.executable, RESEARCH_SCRIPT, ticker],
            cwd=SCRIPT_DIR,
        )
        if result.returncode != 0:
            failures.append(ticker)

    print(f"\n✅ Researched {len(tickers) - len(failures)}/{len(tickers)} tickers.")
    if failures:
        print(f"⚠ Failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
