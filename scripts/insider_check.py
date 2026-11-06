#!/usr/bin/env python3
"""
scripts/insider_check.py — 6-month insider buy/sell analysis for watchlist tickers.

Data source: yfinance insider_transactions (Yahoo Finance Form 4 proxy).
Output: data/insider_signals.json

Signal levels:
  SELLING   — sales and no open-market buys (routine at most large companies)
  BEARISH   — sell:buy ratio > 5:1
  NEUTRAL   — mixed activity
  BULLISH   — more buys than sells
  NO_DATA   — no transaction data available

Usage:
    python3 scripts/insider_check.py
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Missing dependency: pip install yfinance")
    sys.exit(1)

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "data", "insider_signals.json")

LOOKBACK_DAYS = 180


def count_trades(df) -> tuple[int, int, float | None, float | None] | None:
    """Open-market buys and sells with their dollar totals, or None if unreadable.

    Yahoo left its Transaction column blank and moved the description to Text, so
    every stock read as NO_DATA. Awards, gifts and option exercises count as neither:
    only someone spending their own money, or selling, says anything.
    """
    column = next((c for c in ("Text", "Transaction") if c in df.columns), None)
    if column is None:
        return None
    text = df[column].fillna("").astype(str).str.lower()
    is_buy = text.str.contains(r"\bpurchase|\bbuy", regex=True)
    is_sell = text.str.contains(r"\bsale\b|\bsell", regex=True)
    if "Value" not in df.columns:
        return int(is_buy.sum()), int(is_sell.sum()), None, None
    value = pd.to_numeric(df["Value"], errors="coerce")
    return (int(is_buy.sum()), int(is_sell.sum()),
            float(value[is_buy].sum()), float(value[is_sell].sum()))


def _classify(buys: int, sells: int, buy_value, sell_value) -> str:
    if buys == 0 and sells == 0:
        return "NO_DATA"
    # Not a warning by itself: executives sell on schedule at most large companies.
    if buys == 0:
        return "SELLING"
    ratio = sells / buys
    if ratio > 5:
        return "BEARISH"
    if sell_value and buy_value and buy_value > 0 and sell_value / buy_value > 10:
        return "BEARISH"
    if buys > sells:
        return "BULLISH"
    return "NEUTRAL"


def _fetch_one(ticker: str) -> dict:
    base = {
        "ticker":     ticker,
        "signal":     "NO_DATA",
        "buys":       0,
        "sells":      0,
        "buy_value":  None,
        "sell_value": None,
        "note":       "No data",
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        t = yf.Ticker(ticker)
        df = t.insider_transactions
        if df is None or (hasattr(df, "empty") and df.empty):
            return {**base, "note": "No insider transactions found"}

        # Normalize date column and filter to lookback window
        date_col = next(
            (c for c in df.columns if "date" in c.lower() or "start" in c.lower()),
            None,
        )
        if date_col:
            cutoff = pd.Timestamp(datetime.now() - timedelta(days=LOOKBACK_DAYS), tz="UTC")
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
            df = df[df[date_col] >= cutoff]

        if hasattr(df, "empty") and df.empty:
            return {**base, "note": f"No transactions in past {LOOKBACK_DAYS} days"}

        counted = count_trades(df)
        if counted is None:
            return {**base, "note": "Cannot identify transaction type column"}
        buys, sells, buy_value, sell_value = counted

        signal = _classify(buys, sells, buy_value, sell_value)

        note = f"{buys} buy(s), {sells} sell(s) in past 6 months"
        if buy_value is not None and sell_value is not None:
            note += f" | ${buy_value:,.0f} bought / ${sell_value:,.0f} sold"

        return {
            "ticker":     ticker,
            "signal":     signal,
            "buys":       buys,
            "sells":      sells,
            "buy_value":  buy_value,
            "sell_value": sell_value,
            "note":       note,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except Exception as exc:
        return {**base, "signal": "ERROR", "note": str(exc)}


def main():
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)

    # Only check active tickers (skip PASS)
    tickers = [c["ticker"] for c in wl.get("candidates", []) if c.get("verdict") != "PASS"]
    if not tickers:
        print("No active tickers in watchlist.")
        sys.exit(0)

    print(f"Checking insider activity for {len(tickers)} tickers: {', '.join(tickers)}")
    results = {}

    for i, ticker in enumerate(tickers, 1):
        rec = _fetch_one(ticker)
        results[ticker] = rec
        icon = {"SELLING": "⚪", "BEARISH": "🟡", "BULLISH": "🟢", "NEUTRAL": "⚪", "NO_DATA": "—", "ERROR": "⚠"}.get(rec["signal"], "?")
        print(f"  [{i:2d}/{len(tickers)}] {ticker:8s} {icon}  {rec['note']}")
        time.sleep(0.5)

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tickers": results,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    bearish   = [t for t, r in results.items() if r["signal"] == "BEARISH"]
    bullish   = [t for t, r in results.items() if r["signal"] == "BULLISH"]

    print(f"\n✅ Insider signals → {OUTPUT_PATH}")
    if bearish:   print(f"   🟡 BEARISH:   {', '.join(bearish)}")
    if bullish:   print(f"   🟢 BULLISH:   {', '.join(bullish)}")


if __name__ == "__main__":
    main()
