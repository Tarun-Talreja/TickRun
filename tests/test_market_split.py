"""The parts of a move must be from one session and must add up to it."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from market_split import day_changes, fund_for, panel, split_move

STAMP = 1795467601   # 2026-11-23 16:00 New York
MARKET = {"session": "2026-11-23", "changes": {"SPY": 4.7, "QQQ": 7.0, "XSD": 12.1, "RSPU": 1.6}}


def q(pct, **over):
    return {"pct_change_1d": pct, "price_time": STAMP, "sector": "Technology", "industry": "Semiconductors", **over}


def test_parts_add_up():
    s = split_move(q(31.5), MARKET)
    assert (s["market"], s["group"], s["own"]) == (4.7, 7.4, 19.4)
    assert s["market"] + s["group"] + s["own"] == pytest.approx(31.5)


def test_stock_that_lagged_its_group():
    assert split_move(q(2.0), MARKET)["own"] == -10.1


def test_no_group_fund_means_market_only():
    s = split_move(q(6.7, sector=None, industry=None), MARKET)
    assert s["group"] is None and s["own"] == 2.0


def test_other_session_or_missing_market_gives_nothing():
    assert split_move(q(5), {**MARKET, "session": "2026-11-24"}) is None
    assert split_move(q(5), {}) is None and split_move(q(None), MARKET) is None


def test_chips_use_the_chip_fund():
    assert fund_for("Technology", "Semiconductors") == "XSD"
    assert fund_for("Utilities", "Utilities - Regulated Electric") == "RSPU"
    assert fund_for(None, None) is None


def test_changes_use_the_same_two_days_for_everyone():
    out = day_changes({"SPY": {"a": 100, "b": 110}, "XSD": {"a": 50, "b": 55}, "RSPU": {"a": 10},
                       "^TNX": {"a": 4.91, "b": 4.92}})
    assert out["changes"] == {"SPY": 10.0, "XSD": 10.0} and out["treasury"] == 4.92
    assert day_changes({}) == {}


def test_panel_counts_only_followed_stocks_from_this_session():
    quotes = {"A": q(1), "B": q(-1), "SPY": q(4.7), "OLD": q(3, price_time=STAMP - 86400 * 4)}
    p = panel(quotes, MARKET, {"SPY"})
    assert (p["up"], p["counted"]) == (1, 2)
    assert p["best"]["name"] == "chip" and p["worst"]["name"] == "utility"
    assert panel(quotes, {}, set()) is None
