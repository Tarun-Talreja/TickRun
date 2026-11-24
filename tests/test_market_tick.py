"""The relay must start the loop before the open and leave it alone when the market is shut."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from market_tick import active, needs_loop


def utc(*a):
    return datetime(2026, 11, *a, tzinfo=timezone.utc)


def test_before_and_during_the_session():
    assert needs_loop(utc(25, 13, 40)) and needs_loop(utc(25, 16, 0)) and needs_loop(utc(25, 21, 5))


def test_not_at_night_weekend_or_holiday():
    assert not needs_loop(utc(25, 5, 0)) and not needs_loop(utc(25, 21, 30))
    assert not needs_loop(utc(26, 16, 0)) and not needs_loop(utc(28, 16, 0))


def test_queued_counts_as_active():
    assert active([{"status": "queued"}]) and not active([{"status": "completed"}]) and not active([])
