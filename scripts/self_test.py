#!/usr/bin/env python3
"""
scripts/self_test.py — Does each data source still work? Tried on one known stock.

AAPL always has quarterly results, recent news and insider sales, so an empty answer
means the source or our reading of it broke, not that nothing happened. This is what
catches a source going quiet, which a job finishing on time never will.

Writes data/self_test.json. Always exits 0: health_alert.py does the telling.

Usage:
    python3 scripts/self_test.py
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from field_news import fetch_headlines
from insider_check import _fetch_one
from news_feed import NO_NEWS, get_recent_news
from refresh_quotes import _latest_op_margin, _ttm_fcf
from sec_filings import HEADERS as SEC_HEADERS, NOTABLE_FORMS, SUBMISSIONS_URL

SCRIPT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "data", "self_test.json")

TICKER = "AAPL"
APPLE_CIK = "0000320193"
_STAKE_FORM_RE = re.compile(r"13[DG]")


def unknown_stake_forms(forms: list[str]) -> list[str]:
    """Stake forms we don't recognise: how the SEC's renaming went unnoticed."""
    return sorted({f for f in forms if _STAKE_FORM_RE.search(f) and f not in NOTABLE_FORMS})


def _quote() -> str | None:
    info = yf.Ticker(TICKER).info
    missing = [k for k in ("marketCap", "totalRevenue", "forwardPE") if not info.get(k)]
    return f"missing {', '.join(missing)}" if missing else None


def _statements() -> str | None:
    t = yf.Ticker(TICKER)
    if _ttm_fcf(t) is None:
        return "no free cash flow"
    return None if _latest_op_margin(t, {}) else "no operating margin"


def _insiders() -> str | None:
    record = _fetch_one(TICKER)
    return None if record["signal"] not in ("NO_DATA", "ERROR") else record["note"]


def _stock_news() -> str | None:
    return "no headlines" if get_recent_news(TICKER, name="Apple Inc.") == NO_NEWS else None


def _field_news() -> str | None:
    return None if fetch_headlines("data center power") else "no headlines"


def _sec() -> str | None:
    response = requests.get(SUBMISSIONS_URL.format(cik=APPLE_CIK), headers=SEC_HEADERS, timeout=20)
    response.raise_for_status()
    forms = response.json()["filings"]["recent"]["form"]
    unknown = unknown_stake_forms(forms)
    return f"unrecognised forms: {', '.join(unknown)}" if unknown else None


CHECKS = {"Yahoo quote": _quote, "Yahoo statements": _statements, "Yahoo insiders": _insiders,
          "Stock news": _stock_news, "Field news": _field_news, "SEC filings": _sec}


def run_check(name: str, check) -> dict:
    try:
        problem = check()
    except Exception as exc:   # any failure here is the result we're looking for
        problem = str(exc)[:160]
    return {"name": name, "ok": problem is None, "detail": problem}


def main():
    checks = [run_check(name, check) for name, check in CHECKS.items()]
    for c in checks:
        print(f"{'✅' if c['ok'] else '❌'} {c['name']}{': ' + c['detail'] if c['detail'] else ''}")
    with open(OUTPUT_PATH, "w") as f:
        json.dump({"ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "checks": checks}, f, indent=2)


if __name__ == "__main__":
    main()
