#!/usr/bin/env python3
"""
scripts/screener.py — Professional multi-factor stock discovery (opt-in, suggest-only).

Scans a universe (S&P 500 by default) and ranks names on a blended factor model
that professional fundamental/quant investors actually use:

  QUALITY  (35%) — ROE, gross & operating margin, positive free cash flow
                   (à la Greenblatt "return on capital" + quality compounder screens)
  VALUE    (30%) — EV/EBITDA earnings yield, FCF yield, forward P/E, PEG
                   (à la Magic Formula earnings yield + GARP)
  GROWTH   (20%) — revenue growth, earnings growth (Peter Lynch GARP)
  HEALTH   (15%) — debt/equity, current ratio (balance-sheet strength)

HARD DISQUALIFIERS (a pro would auto-reject):
  - market cap < $2B (liquidity/quality floor)
  - unprofitable (operating margin < 0) UNLESS revenue growth > 40%
  - over-levered (debt/equity > 3.0)
  - burning cash (FCF < 0) UNLESS revenue growth > 30%

Outputs the top names NOT already in your watchlist as SUGGESTIONS.
It never auto-adds — you review data/discovered.json and approve.

Usage:
    python3 scripts/screener.py [--limit N] [--universe sp500|FILE]

Requirements:
    pip install yfinance tenacity requests pandas
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

try:
    import yfinance as yf
    import requests
except ImportError:
    print("Missing dependency: pip install yfinance requests")
    sys.exit(1)

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "data", "discovered.json")
CACHE_DIR      = os.path.join(SCRIPT_DIR, "data", "screen_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_TTL_HOURS = 24 * 5
MAX_WORKERS     = 8
TOP_N           = 15
MIN_MARKET_CAP  = 2e9

HEADERS = {"User-Agent": "TickRun Screener tarun888099@gmail.com"}


# ── Universe ─────────────────────────────────────────────────────────────────

def _sp500_universe() -> list[str]:
    """S&P 500 constituents from Wikipedia (free, reliable)."""
    try:
        import io
        import pandas as pd
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        html = requests.get(url, headers=HEADERS, timeout=30).text
        # pandas 2.x: must wrap a literal HTML string in StringIO (raw string
        # is treated as a file path otherwise)
        tables = pd.read_html(io.StringIO(html))
        syms = tables[0]["Symbol"].tolist()
        return [s.replace(".", "-") for s in syms]
    except Exception as e:
        print(f"⚠ Could not fetch S&P 500 list ({e}); using fallback quality universe.")
        # Fallback: a hand-picked quality/large-cap universe
        return ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","AVGO","TSM","ORCL","CRM",
                "ADBE","AMD","QCOM","TXN","INTU","NOW","PANW","SNPS","CDNS","KLAC",
                "LRCX","AMAT","MU","ADI","MRVL","ANET","FTNT","CRWD","DDOG","WDAY",
                "UNH","JNJ","LLY","ABBV","MRK","TMO","DHR","ABT","ISRG","VRTX",
                "JPM","V","MA","COST","WMT","PG","KO","PEP","MCD","HD","NKE","DIS"]


def _load_universe(spec: str) -> list[str]:
    if spec == "sp500":
        return _sp500_universe()
    if os.path.exists(spec):
        with open(spec) as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("tickers", [])
    return spec.split(",")


# ── Fetch w/ cache ───────────────────────────────────────────────────────────

def _cache_path(sym): return os.path.join(CACHE_DIR, f"{sym}.json")

def _fresh(sym):
    p = _cache_path(sym)
    return os.path.exists(p) and (time.time() - os.path.getmtime(p)) < CACHE_TTL_HOURS * 3600

def _fetch(sym: str) -> dict | None:
    if _fresh(sym):
        try:
            with open(_cache_path(sym)) as f:
                return json.load(f)
        except Exception:
            pass
    try:
        info = yf.Ticker(sym).info or {}
        if not info.get("marketCap"):
            return None
        rec = {
            "ticker": sym,
            "name": info.get("longName") or info.get("shortName", sym),
            "sector": info.get("sector"),
            "market_cap": info.get("marketCap"),
            "roe": info.get("returnOnEquity"),
            "gross_margin": info.get("grossMargins"),
            "op_margin": info.get("operatingMargins"),
            "profit_margin": info.get("profitMargins"),
            "rev_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "fcf": info.get("freeCashflow"),
            "ev_ebitda": info.get("enterpriseToEbitda"),
            "forward_pe": info.get("forwardPE"),
            "trailing_pe": info.get("trailingPE"),
            "peg": info.get("pegRatio") or info.get("trailingPegRatio"),
            "debt_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "div_yield": info.get("dividendYield"),
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "drawdown_pct": None,
        }
        h = info.get("fiftyTwoWeekHigh")
        if rec["price"] and h:
            rec["drawdown_pct"] = round((rec["price"] - h) / h * 100, 1)
        with open(_cache_path(sym), "w") as f:
            json.dump(rec, f)
        return rec
    except Exception:
        return None


# ── Scoring ──────────────────────────────────────────────────────────────────

def _clamp(x, lo, hi): return max(lo, min(hi, x))

def _disqualified(r: dict) -> str | None:
    mc = r.get("market_cap") or 0
    if mc < MIN_MARKET_CAP:
        return "below $2B market cap"
    rg = (r.get("rev_growth") or 0) * 100
    om = (r.get("op_margin") or 0) * 100
    if om < 0 and rg < 40:
        return "unprofitable without hypergrowth"
    de = r.get("debt_equity")
    if de is not None and de > 300:   # yfinance reports debt/equity as a percent
        return "over-levered (D/E > 3)"
    fcf = r.get("fcf")
    if fcf is not None and fcf < 0 and rg < 30:
        return "burning cash without hypergrowth"
    return None

def _score(r: dict) -> dict:
    # QUALITY (35)
    roe = (r.get("roe") or 0) * 100
    gm  = (r.get("gross_margin") or 0) * 100
    om  = (r.get("op_margin") or 0) * 100
    fcf_pos = 1 if (r.get("fcf") or 0) > 0 else 0
    q = (_clamp(roe/30, 0, 1)*12 + _clamp(gm/60, 0, 1)*10 +
         _clamp(om/35, 0, 1)*8 + fcf_pos*5)

    # VALUE (30) — cheaper = higher
    ev = r.get("ev_ebitda")
    fpe = r.get("forward_pe")
    peg = r.get("peg")
    ev_s  = _clamp((25 - ev)/25, 0, 1)*12 if ev and ev > 0 else 0
    fpe_s = _clamp((35 - fpe)/35, 0, 1)*10 if fpe and fpe > 0 else 0
    peg_s = _clamp((2.5 - peg)/2.5, 0, 1)*8 if peg and peg > 0 else 0
    v = ev_s + fpe_s + peg_s

    # GROWTH (20)
    rg = (r.get("rev_growth") or 0) * 100
    eg = (r.get("earnings_growth") or 0) * 100
    g = _clamp(rg/30, 0, 1)*12 + _clamp(eg/30, 0, 1)*8

    # HEALTH (15)
    de = r.get("debt_equity")
    cr = r.get("current_ratio")
    de_s = _clamp((150 - de)/150, 0, 1)*9 if de is not None else 4.5
    cr_s = _clamp(cr/2, 0, 1)*6 if cr else 0
    h = de_s + cr_s

    total = round(q + v + g + h, 1)

    # Which classic screens does it pass?
    passes = []
    if (r.get("roe") or 0)*100 > 15 and gm > 40 and (r.get("fcf") or 0) > 0:
        passes.append("Quality")
    if peg and 0 < peg < 1.5 and rg > 10:
        passes.append("GARP")
    if ev and 0 < ev < 12 and roe > 15:
        passes.append("Magic Formula")
    dy = r.get("div_yield")
    if dy and 2 < dy < 6 and de is not None and de < 100:
        passes.append("Dividend Quality")

    return {
        "score": total,
        "quality": round(q,1), "value": round(v,1),
        "growth": round(g,1), "health": round(h,1),
        "passes_screens": passes,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def _watchlist_tickers() -> set[str]:
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)
    return {c["ticker"] for c in wl.get("candidates", [])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=TOP_N)
    parser.add_argument("--universe", type=str, default="sp500")
    parser.add_argument("--max-scan", type=int, default=520,
                        help="cap tickers scanned per run")
    args = parser.parse_args()

    universe = _load_universe(args.universe)[: args.max_scan]
    already  = _watchlist_tickers()
    print(f"🔎 Screening {len(universe)} names (professional multi-factor model)...")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch, s): s for s in universe}
        done = 0
        for fut in as_completed(futures):
            done += 1
            r = fut.result()
            if done % 50 == 0:
                print(f"   ...{done}/{len(universe)}")
            if not r:
                continue
            dq = _disqualified(r)
            if dq:
                continue
            r.update(_score(r))
            results.append(r)

    # Rank, drop names already tracked
    results.sort(key=lambda x: x["score"], reverse=True)
    discovered = [r for r in results if r["ticker"] not in already][: args.limit]

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe": args.universe,
        "scanned": len(universe),
        "qualified": len(results),
        "discovered": [
            {
                "ticker": r["ticker"], "name": r["name"], "sector": r.get("sector"),
                "score": r["score"], "quality": r["quality"], "value": r["value"],
                "growth": r["growth"], "health": r["health"],
                "passes_screens": r["passes_screens"],
                "market_cap": r["market_cap"], "price": r.get("price"),
                "forward_pe": r.get("forward_pe"), "rev_growth": r.get("rev_growth"),
                "roe": r.get("roe"), "drawdown_pct": r.get("drawdown_pct"),
            }
            for r in discovered
        ],
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n🆕 Top {len(discovered)} discoveries NOT in your watchlist:")
    for r in discovered:
        screens = ", ".join(r["passes_screens"]) or "composite"
        print(f"  {r['ticker']:6s} score {r['score']:5.1f}  [{screens}]  {r['name'][:30]}")
    print(f"\n✅ Discoveries → {OUTPUT_PATH}  (suggest-only — review & approve to add)")


if __name__ == "__main__":
    main()
