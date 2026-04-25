#!/usr/bin/env python3
"""
fetch_daily.py — Stock Dashboard Data Fetcher
Run this script to update daily.json with real market data.

Usage:
    python3 fetch_daily.py

Requirements (install once):
    pip3 install yfinance requests

Schedule (optional):
    Run automatically via cron or Mac's launchd.
    See README.md for instructions.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ── Install check ────────────────────────────────────────────
try:
    import yfinance as yf
except ImportError:
    print("Missing dependency. Run this once in Terminal:")
    print("  pip3 install yfinance")
    sys.exit(1)

from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Paths ────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "watchlist.md")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "daily.json")
os.makedirs(os.path.join(SCRIPT_DIR, "output"), exist_ok=True)

# ── Read watchlist ───────────────────────────────────────────
def read_watchlist():
    tickers = []
    with open(WATCHLIST_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            symbol = line.split("#")[0].strip().upper()
            if symbol:
                tickers.append(symbol)
    return tickers

# ── Fetch one ticker ─────────────────────────────────────────
def fetch_ticker(symbol):
    try:
        t = yf.Ticker(symbol)
        info = t.info
        hist = t.history(period="1y")

        if hist.empty:
            raise ValueError("No history")

        price       = round(float(info.get("currentPrice") or info.get("regularMarketPrice") or hist["Close"].iloc[-1]), 2)
        prev_close  = float(info.get("previousClose") or (hist["Close"].iloc[-2] if len(hist) > 1 else price))
        open_week   = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else prev_close
        open_year   = float(hist["Close"].iloc[0])

        chg_1d  = round((price - prev_close) / prev_close * 100, 2) if prev_close else None
        chg_5d  = round((price - open_week) / open_week * 100, 2)   if open_week  else None
        chg_ytd = round((price - open_year) / open_year * 100, 2)   if open_year  else None

        low_52w  = round(float(info.get("fiftyTwoWeekLow")  or hist["Low"].min()), 2)
        high_52w = round(float(info.get("fiftyTwoWeekHigh") or hist["High"].max()), 2)

        pe          = info.get("trailingPE")
        forward_pe  = info.get("forwardPE")
        pe          = round(float(pe), 2)         if pe         else None
        forward_pe  = round(float(forward_pe), 2) if forward_pe else None

        # RSI (14-day)
        closes = hist["Close"]
        delta  = closes.diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rs     = gain / loss
        rsi_series = 100 - (100 / (1 + rs))
        rsi    = round(float(rsi_series.iloc[-1]), 1) if not rsi_series.empty else None

        ma_50  = round(float(closes.rolling(50).mean().iloc[-1]), 2)  if len(closes) >= 50  else None
        ma_200 = round(float(closes.rolling(200).mean().iloc[-1]), 2) if len(closes) >= 200 else None

        # Next earnings — handle both old (DataFrame) and new (dict) yfinance APIs
        earnings_date = None
        try:
            cal = t.calendar
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date") or cal.get("earnings_date")
                if isinstance(ed, list) and ed:
                    ed = ed[0]
                if hasattr(ed, "date"):
                    earnings_date = ed.date().isoformat()
                elif ed:
                    earnings_date = str(ed)[:10]
            elif cal is not None and hasattr(cal, "empty") and not cal.empty:
                col0 = cal.columns[0]
                earnings_date = col0.date().isoformat() if hasattr(col0, "date") else None
        except Exception:
            earnings_date = None

        # Recent news titles (last 24h)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        news_titles = []
        try:
            for n in (t.news or []):
                ts = n.get("providerPublishTime", 0)
                pub = datetime.fromtimestamp(ts, tz=timezone.utc)
                if pub >= cutoff:
                    title = n.get("title", "").strip()
                    if title:
                        news_titles.append(title)
        except Exception:
            pass

        return {
            "symbol":          symbol,
            "price":           price,
            "change_pct_1d":   chg_1d,
            "change_pct_5d":   chg_5d,
            "change_pct_ytd":  chg_ytd,
            "range_52w_low":   low_52w,
            "range_52w_high":  high_52w,
            "pe":              pe,
            "forward_pe":      forward_pe,
            "rsi_14":          rsi,
            "ma_50":           ma_50,
            "ma_200":          ma_200,
            "next_earnings":   earnings_date,
            "news_titles_24h": news_titles[:3]
        }
    except Exception as e:
        print(f"  ⚠ {symbol}: {e}")
        return {
            "symbol": symbol, "price": None, "change_pct_1d": None,
            "change_pct_5d": None, "change_pct_ytd": None,
            "range_52w_low": None, "range_52w_high": None,
            "pe": None, "forward_pe": None, "rsi_14": None,
            "ma_50": None, "ma_200": None,
            "next_earnings": None, "news_titles_24h": []
        }

# ── Market context ───────────────────────────────────────────
def fetch_market_context():
    ctx = {"spy_price": None, "spy_change_pct": None,
           "qqq_price": None, "qqq_change_pct": None,
           "vix": None, "ten_year_yield": None}
    try:
        for sym, price_key, pct_key in [
            ("SPY", "spy_price", "spy_change_pct"),
            ("QQQ", "qqq_price", "qqq_change_pct")
        ]:
            t = yf.Ticker(sym)
            info = t.info
            hist = t.history(period="2d")
            price = float(info.get("currentPrice") or info.get("regularMarketPrice") or hist["Close"].iloc[-1])
            prev  = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
            ctx[price_key] = round(price, 2)
            ctx[pct_key]   = round((price - prev) / prev * 100, 2)

        ctx["vix"]             = round(float(yf.Ticker("^VIX").info.get("regularMarketPrice") or 0), 2) or None
        ctx["ten_year_yield"]  = round(float(yf.Ticker("^TNX").info.get("regularMarketPrice") or 0), 2) or None
    except Exception as e:
        print(f"  ⚠ market context: {e}")
    return ctx

# ── Flags ────────────────────────────────────────────────────
def compute_flags(tickers_data):
    flags = []
    today = datetime.now(timezone.utc).date()
    for t in tickers_data:
        sym = t["symbol"]
        if t.get("next_earnings"):
            try:
                days = (datetime.strptime(t["next_earnings"], "%Y-%m-%d").date() - today).days
                if 0 <= days <= 7:
                    flags.append({"symbol": sym, "type": "earnings_soon", "detail": f"{days}d"})
            except Exception:
                pass
        if t.get("change_pct_1d") and abs(t["change_pct_1d"]) > 5:
            flags.append({"symbol": sym, "type": "big_move", "detail": f"{t['change_pct_1d']:+.1f}%"})
        if t.get("rsi_14"):
            if t["rsi_14"] > 70:
                flags.append({"symbol": sym, "type": "rsi_extreme", "detail": f"RSI {t['rsi_14']}"})
            elif t["rsi_14"] < 30:
                flags.append({"symbol": sym, "type": "rsi_extreme", "detail": f"RSI {t['rsi_14']}"})
    return flags

# ── Main ─────────────────────────────────────────────────────
def main():
    print("📈 Stock Dashboard — Daily Fetch")
    print(f"   Output: {OUTPUT_PATH}\n")

    watchlist = read_watchlist()
    # Remove benchmark symbols from main ticker list
    skip = {"SPY", "QQQ", "VIX", "^VIX", "^TNX"}
    tickers = [t for t in watchlist if t not in skip]

    print(f"Fetching market context...")
    market_ctx = fetch_market_context()
    print(f"  SPY: {market_ctx['spy_price']}  QQQ: {market_ctx['qqq_price']}  VIX: {market_ctx['vix']}")

    print(f"\nFetching {len(tickers)} tickers (parallel, max 5 workers)...")
    tickers_data = [None] * len(tickers)
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(fetch_ticker, sym): i for i, sym in enumerate(tickers)}
        done = 0
        for fut in as_completed(futures):
            i = futures[fut]
            tickers_data[i] = fut.result()
            done += 1
            print(f"  [{done}/{len(tickers)}] {tickers[i]} done")

    flags = compute_flags(tickers_data)

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market_context": market_ctx,
        "tickers": tickers_data,
        "flags": flags
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    flagged = len(flags)
    print(f"\n✅ Done. {len(tickers)} tickers, {flagged} flag(s).")
    print(f"   Saved to: {OUTPUT_PATH}")
    if flags:
        print("\n🚩 Flags:")
        for fl in flags:
            print(f"   {fl['symbol']} — {fl['type']}: {fl['detail']}")

if __name__ == "__main__":
    main()
