"""Warnings on stocks you own, from the rules in data/portfolio.json. They flag; they never say sell."""


def holding_flags(holdings: list[dict], rules: dict, groups: list[list[str]], categories: dict[str, dict]) -> list[dict]:
    owned = [h for h in holdings if h.get("shares") and h.get("market_value")]
    total = sum(h["market_value"] for h in owned)
    picks = {h["ticker"]: h for h in owned if not h.get("core")}
    limit, fall = rules["max_single_position_pct"], rules["review_price_fall_pct"]
    linked = groups if rules.get("count_linked_together") else []
    units = [[t for t in g if t in picks] for g in linked]
    units += [[t] for t in picks if not any(t in u for u in units)]
    flags = []
    for unit in filter(None, units):
        pct = sum(picks[t]["market_value"] for t in unit) / total * 100
        if pct > limit:
            flags.append({"names": unit, "text": f"{pct:.0f}% of the portfolio, above your {limit}% limit"})
    for t, h in picks.items():
        if h.get("pnl_pct") is not None and h["pnl_pct"] <= -fall:
            flags.append({"names": [t], "text": f"Down {abs(h['pnl_pct']):.0f}% from what you paid. Review it."})
        c = categories.get(t) or {}
        if rules.get("review_business_change") and c.get("key") in ("serious", "weak"):
            flags.append({"names": [t], "text": f"{c['label']}: {c['why']}. Review it."})
    return flags
