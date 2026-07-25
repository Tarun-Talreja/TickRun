#!/usr/bin/env python3
"""
scripts/daily_brief.py — The 30-second morning glance.

THE PROBLEM THIS SOLVES
The Signals screen currently renders ~204 cards and the watchlist another 57.
That is comprehensive and completely unglanceable, and most of it is identical
to yesterday: 26 names sit "at research target", but ~24 of them were at target
yesterday too. Re-reading a static list every morning is not information, it is
noise that trains you to ignore the app.

So this reports CHANGE, not STATE. Something earns a slot only if it is new or
newly urgent versus the last snapshot. On a quiet day the right output is "no
changes" — that is a feature, not an empty result.

Ranking is by whether it could change a decision TODAY:
  1. Catalysts landing within 2 days  — the deadline you cannot move
  2. Newly at research target          — a name that crossed the line since yesterday
  3. Big movers                        — with the reason already attached
  4. New SEC ownership stakes          — smart money, filed within 10 days
  5. Verdict changes                   — research changed its mind about something
  6. Data warnings                     — do not act on a broken number

State:
  data/brief_snapshot.json   — yesterday's state, for diffing (committed)
Output:
  output/daily_brief.json    — today's brief (read by build_dashboard.py)

Usage:
    python3 scripts/daily_brief.py
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PATH = os.path.join(SCRIPT_DIR, "output", "dashboard.json")
SNAPSHOT_PATH  = os.path.join(SCRIPT_DIR, "data", "brief_snapshot.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "output", "daily_brief.json")

MAX_ITEMS   = 7      # a glance, not a report
MOVER_PCT   = 5.0    # only surface moves this large
CATALYST_DAYS = 2    # "today or tomorrow" urgency


def _load(path, default=None):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}
    return default if default is not None else {}


def _current_state(d: dict) -> dict:
    """The minimal fingerprint needed to detect meaningful change."""
    sig = d.get("signals", {})
    return {
        "at_target":  sorted(h["ticker"] for h in sig.get("target_hits", [])),
        "verdicts":   {c["ticker"]: c.get("verdict") for c in d.get("watchlist", {}).get("all", [])},
        "sec_stakes": sorted(f"{f['ticker']}:{f.get('filed_date')}"
                             for f in sig.get("sec_ownership_stakes", [])),
        "data_bad":   sorted(c["ticker"] for c in d.get("watchlist", {}).get("all", [])
                             if c.get("data_ok") is False),
    }


def main():
    d = _load(DASHBOARD_PATH)
    if not d:
        print("No dashboard.json — run build_dashboard.py first.")
        sys.exit(0)

    sig  = d.get("signals", {})
    prev = _load(SNAPSHOT_PATH, {})
    cur  = _current_state(d)
    first_run = not prev

    items = []

    # 1. Catalysts landing today/tomorrow — a fixed deadline outranks everything
    for e in (d.get("catalysts") or {}).get("imminent", []):
        if e.get("days_until", 99) <= CATALYST_DAYS and e.get("urgency") != "low":
            when = "TODAY" if e["days_until"] == 0 else f"in {e['days_until']}d"
            est = e.get("eps_estimate")
            bar = f" · consensus EPS {est:.2f}" if isinstance(est, (int, float)) else ""
            items.append({
                "priority": 1, "kind": "catalyst", "ticker": e["ticker"],
                "headline": f"{e['ticker']} {str(e.get('type','')).replace('_',' ')} {when}{bar}",
                "detail": e.get("plan", ""),
                "action": "Decide your number before the print — not after.",
            })

    # 2. NEWLY at research target — the ones that crossed the line since yesterday
    new_targets = [t for t in cur["at_target"] if t not in set(prev.get("at_target", []))]
    if not first_run:
        for h in sig.get("target_hits", []):
            if h["ticker"] in new_targets:
                items.append({
                    "priority": 2, "kind": "new_target", "ticker": h["ticker"],
                    "headline": f"{h['ticker']} newly at research target ({h.get('gap_pct', 0):+.1f}%)",
                    "detail": (h.get("next_action") or "")[:160],
                    "action": "Worth reviewing today — this is new since yesterday.",
                })

    # 3. Big movers — reason already attached by move_explainer
    NO_REASON = {"no clear catalyst in current news.",
                 "see headlines (explanation limited to top movers).",
                 ""}
    for m in sig.get("price_movers", []):
        pct = m.get("primary_pct") or 0
        if abs(pct) >= MOVER_PCT:
            arrow = "▲" if pct > 0 else "▼"
            reason = (m.get("reason") or "").strip()
            has_reason = reason.lower() not in NO_REASON
            items.append({
                "priority": 3, "kind": "mover", "ticker": m["ticker"],
                "headline": f"{m['ticker']} {arrow} {pct:+.1f}%",
                # A real reason IS the detail. With no reason, don't repeat a
                # dead-end sentence — say what to actually do about it instead.
                "detail": reason if has_reason else None,
                "action": ("Verdict unaffected unless this breaks your thesis." if has_reason
                           else "No catalyst found — check the ticker's news tab yourself before acting."),
            })

    # 4. New 5%+ ownership stakes — the early smart-money signal
    for s in sig.get("sec_ownership_stakes", []):
        key = f"{s['ticker']}:{s.get('filed_date')}"
        if first_run or key not in set(prev.get("sec_stakes", [])):
            items.append({
                "priority": 4, "kind": "sec_stake", "ticker": s["ticker"],
                "headline": f"{s['ticker']} — {s.get('label', s.get('form'))} filed {s.get('filed_date')}",
                "detail": s.get("meaning", ""),
                "action": "Read the filing before treating this as a signal — a stake alone isn't a buy/sell call.",
            })

    # 5. Verdict changes — research changed its mind
    if not first_run:
        for ticker, v in cur["verdicts"].items():
            old = prev.get("verdicts", {}).get(ticker)
            if old and old != v:
                items.append({
                    "priority": 5, "kind": "verdict_change", "ticker": ticker,
                    "headline": f"{ticker} verdict changed: {old} → {v}",
                    "detail": "Research reassessed this name since your last check.",
                    "action": ("Now buy-ready — worth a look." if v == "RESEARCH-WORTHY"
                               else "No longer buy-ready — re-read why before adding more."),
                })

    # 6. Data warnings — never act on a number the app itself distrusts
    new_bad = [t for t in cur["data_bad"] if first_run or t not in set(prev.get("data_bad", []))]
    for t in new_bad:
        items.append({
            "priority": 6, "kind": "data_warning", "ticker": t,
            "headline": f"{t} — data quality warning",
            "detail": "Figures look unreliable; verify before acting on this name.",
            "action": "Do not act on this name's targets/verdict until the data is confirmed clean.",
        })

    items.sort(key=lambda i: i["priority"])
    shown, hidden = items[:MAX_ITEMS], max(0, len(items) - MAX_ITEMS)

    brief = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "first_run": first_run,
        "items": shown,
        "hidden_count": hidden,
        "quiet_day": len(shown) == 0,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(brief, f, indent=2)
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(cur, f, indent=2)

    print("☀️  DAILY BRIEF")
    if first_run:
        print("   (first run — establishing baseline, deltas start tomorrow)")
    if not shown:
        print("   Nothing changed since yesterday. No action needed.")
    for i in shown:
        print(f"   • {i['headline']}")
        if i.get("detail"):
            print(f"     {i['detail'][:110]}")
    if hidden:
        print(f"   (+{hidden} more, see Signals)")
    print(f"\n✅ Brief → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
