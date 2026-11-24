"""Has the price moved a lot since a stock was rated? Then the rating is out of date."""
from datetime import datetime, timezone

from market_time import session_date

MOVE_PCT = 15.0      # since the rating
DAY_PCT = 10.0       # in one day, even if it only undid an earlier move


def big_move(candidate: dict, quote: dict) -> dict | None:
    """The move that outdates this rating, or None."""
    price, then, rated_on = quote.get("price"), candidate.get("rated_price"), candidate.get("last_researched")
    if not price or not rated_on:
        return None
    day, stamp = quote.get("pct_change_1d"), quote.get("price_time")
    if day is not None and stamp and abs(day) >= DAY_PCT:
        traded = session_date(datetime.fromtimestamp(stamp, timezone.utc)).isoformat()
        if traded >= rated_on:
            return {"pct": round(day, 1), "span": "in one day"}
    move = (price / then - 1) * 100 if then else 0.0
    return {"pct": round(move, 1), "span": "since it was rated"} if abs(move) >= MOVE_PCT else None
