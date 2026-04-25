"""Validate the weekly_screens.json output is healthy."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestWeeklyOutput:
    @pytest.fixture
    def data(self):
        path = os.path.join(ROOT, "output", "weekly_screens.json")
        assert os.path.exists(path), "weekly_screens.json missing"
        with open(path) as f:
            return json.load(f)

    def test_has_required_keys(self, data):
        for key in ["last_updated", "universe", "screens_run",
                    "top_conviction", "by_screen"]:
            assert key in data

    def test_top_conviction_is_list(self, data):
        assert isinstance(data["top_conviction"], list)

    def test_top_conviction_non_empty(self, data):
        # If this fails, the screener returned no picks → likely bad data
        assert len(data["top_conviction"]) > 0, \
            "top_conviction is empty — yfinance likely rate-limited"

    def test_screen_names_canonical(self, data):
        canonical = {"graham", "magic_formula", "piotroski", "garp",
                     "quality", "momentum", "dividend"}
        for stock in data["top_conviction"]:
            for s in stock["screens_passed"]:
                assert s in canonical, f"Unknown screen: {s}"

    def test_score_matches_screens_passed_count(self, data):
        for stock in data["top_conviction"]:
            assert stock["score"] == len(stock["screens_passed"])

    def test_universe_size_reasonable(self, data):
        # Should fetch 400+ S&P 500 stocks; flag if much lower
        # universe is a string like "S&P 500 (487 fetched)"
        import re
        m = re.search(r"\((\d+)\s+fetched\)", data["universe"])
        if m:
            n = int(m.group(1))
            assert n >= 100, f"Universe too small: {n} stocks fetched"
