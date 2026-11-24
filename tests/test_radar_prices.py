"""Radar cards show the current price, or say which day theirs is from."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from build_dashboard import with_live_prices

CARD = {"ticker": "NVDA", "price": 125.53, "reasons": [{"text": "Quality business 48% below its high"}],
        "watch_outs": ["Down 48% from its high, so find out why first"]}


def test_tracked_stock_gets_the_current_price_and_fall():
    out = with_live_prices({"cards": [CARD]}, {"NVDA": {"price": 165.05, "drawdown_from_high": -32.1}})["cards"][0]
    assert out["price"] == 165.05 and "32% below" in out["reasons"][0]["text"] and "32% from" in out["watch_outs"][0]


def test_untracked_stock_keeps_its_price_with_its_date():
    out = with_live_prices({"cards": [CARD], "universe_as_of": "2026-11-21T19:15:39Z"}, {})["cards"][0]
    assert out["price_date"] == "2026-11-21"


def test_missing_radar():
    assert with_live_prices({}, {}) == {}
