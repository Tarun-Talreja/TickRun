#!/usr/bin/env python3
"""
scripts/data_sanity.py — Auto-flag unreliable data so you never act on a glitch.

yfinance occasionally returns broken data (we hit this with MU, NOW, SNDK —
prices that don't match the 52-week range, impossible P/Es). This script
runs every refresh and flags anything suspicious, so the app can show a
⚠ DATA WARNING badge instead of you having to catch it manually.

Checks per ticker:
  - Price outside its own 52-week [low, high] range   (the NOW/MU/SNDK bug)
  - Absurd P/E (negative-with-positive-price, or > 1000)
  - Forward P/E wildly divergent from trailing (>10x apart) — possible bad field
  - Missing critical fields (price, market cap)
  - Stale fetch (quote older than MAX_STALE_HOURS)
  - Financials reported in another currency (the TSM/ASML bug): no FX rate, or
    P/Es that may mix currencies
  - Impossible balance sheet or multiple (net cash above market cap, EV/EBITDA > 500)

Output:
  data/data_quality.json  — per-ticker flags (read by build_dashboard.py)

Usage:
    python3 scripts/data_sanity.py
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUOTES_PATH  = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
OUTPUT_PATH  = os.path.join(SCRIPT_DIR, "data", "data_quality.json")

MAX_STALE_HOURS = 48
PE_ABSURD       = 1000
EV_EBITDA_ABSURD = 500


def _check_ticker(ticker: str, q: dict) -> list[dict]:
    flags = []
    price = q.get("price")
    high  = q.get("high_52w")
    low   = q.get("low_52w")
    pe    = q.get("pe")
    fpe   = q.get("forward_pe")

    # 1. Price outside 52-week range — the classic yfinance bad-data signal
    if price and high and low and high > 0:
        # allow a small 2% tolerance for intraday spikes beyond the recorded range
        if price > high * 1.02:
            flags.append({"level": "high", "msg": f"Price ${price:.2f} is ABOVE its 52-week high ${high:.2f} — likely stale/bad data"})
        elif price < low * 0.5:
            flags.append({"level": "high", "msg": f"Price ${price:.2f} is far below 52-week low ${low:.2f} — verify (possible split/data error)"})

    # 2. Absurd P/E
    if pe is not None:
        if pe < 0 and price and price > 0:
            flags.append({"level": "low", "msg": f"Negative P/E ({pe:.1f}) — company unprofitable or data issue"})
        elif pe > PE_ABSURD:
            flags.append({"level": "med", "msg": f"Extreme P/E ({pe:.0f}x) — verify earnings figure"})

    # 3. Forward vs trailing PE divergence (both positive, >10x apart)
    if pe and fpe and pe > 0 and fpe > 0:
        ratio = max(pe, fpe) / min(pe, fpe)
        if ratio > 10:
            flags.append({"level": "med", "msg": f"Trailing P/E ({pe:.0f}x) and forward P/E ({fpe:.0f}x) diverge {ratio:.0f}x — check which is real"})

    # 4. Missing price (market cap legitimately absent for ETFs/indices — skip)
    if not price:
        flags.append({"level": "high", "msg": "No price available"})

    # 5. Stale quote
    fetched = q.get("fetched_at")
    if fetched:
        try:
            ft = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
            age_h = (datetime.now(timezone.utc) - ft).total_seconds() / 3600
            if age_h > MAX_STALE_HOURS:
                flags.append({"level": "med", "msg": f"Quote is {age_h:.0f}h old — refresh may have failed"})
        except (ValueError, TypeError):
            pass

    # 6. Reports in another currency. Money fields are converted upstream, but
    # P/Es come straight from Yahoo, which divides a USD price by an EPS whose
    # currency it does not state.
    report_cur, quote_cur = q.get("financial_currency"), q.get("currency")
    if report_cur and quote_cur and report_cur != quote_cur:
        if q.get("fx_rate"):
            flags.append({"level": "low", "msg": f"Reports in {report_cur}; figures converted to {quote_cur} at {q['fx_rate']:.4f}. P/Es may mix currencies — verify against filings"})
        else:
            flags.append({"level": "high", "msg": f"Reports in {report_cur} and no FX rate was available — company financials blanked"})

    # 7. Figures that cannot be true, whatever caused them
    cash, debt, mcap = q.get("total_cash"), q.get("total_debt"), q.get("market_cap")
    if None not in (cash, debt) and mcap and cash - debt > mcap:
        flags.append({"level": "high", "msg": "Net cash exceeds market cap — likely a currency or unit error"})
    ev_ebitda = q.get("ev_ebitda")
    if ev_ebitda and ev_ebitda > EV_EBITDA_ABSURD:
        flags.append({"level": "med", "msg": f"Extreme EV/EBITDA ({ev_ebitda:.0f}x) — verify before relying on it"})

    return flags


def main():
    if not os.path.exists(QUOTES_PATH):
        print("No quotes cache. Run refresh_quotes.py first.")
        sys.exit(0)

    with open(QUOTES_PATH) as f:
        quotes = json.load(f).get("tickers", {})

    quality = {}
    flagged = 0
    for ticker, q in quotes.items():
        if q.get("status") != "ok":
            quality[ticker] = {"ok": False, "flags": [{"level": "high", "msg": "Quote fetch failed"}]}
            flagged += 1
            continue
        flags = _check_ticker(ticker, q)
        quality[ticker] = {"ok": len(flags) == 0, "flags": flags}
        if flags:
            flagged += 1

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checked":      len(quotes),
        "flagged":      flagged,
        "quality":      quality,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"🔍 Checked {len(quotes)} tickers — {flagged} flagged.")
    for ticker, qd in quality.items():
        if not qd["ok"]:
            for flag in qd["flags"]:
                print(f"  [{flag['level'].upper():4s}] {ticker}: {flag['msg']}")
    print(f"\n✅ Data quality → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
