#!/usr/bin/env python3
"""
scripts/refresh_quotes.py — Fetch current quotes for portfolio + watchlist.

Reads data/portfolio.json and data/watchlist.json, fetches current
price/fundamentals for each ticker via yfinance, and writes the results
to data/quotes_cache.json.

Usage:
    python3 scripts/refresh_quotes.py

Requirements:
    pip install yfinance tenacity
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import lru_cache

try:
    import yfinance as yf
except ImportError:
    print("Missing dependency: pip install yfinance")
    sys.exit(1)

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
except ImportError:
    print("Missing dependency: pip install tenacity")
    sys.exit(1)

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(SCRIPT_DIR, "data", "portfolio.json")
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")

# 3 workers avoids Yahoo Finance rate-limit throttling
MAX_WORKERS = 3
# Fail the workflow if more than half the tickers error out
FAILURE_THRESHOLD = 0.5


def _collect_tickers() -> list[str]:
    tickers = set()
    with open(PORTFOLIO_PATH) as f:
        port = json.load(f)
    for item in port.get("core", []):
        tickers.add(item["ticker"])
    for item in port.get("thematic", []):
        tickers.add(item["ticker"])

    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)
    for item in wl.get("candidates", []):
        tickers.add(item["ticker"])

    return sorted(tickers)


@lru_cache(maxsize=None)
def _fx_rate(from_cur: str, to_cur: str) -> float | None:
    """Latest close for from_cur→to_cur, or None if Yahoo has no rate."""
    try:
        closes = yf.Ticker(f"{from_cur}{to_cur}=X").history(period="5d")["Close"].dropna()
        return float(closes.iloc[-1]) if len(closes) else None
    except Exception as exc:
        print(f"  ⚠ no FX rate {from_cur}→{to_cur}: {exc}")
        return None


def _ttm_fcf(t) -> float | None:
    """Operating cash flow minus capex, summed over the last four quarters.

    Not info["freeCashflow"]: that is Yahoo's levered figure, which showed $42B
    for NVDA when its filings give $127B, $3B for MSFT, and -$1.2B for GOOGL.
    """
    try:
        quarters = t.quarterly_cashflow.loc["Free Cash Flow"].dropna().sort_index(ascending=False)
    except KeyError:
        return None
    return float(quarters.iloc[:4].sum()) if len(quarters) >= 4 else None


def _latest_op_margin(t, info: dict) -> float | None:
    """Reported operating margin of the latest quarter, as a percent.

    Not info["operatingMargins"]: Yahoo leaves some charges out of it, so META
    showed 35.4% for a quarter it reported at 20.1%, and NOW 17.4% against 9.4%.
    Falls back to Yahoo's figure when the statement has no operating income line.
    """
    try:
        income = t.quarterly_income_stmt
        latest = income.columns.max()
        margin = income.loc["Operating Income", latest] / income.loc["Total Revenue", latest]
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        margin = None
    if margin is None or margin != margin:
        margin = info.get("operatingMargins")
    return round(float(margin) * 100, 1) if margin else None


def _latest_quarter(t, fx: float | None) -> dict:
    """The newest reported quarter, so notes quote it instead of remembering one."""
    try:
        revenue = t.quarterly_income_stmt.loc["Total Revenue"].dropna()
        latest = revenue.index.max()
        return {"latest_quarter_end": latest.date().isoformat(),
                "latest_quarter_revenue": float(revenue[latest]) * fx if fx else None}
    except (KeyError, ValueError, AttributeError):
        return {"latest_quarter_end": None, "latest_quarter_revenue": None}


def _normalize_money(info: dict, fx: float | None) -> dict:
    """Company-level money fields, in the same currency as the quote.

    Yahoo gives foreign filers' financials in their reporting currency while
    price and market cap stay in USD, so TSM's NT$4.9T revenue reached the
    research prompt as "$4.9T" and "net cash" came out larger than its market
    cap. Its enterprise multiples are unusable for these names too (ASML showed
    1,783x EV/EBITDA), so they are recomputed from market cap.

    With no FX rate the fields are blanked: "unverified" beats a wrong number.
    """
    quote_cur = info.get("currency")
    report_cur = info.get("financialCurrency") or quote_cur
    money = {"currency": quote_cur, "financial_currency": report_cur, "fx_rate": fx}

    if report_cur == quote_cur:
        return {**money,
                "revenue_ttm": info.get("totalRevenue"),
                "fcf_ttm":     info.get("freeCashflow"),
                "total_cash":  info.get("totalCash"),
                "total_debt":  info.get("totalDebt"),
                "ev_ebitda":   info.get("enterpriseToEbitda")}

    def convert(key):
        value = info.get(key)
        return value * fx if value is not None and fx else None

    revenue, ebitda = convert("totalRevenue"), convert("ebitda")
    cash, debt = convert("totalCash"), convert("totalDebt")
    mcap = info.get("marketCap")
    ev = mcap + debt - cash if None not in (mcap, cash, debt) else None
    return {**money,
            "revenue_ttm": revenue,
            "fcf_ttm":     convert("freeCashflow"),
            "total_cash":  cash,
            "total_debt":  debt,
            "ev_ebitda":   round(ev / ebitda, 1) if ev and ebitda and ebitda > 0 else None}


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)
def _fetch_with_retry(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info or {}
    if not info or not info.get("regularMarketPrice") and not info.get("currentPrice"):
        raise ValueError(f"{ticker}: empty info from yfinance")

    hist = t.history(period="1y")
    price    = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
    high_52w = float(info.get("fiftyTwoWeekHigh") or (hist["Close"].max() if not hist.empty else 0))
    low_52w  = float(info.get("fiftyTwoWeekLow")  or (hist["Close"].min() if not hist.empty else 0))
    drawdown_from_high = round((price - high_52w) / high_52w * 100, 1) if high_52w else None

    prev_close = float(info.get("regularMarketPreviousClose") or info.get("previousClose") or 0)
    pct_change_1d = round((price - prev_close) / prev_close * 100, 2) if prev_close else None

    # Dividend yield: derive from dividendRate / price when possible. That is
    # unambiguous and self-verifying, unlike info["dividendYield"], whose units
    # changed — it used to return a decimal (0.0095) and now returns a percent
    # (0.95). The old "multiply by 100 if < 1" heuristic silently inflated every
    # sub-1% payer by 100x (MSFT showed a 95% yield), which in turn corrupted the
    # projected dividend income in portfolio_analytics.
    div_yield_pct = None
    dividend_rate = info.get("dividendRate")
    if dividend_rate and price:
        div_yield_pct = round(dividend_rate / price * 100, 2)
    else:
        raw_yield = info.get("dividendYield")
        if raw_yield:
            # Fall back to the reported field, treating it as a percent, and
            # discard implausible values rather than trusting ambiguous units.
            div_yield_pct = round(raw_yield, 2) if raw_yield < 25 else None

    quote_cur = info.get("currency")
    report_cur = info.get("financialCurrency") or quote_cur
    fx = 1.0 if report_cur == quote_cur else _fx_rate(report_cur, quote_cur)
    money = _normalize_money({**info, "freeCashflow": _ttm_fcf(t)}, fx)

    return {
        "ticker":               ticker,
        "name":                 info.get("longName") or info.get("shortName", ticker),
        "price":                price,
        "pct_change_1d":        pct_change_1d,
        "market_cap":           info.get("marketCap"),
        "sector":               info.get("sector"),
        "industry":             info.get("industry"),
        "high_52w":             high_52w,
        "low_52w":              low_52w,
        "drawdown_from_high":   drawdown_from_high,
        "pe":                   info.get("trailingPE"),
        "forward_pe":           info.get("forwardPE"),
        "revenue_growth":       round(info.get("revenueGrowth", 0) * 100, 1) if info.get("revenueGrowth") else None,
        "gross_margin":         round(info.get("grossMargins", 0) * 100, 1) if info.get("grossMargins") else None,
        "op_margin":            _latest_op_margin(t, info),
        **money,
        **_latest_quarter(t, fx),
        "div_yield_pct":        div_yield_pct,
        "short_percent_float":  round(info.get("shortPercentOfFloat", 0) * 100, 2) if info.get("shortPercentOfFloat") else None,
        "short_ratio":          round(info.get("shortRatio", 0), 1) if info.get("shortRatio") else None,
        "next_earnings":        info.get("earningsTimestamp"),
        "shares_outstanding":   info.get("sharesOutstanding"),
        "fetched_at":           datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status":               "ok",
        "errors":               [],
    }


def _fetch_one(ticker: str) -> dict:
    try:
        return _fetch_with_retry(ticker)
    except Exception as exc:
        return {
            "ticker":     ticker,
            "status":     "error",
            "errors":     [str(exc)],
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }


def main():
    tickers = _collect_tickers()
    if not tickers:
        print("No tickers found in portfolio.json or watchlist.json.")
        sys.exit(0)

    print(f"Refreshing quotes for {len(tickers)} tickers: {', '.join(tickers)}")
    results = {}
    errors = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        for i, future in enumerate(as_completed(futures), 1):
            ticker = futures[future]
            rec = future.result()
            results[ticker] = rec
            status = "✓" if rec["status"] == "ok" else "✗"
            print(f"  [{i:2d}/{len(tickers)}] {ticker} {status}")
            if rec["status"] != "ok":
                errors.append(ticker)
            time.sleep(0.3)

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tickers":      results,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    ok_count = len(results) - len(errors)
    print(f"\n✅ Wrote quotes for {ok_count}/{len(tickers)} tickers → {OUTPUT_PATH}")
    if errors:
        print(f"⚠ Errors on: {', '.join(errors)}")

    if len(errors) / len(tickers) > FAILURE_THRESHOLD:
        print(f"\nERROR: {len(errors)}/{len(tickers)} tickers failed — exceeds {FAILURE_THRESHOLD*100:.0f}% threshold.")
        sys.exit(1)


if __name__ == "__main__":
    main()
