#!/usr/bin/env python3
"""
scripts/company_events.py — News that makes a buy-below price unsafe to rely on.

From the company's own SEC filings where possible: each 8-K states what it is about by
item number, so no headline has to be interpreted. Headlines add only what a company
wouldn't file itself, such as a short-seller report, and are quoted, not judged.

Output: data/company_events.json (read by build_dashboard.py)
Usage:  python3 scripts/company_events.py
"""
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from company_measures import MEASURES
from io_utils import load_json
from sec_facts import HEADERS, REQUEST_GAP_SECONDS

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUNDAMENTALS_PATH = os.path.join(SCRIPT_DIR, "data", "fundamentals.json")
NEWS_PATH = os.path.join(SCRIPT_DIR, "data", "news_cache.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "data", "company_events.json")
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

FILING_DAYS, HEADLINE_DAYS = 120, 30
RESULTS = "2.02"
SERIOUS_ITEMS = {"4.02": "said past financial statements can't be relied on", "1.03": "filed for bankruptcy",
                 "3.01": "received a delisting notice", "4.01": "changed its auditor",
                 "2.06": "wrote down assets", "1.05": "reported a serious cyber attack"}
_SERIOUS_RE = re.compile(
    r"\bfraud|short[- ]seller|\brestate(?:s|d|ment)\b|\bSEC (?:probe|investigat|charges|subpoena)|subpoena|"
    r"(?:withdraws?|pulls?|suspends?) (?:[\w-]+ ){0,3}(?:guidance|outlook|forecast)|going concern|bankrupt|"
    r"delist|accounting (?:probe|irregular)|"
    r"(?:cuts?|lowers?|slashes) (?:[\w-]+ ){0,3}(?:guidance|outlook)", re.IGNORECASE)
# Law firms advertise for clients after any fall, and that isn't an event.
_NOISE_RE = re.compile(r"class action|law (?:firm|offices)|shareholder alert|investors? (?:who|with)|deadline|"
                       r"reminds|anti-fraud|fraud (?:detection|prevention|protection|tool)|fight fraud|\?", re.IGNORECASE)


def filing_events(recent: dict, today: date) -> list[dict]:
    since = (today - timedelta(days=FILING_DAYS)).isoformat()
    rows = zip(recent["form"], recent["filingDate"], recent["items"], recent["accessionNumber"])
    return [{"date": filed, "source": "SEC filing", "text": f"The company {SERIOUS_ITEMS[item]}", "accession": acc}
            for form, filed, items, acc in rows if form.startswith("8-K") and filed >= since
            for item in items.split(",") if item in SERIOUS_ITEMS]


def newer_results(recent: dict) -> str | None:
    """When results were announced after the last full report, so the SEC figures are a quarter old."""
    rows = list(zip(recent["form"], recent["filingDate"], recent["items"]))
    announced = max((d for f, d, items in rows if f == "8-K" and RESULTS in items.split(",")), default="")
    reported = max((d for f, d, _ in rows if f in ("10-Q", "10-K")), default="")
    return announced if announced > reported else None


def headline_events(news: list[dict], today: date) -> list[dict]:
    since = (today - timedelta(days=HEADLINE_DAYS)).isoformat()
    return [{"date": n["date"], "source": n.get("publisher") or "headline", "text": n["title"], "url": n.get("url")}
            for n in news if n.get("date", "") >= since and _SERIOUS_RE.search(n.get("title", ""))
            and not _NOISE_RE.search(n["title"])]


def main() -> None:
    fundamentals, news = load_json(FUNDAMENTALS_PATH).get("tickers", {}), load_json(NEWS_PATH).get("news", {})
    old = load_json(OUTPUT_PATH).get("tickers", {})
    today, out, failed = datetime.now(timezone.utc).date(), {}, []
    for ticker, record in sorted(fundamentals.items()):
        try:
            response = requests.get(SUBMISSIONS_URL.format(cik=record["cik"]), headers=HEADERS, timeout=30)
            response.raise_for_status()
            recent = response.json()["filings"]["recent"]
            filings = filing_events(recent, today)
            results = None if ticker in MEASURES else newer_results(recent)
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"⚠ {ticker}: {str(exc)[:100]}")
            failed.append(ticker)
            filings = [e for e in old.get(ticker, {}).get("serious", []) if e["source"] == "SEC filing"]
            results = old.get(ticker, {}).get("newer_results")
        out[ticker] = {"serious": [*filings, *headline_events(news.get(ticker, []), today)], "newer_results": results}
        time.sleep(REQUEST_GAP_SECONDS)
    if len(failed) * 2 > len(out):
        sys.exit("SEC filings unavailable, keeping the last events file.")
    with open(OUTPUT_PATH, "w") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "failed": failed, "tickers": out}, f, indent=1)
    flagged = {t: len(e["serious"]) for t, e in out.items() if e["serious"]}
    print(f"✅ Events checked for {len(out)}; serious: {flagged or 'none'}; newer results: "
          f"{', '.join(t for t, e in out.items() if e['newer_results']) or 'none'}")


if __name__ == "__main__":
    main()
