"""Warnings follow the saved rules and only concern stocks that are owned."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from holding_flags import holding_flags

RULES = {"max_single_position_pct": 15, "review_price_fall_pct": 30, "review_business_change": True, "count_linked_together": True}


def h(t, value, pnl=0.0, **k):
    return {"ticker": t, "shares": 1, "market_value": value, "pnl_pct": pnl, **k}


CORE = h("VTI", 80, core=True)


def test_nothing_owned_means_no_flags():
    assert holding_flags([h("VST", None), {"ticker": "CEG", "shares": 0}], RULES, [["CEG", "VST"]], {"VST": {"key": "weak"}}) == []


def test_linked_stocks_count_together():
    f = holding_flags([CORE, h("VST", 10), h("CEG", 10)], RULES, [["CEG", "VST"]], {})
    assert len(f) == 1 and f[0]["names"] == ["CEG", "VST"] and "20%" in f[0]["text"]
    assert holding_flags([CORE, h("VST", 10), h("CEG", 10)], {**RULES, "count_linked_together": False}, [["CEG", "VST"]], {}) == []


def test_core_fund_is_never_over_the_limit():
    assert holding_flags([CORE], RULES, [], {}) == []


def test_price_fall_or_business_change():
    f = holding_flags([CORE, h("X", 5, pnl=-31.0), h("Y", 5)], RULES, [], {"Y": {"key": "weak", "label": "Fails checks", "why": "w"}})
    assert [x["names"] for x in f] == [["X"], ["Y"]] and not any("sell" in x["text"].lower() for x in f)
