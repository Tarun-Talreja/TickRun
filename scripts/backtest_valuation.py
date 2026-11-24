#!/usr/bin/env python3
"""
scripts/backtest_valuation.py — Would the buy-below price have helped in the past?

Replays valuation.py on what was public at each date. The pass rule was fixed first:
see docs/BACKTEST_RULES.md. Run by hand, not in CI (downloads several GB).

Usage: python3 scripts/backtest_valuation.py CACHE_DIR
"""
import json
import os
import sys
import time
from datetime import date

import numpy as np
import pandas as pd
import requests
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from company_measures import MEASURES
from io_utils import load_json
from sec_facts import (CONCEPTS, FACTS_URL, HEADERS, REQUEST_GAP_SECONDS, TICKERS_URL, annual_series,
                       extract, pick_concept)
from valuation import latest_growth, value_ticker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = sorted({n for names in CONCEPTS.values() for n in names})
HORIZONS = {"1y": 365, "3y": 1096}
CLOSE_GAP = 0.25
RESAMPLES = 4000


def as_of(facts: dict, day: str) -> dict:
    """The company's facts with every row filed after day removed."""
    out = {}
    for name, units in facts.items():
        rows = [r for r in next(iter(units.values()), []) if r.get("filed", "9999") <= day]
        if rows:
            out[name] = {"units": {"u": rows}}
    return {"facts": {"us-gaap": out}}


def split_factor(splits: dict[str, float], after: str) -> float:
    """Yahoo's prices are in today's shares; multiply by this for the shares of that day."""
    return float(np.prod([r for d, r in splits.items() if d > after] or [1.0]))


def split_since_filing(facts: dict, splits: dict[str, float], day: str) -> bool:
    filed = max((r["filed"] for e in facts["facts"]["us-gaap"].values()
                 for u in e["units"].values() for r in u), default="")
    return any(filed < d <= day for d in splits)


def quarter_growth(facts: dict) -> float | None:
    """Year-on-year growth of the newest quarter, in percent, as Yahoo reports it."""
    _, rows = pick_concept(facts, CONCEPTS["revenue"])
    best = {}
    for r in sorted(rows, key=lambda r: r["filed"]):
        if r.get("start") and 80 <= (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days <= 100:
            best[r["end"]] = r["val"]
    years = annual_series(rows)
    if not best or (years and max(years) > max(best)):
        g = latest_growth(years)
        return None if g is None else g * 100
    end = max(best)
    prior = [e for e in best if 355 <= (date.fromisoformat(end) - date.fromisoformat(e)).days <= 375]
    return (best[end] / best[prior[0]] - 1) * 100 if prior and best[prior[0]] > 0 else None


def group_of(result: dict, price: float) -> str:
    if result["status"] == "market_expects_decline":
        return "decline"
    if result["status"] != "ok":
        return "none"
    gap = price / result["buy_below"] - 1
    return "below" if gap <= 0 else "close" if gap <= CLOSE_GAP else "expensive"


def load_facts(tickers: list[str], cache: str) -> dict:
    ciks = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in requests.get(TICKERS_URL, headers=HEADERS, timeout=30).json().values()}
    out = {}
    for t in tickers:
        path = os.path.join(cache, f"{t}.json")
        if not os.path.exists(path):
            cik = ciks.get(t) or ciks.get(t.replace("-", "."))
            if not cik:
                continue
            try:
                gaap = requests.get(FACTS_URL.format(cik=cik), headers=HEADERS, timeout=60).json()["facts"]["us-gaap"]
            except (requests.RequestException, ValueError, KeyError) as exc:
                print(f"no facts {t}: {str(exc)[:60]}")
                gaap = {}
            slim = {n: {u: [{k: r.get(k) for k in ("start", "end", "val", "form", "filed")} for r in rows]
                        for u, rows in gaap[n]["units"].items()} for n in NAMES if n in gaap}
            json.dump(slim, open(path, "w"))
            time.sleep(REQUEST_GAP_SECONDS)
        facts = load_json(path)
        if facts:
            out[t] = facts
    return out


def load_prices(tickers: list[str], cache: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    path = os.path.join(cache, "prices.pkl")
    if not os.path.exists(path):
        parts = []
        for i in range(0, len(tickers), 40):
            parts.append(yf.download(tickers[i:i + 40], start="2006-01-01", auto_adjust=False, actions=True,
                                     progress=False, threads=4))
            time.sleep(1)
        pd.concat(parts, axis=1).to_pickle(path)
    frame = pd.read_pickle(path)
    return frame["Close"], frame["Adj Close"], frame["Stock Splits"]


def test_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    month_ends = pd.Series(index, index=index).groupby([index.year, index.month]).last()
    return [d for d in month_ends if d.month in (2, 5, 8, 11) and 2013 <= d.year <= 2025]


def forward(adj: pd.Series, day: pd.Timestamp, days: int) -> float | None:
    """Total return from the next session's close; nothing if the window isn't over."""
    after = adj.index[adj.index > day]
    if not len(after):
        return None
    start, end = after[0], after[0] + pd.Timedelta(days=days)
    if end > adj.index[-1]:
        return None
    return float(adj[adj.index <= end].iloc[-1] / adj[start] - 1)


def replay(ticker: str, facts: dict, close: pd.Series, adj: pd.Series, splits: dict, spy: pd.Series,
           tnx: pd.Series, dates: list) -> list[dict]:
    rows = []
    monthly = pd.concat([adj, spy], axis=1, keys=["s", "m"]).dropna().resample("ME").last().pct_change().dropna()
    for day in dates:
        iso, past = day.strftime("%Y-%m-%d"), close[close.index <= day]
        if len(past) < 250 or (day - past.index[-1]).days > 5:
            continue
        known = as_of(facts, iso)
        record = extract(known)
        if not record["annual"].get("revenue") or split_since_filing(known, splits, iso):
            continue
        factor = split_factor(splits, iso)
        price = float(past.iloc[-1]) * factor
        m = monthly[monthly.index <= day].tail(60)
        beta = float(m.s.cov(m.m) / m.m.var()) if len(m) >= 24 else None
        ends = {e: past[past.index <= e] for e in record["annual"].get("diluted_shares", {})}
        year_end = {e: float(p.iloc[-1]) * factor for e, p in ends.items() if len(p)}
        quote = {"price": price, "revenue_growth": quarter_growth(known)}
        result = value_ticker(record, quote, year_end, round(float(tnx[tnx.index <= day].iloc[-1]) / 100, 4),
                              day.date(), beta)
        rows.append({"ticker": ticker, "date": iso, "year": day.year, "group": group_of(result, price),
                     "price": price, "base": result["base"], "buy_below": result["buy_below"],
                     **{h: forward(adj, day, n) for h, n in HORIZONS.items()},
                     **{f"spy_{h}": forward(spy, day, n) for h, n in HORIZONS.items()}})
    return rows


def interval(frame: pd.DataFrame, column: str) -> tuple[float, float]:
    """90% interval, resampling whole calendar years."""
    rng = np.random.default_rng(0)
    sums = frame.groupby("year")[column].agg(["sum", "count"]).to_numpy()
    picks = rng.integers(0, len(sums), (RESAMPLES, len(sums)))
    drawn = sums[picks].sum(axis=1)
    return tuple(float(x) for x in np.percentile(drawn[:, 0] / drawn[:, 1], [5, 95]))


def report(data: pd.DataFrame) -> dict:
    out = {"observations": len(data), "stocks": int(data.ticker.nunique()),
           "groups": data.group.value_counts().to_dict()}
    for h in HORIZONS:
        d = data.dropna(subset=[h]).copy()
        priced = d[d.group.isin(["below", "close", "expensive"])]
        d["vs_priced"] = d[h] - d.date.map(priced.groupby("date")[h].mean())
        d["vs_all"] = d[h] - d.date.map(d.groupby("date")[h].mean())
        d["vs_spy"] = d[h] - d[f"spy_{h}"]
        res = {}
        for g, part in d.groupby("group"):
            part = part.dropna(subset=["vs_priced"])
            if len(part) < 5:
                continue
            res[g] = {"n": len(part), "stocks": int(part.ticker.nunique()), "years": int(part.year.nunique()),
                      "median_return": round(part[h].median() * 100, 1),
                      **{k: {"mean": round(part[k].mean() * 100, 1), "median": round(part[k].median() * 100, 1),
                             "beat": round((part[k] > 0).mean() * 100),
                             "ci90": [round(x * 100, 1) for x in interval(part, k)]}
                         for k in ("vs_priced", "vs_all", "vs_spy")}}
        cheap = priced.assign(ratio=priced.price / priced.base)
        ranks = [(x.ratio.rank().corr(x[h].rank()), len(x)) for _, x in cheap.groupby("date") if len(x) >= 15]
        below = d[d.group == "below"].dropna(subset=["vs_priced"])
        out[h] = {"groups": res, "cheap_rank_corr": round(float(np.mean([-r for r, _ in ranks])), 3) if ranks else None,
                  "rank_dates_positive": f"{sum(r < 0 for r, _ in ranks)}/{len(ranks)}",
                  "below_by_year": {int(y): [len(x), round(x.vs_priced.mean() * 100, 1)] for y, x in below.groupby("year")}}
    return out


def main() -> None:
    cache = sys.argv[1]
    os.makedirs(cache, exist_ok=True)
    followed = [t for t in load_json(os.path.join(ROOT, "data", "fundamentals.json"))["tickers"]]
    screen = [s["ticker"] for s in load_json(os.path.join(ROOT, "data", "screen_universe.json"))["stocks"]]
    tickers = sorted({*followed, *screen} - set(MEASURES))
    facts = load_facts(tickers, cache)
    close, adj, splits = load_prices([*tickers, "SPY", "^TNX"], cache)
    dates = test_dates(close["SPY"].dropna().index)
    spy, tnx, rows = adj["SPY"].dropna(), close["^TNX"].dropna(), []
    for t, f in facts.items():
        if t not in close or close[t].dropna().empty:
            print("no prices", t)
            continue
        s = splits[t].dropna()
        s = {d.strftime("%Y-%m-%d"): float(v) for d, v in s[s > 0].items()}
        rows += replay(t, f, close[t].dropna(), adj[t].dropna(), s, spy, tnx, dates)
    data = pd.DataFrame(rows)
    data.to_pickle(os.path.join(cache, "rows.pkl"))
    print(json.dumps({"screen": report(data[data.ticker.isin(screen)]),
                      "followed": report(data[data.ticker.isin(followed)])}, indent=1))


if __name__ == "__main__":
    main()
