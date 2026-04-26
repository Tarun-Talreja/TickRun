#!/usr/bin/env python3
"""
fundamentals.py — Parallel yfinance fundamentals fetcher with disk cache.

Reads data/universe.json, fetches fundamentals + 1y price history per
ticker (in parallel, with retries), caches each ticker's payload to disk
so repeat runs skip the network, and writes data/fundamentals.json.

The cache lives in data/cache/<TICKER>.json with a TTL — anything
older than CACHE_TTL_HOURS gets refetched. This makes the weekly run
incremental: a single fresh start takes ~25 min; subsequent runs in the
same week (e.g. local testing) take seconds.

Each ticker record carries an explicit `status` and `errors` field, so
"missing" is never silent.

Usage:
    python3 fundamentals.py [--no-cache] [--limit N]

Requirements:
    pip3 install yfinance tenacity
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

try:
    import yfinance as yf
except ImportError:
    print("Missing dependency: pip3 install yfinance")
    sys.exit(1)

try:
    from tenacity import retry, stop_after_attempt, wait_exponential
    _HAS_TENACITY = True
except ImportError:
    _HAS_TENACITY = False

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_PATH = os.path.join(SCRIPT_DIR, "data", "universe.json")
OUTPUT_PATH   = os.path.join(SCRIPT_DIR, "data", "fundamentals.json")
CACHE_DIR     = os.path.join(SCRIPT_DIR, "data", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_TTL_HOURS = 24 * 6   # Refresh weekly — cache survives a session.
MAX_WORKERS     = 12        # yfinance throttles aggressively above this.

# yfinance.info fields that must be present for the record to count
# as "complete." If the call returns an empty dict (rate-limited),
# none of these will populate.
INFO_REQUIRED = ("marketCap", "sector")


def _cache_path(symbol: str) -> str:
    return os.path.join(CACHE_DIR, f"{symbol}.json")


def _is_cache_fresh(symbol: str) -> bool:
    p = _cache_path(symbol)
    if not os.path.exists(p):
        return False
    age = time.time() - os.path.getmtime(p)
    return age < CACHE_TTL_HOURS * 3600


def _read_cache(symbol: str) -> dict | None:
    try:
        with open(_cache_path(symbol)) as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(symbol: str, data: dict) -> None:
    try:
        with open(_cache_path(symbol), "w") as f:
            json.dump(data, f)
    except Exception:
        pass  # Cache write failures are non-fatal.


def _yf_call(symbol: str) -> tuple[dict, "pd.DataFrame"]:
    """Single attempt — raises on rate-limit / empty info."""
    t = yf.Ticker(symbol)
    info = t.info or {}
    if not any(info.get(f) for f in INFO_REQUIRED):
        raise RuntimeError("empty info (rate-limited or delisted)")
    hist = t.history(period="1y")
    if hist.empty:
        raise RuntimeError("empty price history")
    return info, hist


if _HAS_TENACITY:
    _yf_call = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )(_yf_call)


def fetch_one(symbol: str, *, use_cache: bool = True) -> dict:
    """Fetch a single ticker, with cache check + retry.

    Always returns a dict with `symbol`, `status`, and `errors`. Other
    fields are present when status == "ok"; partial data is allowed
    when status == "partial" but flagged so downstream scoring can
    decide how to handle it.
    """
    if use_cache and _is_cache_fresh(symbol):
        cached = _read_cache(symbol)
        if cached:
            return cached

    record: dict = {"symbol": symbol, "status": "ok", "errors": []}
    try:
        info, hist = _yf_call(symbol)
    except Exception as exc:
        record["status"] = "failed"
        record["errors"].append(str(exc))
        _write_cache(symbol, record)
        return record

    closes = hist["Close"]
    price  = float(closes.iloc[-1])

    def _g(field: str):
        v = info.get(field)
        return v if v not in (None, "", float("inf")) else None

    market_cap = _g("marketCap")
    sector     = _g("sector") or "Unknown"
    industry   = _g("industry") or "Unknown"
    summary    = _g("longBusinessSummary") or ""
    quote_type = _g("quoteType") or "EQUITY"

    revenue       = _g("totalRevenue")
    fcf           = _g("freeCashflow")
    operating_cf  = _g("operatingCashflow")
    net_income    = _g("netIncomeToCommon")
    ebitda        = _g("ebitda")
    total_debt    = _g("totalDebt")
    total_cash    = _g("totalCash")

    pe         = _g("trailingPE")
    forward_pe = _g("forwardPE")
    pb         = _g("priceToBook")
    peg        = _g("trailingPegRatio") or _g("pegRatio")
    ps         = _g("priceToSalesTrailing12Months")
    ev_ebitda  = _g("enterpriseToEbitda")
    ev_sales   = _g("enterpriseToRevenue")

    roe          = _g("returnOnEquity")
    roa          = _g("returnOnAssets")
    gross_margin = _g("grossMargins")
    op_margin    = _g("operatingMargins")
    net_margin   = _g("profitMargins")
    eps_qoq      = _g("earningsQuarterlyGrowth")
    rev_growth   = _g("revenueGrowth")

    current_ratio = _g("currentRatio")
    debt_equity   = _g("debtToEquity")  # yfinance returns as %, not ratio
    short_pct     = _g("shortPercentOfFloat")
    beta          = _g("beta")

    div_yield    = _g("dividendYield")
    payout_ratio = _g("payoutRatio")

    # Derived metrics
    de_ratio          = (debt_equity / 100.0) if debt_equity is not None else None
    fcf_margin        = (fcf / revenue) if (fcf and revenue and revenue > 0) else None
    fcf_yield         = (fcf / market_cap) if (fcf and market_cap) else None
    debt_to_ebitda    = ((total_debt or 0) / ebitda) if (total_debt and ebitda and ebitda > 0) else None
    net_debt_to_ebitda = (((total_debt or 0) - (total_cash or 0)) / ebitda) if (ebitda and ebitda > 0) else None

    ret_12m = ((price - float(closes.iloc[0])) / float(closes.iloc[0]) * 100) if len(closes) > 1 else None
    ma_50   = float(closes.rolling(50).mean().iloc[-1])  if len(closes) >= 50  else None
    ma_200  = float(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else None

    # Track which proxy approximations were applied so downstream
    # consumers (and the dashboard) can show them honestly.
    proxy_notes: list[str] = []
    earnings_yield_proxy = None
    if ev_ebitda and ev_ebitda > 0:
        earnings_yield_proxy = 1.0 / ev_ebitda
        proxy_notes.append("earnings_yield_proxy=1/EV_EBITDA")
    roic_proxy = None
    if roe is not None:
        roic_proxy = roe * 100
        proxy_notes.append("roic_proxy=ROE")

    record.update({
        "name":          info.get("longName") or info.get("shortName") or symbol,
        "sector":        sector,
        "industry":      industry,
        "quote_type":    quote_type,
        "summary":       summary,
        "price":         round(price, 2),
        "market_cap":    market_cap,
        # Valuation
        "pe":             round(pe, 2)            if pe          is not None else None,
        "forward_pe":     round(forward_pe, 2)    if forward_pe  is not None else None,
        "pb":             round(pb, 2)            if pb          is not None else None,
        "peg":            round(peg, 2)           if peg         is not None else None,
        "ps":             round(ps, 2)            if ps          is not None else None,
        "ev_ebitda":      round(ev_ebitda, 2)     if ev_ebitda   is not None else None,
        "ev_sales":       round(ev_sales, 2)      if ev_sales    is not None else None,
        "fcf_yield":      round(fcf_yield * 100, 2) if fcf_yield is not None else None,
        "earnings_yield_proxy": round(earnings_yield_proxy, 4) if earnings_yield_proxy is not None else None,
        # Profitability
        "roe":            round(roe * 100, 2)     if roe          is not None else None,
        "roa":            round(roa * 100, 2)     if roa          is not None else None,
        "roic_proxy":     round(roic_proxy, 2)    if roic_proxy   is not None else None,
        "gross_margin":   round(gross_margin * 100, 2) if gross_margin is not None else None,
        "op_margin":      round(op_margin * 100, 2)    if op_margin    is not None else None,
        "net_margin":     round(net_margin * 100, 2)   if net_margin   is not None else None,
        "fcf_margin":     round(fcf_margin * 100, 2)   if fcf_margin   is not None else None,
        # Growth
        "eps_growth":     round(eps_qoq * 100, 2)  if eps_qoq    is not None else None,
        "rev_growth":     round(rev_growth * 100, 2) if rev_growth is not None else None,
        # Risk / balance sheet
        "current_ratio":  round(current_ratio, 2) if current_ratio is not None else None,
        "debt_equity":    round(de_ratio, 2)      if de_ratio      is not None else None,
        "debt_to_ebitda": round(debt_to_ebitda, 2) if debt_to_ebitda is not None else None,
        "net_debt_to_ebitda": round(net_debt_to_ebitda, 2) if net_debt_to_ebitda is not None else None,
        "short_pct_float": round(short_pct * 100, 2) if short_pct is not None else None,
        "beta":           round(beta, 2)          if beta          is not None else None,
        # Income / dividends
        "div_yield":      round(div_yield * 100, 2)  if div_yield  is not None else None,
        "payout_ratio":   round(payout_ratio * 100, 2) if payout_ratio is not None else None,
        # Raw bigs (for downstream gates)
        "fcf":            fcf,
        "ebitda":         ebitda,
        "net_income":     net_income,
        "operating_cf":   operating_cf,
        "total_debt":     total_debt,
        "total_cash":     total_cash,
        "revenue":        revenue,
        # Price action
        "ret_12m":        round(ret_12m, 2) if ret_12m is not None else None,
        "ma_50":          round(ma_50, 2)   if ma_50   is not None else None,
        "ma_200":         round(ma_200, 2)  if ma_200  is not None else None,
        "proxy_notes":    proxy_notes,
        "fetched_at":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    # Mark partial when core scoring inputs are missing.
    missing = [f for f in ("market_cap", "ev_ebitda", "fcf", "revenue") if record.get(f) is None]
    if missing:
        record["status"] = "partial"
        record["errors"].append(f"missing_fields={missing}")

    _write_cache(symbol, record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-cache", action="store_true", help="Bypass per-ticker disk cache")
    parser.add_argument("--limit", type=int, default=None, help="Cap on tickers fetched (debug)")
    args = parser.parse_args()

    with open(UNIVERSE_PATH) as f:
        universe = json.load(f)
    tickers = [t["symbol"] for t in universe["tickers"]]
    if args.limit:
        tickers = tickers[: args.limit]

    print(f"📡 Fetching {len(tickers)} tickers (parallel × {MAX_WORKERS})…")
    start = time.time()

    records: dict[str, dict] = {}
    use_cache = not args.no_cache

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_one, sym, use_cache=use_cache): sym for sym in tickers}
        done = 0
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                rec = fut.result()
            except Exception as exc:
                rec = {"symbol": sym, "status": "failed", "errors": [str(exc)]}
            records[sym] = rec
            done += 1
            if done % 100 == 0 or done == len(tickers):
                ok      = sum(1 for r in records.values() if r["status"] == "ok")
                partial = sum(1 for r in records.values() if r["status"] == "partial")
                failed  = sum(1 for r in records.values() if r["status"] == "failed")
                elapsed = time.time() - start
                print(f"  [{done}/{len(tickers)}] ok={ok} partial={partial} failed={failed} ({elapsed:.0f}s)")

    output = {
        "last_updated":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe_size":  len(tickers),
        "ok":             sum(1 for r in records.values() if r["status"] == "ok"),
        "partial":        sum(1 for r in records.values() if r["status"] == "partial"),
        "failed":         sum(1 for r in records.values() if r["status"] == "failed"),
        "tickers":        list(records.values()),
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Wrote {len(records)} records → {OUTPUT_PATH}")
    print(f"   ok={output['ok']} · partial={output['partial']} · failed={output['failed']}")


if __name__ == "__main__":
    main()
