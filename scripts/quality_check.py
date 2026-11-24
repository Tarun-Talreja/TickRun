"""Five yes/no checks on the business from filed figures. A missing figure is "unknown", never a pass."""
from statistics import mean

CASH_YEARS = 3
MIN_CASH_SHARE = 0.8       # cash after equipment spending, as a share of reported profit
MAX_SHARE_GROWTH = 0.02    # a year
MAX_DEBT_YEARS = 4.0       # years of operating cash flow to repay debt net of cash
CHRONIC_LOSSES = 3         # this many loss years fails the business by itself
MARGIN_DROP = 0.75         # latest margin against its own earlier average
LENDERS = {"Financial Services", "Real Estate"}   # debt is the business, so that check says nothing


def _row(name: str, ok: bool | None, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def _profit(annual: dict) -> dict:
    profits = annual.get("net_income", {})
    latest = sorted(annual.get("revenue", {}))[-2:]
    if any(y not in profits for y in latest):
        return _row("Profitable every year", None, "recent years are missing from the filings' figures")
    if len(profits) < 4:
        return _row("Profitable every year", None, "fewer than 4 years on file")
    losses = [y[:4] for y, v in profits.items() if v <= 0]
    row = _row("Profitable every year", not losses,
               f"lost money in {', '.join(losses)}" if losses else f"all {len(profits)} years on file")
    return {**row, "chronic": len(losses) >= CHRONIC_LOSSES}


def _cash(annual: dict, quote: dict) -> dict:
    name, ocf, capex, profit = "Profit turns into cash", *(annual.get(k, {}) for k in
                                                          ("operating_cash_flow", "capex", "net_income"))
    if quote.get("sector") in LENDERS:
        return _row(name, None, "doesn't apply to financial and property companies")
    years = sorted(set(ocf) & set(capex) & set(profit))[-CASH_YEARS:]
    total = sum(profit[y] for y in years)
    if len(years) < CASH_YEARS or total <= 0:
        return _row(name, None, "not enough filed figures")
    share = sum(ocf[y] - capex[y] for y in years) / total
    return _row(name, share >= MIN_CASH_SHARE, f"{share:.0%} of three years' profit arrived as cash after spending")


def _shares(annual: dict) -> dict:
    shares = sorted(annual.get("diluted_shares", {}).items())
    if len(shares) < 3 or shares[0][1] <= 0:
        return _row("Share count not swelling", None, "fewer than 3 years on file")
    growth = (shares[-1][1] / shares[0][1]) ** (1 / (len(shares) - 1)) - 1
    word = "grew" if growth > 0 else "fell"
    return _row("Share count not swelling", growth <= MAX_SHARE_GROWTH, f"{word} {abs(growth):.1%} a year")


def _debt(ttm: dict, quote: dict) -> dict:
    name, cash_flow = "Debt is manageable", (ttm.get("operating_cash_flow") or {}).get("value")
    debt, cash = quote.get("total_debt"), quote.get("total_cash")
    if quote.get("sector") in LENDERS:
        return _row(name, None, "doesn't apply to lenders and property companies")
    if debt is None or cash is None or cash_flow is None:
        return _row(name, None, "figures missing")
    if debt <= cash:
        return _row(name, True, "more cash than debt")
    if cash_flow <= 0:
        return _row(name, False, "has net debt and no operating cash flow")
    years = (debt - cash) / cash_flow
    return _row(name, years <= MAX_DEBT_YEARS, f"net debt is {years:.1f} years of operating cash flow (debt from Yahoo)")


def _margin(annual: dict, ttm: dict) -> dict:
    name, profit, revenue = "Margins holding up", annual.get("net_income", {}), annual.get("revenue", {})
    years = sorted(y for y in profit if revenue.get(y))[-5:]
    now = [(ttm.get(k) or {}).get("value") for k in ("net_income", "revenue")]
    if len(years) < 3 or None in now or not now[1]:
        return _row(name, None, "not enough filed figures")
    before, latest = mean(profit[y] / revenue[y] for y in years), now[0] / now[1]
    if before <= 0:
        return _row(name, None, "lost money on average, so there is nothing to compare")
    return _row(name, latest >= before * MARGIN_DROP, f"{latest:.1%} over the last year, {before:.1%} on average before")


def quality(record: dict | None, quote: dict) -> dict | None:
    if not record or not record.get("annual"):
        return None
    annual, ttm = record["annual"], record.get("ttm", {})
    checks = [_profit(annual), _cash(annual, quote), _shares(annual), _debt(ttm, quote), _margin(annual, ttm)]
    return {"checks": checks, "passed": sum(c["ok"] is True for c in checks),
            "failed": sum(c["ok"] is False for c in checks), "known": sum(c["ok"] is not None for c in checks)}
