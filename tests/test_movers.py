"""On a market-wide selloff the mover list must explain itself and stay readable."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from daily_brief import _mover_items
from move_explainer import _market_note, _market_reason

SELLOFF = {"SPY": {"pct_change_1d": -4.41}, "QQQ": {"pct_change_1d": -6.49}}
QUIET = {"SPY": {"pct_change_1d": 0.2}, "QQQ": {"pct_change_1d": 0.4}}


class TestMarketReason:
    def test_down_with_a_falling_market(self):
        reason = _market_reason(-17.3, SELLOFF)
        assert "-6.5%" in reason and "-4.4%" in reason

    def test_up_against_a_falling_market_is_not_explained_by_it(self):
        assert _market_reason(8.0, SELLOFF) is None

    def test_quiet_market_explains_nothing(self):
        assert _market_reason(-9.0, QUIET) is None

    def test_missing_index_quotes(self):
        assert _market_reason(-9.0, {}) is None

    def test_note_for_the_prompt(self):
        assert "-6.5%" in _market_note(SELLOFF)
        assert _market_note({}) == ""


def _mover(ticker, pct):
    return {"ticker": ticker, "primary_pct": pct, "reason": "Part of a selloff."}


class TestMoverItems:
    verdicts = {"LITE": "PASS", "CRDO": "PASS", "MU": "RED FLAG", "AMD": "WATCHLIST",
                "CLS": "WATCHLIST", "TSM": "RESEARCH-WORTHY", "NVT": "WATCHLIST"}
    movers = [_mover("LITE", -18.7), _mover("CRDO", -17.7), _mover("MU", -17.5),
              _mover("AMD", -17.3), _mover("CLS", -13.0), _mover("TSM", -6.0), _mover("NVT", -5.5)]

    def test_tracked_names_come_before_passed_ones(self):
        tickers = [i["ticker"] for i in _mover_items(self.movers, self.verdicts)]
        assert tickers[:3] == ["AMD", "CLS", "TSM"]

    def test_the_rest_collapse_into_one_line(self):
        items = _mover_items(self.movers, self.verdicts)
        assert len(items) == 4
        assert items[-1]["kind"] == "mover_summary" and "4 more" in items[-1]["headline"]

    def test_small_moves_are_ignored(self):
        assert _mover_items([_mover("AMD", -2.0)], self.verdicts) == []

    def test_no_summary_when_nothing_is_hidden(self):
        items = _mover_items([_mover("AMD", -9.0)], self.verdicts)
        assert [i["kind"] for i in items] == ["mover"]
