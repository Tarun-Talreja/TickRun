#!/usr/bin/env python3
"""
scripts/catalyst_calendar.py — Look FORWARD at what could move your names.

The rest of the pipeline is reactive: a stock moves, then it explains why. This
is the other half — scheduled events that are knowable in advance, with the
market's expectations attached, so you are positioned before the move rather
than reading about it after.

WHAT THIS DOES AND DOES NOT CLAIM
It does not predict prices or direction — nothing can. What it does is surface
(a) when a catalyst lands and (b) the bar the company has to clear, which is
the part people usually miss. A stock can beat on EPS and still fall, because
what matters is the result versus expectations, not the result alone.

Catalysts tracked:
  - Earnings, with consensus EPS/revenue estimates (the actual bar)
  - Ex-dividend dates (matters for the high-yield names routed to your Roth)
  - Macro events you list in data/macro_events.json (FOMC, CPI, jobs). These
    are user-supplied on purpose — the Fed publishes its calendar a year ahead
    and it should be copied from the source rather than guessed at here.

Output:
  data/catalysts.json          (read by build_dashboard.py)

Usage:
    python3 scripts/catalyst_calendar.py
    python3 scripts/catalyst_calendar.py --horizon 45
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

try:
    import yfinance as yf
except ImportError:
    print("Missing dependency: pip install yfinance")
    sys.exit(1)

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
MACRO_PATH     = os.path.join(SCRIPT_DIR, "data", "macro_events.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "data", "catalysts.json")

HORIZON_DAYS = 30
IMMINENT_DAYS = 7        # inside this window a catalyst is "act now" relevant
MAX_WORKERS  = 4


def _load(path, default=None):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}
    return default if default is not None else {}


def _as_date(v):
    """yfinance hands back date, datetime, or unix ts depending on the field."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc).date()
        except (ValueError, OSError):
            return None
    if isinstance(v, datetime):
        return v.date()
    if hasattr(v, "year"):          # datetime.date
        return v
    return None


def _fetch_catalysts(ticker: str) -> list[dict]:
    out = []
    try:
        cal = yf.Ticker(ticker).calendar or {}
    except Exception:
        return out

    # Earnings — carry the consensus so you know the bar, not just the date
    ed = cal.get("Earnings Date")
    ed = ed[0] if isinstance(ed, list) and ed else ed
    d = _as_date(ed)
    if d:
        out.append({
            "ticker": ticker, "type": "earnings", "date": d.isoformat(),
            "eps_estimate": cal.get("Earnings Average"),
            "eps_low": cal.get("Earnings Low"),
            "eps_high": cal.get("Earnings High"),
            "revenue_estimate": cal.get("Revenue Average"),
        })

    d = _as_date(cal.get("Ex-Dividend Date"))
    if d:
        out.append({"ticker": ticker, "type": "ex_dividend", "date": d.isoformat()})

    return out


def _urgency(days_until: int, ctype: str, verdict: str, drawdown) -> str:
    """High = worth acting on now. Earnings on a name you're close to buying is
    the case that actually changes a decision."""
    if ctype == "earnings":
        if days_until <= IMMINENT_DAYS and verdict == "RESEARCH-WORTHY":
            return "high"
        if days_until <= IMMINENT_DAYS:
            return "medium"
        return "low"
    if ctype == "ex_dividend":
        return "medium" if days_until <= 3 else "low"
    return "medium" if days_until <= IMMINENT_DAYS else "low"


def _plan(c: dict, cand: dict) -> str:
    """Concrete, pre-committed action — decided before the event, not during it."""
    t, v = c["type"], cand.get("verdict", "")
    if t == "earnings":
        est = c.get("eps_estimate")
        bar = f" Consensus EPS ~{est:.2f}." if isinstance(est, (int, float)) else ""
        if v == "RESEARCH-WORTHY":
            return (f"Decide BEFORE the print.{bar} If you would buy on a beat, size the "
                    f"order now; if a miss would break the thesis, write down what number "
                    f"does that. Reacting after the move is how you end up chasing.")
        return (f"Re-read the thesis against what is being reported.{bar} This is the "
                f"quarter that either confirms the reason it is on the list or removes it.")
    if t == "ex_dividend":
        return ("Ex-dividend date — buy before it to receive the dividend. Tax-free in "
                "the Roth, which is where this name is routed.")
    return "Review positioning ahead of this event."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=HORIZON_DAYS)
    args = ap.parse_args()

    wl = _load(WATCHLIST_PATH, {"candidates": []})
    quotes = _load(QUOTES_PATH).get("tickers", {})
    cands = {c["ticker"]: c for c in wl.get("candidates", [])}
    tickers = [t for t, c in cands.items()
               if not t.startswith("^") and c.get("verdict") != "PASS"]

    print(f"🔭 Scanning {len(tickers)} names for catalysts in the next {args.horizon} days...")
    raw = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(_fetch_catalysts, t): t for t in tickers}
        for f in as_completed(futs):
            raw.extend(f.result())
            time.sleep(0.05)

    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=args.horizon)

    events = []
    for c in raw:
        d = datetime.fromisoformat(c["date"]).date()
        if not (today <= d <= horizon):
            continue
        cand = cands.get(c["ticker"], {})
        days = (d - today).days
        q = quotes.get(c["ticker"], {})
        events.append({
            **c,
            "name": cand.get("name", c["ticker"]),
            "verdict": cand.get("verdict"),
            "theme": cand.get("theme"),
            "days_until": days,
            "price": q.get("price"),
            "drawdown_from_high": q.get("drawdown_from_high"),
            "urgency": _urgency(days, c["type"], cand.get("verdict", ""), q.get("drawdown_from_high")),
            "plan": _plan(c, cand),
        })

    # User-supplied macro events (FOMC/CPI/jobs) — see module docstring
    for m in _load(MACRO_PATH, {}).get("events", []):
        try:
            d = datetime.fromisoformat(m["date"]).date()
        except Exception:
            continue
        if today <= d <= horizon:
            days = (d - today).days
            events.append({
                "ticker": "MACRO", "name": m.get("name", "Macro event"),
                "type": "macro", "date": m["date"], "days_until": days,
                "urgency": "high" if days <= IMMINENT_DAYS else "low",
                "plan": m.get("plan", "Rate-sensitive names (utilities, REITs, long-duration "
                                      "growth) react most — check ^TNX around this."),
            })

    events.sort(key=lambda e: (e["days_until"], {"high": 0, "medium": 1, "low": 2}[e["urgency"]]))
    imminent = [e for e in events if e["days_until"] <= IMMINENT_DAYS]
    high = [e for e in events if e["urgency"] == "high"]

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "horizon_days": args.horizon,
        "counts": {"total": len(events), "imminent": len(imminent), "high_urgency": len(high)},
        "events": events,
        "imminent": imminent,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n📅 {len(events)} catalysts in window · {len(imminent)} within {IMMINENT_DAYS} days")
    for e in events[:12]:
        mark = {"high": "🔴", "medium": "🟡", "low": "⚪"}[e["urgency"]]
        est = e.get("eps_estimate")
        bar = f" (cons. EPS {est:.2f})" if isinstance(est, (int, float)) else ""
        print(f"  {mark} {e['days_until']:>3}d  {e['ticker']:6s} {e['type']:12s}{bar}")
    print(f"\n✅ Catalysts → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
