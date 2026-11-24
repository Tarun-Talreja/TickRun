#!/usr/bin/env python3
"""
scripts/plan_review.py — Where the saved plan conflicts with itself or with today's facts.

States facts and the question each one raises. It changes nothing in the plan and
suggests no trade: the owner settles each conflict.

Output: data/plan_review.json   Usage: python3 scripts/plan_review.py
"""
import json
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import load_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(ROOT, "data", "portfolio.json")
OUTPUT_PATH = os.path.join(ROOT, "data", "plan_review.json")

# IRS limits for people under 50, checked 2026-11-24 at LIMIT_URL. Add a year when the IRS page shows it.
IRA_LIMITS = {2025: 7000, 2026: 7500}
LIMIT_URL = "https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-ira-contribution-limits"
LINKED = 0.6            # weekly return correlation over two years
WEEKS = 104
STRESS = 0.5
STALE_PLAN_DAYS = 90


def linked_groups(tickers: list[str], corr: dict[str, dict[str, float]]) -> list[list[str]]:
    """Picks whose weekly moves go together, joined through any shared link."""
    groups: list[list[str]] = []
    for t in tickers:
        near = [g for g in groups if any(corr.get(t, {}).get(o, 0) >= LINKED for o in g)]
        groups = [g for g in groups if g not in near] + [[*(x for g in near for x in g), t]]
    return [sorted(g) for g in groups if len(g) > 1]


def _conflict(title: str, fact: str, question: str, url: str | None = None) -> dict:
    return {"title": title, "fact": fact, "question": question, "url": url}


def conflicts(plan: dict, market: dict, today: date) -> list[dict]:
    rules, alloc = plan["rules"], plan["target_allocation"]
    deploy, picks = plan["deployment_plan"], plan["thematic"]
    total, cap = deploy["total"], rules["max_single_position_pct"]
    dollars = {p["ticker"]: p["target_dollars"] for p in picks}
    groups = linked_groups(list(dollars), market.get("corr", {}))
    limit = IRA_LIMITS.get(today.year)
    out = []
    if plan.get("money_already_in_account"):
        pass   # the limit is on new contributions, not on investing what is there
    elif limit is None:
        out.append(_conflict("Yearly limit not checked", f"The {today.year} IRA limit isn't in the app yet.",
                             "Check the IRS page before adding money.", LIMIT_URL))
    elif rules.get("account_type") == "Roth IRA" and total > limit:
        out.append(_conflict(
            "More money than one year allows",
            f"The plan uses ${total:,}. The {today.year} limit is ${limit:,} if you're under 50, or your taxable pay if "
            f"that's less. Income limits apply too.",
            "Is the rest already in the account, from a rollover, or meant for another year or account?", LIMIT_URL))
    intl = alloc.get("international_pct", 0)
    if intl and not plan.get("international"):
        out.append(_conflict("International has nothing in it",
                             f"The target is {intl}% international, but no fund is listed. The ${deploy['cash_reserve']:,} left "
                             f"over is called a cash reserve.", "Is that share meant to be international or cash?"))
    for g in groups:
        pct = sum(dollars[t] for t in g) / total * 100
        if pct > cap:
            out.append(_conflict(
                f"{' and '.join(g)} act like one bet",
                f"Their weekly moves had a correlation of {market['corr'][g[0]].get(g[1], 0):.2f} over two years (1 means identical). Together they are "
                f"{pct:.0f}% of the plan, above the {cap}% limit for one position.",
                f"Does the {cap}% limit count linked stocks together?"))
    stop = rules["stop_loss_pct"]
    worst = {t: d for t, d in market.get("worst_fall", {}).items() if t in dollars and abs(d) >= stop}
    if worst:
        out.append(_conflict(
            f"The {stop}% stop-loss is inside normal swings",
            "Worst fall from a high in five years (or since listing): "
            + ", ".join(f"{t} {abs(d):.0f}%" for t, d in sorted(worst.items())) + ".",
            "What should make you sell: a price fall, or a change in the business?"))
    if rules["trim_trigger_pct"] > cap:
        out.append(_conflict("Limit and trim rule differ",
                             f"No position may exceed {cap}%, but trimming starts at {rules['trim_trigger_pct']}%.",
                             f"What happens between {cap}% and {rules['trim_trigger_pct']}%?"))
    age = (today - date.fromisoformat(plan["last_updated"])).days
    if age > STALE_PLAN_DAYS:
        now = [f"{t}: {f['forward_pe']:.1f}x next-year earnings, sales {f['revenue_growth']:+.0f}%"
               for t, f in market.get("now", {}).items() if t in dollars and f.get("forward_pe") and f.get("revenue_growth") is not None]
        out.append(_conflict(
            "The reasons are from another time",
            f"Written {age} days ago, with steps dated “this week” and buy targets the app has since dropped. Now: "
            + "; ".join(now) + ".", "Do these picks still belong, or should the steps be cleared?"))
    return out


def overlap(plan: dict, fund: dict[str, float]) -> list[dict]:
    """How much of each pick the core fund already holds, from its ten largest holdings."""
    smallest = min(fund.values()) if fund else None
    return [{"ticker": p["ticker"], "pct": round(fund[p["ticker"]] * 100, 1) if p["ticker"] in fund else None,
             "below_pct": round(smallest * 100, 1) if smallest else None} for p in plan["thematic"]]


def stress(plan: dict, groups: list[list[str]]) -> list[dict]:
    """What the plan would lose if each linked group, or single pick, halved and nothing else moved."""
    dollars = {p["ticker"]: p["target_dollars"] for p in plan["thematic"]}
    total, grouped = plan["deployment_plan"]["total"], {t for g in groups for t in g}
    units = [*groups, *[[t] for t in dollars if t not in grouped]]
    rows = [{"names": g, "pct": round(sum(dollars[t] for t in g) * STRESS / total * 100, 1)} for g in units]
    return sorted(rows, key=lambda r: -r["pct"])


def _market(tickers: list[str], core: str) -> dict:
    import yfinance as yf
    close = yf.download([*tickers, core], period="5y", auto_adjust=True, progress=False)["Close"]
    weekly = close.resample("W-FRI").last().pct_change(fill_method=None).tail(WEEKS)
    corr = weekly.corr(min_periods=52)
    info = {t: yf.Ticker(t).info or {} for t in tickers}
    holdings = yf.Ticker(core).funds_data.top_holdings["Holding Percent"]
    return {"corr": {a: {b: round(float(corr.loc[a, b]), 2) for b in tickers if b != a} for a in tickers},
            "worst_fall": {t: round(float((close[t].dropna() / close[t].dropna().cummax() - 1).min() * 100), 1) for t in tickers},
            "fund": {str(k): float(v) for k, v in holdings.items()},
            "now": {t: {"forward_pe": i.get("forwardPE"), "revenue_growth": (i.get("revenueGrowth") or 0) * 100
                        if i.get("revenueGrowth") is not None else None} for t, i in info.items()}}


def main() -> None:
    plan = load_json(PORTFOLIO_PATH)
    tickers = [p["ticker"] for p in plan["thematic"]]
    market = _market(tickers, plan["core"][0]["ticker"])
    groups = linked_groups(tickers, market["corr"])
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "plan_date": plan["last_updated"],
           "core": plan["core"][0]["ticker"], "conflicts": conflicts(plan, market, datetime.now(timezone.utc).date()),
           "overlap": overlap(plan, market["fund"]), "stress": stress(plan, groups), "groups": groups}
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=1)
    print(f"✅ Plan review: {len(out['conflicts'])} conflicts")


if __name__ == "__main__":
    main()
