#!/usr/bin/env python3
"""
scripts/sec_filings.py — Early smart-money signal via SEC EDGAR (free, no API key).

The quarterly 13F (hedge_fund_signal.py) lags 45 days. These filings are FAST:
  - SC 13D / SC 13G  → 5%+ ownership stake (activist or passive). Filed within 10 days.
  - Form 4           → insider buy/sell. Filed within 2 business days.
  - 8-K              → material corporate event (M&A, guidance, exec change).

This surfaces them for watchlist tickers BEFORE they show up in quarterly 13F data.

Output:
  data/sec_filings.json  — recent notable filings (read by build_dashboard.py)

Usage:
    python3 scripts/sec_filings.py

Free: SEC EDGAR requires only a descriptive User-Agent header (your email).
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests")
    sys.exit(1)

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "data", "sec_filings.json")

# SEC requires a descriptive User-Agent with contact info
HEADERS = {"User-Agent": "TickRun Research tarun888099@gmail.com"}

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# Forms we care about — early smart-money + material-event signals
NOTABLE_FORMS = {
    "SC 13D":    ("ACTIVIST STAKE", "5%+ stake with intent to influence — strongest signal"),
    "SC 13D/A":  ("ACTIVIST UPDATE", "Activist changed their 5%+ position"),
    "SC 13G":    ("PASSIVE 5% STAKE", "5%+ passive stake — institutional conviction"),
    "SC 13G/A":  ("PASSIVE UPDATE", "Passive holder changed their 5%+ position"),
    "4":         ("INSIDER TRADE", "Officer/director bought or sold — filed within 2 days"),
    "8-K":       ("MATERIAL EVENT", "Corporate event: M&A, guidance, exec change"),
}

LOOKBACK_DAYS = 14   # Only surface filings from the last 2 weeks


def _load_watchlist_tickers() -> list[str]:
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)
    # Skip index benchmarks and PASS verdicts — only track real candidates
    tickers = []
    for c in wl.get("candidates", []):
        if c.get("ticker", "").startswith("^"):
            continue
        if c.get("verdict") == "PASS":
            continue
        tickers.append(c["ticker"])
    return tickers


def _build_cik_map(tickers: set[str]) -> dict[str, str]:
    data = requests.get(TICKERS_URL, headers=HEADERS, timeout=30).json()
    cik_map = {}
    for v in data.values():
        t = v["ticker"]
        if t in tickers:
            cik_map[t] = str(v["cik_str"]).zfill(10)
    return cik_map


def _fetch_filings(ticker: str, cik: str, cutoff: datetime) -> list[dict]:
    url = SUBMISSIONS_URL.format(cik=cik)
    try:
        sub = requests.get(url, headers=HEADERS, timeout=30).json()
    except Exception as exc:
        print(f"  {ticker}: error fetching submissions — {exc}")
        return []

    recent = sub.get("filings", {}).get("recent", {})
    forms      = recent.get("form", [])
    dates      = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    docs       = recent.get("primaryDocument", [])

    results = []
    for i, form in enumerate(forms):
        if form not in NOTABLE_FORMS:
            continue
        try:
            fdate = datetime.fromisoformat(dates[i]).replace(tzinfo=timezone.utc)
        except (ValueError, IndexError):
            continue
        if fdate < cutoff:
            continue

        label, meaning = NOTABLE_FORMS[form]
        acc = accessions[i].replace("-", "") if i < len(accessions) else ""
        doc = docs[i] if i < len(docs) else ""
        url_link = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
            if acc and doc else
            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form}"
        )

        results.append({
            "ticker":     ticker,
            "form":       form,
            "label":      label,
            "meaning":    meaning,
            "filed_date": dates[i],
            "url":        url_link,
        })
    return results


def main():
    tickers = _load_watchlist_tickers()
    if not tickers:
        print("No watchlist tickers found.")
        sys.exit(0)

    print(f"📑 Checking SEC EDGAR filings for {len(tickers)} tickers (last {LOOKBACK_DAYS} days)...")
    cik_map = _build_cik_map(set(tickers))

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    all_filings = []

    for ticker in tickers:
        cik = cik_map.get(ticker)
        if not cik:
            continue   # ADRs/ETFs may not have a CIK
        filings = _fetch_filings(ticker, cik, cutoff)
        all_filings.extend(filings)

    # Sort: activist/passive stakes first, then by date (newest first)
    priority = {"SC 13D": 0, "SC 13D/A": 1, "SC 13G": 2, "SC 13G/A": 3, "8-K": 4, "4": 5}
    all_filings.sort(key=lambda f: (priority.get(f["form"], 9), f["filed_date"]), reverse=False)
    all_filings.sort(key=lambda f: f["filed_date"], reverse=True)
    all_filings.sort(key=lambda f: priority.get(f["form"], 9))

    output = {
        "generated_at":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": LOOKBACK_DAYS,
        "filings":       all_filings,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    # Summary
    stakes = [f for f in all_filings if f["form"].startswith("SC 13")]
    insider = [f for f in all_filings if f["form"] == "4"]
    events = [f for f in all_filings if f["form"] == "8-K"]

    print(f"\n✅ {len(all_filings)} notable filings → {OUTPUT_PATH}")
    if stakes:
        print(f"\n🎯 {len(stakes)} OWNERSHIP STAKE filing(s) — the early smart-money signal:")
        for s in stakes:
            print(f"  [{s['label']}] {s['ticker']} — {s['form']} filed {s['filed_date']}")
    if events:
        print(f"\n📰 {len(events)} material event(s) (8-K):")
        for e in events[:10]:
            print(f"  {e['ticker']} — filed {e['filed_date']}")
    print(f"\n💼 {len(insider)} insider (Form 4) filings in window.")


if __name__ == "__main__":
    main()
