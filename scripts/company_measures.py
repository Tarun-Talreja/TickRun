#!/usr/bin/env python3
"""
scripts/company_measures.py — Company-reported cash flow, read from the filed earnings release.

Power producers post cash collateral on their energy hedges, so their reported operating
cash flow swings with power prices: CEG's was negative in 2023 and 2024 while it earned
$1.6B and $3.75B. Their own adjusted measures remove that swing (VST's definition
excludes "changes in margin deposits and working capital"), which is what the
valuation needs for these companies.

Each company here has a reviewed rule: which measure, and the wording that finds it in
the release. The figure is kept with its exact quote and filing, so it can be checked.
If the wording changes, the rule finds nothing and the stock gets no price rather than
a guess. Wording does change between quarters, so a miss is expected occasionally and
the rule is then updated by hand after reading the new release.

Output: data/company_measures.json (read by valuation.py)
Usage:  python3 scripts/company_measures.py
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sec_facts import HEADERS, REQUEST_GAP_SECONDS

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUNDAMENTALS_PATH = os.path.join(SCRIPT_DIR, "data", "fundamentals.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "data", "company_measures.json")
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{name}"
RESULTS_ITEM = "2.02"   # 8-K item for "Results of Operations and Financial Condition"
QUOTE_PADDING = 60
_NUMBER = r"([\d,]+(?:\.\d+)?)"

# kind: cash_flow_total (dollars, divided by shares) or earnings_per_share.
# scale turns the release's units into dollars.
MEASURES = {
    "VST": {"name": "Adjusted free cash flow before growth (company guidance)",
            "kind": "cash_flow_total", "scale": 1e6,
            "pattern": rf"Adjusted free cash flow before growth guidance \$ {_NUMBER} \$ {_NUMBER}"},
    "TLN": {"name": "Adjusted free cash flow (company guidance)",
            "kind": "cash_flow_total", "scale": 1e6,
            "pattern": (rf"Adjusted Free Cash Flow guidance ranges? (?:to|of) \$[\d,]+ million - "
                        rf"\$[\d,]+ million and \${_NUMBER} million - \${_NUMBER} million")},
    "CEG": {"name": "Adjusted operating earnings per share (company guidance, used as a cash proxy)",
            "kind": "earnings_per_share", "scale": 1.0,
            "pattern": rf"Operating Earnings guidance range to \${_NUMBER} - \${_NUMBER} per share"},
}


def release_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;|&#xa0;", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"&#8211;|&#8212;|&#x2013;|&#x2014;|&ndash;|&mdash;", "-", text, flags=re.IGNORECASE)
    text = re.sub(r"&#?[0-9a-z]+;", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def find_measure(ticker: str, text: str) -> dict | None:
    rule = MEASURES.get(ticker)
    match = re.search(rule["pattern"], text) if rule else None
    if not match:
        return None
    low, high = (float(g.replace(",", "")) * rule["scale"] for g in match.groups())
    start, end = max(match.start() - QUOTE_PADDING, 0), match.end()
    return {"name": rule["name"], "kind": rule["kind"], "low": low, "high": high,
            "mid": (low + high) / 2, "quote": text[start:end]}


def _get(url: str) -> requests.Response:
    time.sleep(REQUEST_GAP_SECONDS)
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response


def latest_release(cik: str) -> tuple[str, str, str]:
    """(filing date, document url, text) of the newest earnings-release 8-K."""
    recent = _get(SUBMISSIONS_URL.format(cik=cik)).json()["filings"]["recent"]
    i = next(i for i, (form, items) in enumerate(zip(recent["form"], recent["items"]))
             if form == "8-K" and RESULTS_ITEM in items)
    accession, primary = recent["accessionNumber"][i].replace("-", ""), recent["primaryDocument"][i]
    folder = ARCHIVE_URL.format(cik=int(cik), accession=accession, name="index.json")
    files = _get(folder).json()["directory"]["item"]
    # The release is the exhibit: the largest page other than the 8-K cover and SEC's own.
    exhibits = [f for f in files if f["name"].endswith(".htm") and f["name"] != primary
                and not re.match(r"R\d+\.htm|.*index", f["name"])]
    name = max(exhibits, key=lambda f: int(f.get("size") or 0))["name"]
    url = ARCHIVE_URL.format(cik=int(cik), accession=accession, name=name)
    return recent["filingDate"][i], url, release_text(_get(url).text)


def main() -> None:
    fundamentals = json.load(open(FUNDAMENTALS_PATH)).get("tickers", {})
    results, misses = {}, []
    for ticker in MEASURES:
        cik = fundamentals.get(ticker, {}).get("cik")
        if not cik:
            misses.append(f"{ticker}: no SEC number")
            continue
        try:
            filed, url, text = latest_release(cik)
        except (requests.RequestException, StopIteration, ValueError) as exc:
            misses.append(f"{ticker}: release unavailable ({str(exc)[:80]})")
            continue
        found = find_measure(ticker, text)
        if found is None:
            misses.append(f"{ticker}: wording not found in the {filed} release, rule needs review")
        results[ticker] = {"filed": filed, "url": url, "measure": found}
    with open(OUTPUT_PATH, "w") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "tickers": results, "misses": misses}, f, indent=1)
    for miss in misses:
        print(f"⚠ {miss}")
    print(f"✅ Company measures found for {sum(bool(r['measure']) for r in results.values())}/{len(MEASURES)}")


if __name__ == "__main__":
    main()
