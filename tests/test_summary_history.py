"""A missed summary must still be readable, and a day's changes must not vanish within the day."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from daily_brief import baseline
from summary_history import KEPT_DAYS, with_changes, with_summary


def test_latest_summary_wins_and_other_days_stay():
    days = with_summary({"2026-11-20": {"narrative": "old"}}, "2026-11-23", "noon", "t1")
    days = with_summary(days, "2026-11-23", "close", "t2")
    assert days["2026-11-23"]["narrative"] == "close" and days["2026-11-20"]["narrative"] == "old"


def test_changes_add_up_without_repeats_or_moves():
    a = {"kind": "verdict_change", "headline": "A changed"}
    b = {"kind": "sec_stake", "headline": "B filed", "detail": "x"}
    move = {"kind": "mover", "headline": "NVDA +31%"}
    days = with_changes(with_changes({}, "d", [a, move]), "d", [a, b])
    assert [c["headline"] for c in days["d"]["changes"]] == ["A changed", "B filed"]


def test_summary_keeps_the_days_changes():
    days = with_changes({}, "d", [{"kind": "sec_stake", "headline": "B"}])
    assert with_summary(days, "d", "n", "t")["d"]["changes"]


def test_old_days_are_dropped():
    days = {}
    for n in range(KEPT_DAYS + 5):
        days = with_summary(days, f"2026-{n:04d}", "n", "t")
    assert len(days) == KEPT_DAYS and "2026-0000" not in days


def test_baseline_is_kept_all_day():
    yesterday = {"verdicts": {"A": "PASS"}, "day": "2026-11-23", "base": {"verdicts": {}}}
    base = baseline(yesterday, "2026-11-24")
    assert base["verdicts"] == {"A": "PASS"} and "base" not in base
    later = {"verdicts": {"A": "WATCHLIST"}, "day": "2026-11-24", "base": base}
    assert baseline(later, "2026-11-24") == base


def test_baseline_of_an_old_snapshot_without_a_day():
    assert baseline({"verdicts": {"A": "PASS"}}, "2026-11-24") == {"verdicts": {"A": "PASS"}}
    assert baseline({}, "2026-11-24") == {}
