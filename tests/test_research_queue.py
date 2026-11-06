"""A selloff must not let the same falling names take every research slot."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import research_batch


def _queue(tmp_path, monkeypatch, candidates, drawdowns, max_n=8):
    watchlist, quotes = tmp_path / "w.json", tmp_path / "q.json"
    watchlist.write_text(json.dumps({"candidates": candidates}))
    quotes.write_text(json.dumps({"tickers": {t: {"drawdown_from_high": d} for t, d in drawdowns.items()}}))
    monkeypatch.setattr(research_batch, "WATCHLIST_PATH", str(watchlist))
    monkeypatch.setattr(research_batch, "QUOTES_PATH", str(quotes))
    return research_batch._select_tickers(max_n)


def _candidate(ticker, days_ago):
    date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    return {"ticker": ticker, "verdict": "WATCHLIST", "research_file": "x.md", "last_researched": date,
            "rating_version": research_batch.RATING_VERSION}


def test_name_researched_today_is_not_requeued_for_a_dip(tmp_path, monkeypatch):
    assert _queue(tmp_path, monkeypatch, [_candidate("AMD", 0)], {"AMD": -40}) == []


def test_old_research_on_a_dipping_name_is_queued(tmp_path, monkeypatch):
    assert _queue(tmp_path, monkeypatch, [_candidate("AMD", 4)], {"AMD": -40}) == ["AMD"]


def test_stale_name_beats_recently_researched_dip(tmp_path, monkeypatch):
    candidates = [_candidate("AMD", 1), _candidate("AAPL", 90)]
    assert _queue(tmp_path, monkeypatch, candidates, {"AMD": -40, "AAPL": -5}) == ["AAPL"]


def _rated(ticker, days_ago, verdict="WATCHLIST", version=None):
    version = research_batch.RATING_VERSION if version is None else version
    return {**_candidate(ticker, days_ago), "verdict": verdict, "rating_version": version}


def test_rating_from_old_logic_is_requeued_even_if_fresh(tmp_path, monkeypatch):
    old = _rated("NVDA", 0, version=research_batch.RATING_VERSION - 1)
    assert _queue(tmp_path, monkeypatch, [old], {}) == ["NVDA"]


def test_missing_version_counts_as_old(tmp_path, monkeypatch):
    unversioned = {k: v for k, v in _candidate("NVDA", 0).items() if k != "rating_version"}
    assert _queue(tmp_path, monkeypatch, [unversioned], {}) == ["NVDA"]


def test_old_logic_outranks_ordinary_staleness(tmp_path, monkeypatch):
    candidates = [_rated("AAPL", 30), _rated("NVDA", 0, version=0)]
    assert _queue(tmp_path, monkeypatch, candidates, {}, max_n=1) == ["NVDA"]


def test_pass_and_red_flag_on_old_logic_are_requeued(tmp_path, monkeypatch):
    candidates = [_rated("X", 0, "PASS", 0), _rated("MU", 0, "RED FLAG", 0)]
    assert sorted(_queue(tmp_path, monkeypatch, candidates, {})) == ["MU", "X"]


def test_pass_waits_a_month_for_a_second_look(tmp_path, monkeypatch):
    assert _queue(tmp_path, monkeypatch, [_rated("X", 20, "PASS")], {}) == []
    assert _queue(tmp_path, monkeypatch, [_rated("X", 31, "PASS")], {}) == ["X"]


def test_red_flag_is_rechecked_weekly(tmp_path, monkeypatch):
    assert _queue(tmp_path, monkeypatch, [_rated("MU", 8, "RED FLAG")], {}) == ["MU"]


def test_benchmarks_are_never_queued(tmp_path, monkeypatch):
    assert _queue(tmp_path, monkeypatch, [_rated("SPY", 0, version=0), _rated("^TNX", 0, version=0)], {}) == []


def test_wrongly_held_back_names_go_first(tmp_path, monkeypatch):
    held = {**_rated("NVDA", 0, version=0), "bear_downgraded": True}
    flagged = _rated("MU", 0, "RED FLAG", 0)
    plain = _rated("AAPL", 30, version=0)
    assert sorted(_queue(tmp_path, monkeypatch, [plain, held, flagged], {}, max_n=2)) == ["MU", "NVDA"]


def test_stops_after_repeated_total_failures():
    assert not research_batch.models_look_down(research_batch.MAX_FAILS_IN_A_ROW - 1)
    assert research_batch.models_look_down(research_batch.MAX_FAILS_IN_A_ROW)
