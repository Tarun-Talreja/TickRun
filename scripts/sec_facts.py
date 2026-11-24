#!/usr/bin/env python3
"""
scripts/sec_facts.py — The figures companies actually filed with the SEC.

Yahoo's summary fields were wrong often enough to mislead (MSFT net debt, NVDA free
cash flow, VST's June quarter shown as Q3). The SEC's "company facts" data holds
every figure from every 10-K and 10-Q, with its period and filing date, so each
number here can be traced to a filing.

Two traps this handles:
  - Field names change. MSFT's "Revenues" stops in 2010 and continues under a
    newer name, so the name with the most recent filing wins.
  - Filings repeat and restate past years, so the latest filing wins for a period.

Foreign filers (TSM, ASML) report under IFRS on 20-F and have no us-gaap facts;
they come back empty and the valuation says so rather than guessing.

Output: data/fundamentals.json — compact per-ticker history (read by valuation.py)
Usage:  python3 scripts/sec_facts.py
"""
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import load_json

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "data", "fundamentals.json")

# SEC asks for a descriptive client name; set SEC_USER_AGENT to add a contact.
HEADERS = {"User-Agent": os.environ.get("SEC_USER_AGENT", "TickRun personal research tool")}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
REQUEST_GAP_SECONDS = 0.2   # SEC allows 10 requests a second

ANNUAL_FORMS = {"10-K", "10-K/A"}
QUARTER_FORMS = {"10-Q", "10-Q/A"}
FULL_YEAR_DAYS = (350, 380)
SAME_PERIOD_SLACK_DAYS = 10
YEARS_KEPT = 6

# First name wins when several are current. Order reflects which is the total.
CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
              "PaymentsToAcquireOtherPropertyPlantAndEquipment"],
    # Software a company builds for itself is capital spending too (ADP, MKTX, TW).
    "software_capex": ["PaymentsToDevelopSoftware", "PaymentsForSoftware", "PaymentsToAcquireIntangibleAssets"],
    "stock_comp": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "diluted_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}
# Additive over time, so a trailing-twelve-month figure can be built from them.
FLOW_CONCEPTS = {"revenue", "operating_income", "net_income", "operating_cash_flow",
                 "capex", "software_capex", "stock_comp"}
# A field more than this far behind revenue was renamed; its old series would be stale.
STALE_DAYS = 400


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _latest_filed(rows: list[dict]) -> dict:
    """One row per period, from the most recent filing (restatements win)."""
    best = {}
    for r in rows:
        key = (r.get("start"), r["end"])
        if key not in best or r.get("filed", "") >= best[key].get("filed", ""):
            best[key] = r
    return best


def annual_series(rows: list[dict], latest_report_only: bool = False) -> dict[str, float]:
    """Fiscal-year end -> value, full years from annual reports only.

    latest_report_only keeps the years in the newest annual report. Share counts need
    it: the latest report restates past years after a stock split, older ones don't.
    """
    annual = [r for r in rows if r.get("form") in ANNUAL_FORMS and r.get("start")
              and FULL_YEAR_DAYS[0] <= _days(r["start"], r["end"]) <= FULL_YEAR_DAYS[1]]
    if latest_report_only and annual:
        newest = max(r.get("filed", "") for r in annual)
        annual = [r for r in annual if r.get("filed", "") == newest]
    return {end: r["val"] for (_, end), r in sorted(_latest_filed(annual).items())}


def _rows(facts: dict, name: str) -> list[dict]:
    units = facts.get("facts", {}).get("us-gaap", {}).get(name, {}).get("units", {})
    return next(iter(units.values()), [])


def pick_concept(facts: dict, names: list[str]) -> tuple[str | None, list[dict]]:
    """The name still being filed: newest period end, earlier names winning ties."""
    best, best_end, best_rows = None, "", []
    for name in names:
        rows = _rows(facts, name)
        end = max((r["end"] for r in rows), default="")
        if end > best_end:
            best, best_end, best_rows = name, end, rows
    return best, best_rows


def _near(a: str, b: str) -> bool:
    return abs(_days(a, b)) <= SAME_PERIOD_SLACK_DAYS


def ttm(rows: list[dict]) -> dict | None:
    """Last twelve months: last full year + this year to date - last year to date."""
    annual = annual_series(rows)
    if not annual:
        return None
    fy_end = max(annual)
    ytd = [r for r in _latest_filed([r for r in rows if r.get("form") in QUARTER_FORMS
                                     and r.get("start")]).values()]
    newer = [r for r in ytd if r["end"] > fy_end and _days(fy_end, r["start"]) <= SAME_PERIOD_SLACK_DAYS]
    if not newer:
        return {"end": fy_end, "value": annual[fy_end]}
    now = max(newer, key=lambda r: r["end"])
    length = _days(now["start"], now["end"])
    year_ago = date.fromisoformat(now["end"]) - timedelta(days=365)   # safe on Feb 29
    prior = next((r for r in ytd if _near(r["end"], year_ago.isoformat())
                  and abs(_days(r["start"], r["end"]) - length) <= SAME_PERIOD_SLACK_DAYS), None)
    if prior is None:
        return None
    return {"end": now["end"], "value": annual[fy_end] + now["val"] - prior["val"]}


def latest_value(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    newest = max(rows, key=lambda r: (r["end"], r.get("filed", "")))
    return {"end": newest["end"], "value": newest["val"]}


def _is_stale(years: dict[str, float], newest: str | None) -> bool:
    return bool(newest) and (not years or _days(max(years), newest) > STALE_DAYS)


def extract(facts: dict) -> dict:
    """Compact history for one company: annual values, trailing twelve months, source names.

    A field whose latest annual figure is over a year behind revenue's is dropped and
    listed as stale: TPL's capital spending stopped in 2023 and EME's stock-based pay in
    2011 under the names found, and using them would understate today's spending.
    """
    out = {"annual": {}, "ttm": {}, "source": {}, "stale": []}
    revenue_end = max(annual_series(pick_concept(facts, CONCEPTS["revenue"])[1]), default=None)
    for concept, names in CONCEPTS.items():
        name, rows = pick_concept(facts, names)
        if not name:
            continue
        flow = concept in FLOW_CONCEPTS
        years = annual_series(rows, latest_report_only=not flow)
        if _is_stale(years, revenue_end):
            out["stale"].append(concept)
            continue
        out["source"][concept] = name
        out["annual"][concept] = dict(sorted(years.items())[-YEARS_KEPT:]) if flow else years
        out["ttm"][concept] = ttm(rows) if flow else latest_value(rows)
    return _same_period(out)


def _same_period(record: dict) -> dict:
    """Only figures from the same years as revenue, and the same last twelve months.

    AVGO's profit stopped in 2024 under the name found and was being divided by 2026
    sales; PAYX's and TLN's series jumped back to 2013.
    """
    revenue_years = record["annual"].get("revenue", {})
    end = (record["ttm"].get("revenue") or {}).get("end")
    if not revenue_years or not end:
        return record
    first = min(revenue_years)
    annual = {k: {y: v for y, v in years.items() if y >= first} if k in FLOW_CONCEPTS else years
              for k, years in record["annual"].items()}
    ttm_rows = {k: None if k in FLOW_CONCEPTS and v and not _near(v["end"], end) else v
                for k, v in record["ttm"].items()}
    return {**record, "annual": annual, "ttm": ttm_rows}


def _cik_map() -> dict[str, str]:
    response = requests.get(TICKERS_URL, headers=HEADERS, timeout=30)
    if response.status_code == 403:
        # www.sec.gov wants a contact address in the client name; data.sec.gov doesn't.
        sys.exit("SEC refused the ticker list. Set SEC_USER_AGENT to 'TickRun <your email>'.")
    response.raise_for_status()
    return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in response.json().values()}


def _tickers() -> list[str]:
    candidates = load_json(WATCHLIST_PATH, {"candidates": []}).get("candidates", [])
    return sorted({c["ticker"] for c in candidates if not c["ticker"].startswith("^")})


def main() -> None:
    ciks = _cik_map()
    results, missing = {}, []
    for ticker in _tickers():
        cik = ciks.get(ticker.replace("-", "."), ciks.get(ticker))
        if not cik:
            missing.append(ticker)
            continue
        try:
            facts = requests.get(FACTS_URL.format(cik=cik), headers=HEADERS, timeout=60).json()
        except (requests.RequestException, ValueError) as exc:
            print(f"⚠ {ticker}: {str(exc)[:120]}")
            missing.append(ticker)
            continue
        record = extract(facts)
        if not record["annual"]:
            missing.append(ticker)   # foreign filer: no us-gaap facts
        results[ticker] = {**record, "cik": cik, "name": facts.get("entityName")}
        time.sleep(REQUEST_GAP_SECONDS)
    with open(OUTPUT_PATH, "w") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "tickers": results, "missing": missing}, f, indent=1)
    found = sum(1 for r in results.values() if r["annual"])
    print(f"✅ SEC figures for {found} companies; none for {', '.join(missing) or 'none'}")
    if found < len(missing):
        sys.exit(1)


if __name__ == "__main__":
    main()
