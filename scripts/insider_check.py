#!/usr/bin/env python3
"""
scripts/insider_check.py — 6-month insider buy/sell analysis for watchlist tickers.

Data source: yfinance insider_transactions (Yahoo Finance Form 4 proxy).
Output: data/insider_signals.json

Signal levels:
  RED_FLAG  — insiders selling, zero buys (strongest bearish signal)
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


def _classify(buys: int, sells: int, buy_value, sell_value) -> str:
    if buys == 0 and sells == 0:
        return "NO_DATA"
    if buys == 0 and sells > 0:
        return "RED_FLAG"
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

        # Find transaction type column
        tx_col = next(
            (
                c for c in df.columns
                if "transaction" in c.lower()
                or c.lower() in ("trans", "type", "transactiontype")
            ),
            None,
        )
        if not tx_col:
            return {**base, "note": "Cannot identify transaction type column"}

        tx = df[tx_col].astype(str).str.lower()
        buy_mask  = tx.str.contains(r"purchase|buy|acquisition|grant", na=False, regex=True)
        sell_mask = tx.str.contains(r"sale|sell|dispos", na=False, regex=True)

        buys  = int(buy_mask.sum())
        sells = int(sell_mask.sum())

        # Optional: sum dollar values
        val_col = next(
            (c for c in df.columns if c.lower() in ("value", "amount", "dollarvalue")),
            None,
        )
        buy_value = sell_value = None
        if val_col:
            try:
                buy_value  = float(df.loc[buy_mask,  val_col].apply(pd.to_numeric, errors="coerce").sum())
                sell_value = float(df.loc[sell_mask, val_col].apply(pd.to_numeric, errors="coerce").sum())
            except Exception:
                pass

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
        icon = {"RED_FLAG": "🔴", "BEARISH": "🟡", "BULLISH": "🟢", "NEUTRAL": "⚪", "NO_DATA": "—", "ERROR": "⚠"}.get(rec["signal"], "?")
        print(f"  [{i:2d}/{len(tickers)}] {ticker:8s} {icon}  {rec['note']}")
        time.sleep(0.5)

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tickers": results,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    red_flags = [t for t, r in results.items() if r["signal"] == "RED_FLAG"]
    bearish   = [t for t, r in results.items() if r["signal"] == "BEARISH"]
    bullish   = [t for t, r in results.items() if r["signal"] == "BULLISH"]

    print(f"\n✅ Insider signals → {OUTPUT_PATH}")
    if red_flags: print(f"   🔴 RED FLAG:  {', '.join(red_flags)}")
    if bearish:   print(f"   🟡 BEARISH:   {', '.join(bearish)}")
    if bullish:   print(f"   🟢 BULLISH:   {', '.join(bullish)}")


if __name__ == "__main__":
    main()
