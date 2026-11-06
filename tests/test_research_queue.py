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
    return {"ticker": ticker, "verdict": "WATCHLIST", "research_file": "x.md", "last_researched": date}


def test_name_researched_today_is_not_requeued_for_a_dip(tmp_path, monkeypatch):
    assert _queue(tmp_path, monkeypatch, [_candidate("AMD", 0)], {"AMD": -40}) == []


def test_old_research_on_a_dipping_name_is_queued(tmp_path, monkeypatch):
    assert _queue(tmp_path, monkeypatch, [_candidate("AMD", 4)], {"AMD": -40}) == ["AMD"]


def test_stale_name_beats_recently_researched_dip(tmp_path, monkeypatch):
    candidates = [_candidate("AMD", 1), _candidate("AAPL", 90)]
    assert _queue(tmp_path, monkeypatch, candidates, {"AMD": -40, "AAPL": -5}) == ["AAPL"]
