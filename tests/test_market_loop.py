"""Refreshes must cover the whole session and only the session."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from market_loop import RUN_LIMIT, step, window


def utc(*a):
    return datetime(2026, 11, *a, tzinfo=timezone.utc)


def test_refreshes_during_the_session():
    now = utc(24, 16, 0)
    assert step(now, now) == ("refresh", 900)


def test_waits_for_the_open_only_if_it_can_last():
    now = utc(24, 13, 32)
    assert step(now, now) == ("wait", 3600)
    assert step(utc(24, 7, 0), utc(24, 7, 0))[0] == "stop"


def test_closing_price_is_fetched_then_it_stops():
    now = utc(24, 21, 5)
    action, seconds = step(now, now)
    assert action == "refresh" and 60 <= seconds <= 420
    assert step(utc(24, 21, 13), now)[0] == "stop"


def test_shut_days_and_early_close():
    assert window(utc(26, 16, 0)) is None and window(utc(28, 16, 0)) is None
    assert step(utc(27, 18, 30), utc(27, 18, 0))[0] == "stop"


def test_hands_over_before_the_limit():
    now = utc(24, 20, 45)
    assert step(now, now - RUN_LIMIT - timedelta(minutes=1))[0] == "hand_over"


def test_summer_time():
    now = datetime(2026, 7, 14, 13, 40, tzinfo=timezone.utc)
    assert step(now, now)[0] == "refresh"


def test_waiting_run_keeps_going_when_the_open_comes():
    assert step(utc(24, 14, 33), utc(24, 13, 0))[0] == "refresh"
