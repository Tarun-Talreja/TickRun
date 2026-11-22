#!/usr/bin/env python3
"""
scripts/valuation.py — What each business is worth, and the price that leaves a margin.

The old buy target was "X% below the 52-week high", with X picked by the AI. It said
nothing about the business: RDDT showed a $211 target while trading at $85 and rated
"wait". This replaces it with two independent estimates from filed figures:

  CASH FLOW     Owner cash flow (operating cash flow - capital spending - stock-based
                pay) per share, grown at the company's own revenue growth (capped)
                for five years, fading to long-run growth, discounted mid-year at
                the 10-year Treasury yield plus beta x an equity premium.
  OWN MULTIPLE  The stock's median price/earnings over its last five fiscal year-ends,
                times normalised earnings per share.

Both use normalised margins applied to current revenue: the last three years plus the
last twelve months, or every year on file for a cyclical business. One great or
terrible year can't set the value.

Checked against Anthropic's financial-analysis DCF skill (2026-11-22): mid-year
discounting, CAPM discount rate, terminal growth below the Treasury yield, margins
normalised across a cycle, and a flag when most value sits beyond the forecast.

The buy-below price is the average of the two, less a margin of safety. No price is
given when only one method works, when they disagree badly, or when the data fails a
check. "No reliable price" is the honest answer then, not a guess.

This shows where a stock meets these rules. It is not a forecast and not advice.

Output: data/valuations.json
Usage:  python3 scripts/valuation.py
"""
import json
import os
import statistics
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import load_json

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUNDAMENTALS_PATH = os.path.join(SCRIPT_DIR, "data", "fundamentals.json")
QUOTES_PATH = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "data", "valuations.json")

MARGIN_OF_SAFETY = 0.25      # buy below 75% of the base value
EQUITY_PREMIUM = 0.05        # return demanded above the 10-year Treasury, for an average stock
MIN_BETA, MAX_BETA = 0.8, 2.0  # how much riskier than average a stock is assumed to be
MAX_TERMINAL_SHARE = 0.75    # above this, the value rests mostly on the far future
CYCLE_SWING = 2.0            # best margin over twice the worst marks a cyclical business
MAX_GROWTH = 0.15            # no company is assumed to grow faster than this for 5 years
TERMINAL_GROWTH = 0.025      # long-run growth, about inflation plus a little
HIGH_GROWTH_YEARS = 5
FADE_YEARS = 5
MIN_GROWTH_SPAN_YEARS = 3
MIN_PE_YEARS = 3
PE_YEARS = 5
NORMALISE_YEARS = 3          # steady businesses: last three years plus the last twelve months
CYCLE_YEARS = 6              # cyclical ones: every year on file, to span a cycle
MAX_SPREAD = 2.5             # methods further apart than this ratio don't agree
MAX_DATA_AGE_DAYS = 200      # last filed period older than this is stale
MAX_REVENUE_GAP = 0.10       # SEC and Yahoo revenue must agree this closely


def dcf_parts(cash: float, growth: float, rate: float,
              terminal: float = TERMINAL_GROWTH) -> tuple[float, float]:
    """Present value of the ten projected years, and of everything after.

    Cash is assumed to arrive mid-year, as in Anthropic's DCF skill, so year one is
    discounted half a year and the terminal value from year 9.5.
    """
    value, flow = 0.0, cash
    years = HIGH_GROWTH_YEARS + FADE_YEARS
    for year in range(1, years + 1):
        fade = max(0, year - HIGH_GROWTH_YEARS) / FADE_YEARS
        flow *= 1 + growth + (terminal - growth) * fade
        value += flow / (1 + rate) ** (year - 0.5)
    return value, flow * (1 + terminal) / (rate - terminal) / (1 + rate) ** (years - 0.5)


def dcf_per_share(cash: float, growth: float, rate: float, terminal: float = TERMINAL_GROWTH) -> float:
    return sum(dcf_parts(cash, growth, rate, terminal))


def terminal_share(cash: float, growth: float, rate: float) -> float:
    explicit, after = dcf_parts(cash, growth, rate)
    return after / (explicit + after)


def discount_rate(treasury: float, beta: float | None) -> float:
    """Treasury yield plus a premium scaled by how much the stock swings (CAPM)."""
    beta = 1.0 if beta is None else min(max(beta, MIN_BETA), MAX_BETA)
    return round(treasury + beta * EQUITY_PREMIUM, 4)


def implied_growth(price: float, cash: float, rate: float) -> float | None:
    """The five-year growth today's price assumes, or None outside -50%..60%."""
    if not cash or cash <= 0:
        return None
    low, high = -0.5, 0.6
    if not dcf_per_share(cash, low, rate) <= price <= dcf_per_share(cash, high, rate):
        return None
    for _ in range(60):
        mid = (low + high) / 2
        low, high = (mid, high) if dcf_per_share(cash, mid, rate) < price else (low, mid)
    return round((low + high) / 2, 4)


def growth_rate(revenue: dict[str, float]) -> float | None:
    """Compound revenue growth over the years on file, between 0 and MAX_GROWTH."""
    years = sorted(revenue.items())
    if len(years) < 2:
        return None
    (first_end, first), (last_end, last) = years[0], years[-1]
    span = int(last_end[:4]) - int(first_end[:4])
    if span < MIN_GROWTH_SPAN_YEARS or first <= 0 or last <= 0:
        return None
    return round(min(max((last / first) ** (1 / span) - 1, 0.0), MAX_GROWTH), 4)


def is_cyclical(operating_income: dict[str, float], revenue: dict[str, float]) -> bool:
    """A loss year, or a best margin more than twice the worst."""
    margins = [operating_income[y] / revenue[y] for y in operating_income if revenue.get(y)]
    if len(margins) < MIN_GROWTH_SPAN_YEARS:
        return False
    return min(margins) <= 0 or max(margins) > CYCLE_SWING * min(margins)


def normalised_margin(values: dict[str, float], revenue: dict[str, float], years: int,
                      ttm: float | None = None, ttm_revenue: float | None = None) -> float | None:
    """Average margin over recent years and the last twelve months.

    Margins, not dollars: averaging dollars undervalues a fast grower, whose early
    years were much smaller. The margin is applied to current revenue instead.
    """
    shared = sorted(y for y in values if revenue.get(y))[-years:]
    margins = [values[y] / revenue[y] for y in shared]
    if ttm is not None and ttm_revenue:
        margins.append(ttm / ttm_revenue)
    return statistics.mean(margins) if len(margins) >= 2 else None


def cash_flow_is_distorted(cash_flow: dict[str, float], profit: dict[str, float]) -> bool:
    """Negative operating cash flow in a profitable year: an accounting quirk, not a value."""
    years = sorted(set(cash_flow) & set(profit))[-NORMALISE_YEARS:]
    return any(cash_flow[y] < 0 < profit[y] for y in years)


def eps_by_year(net_income: dict[str, float], shares: dict[str, float]) -> dict[str, float]:
    """Earnings per share from profit and diluted shares, for years with both."""
    return {y: net_income[y] / shares[y] for y in sorted(shares) if y in net_income and shares[y] > 0}


def own_multiple_value(past_pes: list[float], eps: float | None) -> float | None:
    positive = [pe for pe in past_pes if pe > 0]
    if eps is None or eps <= 0 or len(positive) < MIN_PE_YEARS:
        return None
    return round(statistics.median(positive) * eps, 2)


def combine(methods: dict[str, float | None], price: float, problems: list[str] | None = None,
            implied: float | None = None) -> dict:
    values = {k: round(v, 2) for k, v in methods.items() if v and v > 0}
    out = {"methods": values, "price": price, "status": "no_reliable_price",
           "low": None, "base": None, "high": None, "buy_below": None}
    if values:
        out = {**out, "low": min(values.values()), "high": max(values.values()),
               "base": round(statistics.mean(values.values()), 2)}
    if problems:
        return {**out, "reason": "; ".join(problems)}
    if implied is not None and implied < 0:
        # The value assumes past growth continues; the price says the market disagrees.
        # Until news is judged (v2 phase 4), a value trap and a bargain look the same here.
        return {**out, "status": "market_expects_decline",
                "reason": f"today's price implies the business shrinks about {abs(implied):.0%} a year; "
                          f"find out why before trusting a higher value"}
    if len(values) < 2:
        missing = [k.replace("_", " ") for k in methods if k not in values]
        return {**out, "reason": f"only one valuation method could be used (no {', '.join(missing)})"}
    if out["high"] / out["low"] > MAX_SPREAD:
        parts = ", ".join(f"{k.replace('_', ' ')} ${v:,.0f}" for k, v in values.items())
        return {**out, "reason": f"the methods disagree too much to trust ({parts})"}
    return {**out, "status": "ok", "reason": None,
            "buy_below": round(out["base"] * (1 - MARGIN_OF_SAFETY), 2)}


def _owner_cash(annual: dict, ttm: dict) -> tuple[dict[str, float], float | None]:
    """Operating cash flow - capital spending - stock-based pay, per year and last twelve months."""
    ocf, capex, comp = (annual.get(k, {}) for k in ("operating_cash_flow", "capex", "stock_comp"))
    years = {y: ocf[y] - capex[y] - comp.get(y, 0) for y in ocf if y in capex}
    now = [(ttm.get(k) or {}).get("value") for k in ("operating_cash_flow", "capex")]
    comp_now = (ttm.get("stock_comp") or {}).get("value") or 0
    return years, (now[0] - now[1] - comp_now if None not in now else None)


def _problems(record: dict, quote: dict, today: date) -> list[str]:
    ttm, problems = record.get("ttm", {}), []
    revenue = (ttm.get("revenue") or {})
    if not record.get("annual"):
        return ["no filed US figures (foreign companies file differently)"]
    if not revenue.get("end"):
        return ["no recent revenue on file"]
    age = (today - date.fromisoformat(revenue["end"])).days
    if age > MAX_DATA_AGE_DAYS:
        problems.append(f"latest filed figures are {age} days old")
    yahoo = quote.get("revenue_ttm")
    if yahoo and revenue.get("value") and quote.get("financial_currency") in (None, "USD"):
        gap = abs(revenue["value"] - yahoo) / yahoo
        if gap > MAX_REVENUE_GAP:
            problems.append(f"SEC and Yahoo revenue differ by {gap:.0%}")
    if not (ttm.get("diluted_shares") or {}).get("value"):
        problems.append("no share count on file")
    return problems


def value_ticker(record: dict, quote: dict, year_end_prices: dict[str, float],
                 treasury: float | None, today: date, beta: float | None = None) -> dict:
    """Value one company from its filed figures. Every input is kept for the page to show."""
    price = quote.get("price")
    problems = _problems(record, quote, today)
    if treasury is None:
        problems.append("no 10-year Treasury yield")
    if not price:
        problems.append("no current price")
    if problems:
        return {**combine({}, price, problems), "notes": [], "inputs": {}}
    annual, ttm = record["annual"], record["ttm"]
    value_of = lambda key: (ttm.get(key) or {}).get("value")   # noqa: E731
    shares, revenue, revenue_now = value_of("diluted_shares"), annual.get("revenue", {}), value_of("revenue")
    rate = discount_rate(treasury, beta)
    cyclical = is_cyclical(annual.get("operating_income", {}), revenue)
    years = CYCLE_YEARS if cyclical else NORMALISE_YEARS
    owner_years, owner_now = _owner_cash(annual, ttm)
    cash_margin = normalised_margin(owner_years, revenue, years, owner_now, revenue_now)
    net_margin = normalised_margin(annual.get("net_income", {}), revenue, years,
                                   value_of("net_income"), revenue_now)
    cash_ps = cash_margin * revenue_now / shares if cash_margin is not None else 0.0
    eps = net_margin * revenue_now / shares if net_margin is not None else None
    growth = growth_rate(revenue)
    distorted = cash_flow_is_distorted(annual.get("operating_cash_flow", {}), annual.get("net_income", {}))
    past_eps = eps_by_year(annual.get("net_income", {}), annual.get("diluted_shares", {}))
    pes = [year_end_prices[y] / e for y, e in sorted(past_eps.items())[-PE_YEARS:]
           if e > 0 and year_end_prices.get(y)]
    usable = cash_ps > 0 and growth is not None and not distorted
    cash_value = dcf_per_share(cash_ps, growth, rate) if usable else None
    implied = implied_growth(price, cash_ps, rate) if usable else None
    result = combine({"cash_flow": cash_value, "own_multiple": own_multiple_value(pes, eps)}, price,
                     implied=implied)
    far_future = terminal_share(cash_ps, growth, rate) if usable else None
    notes = [
        *(["cash flow skipped: reported operating cash flow was negative in a profitable year"]
          if distorted else []),
        *(["cyclical business: margins averaged over every year on file"] if cyclical else []),
        *([f"{far_future:.0%} of the cash-flow value comes after year 10, so it rests on long-run guesses"]
          if far_future and far_future > MAX_TERMINAL_SHARE else []),
        *(["no beta available, so average market risk was assumed"] if beta is None else []),
    ]
    return {**result, "notes": notes, "inputs": {
        "owner_cash_per_share": round(cash_ps, 2), "cash_margin": round(cash_margin, 4) if cash_margin else None,
        "growth_used": growth, "discount_rate": rate, "beta": beta, "cyclical": cyclical,
        "eps_normalised": round(eps, 2) if eps else None,
        "median_past_pe": round(statistics.median(pes), 1) if len(pes) >= MIN_PE_YEARS else None,
        "terminal_share": round(far_future, 3) if far_future else None,
        "implied_growth": implied,
        "figures_as_of": ttm["revenue"]["end"], "sources": record.get("source", {})}}


def _year_end_prices(ticker: str, ends: list[str]) -> dict[str, float]:
    """Closing price on or just before each fiscal year end."""
    import yfinance as yf
    history = yf.Ticker(ticker).history(period="7y", interval="1d", auto_adjust=False)["Close"]
    history.index = history.index.tz_localize(None)
    out = {}
    for end in ends:
        before = history[history.index <= end]
        if len(before):
            out[end] = float(before.iloc[-1])
    return out


def _beta(ticker: str) -> float | None:
    """Yahoo's five-year monthly beta against the market."""
    import yfinance as yf
    beta = (yf.Ticker(ticker).info or {}).get("beta")
    return round(float(beta), 2) if isinstance(beta, (int, float)) else None


def _treasury_yield() -> float | None:
    import yfinance as yf
    try:
        tnx = yf.Ticker("^TNX").history(period="5d")["Close"]
        return round(float(tnx.iloc[-1]) / 100, 4) if len(tnx) else None
    except Exception as exc:   # network or Yahoo change: no yield means no prices, said loudly
        print(f"⚠ 10-year Treasury yield unavailable: {str(exc)[:120]}")
        return None


def main() -> None:
    fundamentals = load_json(FUNDAMENTALS_PATH).get("tickers", {})
    quotes = load_json(QUOTES_PATH).get("tickers", {})
    if not fundamentals:
        print("No data/fundamentals.json — run scripts/sec_facts.py first.")
        sys.exit(1)
    treasury, today = _treasury_yield(), datetime.now(timezone.utc).date()
    results = {}
    for ticker, record in sorted(fundamentals.items()):
        ends = list(record.get("annual", {}).get("diluted_shares", {}))
        try:
            prices = _year_end_prices(ticker, ends) if ends else {}
            beta = _beta(ticker)
        except Exception as exc:
            print(f"⚠ {ticker}: price history unavailable ({str(exc)[:100]})")
            prices, beta = {}, None
        results[ticker] = value_ticker(record, quotes.get(ticker, {}), prices, treasury, today, beta)
    priced = sum(r["status"] == "ok" for r in results.values())
    with open(OUTPUT_PATH, "w") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "treasury_10y": treasury, "margin_of_safety": MARGIN_OF_SAFETY,
                   "equity_premium": EQUITY_PREMIUM, "tickers": results}, f, indent=1)
    print(f"✅ Valued {len(results)} companies; {priced} have a reliable buy-below price")


if __name__ == "__main__":
    main()
