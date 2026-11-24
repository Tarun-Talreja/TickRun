"""What the stock page may show from a saved valuation, checked against today's price."""
from datetime import datetime, timezone

MAX_AGE_DAYS = 4          # a long weekend; older than this, no buy-below price is shown
KEPT = ("status", "low", "base", "high", "buy_below", "reason", "notes", "methods", "inputs")


def valuation_view(record: dict | None, price: float | None, generated_at: str | None,
                   now: datetime | None = None) -> dict | None:
    if not record or not generated_at:
        return None
    now = now or datetime.now(timezone.utc)
    made = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    view = {**{k: record.get(k) for k in KEPT}, "valued_on": generated_at[:10], "gap_pct": None}
    if view["status"] != "ok":
        return view
    floor = record.get("no_growth_value")
    if (now - made).days > MAX_AGE_DAYS:
        return {**view, "status": "no_reliable_price", "buy_below": None,
                "reason": f"the valuation is from {generated_at[:10]} and hasn't been refreshed"}
    if not price:
        return {**view, "status": "no_reliable_price", "buy_below": None, "reason": "no current price"}
    if floor and price < floor:
        return {**view, "status": "market_expects_decline", "buy_below": None,
                "reason": "the price has fallen to where it assumes the business shrinks; "
                          "find out why before trusting a higher value"}
    return {**view, "gap_pct": round((price / view["buy_below"] - 1) * 100, 1)}
