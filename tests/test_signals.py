"""Signals must be able to say both yes and no, or they carry no information."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from research_ticker import _anchor_trigger
from target_alerts import _refresh_live_targets


class TestAnchorTrigger:
    quotes = {"tickers": {"NVT": {"drawdown_from_high": -46.7}}}

    def test_zero_locks_in_todays_drawdown(self):
        assert _anchor_trigger("NVT", 0.0, self.quotes) == -46.7

    def test_real_trigger_is_kept(self):
        assert _anchor_trigger("NVT", -20.0, self.quotes) == -20.0

    def test_no_trigger_stays_none(self):
        assert _anchor_trigger("NVT", None, self.quotes) is None

    def test_zero_without_quote_stays_zero(self):
        assert _anchor_trigger("XYZ", 0.0, self.quotes) == 0.0


class TestLiveTargets:
    def test_zero_trigger_target_does_not_follow_price_down(self):
        wl = {"candidates": [{"ticker": "COHR", "buy_trigger_drawdown_pct": 0.0, "buy_target": 195.0}]}
        _refresh_live_targets(wl, {"COHR": {"price": 169.76, "high_52w": 440.0}})
        assert wl["candidates"][0]["buy_target"] == 195.0

    def test_zero_trigger_without_target_starts_at_price(self):
        wl = {"candidates": [{"ticker": "COHR", "buy_trigger_drawdown_pct": 0.0}]}
        _refresh_live_targets(wl, {"COHR": {"price": 169.76, "high_52w": 440.0}})
        assert wl["candidates"][0]["buy_target"] == 169.76

    def test_drawdown_trigger_tracks_the_high(self):
        wl = {"candidates": [{"ticker": "AMD", "buy_trigger_drawdown_pct": -25.0, "buy_target": 1.0}]}
        _refresh_live_targets(wl, {"AMD": {"price": 404.4, "high_52w": 660.0}})
        assert wl["candidates"][0]["buy_target"] == 495.0
