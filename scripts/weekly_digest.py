#!/usr/bin/env python3
"""
scripts/weekly_digest.py — Plain-English summary for the home screen, rebuilt daily.

Reads the assembled dashboard.json and produces a short, readable digest:
  - Biggest movers and why
  - New buy-ready (RESEARCH-WORTHY) names at or below buy target
  - Upcoming earnings to watch
  - Any data warnings to be aware of
  - SEC ownership stakes (early smart-money)

If an LLM key is set, it writes a 3-4 sentence narrative summary on top.
Otherwise it produces a clean structured digest with no LLM.

Output:
  output/weekly_digest.json  — structured + narrative (read by dashboard/app)

Usage:
    python3 scripts/weekly_digest.py
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fact_check import find_unsupported
from io_utils import load_json as _load
from llm_client import chat

SCRIPT_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PATH = os.path.join(SCRIPT_DIR, "output", "dashboard.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "output", "weekly_digest.json")
FALLBACK_FIELDS = 3
MAX_RADAR_FACTS = 5


def narrative_is_grounded(text: str, facts: dict) -> bool:
    """True if every figure in text is in the facts. Bare JSON numbers count as any unit."""
    raw = json.dumps(facts)
    numbers = re.findall(r"\d+\.?\d*", raw)
    return not find_unsupported(text, raw + " " + " ".join(f"{n}% {n}x ${n}" for n in numbers))


def fallback_summary(fields: dict) -> str | None:
    """Field summaries that already passed their own check, so the card is never empty."""
    lines = [f"{f['name']}: {f['summary']}" for f in fields.values() if f.get("summary")]
    return " ".join(lines[:FALLBACK_FIELDS]) or None


def _narrative(facts: dict) -> str | None:
    key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("⚠ summary skipped: no API key")
        return None

    prompt = (
        "Based ONLY on these facts, write a 3-4 sentence plain-English summary of what "
        "changed for someone following these stocks and fields. Lead with the most "
        "important change. Give no advice to buy or sell, and do not add any fact or "
        f"figure that isn't listed here.\n\n{json.dumps(facts, indent=2)}"
    )
    messages = [{"role": "system", "content": "detailed thinking off"},
                {"role": "user", "content": prompt}]
    try:
        text, _ = chat(key, messages, max_tokens=1500, temperature=0.3, timeout=60)
    except RuntimeError as exc:
        print(f"⚠ summary skipped: {str(exc)[:160]}")
        return None
    if not narrative_is_grounded(text, facts):
        print("⚠ summary dropped: it used a figure that isn't in the facts")
        return None
    return text


def main():
    if not os.path.exists(DASHBOARD_PATH):
        print("No dashboard.json. Run build_dashboard.py first.")
        sys.exit(0)

    d = _load(DASHBOARD_PATH)
    sig = d.get("signals", {})
    wl  = d.get("watchlist", {})
    fields = d.get("field_news", {}).get("fields", {})

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

    movers = [
        {"ticker": m["ticker"], "pct": m.get("pct_day"), "reason": m.get("reason")}
        for m in sig.get("price_movers", [])[:6]
    ]
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

    facts = {
        "buy_ready_at_target": [b["ticker"] for b in buy_ready if b["at_or_below_target"]],
        "movers": movers,
        "upcoming_earnings": earnings,
        "sec_stakes": stakes,
        "data_warnings": data_warnings,
        "field_news": {f["name"]: f["summary"] for f in fields.values() if f.get("summary")},
        "radar": [{"ticker": c["ticker"], "reasons": [r["text"] for r in c["reasons"]]}
                  for c in d.get("radar", {}).get("cards", [])[:MAX_RADAR_FACTS]],
    }

    narrative = _narrative(facts) or fallback_summary(fields)

    digest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "narrative":    narrative,
        "buy_ready":    buy_ready,
        "movers":       movers,
        "upcoming_earnings": earnings,
        "sec_stakes":   stakes,
        "data_warnings": data_warnings,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(digest, f, indent=2)

    print("📋 WEEKLY DIGEST")
    if narrative:
        print(f"\n{narrative}\n")
    print(f"Buy-ready at target: {', '.join(facts['buy_ready_at_target']) or 'none'}")
    print(f"Movers: {', '.join(m['ticker'] for m in movers) or 'none'}")
    print(f"Earnings ahead: {', '.join(e['ticker'] for e in earnings) or 'none'}")
    if data_warnings:
        print(f"⚠ Data warnings: {', '.join(data_warnings)}")
    print(f"\n✅ Digest → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
