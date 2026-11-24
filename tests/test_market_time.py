"""A price is out of date once the market has traded past it, whatever day it was fetched."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from market_time import price_due_at, prices_as_of


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_friday_close_is_due_after_monday_opens():
    # 4pm ET Friday -> 10:15am ET Monday, 45 minutes into the session.
    assert price_due_at(_utc(2026, 11, 20, 21, 0)) == _utc(2026, 11, 23, 15, 15)


def test_mid_session_price_is_due_45_minutes_later():
    assert price_due_at(_utc(2026, 11, 23, 16, 0)) == _utc(2026, 11, 23, 16, 45)


def test_before_the_open_is_due_that_morning():
    assert price_due_at(_utc(2026, 11, 23, 13, 36)) == _utc(2026, 11, 23, 15, 15)


def test_thanksgiving_is_skipped():
    assert price_due_at(_utc(2026, 11, 25, 21, 0)) == _utc(2026, 11, 27, 15, 15)


def test_good_friday_is_skipped():
    # 2027-03-26 is Good Friday; the next session is Monday, in daylight saving time.
    assert price_due_at(_utc(2027, 3, 25, 20, 0)) == _utc(2027, 3, 29, 14, 15)


def test_one_frozen_quote_does_not_set_the_age():
    fresh, old = 1795467602, 1795208402
    quotes = {"A": {"price_time": fresh}, "B": {"price_time": fresh}, "C": {"price_time": old}, "D": {}}
    assert prices_as_of(quotes) == "2026-11-23T21:00:02Z"


def test_no_market_times_means_unknown():
    assert prices_as_of({"A": {}}) is None and prices_as_of({}) is None


def test_early_close_after_thanksgiving_is_not_stale_all_weekend():
    assert price_due_at(_utc(2026, 11, 27, 18, 0)) == _utc(2026, 11, 30, 15, 15)


def test_a_last_trade_seconds_before_the_bell_counts_as_the_close():
    assert price_due_at(_utc(2026, 11, 23, 20, 59, 58)) == _utc(2026, 11, 24, 15, 15)
