"""How much of a stock's day was the market, its group, or the stock itself.

Plain subtraction against index funds over the same session; it says what moved
together, not what caused what. Group funds are equal-weight, so one giant like NVDA
can't be most of the group it is compared with.
"""
from datetime import datetime, timezone

from market_time import session_date

# Yahoo sector -> (equal-weight fund, plain name)
SECTOR_FUNDS = {
    "Technology": ("RSPT", "technology"), "Communication Services": ("RSPC", "media and communication"),
    "Consumer Cyclical": ("RSPD", "consumer spending"), "Consumer Defensive": ("RSPS", "everyday goods"),
    "Healthcare": ("RSPH", "healthcare"), "Financial Services": ("RSPF", "financial"),
    "Industrials": ("RSPN", "industrial"), "Utilities": ("RSPU", "utility"),
    "Real Estate": ("RSPR", "real estate"), "Energy": ("RSPG", "energy"), "Basic Materials": ("RSPM", "materials"),
}
CHIP_INDUSTRIES = {"Semiconductors", "Semiconductor Equipment & Materials"}
CHIP_FUND = ("XSD", "chip")
MARKET, NASDAQ, TREASURY = "SPY", "QQQ", "^TNX"
FUND_NAMES = {fund: name for fund, name in [*SECTOR_FUNDS.values(), CHIP_FUND]}
SYMBOLS = [MARKET, NASDAQ, TREASURY, *FUND_NAMES]


def fund_for(sector: str | None, industry: str | None) -> str | None:
    if industry in CHIP_INDUSTRIES:
        return CHIP_FUND[0]
    return SECTOR_FUNDS.get(sector, (None,))[0]


def day_changes(closes: dict[str, dict[str, float]]) -> dict:
    """Session date and each symbol's change from the session before it, same days for all."""
    days = sorted(closes.get(MARKET, {}))
    if len(days) < 2:
        return {}
    before, day = days[-2:]
    changes = {s: round((c[day] / c[before] - 1) * 100, 2) for s, c in closes.items()
               if s != TREASURY and c.get(day) and c.get(before)}
    tnx = closes.get(TREASURY, {})
    out = {"session": day, "changes": changes}
    return {**out, "treasury": round(tnx[day], 2), "treasury_before": round(tnx[before], 2)} \
        if tnx.get(day) and tnx.get(before) else out


def _session(quote: dict) -> str | None:
    stamp = quote.get("price_time")
    return session_date(datetime.fromtimestamp(stamp, timezone.utc)).isoformat() if stamp else None


def split_move(quote: dict, market: dict) -> dict | None:
    """Points of the day's move from the market, the group beyond it, and the stock alone."""
    pct, changes = quote.get("pct_change_1d"), market.get("changes", {})
    base = changes.get(MARKET)
    if pct is None or base is None or _session(quote) != market.get("session"):
        return None
    fund = fund_for(quote.get("sector"), quote.get("industry"))
    group = changes.get(fund)
    return {"session": market["session"], "pct": round(pct, 1), "market": round(base, 1),
            "group": round(group - base, 1) if group is not None else None,
            "group_name": FUND_NAMES.get(fund) if group is not None else None,
            "fund": fund if group is not None else None,
            "own": round(pct - (group if group is not None else base), 1)}


def panel(quotes: dict, market: dict, skip: set[str]) -> dict | None:
    changes = market.get("changes", {})
    if changes.get(MARKET) is None:
        return None
    mine = [q["pct_change_1d"] for t, q in quotes.items() if t not in skip
            and q.get("pct_change_1d") is not None and _session(q) == market["session"]]
    groups = sorted(((changes[f], n) for f, n in FUND_NAMES.items() if f in changes), reverse=True)
    return {"session": market["session"], "sp500": changes[MARKET], "nasdaq100": changes.get(NASDAQ),
            "treasury": market.get("treasury"), "treasury_before": market.get("treasury_before"),
            "up": sum(p > 0 for p in mine), "counted": len(mine),
            "best": {"name": groups[0][1], "pct": groups[0][0]} if groups else None,
            "worst": {"name": groups[-1][1], "pct": groups[-1][0]} if groups else None}
