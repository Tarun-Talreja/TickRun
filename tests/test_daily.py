"""Smoke tests for fetch_daily logic and output validity.

Network-free unit tests + a JSON schema validation pass on the committed output.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_daily import compute_flags, read_watchlist


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestComputeFlags:
    def test_big_move_flagged(self):
        tickers = [{"symbol": "X", "change_pct_1d": 7.0, "rsi_14": 50}]
        flags = compute_flags(tickers)
        assert any(f["type"] == "big_move" for f in flags)

    def test_small_move_not_flagged(self):
        tickers = [{"symbol": "X", "change_pct_1d": 1.0, "rsi_14": 50}]
        flags = compute_flags(tickers)
        assert not any(f["type"] == "big_move" for f in flags)

    def test_rsi_overbought_flagged(self):
        tickers = [{"symbol": "X", "change_pct_1d": 0.5, "rsi_14": 78}]
        flags = compute_flags(tickers)
        assert any(f["type"] == "rsi_extreme" for f in flags)

    def test_rsi_oversold_flagged(self):
        tickers = [{"symbol": "X", "change_pct_1d": 0.5, "rsi_14": 22}]
        flags = compute_flags(tickers)
        assert any(f["type"] == "rsi_extreme" for f in flags)

    def test_rsi_neutral_not_flagged(self):
        tickers = [{"symbol": "X", "change_pct_1d": 0.5, "rsi_14": 50}]
        flags = compute_flags(tickers)
        assert not any(f["type"] == "rsi_extreme" for f in flags)

    def test_handles_none_values(self):
        tickers = [{"symbol": "X", "change_pct_1d": None, "rsi_14": None,
                    "next_earnings": None}]
        # Should not raise
        flags = compute_flags(tickers)
        assert isinstance(flags, list)


class TestWatchlist:
    def test_reads_tickers(self):
        tickers = read_watchlist()
        assert isinstance(tickers, list)
        assert len(tickers) > 0
        assert all(isinstance(t, str) for t in tickers)

    def test_skips_comments_and_blanks(self):
        tickers = read_watchlist()
        for t in tickers:
            assert not t.startswith("#")
            assert t.strip() == t


class TestDailyOutput:
    """Validate the live output file matches expected shape."""

    def test_output_exists_and_valid_json(self):
        path = os.path.join(ROOT, "output", "daily.json")
        assert os.path.exists(path), "daily.json missing"
        with open(path) as f:
            data = json.load(f)
        assert "last_updated" in data
        assert "tickers" in data
        assert isinstance(data["tickers"], list)

    def test_all_tickers_have_symbol(self):
        path = os.path.join(ROOT, "output", "daily.json")
        with open(path) as f:
            data = json.load(f)
        for t in data["tickers"]:
            assert t.get("symbol"), f"Ticker missing symbol: {t}"
