#!/usr/bin/env python3
"""
universe.py — Construct the candidate stock universe for TickRun.

Pulls iShares IWR (mid-cap) + IWM (small-cap) holdings, deduplicates,
filters to U.S.-listed equities in the $300M–$10B market-cap band,
and writes data/universe.json.

This replaces the prior S&P 500 fetch from Wikipedia. The universe is
the FILTER STAGE — fundamentals, scoring, and exclusions run downstream
on this list.

Usage:
    python3 universe.py

Requirements:
    pip3 install requests pandas
"""

import csv
import io
import json
import os
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("Missing dependency: pip3 install requests")
    sys.exit(1)

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "data", "universe.json")
os.makedirs(os.path.join(SCRIPT_DIR, "data"), exist_ok=True)

# iShares CSV endpoints (free, public, daily-updated).
SOURCES = {
    "IWR": ("https://www.ishares.com/us/products/239708/ishares-russell-mid-cap-etf/"
            "1467271812596.ajax?fileType=csv&fileName=IWR_holdings&dataType=fund"),
    "IWM": ("https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
            "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"),
}

# Hard universe gates — market-cap band is enforced downstream by
# fundamentals.py using real yfinance mcap, since the iShares CSV does
# not expose per-company market cap directly. Russell IWR + IWM
# membership already restricts the universe to roughly $300M–$50B.
ALLOWED_EXCHANGES = {"NYSE", "NASDAQ", "Cboe BZX", "Nyse Mkt Llc"}
EXCLUDED_ASSET_CLASSES = {
    "Cash", "Cash Equivalent", "Money Market", "Bond", "Currency Hedging",
    "Cash Collateral and Margins", "Futures",
}
EXCLUDED_NAME_KEYWORDS = (
    "ETF", "ETN", "ETP", "FUND", "TRUST", "ADR", "PREFERRED", "WARRANT",
    "RIGHTS", "UNIT", "WHEN ISSUED", "SPAC", " 2X ", " 3X ", "INVERSE",
    "LEVERAGED", "BULL", "BEAR",
)


def fetch_holdings_csv(url: str) -> list[dict]:
    """Download an iShares holdings CSV and parse it into rows.

    The CSV has a multi-line header (fund metadata) before the actual
    table. We skip until we find the row beginning with 'Ticker'.
    """
    resp = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (TickRun universe.py)"},
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig")  # strip BOM

    lines = text.splitlines()
    # Find the header row.
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("Ticker,")),
        None,
    )
    if header_idx is None:
        raise ValueError(f"Could not locate header row in CSV from {url}")

    table = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(table))
    return [row for row in reader]


def parse_money(s: str) -> float | None:
    if not s or s in ("-", ""):
        return None
    try:
        return float(s.replace(",", "").replace('"', ""))
    except ValueError:
        return None


def is_excluded(row: dict) -> tuple[bool, str]:
    """Return (excluded, reason) — runs the hard gates."""
    asset_class = (row.get("Asset Class") or "").strip()
    if asset_class != "Equity":
        return True, f"asset_class={asset_class!r}"

    if asset_class in EXCLUDED_ASSET_CLASSES:
        return True, f"excluded_asset_class={asset_class!r}"

    location = (row.get("Location") or "").strip()
    if location and location != "United States":
        return True, f"non_us={location!r}"

    exchange = (row.get("Exchange") or "").strip()
    if exchange and exchange not in ALLOWED_EXCHANGES:
        return True, f"exchange={exchange!r}"

    name = (row.get("Name") or "").upper()
    for kw in EXCLUDED_NAME_KEYWORDS:
        if kw in name:
            return True, f"name_keyword={kw!r}"

    weight = parse_money(row.get("Weight (%)", ""))
    if weight is None or weight <= 0:
        return True, "no_weight"

    ticker = (row.get("Ticker") or "").strip()
    if not ticker or len(ticker) > 6:
        return True, f"bad_ticker={ticker!r}"

    return False, ""


def normalize_ticker(t: str) -> str:
    # iShares uses '.' for share class (e.g. BRK.B); yfinance uses '-'.
    return t.strip().upper().replace(".", "-")


def build_universe():
    print("🌐 TickRun universe builder")
    print(f"   Sources: {', '.join(SOURCES.keys())}\n")

    seen: dict[str, dict] = {}
    excluded_counts: dict[str, int] = {}

    for fund, url in SOURCES.items():
        print(f"Fetching {fund} holdings…")
        try:
            rows = fetch_holdings_csv(url)
        except Exception as exc:
            print(f"  ⚠ {fund}: {exc}")
            continue
        print(f"  Parsed {len(rows)} rows")

        kept = 0
        for row in rows:
            excluded, reason = is_excluded(row)
            if excluded:
                bucket = reason.split("=")[0].split(":")[0]
                excluded_counts[bucket] = excluded_counts.get(bucket, 0) + 1
                continue

            ticker = normalize_ticker(row["Ticker"])
            if ticker in seen:
                continue

            seen[ticker] = {
                "symbol":      ticker,
                "name":        row.get("Name", "").strip(),
                "sector_etf":  row.get("Sector", "").strip(),
                "exchange":    row.get("Exchange", "").strip(),
                "source_fund": fund,
            }
            kept += 1

        print(f"  Kept {kept} from {fund}")

    universe = sorted(seen.values(), key=lambda x: x["symbol"])

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources":      list(SOURCES.keys()),
        "filters": {
            "allowed_exchanges": sorted(ALLOWED_EXCHANGES),
            "asset_class":       "Equity (US-listed)",
            "size_band":         "Russell mid+small (IWR+IWM membership)",
            "note":               "Per-company market-cap gate (300M–10B) is enforced downstream in fundamentals.py against live yfinance data.",
        },
        "size":       len(universe),
        "exclusions": dict(sorted(excluded_counts.items(), key=lambda x: -x[1])),
        "tickers":    universe,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Universe built: {len(universe)} tickers → {OUTPUT_PATH}")
    print(f"   Exclusions: {dict(list(output['exclusions'].items())[:6])}")


if __name__ == "__main__":
    build_universe()
