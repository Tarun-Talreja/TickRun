#!/usr/bin/env python3
"""
fetch_weekly.py — Weekly S&P 500 Stock Screener
Run every Sunday evening to update weekly_screens.json.

Usage:
    python3 fetch_weekly.py

Requirements (install once):
    pip3 install yfinance pandas requests lxml

Takes 15-20 minutes for the full S&P 500.
Progress is printed as it runs — safe to leave running in background.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

# ── Install check ────────────────────────────────────────────
try:
    import yfinance as yf
    import pandas as pd
    import requests
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip3 install yfinance pandas requests lxml")
    sys.exit(1)

# ── Paths ────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH  = os.path.join(SCRIPT_DIR, "output", "weekly_screens.json")
os.makedirs(os.path.join(SCRIPT_DIR, "output"), exist_ok=True)

# ── Fetch S&P 500 tickers from Wikipedia ─────────────────────
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

def get_sp500_tickers():
    print("Fetching S&P 500 constituent list from Wikipedia...")
    try:
        # Use requests (certifi CA bundle) to avoid macOS SSL verify failures
        # from pd.read_html's default urlopen.
        resp = requests.get(
            SP500_URL,
            headers={"User-Agent": "Mozilla/5.0 (StockDashboard fetch_weekly)"},
            timeout=30,
        )
        resp.raise_for_status()
        from io import StringIO
        tables = pd.read_html(StringIO(resp.text))
        df = tables[0]
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        print(f"  Found {len(tickers)} tickers")
        return tickers
    except Exception as e:
        print(f"  ⚠ Could not fetch S&P 500 list: {e}")
        print("  Falling back to top 100 well-known tickers...")
        return FALLBACK_100

# ── Fallback list if Wikipedia fetch fails ───────────────────
FALLBACK_100 = [
    "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","LLY","UNH",
    "V","XOM","JPM","MA","PG","COST","HD","MRK","ABBV","CVX","PEP","KO",
    "WMT","BAC","ADBE","TMO","CRM","ACN","MCD","CSCO","ABT","WFC","TXN",
    "DHR","NEE","ORCL","PM","IBM","CAT","AMGN","INTU","QCOM","GE","RTX",
    "LOW","SPGI","AMAT","NOW","BKNG","SYK","GS","AXP","BLK","MS","MDT",
    "ADI","GILD","PLD","T","VZ","C","MDLZ","CI","ADP","USB","MMC","DE",
    "COP","EOG","SLB","PSA","TGT","CME","ZTS","F","GM","FDX","DUK","SO",
    "D","EXC","PEG","XEL","WEC","ED","ETR","FE","PPL","ES","AEE","LNT",
    "EVRG","NI","CMS","NRG","AES","PNW","OTTR","AVA","NWE","POR"
]

# ── Fetch fundamentals for one ticker ────────────────────────
def fetch_fundamentals(symbol):
    try:
        t    = yf.Ticker(symbol)
        info = t.info
        hist = t.history(period="1y")

        if hist.empty or not info:
            return None

        closes = hist["Close"]
        price  = float(closes.iloc[-1])

        # Price changes
        ret_12m = ((price - float(closes.iloc[0])) / float(closes.iloc[0]) * 100) if len(closes) > 1 else None

        # Moving averages
        ma_50  = float(closes.rolling(50).mean().iloc[-1])  if len(closes) >= 50  else None
        ma_200 = float(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else None

        # Valuation
        pe           = info.get("trailingPE")
        forward_pe   = info.get("forwardPE")
        pb           = info.get("priceToBook")
        peg          = info.get("trailingPegRatio") or info.get("pegRatio")
        ps           = info.get("priceToSalesTrailing12Months")
        ev_ebitda    = info.get("enterpriseToEbitda")
        market_cap   = info.get("marketCap")

        # Profitability
        roe          = info.get("returnOnEquity")       # decimal, e.g. 0.28
        roa          = info.get("returnOnAssets")
        gross_margin = info.get("grossMargins")         # decimal
        op_margin    = info.get("operatingMargins")
        profit_margin = info.get("profitMargins")

        # Growth
        eps_growth_5y     = info.get("earningsGrowth")       # trailing, use as proxy
        rev_growth        = info.get("revenueGrowth")
        eps_qoq_growth    = info.get("earningsQuarterlyGrowth")

        # Financial health
        current_ratio     = info.get("currentRatio")
        debt_equity       = info.get("debtToEquity")         # as whole number e.g. 142 = 1.42x
        total_cash        = info.get("totalCash")
        total_debt        = info.get("totalDebt")
        fcf               = info.get("freeCashflow")
        operating_cf      = info.get("operatingCashflow")
        revenue           = info.get("totalRevenue")
        net_income        = info.get("netIncomeToCommon")

        # Dividends
        div_yield         = info.get("dividendYield")         # decimal
        payout_ratio      = info.get("payoutRatio")           # decimal
        div_growth_years  = info.get("lastDividendDate")      # we'll use 5yr growth as proxy

        # Shares
        shares_outstanding = info.get("sharesOutstanding")
        float_shares       = info.get("floatShares")

        # Sector
        sector   = info.get("sector", "Unknown")
        company  = info.get("longName") or info.get("shortName") or symbol

        # Normalize debt/equity (yfinance returns as %, divide by 100)
        de_ratio = (debt_equity / 100) if debt_equity else None

        # FCF margin
        fcf_margin = (fcf / revenue) if (fcf and revenue and revenue > 0) else None

        # Earnings yield (EBIT / EV proxy) — use 1/EV_EBITDA
        earnings_yield = (1 / ev_ebitda) if ev_ebitda and ev_ebitda > 0 else None

        # ROIC proxy: use ROE as stand-in (imperfect but available)
        roic_proxy = (roe * 100) if roe else None

        return {
            "symbol":          symbol,
            "company":         company,
            "sector":          sector,
            "price":           round(price, 2),
            "market_cap":      market_cap,
            "pe":              round(pe, 2)           if pe           else None,
            "forward_pe":      round(forward_pe, 2)   if forward_pe   else None,
            "pb":              round(pb, 2)            if pb           else None,
            "peg":             round(peg, 2)           if peg          else None,
            "ps":              round(ps, 2)            if ps           else None,
            "ev_ebitda":       round(ev_ebitda, 2)     if ev_ebitda    else None,
            "earnings_yield":  round(earnings_yield, 4) if earnings_yield else None,
            "roe":             round(roe * 100, 2)     if roe          else None,
            "roa":             round(roa * 100, 2)     if roa          else None,
            "roic_proxy":      round(roic_proxy, 2)    if roic_proxy   else None,
            "gross_margin":    round(gross_margin * 100, 2) if gross_margin else None,
            "op_margin":       round(op_margin * 100, 2)    if op_margin    else None,
            "profit_margin":   round(profit_margin * 100, 2) if profit_margin else None,
            "fcf_margin":      round(fcf_margin * 100, 2) if fcf_margin else None,
            "eps_growth":      round(eps_qoq_growth * 100, 2) if eps_qoq_growth else None,
            "rev_growth":      round(rev_growth * 100, 2)  if rev_growth  else None,
            "current_ratio":   round(current_ratio, 2) if current_ratio else None,
            "debt_equity":     round(de_ratio, 2)      if de_ratio     else None,
            "div_yield":       round(div_yield * 100, 2) if div_yield  else None,
            "payout_ratio":    round(payout_ratio * 100, 2) if payout_ratio else None,
            "fcf":             fcf,
            "net_income":      net_income,
            "operating_cf":    operating_cf,
            "ret_12m":         round(ret_12m, 2)       if ret_12m      else None,
            "ma_50":           round(ma_50, 2)          if ma_50        else None,
            "ma_200":          round(ma_200, 2)         if ma_200       else None,
        }
    except Exception as e:
        return None

# ── Apply screens ─────────────────────────────────────────────
def apply_screens(stocks, all_ret12m):
    # Precompute momentum threshold (top 20% of 12m returns)
    valid_returns = [r for r in all_ret12m if r is not None]
    momentum_cutoff = sorted(valid_returns)[int(len(valid_returns) * 0.80)] if valid_returns else 999

    # Magic Formula: rank by earnings_yield + roic
    ef_stocks = [s for s in stocks if s.get("earnings_yield") and s.get("roic_proxy")]
    ey_sorted  = sorted(ef_stocks, key=lambda x: x["earnings_yield"], reverse=True)
    roi_sorted = sorted(ef_stocks, key=lambda x: x["roic_proxy"], reverse=True)
    ey_rank  = {s["symbol"]: i for i, s in enumerate(ey_sorted)}
    roi_rank = {s["symbol"]: i for i, s in enumerate(roi_sorted)}
    mf_scores = {s["symbol"]: ey_rank.get(s["symbol"], 999) + roi_rank.get(s["symbol"], 999) for s in ef_stocks}
    mf_threshold = sorted(mf_scores.values())[min(29, len(mf_scores)-1)] if mf_scores else 0

    results = []
    for s in stocks:
        sym = s["symbol"]
        screens_passed = []

        # 1. Graham Defensive
        if (s.get("pe") and s["pe"] < 15 and
            s.get("pb") and s["pb"] < 1.5 and
            s.get("current_ratio") and s["current_ratio"] > 2 and
            s.get("market_cap") and s["market_cap"] > 2_000_000_000 and
            s.get("net_income") and s["net_income"] > 0 and
            s.get("div_yield") and s["div_yield"] > 0):
            screens_passed.append("graham")

        # 2. Magic Formula
        if sym in mf_scores and mf_scores[sym] <= mf_threshold:
            screens_passed.append("magic_formula")

        # 3. Piotroski (simplified — 5 of 9 checkable from yfinance)
        piotroski = 0
        if s.get("net_income") and s["net_income"] > 0:               piotroski += 1
        if s.get("operating_cf") and s["operating_cf"] > 0:           piotroski += 1
        if (s.get("operating_cf") and s.get("net_income") and
            s["operating_cf"] > s["net_income"]):                      piotroski += 1
        if s.get("roa") and s["roa"] > 0:                             piotroski += 1
        if s.get("debt_equity") and s["debt_equity"] < 1:             piotroski += 1
        if s.get("current_ratio") and s["current_ratio"] > 1.5:       piotroski += 1
        if s.get("gross_margin") and s["gross_margin"] > 30:          piotroski += 1
        if piotroski >= 5:
            screens_passed.append("piotroski")

        # 4. GARP
        if (s.get("eps_growth") and s["eps_growth"] > 15 and
            s.get("peg") and 0 < s["peg"] < 1.5 and
            s.get("roe") and s["roe"] > 15 and
            s.get("debt_equity") and s["debt_equity"] < 0.5):
            screens_passed.append("garp")

        # 5. Quality
        if (s.get("roic_proxy") and s["roic_proxy"] > 15 and
            s.get("gross_margin") and s["gross_margin"] > 40 and
            s.get("fcf_margin") and s["fcf_margin"] > 10 and
            s.get("debt_equity") is not None and s["debt_equity"] < 1 and
            s.get("market_cap") and s["market_cap"] > 10_000_000_000):
            screens_passed.append("quality")

        # 6. Momentum
        if (s.get("ret_12m") and s["ret_12m"] >= momentum_cutoff and
            s.get("price") and s.get("ma_200") and s["price"] > s["ma_200"] and
            s.get("ma_50") and s["price"] > s["ma_50"] and
            s["ma_50"] > s["ma_200"]):
            screens_passed.append("momentum")

        # 7. Dividend Quality
        if (s.get("div_yield") and 2 <= s["div_yield"] <= 6 and
            s.get("payout_ratio") and 0 < s["payout_ratio"] < 60 and
            s.get("debt_equity") is not None and s["debt_equity"] < 1 and
            s.get("fcf") and s.get("net_income") and s["net_income"] > 0 and
            s["fcf"] > 0):
            screens_passed.append("dividend")

        if screens_passed:
            results.append({
                "symbol":         sym,
                "company":        s["company"],
                "sector":         s["sector"],
                "price":          s["price"],
                "screens_passed": screens_passed,
                "score":          len(screens_passed),
                "metrics": {
                    "pe":           s.get("pe"),
                    "pb":           s.get("pb"),
                    "peg":          s.get("peg"),
                    "roe":          s.get("roe"),
                    "gross_margin": s.get("gross_margin"),
                    "fcf_margin":   s.get("fcf_margin"),
                    "debt_equity":  s.get("debt_equity"),
                    "div_yield":    s.get("div_yield"),
                    "ret_12m":      s.get("ret_12m"),
                    "rsi":          None
                },
                "one_line_thesis": build_thesis(s, screens_passed)
            })

    return sorted(results, key=lambda x: x["score"], reverse=True)

# ── Build one-line thesis ─────────────────────────────────────
def build_thesis(s, screens):
    parts = []
    if "graham"       in screens: parts.append(f"P/E {s.get('pe','—')}, P/B {s.get('pb','—')}, current ratio {s.get('current_ratio','—')}")
    if "magic_formula"in screens: parts.append(f"high earnings yield + ROIC combo")
    if "piotroski"    in screens: parts.append(f"improving fundamentals (Piotroski)")
    if "garp"         in screens: parts.append(f"EPS growth {s.get('eps_growth','—')}%, PEG {s.get('peg','—')}, ROE {s.get('roe','—')}%")
    if "quality"      in screens: parts.append(f"ROIC {s.get('roic_proxy','—')}%, gross margin {s.get('gross_margin','—')}%, FCF margin {s.get('fcf_margin','—')}%")
    if "momentum"     in screens: parts.append(f"12M return {s.get('ret_12m','—')}%, above 50d + 200d MA")
    if "dividend"     in screens: parts.append(f"{s.get('div_yield','—')}% yield, payout {s.get('payout_ratio','—')}%, FCF positive")
    return " · ".join(parts) if parts else "Passes multiple screens"

# ── Sector mix ────────────────────────────────────────────────
def sector_mix(top20):
    mix = {}
    for s in top20:
        sector = s.get("sector", "Unknown")
        mix[sector] = mix.get(sector, 0) + 1
    return mix

# ── By-screen grouping ────────────────────────────────────────
def by_screen(results):
    screens = ["graham","magic_formula","piotroski","garp","quality","momentum","dividend"]
    grouped = {s: [] for s in screens}
    for stock in results:
        for sc in stock["screens_passed"]:
            if sc in grouped and len(grouped[sc]) < 10:
                grouped[sc].append({
                    "symbol":  stock["symbol"],
                    "company": stock["company"],
                    "sector":  stock["sector"]
                })
    return grouped

# ── Main ──────────────────────────────────────────────────────
def main():
    print("📊 Weekly S&P 500 Screener")
    print(f"   Output: {OUTPUT_PATH}\n")

    tickers = get_sp500_tickers()
    total   = len(tickers)
    stocks  = []
    errors  = 0

    print(f"Fetching fundamentals for {total} tickers (this takes 15-20 min)...\n")

    for i, sym in enumerate(tickers, 1):
        print(f"  [{i:3d}/{total}] {sym:<8}", end=" ", flush=True)
        data = fetch_fundamentals(sym)
        if data:
            stocks.append(data)
            print("✓")
        else:
            errors += 1
            print("✗ skipped")
        # Be polite to Yahoo Finance — small delay every 10 tickers
        if i % 10 == 0:
            time.sleep(1)

    print(f"\nFetched {len(stocks)} stocks ({errors} skipped)")
    print("Running screens...")

    all_ret12m = [s.get("ret_12m") for s in stocks]
    results    = apply_screens(stocks, all_ret12m)
    top20      = results[:20]

    output = {
        "last_updated":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe":        f"S&P 500 ({len(stocks)} fetched)",
        "screens_run":     ["graham","magic_formula","piotroski","garp","quality","momentum","dividend"],
        "top_conviction":  top20,
        "by_screen":       by_screen(results),
        "sector_mix_top20": sector_mix(top20),
        "total_passes":    len(results)
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Done. {len(results)} stocks passed at least one screen.")
    print(f"   Top conviction: {len(top20)} stocks")
    print(f"   Saved to: {OUTPUT_PATH}")

    if top20:
        print("\n🏆 Top conviction picks:")
        for s in top20[:5]:
            print(f"   {s['symbol']:<8} {s['score']}× — {', '.join(s['screens_passed'])}")
        if len(top20) > 5:
            print(f"   ... and {len(top20)-5} more in weekly_screens.json")

if __name__ == "__main__":
    main()
