#!/usr/bin/env python3
"""
scripts/radar_promote.py — Research the radar's top new names and keep the strong ones.

Each pick briefly joins the watchlist, because research reads from it. Afterwards
only RESEARCH-WORTHY names stay, up to MAX_ADDS a week, marked as found by the
radar; the rest go back off. Every result is logged so the card shows its rating
and the same name isn't researched again next week.

Kept names also go in watchlist.md: sync_watchlist.py deletes anything missing
from that file.

Usage:
    export NVIDIA_API_KEY=nvapi-...
    python3 scripts/radar_promote.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import load_json
from radar import LOG_PATH, OUTPUT_PATH, SCRIPT_DIR, WATCHLIST_PATH

MARKDOWN_PATH = os.path.join(SCRIPT_DIR, "watchlist.md")
SCRIPTS = os.path.join(SCRIPT_DIR, "scripts")
MAX_RESEARCH = 5
MAX_ADDS = 3
SECTION = "## Discovered by the radar"
BENCHMARKS = "## Index benchmarks"


def choose(cards: list[dict], limit: int) -> list[str]:
    fresh = [c["ticker"] for c in cards if not c.get("tracked") and not c.get("rating")]
    return fresh[:limit]


def split_results(results: dict) -> tuple[list[str], list[str]]:
    """(tickers to keep, tickers to take back off the watchlist)."""
    strong = [t for t, verdict in results.items() if verdict == "RESEARCH-WORTHY"]
    keep = strong[:MAX_ADDS]
    return keep, [t for t in results if t not in keep]


def add_to_markdown(text: str, tickers: list[str]) -> str:
    lines = text.split("\n")
    new = [t for t in tickers if t not in lines]
    if not new:
        return text
    if SECTION in lines:
        at = lines.index(SECTION) + 1
        return "\n".join(lines[:at] + new + lines[at:])
    at = next((i for i, ln in enumerate(lines) if ln.startswith(BENCHMARKS)), len(lines))
    return "\n".join(lines[:at] + [SECTION, *new, ""] + lines[at:])


def _pending(ticker: str, card: dict, today: str) -> dict:
    return {"ticker": ticker, "name": card.get("name"), "theme": "uncategorized", "source": "radar",
            "status": "pending", "verdict": "PENDING", "added": today}


def _save_watchlist(watchlist: dict) -> None:
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(watchlist, f, indent=2)


def _run(script: str, *args: str) -> bool:
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          cwd=SCRIPT_DIR).returncode == 0


def main() -> None:
    cards = {c["ticker"]: c for c in load_json(OUTPUT_PATH).get("cards", [])}
    picks = choose(list(cards.values()), MAX_RESEARCH)
    if not picks:
        print("📡 No new radar names to research.")
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    watchlist = load_json(WATCHLIST_PATH)
    _save_watchlist({**watchlist, "candidates": [
        *watchlist["candidates"], *[_pending(t, cards[t], today) for t in picks]]})

    if not _run("refresh_quotes.py"):
        print("⚠ quote refresh failed; research may be missing prices")
    finished = {t: _run("research_ticker.py", t) for t in picks}

    after = load_json(WATCHLIST_PATH)
    verdicts = {c["ticker"]: c.get("verdict") for c in after["candidates"]}
    results = {t: verdicts.get(t) if finished[t] else None for t in picks}
    keep, drop = split_results(results)

    _save_watchlist({**after, "candidates": [c for c in after["candidates"] if c["ticker"] not in drop]})
    with open(MARKDOWN_PATH) as f:
        text = f.read()
    with open(MARKDOWN_PATH, "w") as f:
        f.write(add_to_markdown(text, keep))

    log = load_json(LOG_PATH)
    rated = {t: {**log.get(t, {}), "rating": results[t], "rated_on": today}
             for t in picks if results[t]}
    with open(LOG_PATH, "w") as f:
        json.dump({**log, **rated}, f, indent=2, sort_keys=True)

    print(f"📡 Researched {len(picks)}: {results}. Added: {keep or 'none'}")
    if not any(finished.values()):
        print("❌ No radar research finished.")
        sys.exit(1)


if __name__ == "__main__":
    main()
