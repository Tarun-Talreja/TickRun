"""A buy-below price may only show when it is fresh and consistent with today's price."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from build_dashboard import without_made_up_figures
from fact_check import drop_unsupported
from rating_move import big_move
from valuation import _share_problems, capped_by_now, combine
from valuation_view import valuation_view

NOW = datetime(2026, 11, 24, tzinfo=timezone.utc)
MADE = "2026-11-23T22:00:00Z"
OK = {"status": "ok", "low": 90, "base": 100, "high": 110, "buy_below": 75.0, "no_growth_value": 60}


def test_gap_uses_todays_price():
    assert valuation_view(OK, 90, MADE, NOW)["gap_pct"] == 20.0


def test_old_valuation_gives_no_price():
    v = valuation_view(OK, 90, "2026-11-10T00:00:00Z", NOW)
    assert v["buy_below"] is None and v["status"] == "no_reliable_price"


def test_price_collapse_after_the_valuation_hides_it():
    v = valuation_view(OK, 55, MADE, NOW)
    assert v["buy_below"] is None and v["status"] == "market_expects_decline"


def test_missing_price_or_record():
    assert valuation_view(OK, None, MADE, NOW)["buy_below"] is None
    assert valuation_view(None, 90, MADE, NOW) is None


def test_price_below_any_implied_growth_is_still_a_decline():
    out = combine({"a": 100, "b": 110}, 5, implied=None, no_growth_value=60)
    assert out["status"] == "market_expects_decline" and out["buy_below"] is None


def test_split_blocks_the_price():
    assert _share_problems(100, {"2025-12-31": 10}, {})
    assert _share_problems(100, {}, {"price": 5, "market_cap": 5000})
    assert _share_problems(100, {"2025-12-31": 102}, {"price": 50, "market_cap": 5100}) == []


def test_sentences_with_made_up_figures_are_dropped():
    out = drop_unsupported("Margin is 40%. Azure grew 29%. It is cheap.", ["29%"])
    assert "29%" not in out.split("[")[0] and "Margin is 40%." in out and "1 sentence(s) removed" in out


def test_longer_figure_is_not_matched_by_a_shorter_one():
    assert drop_unsupported("Grew 129%.", ["29%"]) == "Grew 129%."


def test_stock_text_and_action_are_cleaned():
    s = without_made_up_figures({"thesis": "Good. Worth $9T.", "bear_check": None, "unsupported_figures": ["$9T"],
                                 "next_action": "WAIT — Good. Worth $9T."})
    assert "$9T" not in s["thesis"] and s["next_action"].startswith("WAIT — Good.") and "$9T" not in s["next_action"]


def test_big_move_since_rating():
    c = {"ticker": "X", "last_researched": "2026-11-18", "rated_price": 100.0}
    assert big_move(c, {"price": 131.5})["pct"] == 31.5
    assert big_move(c, {"price": 110}) is None
    assert big_move({**c, "rated_price": None}, {"price": 131}) is None


def test_big_day_counts_only_after_the_rating():
    quote = {"price": 101, "pct_change_1d": 31.5, "price_time": 1795467601}   # 2026-11-23 16:00 New York
    c = {"rated_price": 100.0, "last_researched": "2026-11-18"}
    assert big_move(c, quote) == {"pct": 31.5, "span": "in one day"}
    assert big_move({**c, "last_researched": "2026-11-24"}, quote) is None


def test_growth_is_capped_by_the_latest_quarter():
    assert capped_by_now(0.099, 5.4)[0] == 0.054
    assert capped_by_now(0.04, 5.4) == (0.04, None)
    assert capped_by_now(0.04, -3)[0] == 0.0
    assert capped_by_now(0.04, None) == (0.04, None)


def test_text_that_is_all_made_up_says_so():
    assert drop_unsupported("Worth $9T.", ["$9T"]).startswith("No summary")
