"""Validate the weekly_screens.json output is healthy under the new
composite-scoring pipeline."""
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
        assert os.path.exists(path), "weekly_screens.json missing — run python fetch_weekly.py"
        with open(path) as f:
            return json.load(f)

    def test_has_required_keys(self, data):
        for key in ["last_updated", "universe", "scoring", "top_conviction"]:
            assert key in data

    def test_top_conviction_non_empty(self, data):
        assert isinstance(data["top_conviction"], list)
        assert len(data["top_conviction"]) > 0, \
            "top_conviction is empty — yfinance likely throttled the run"

    def test_factor_keys_canonical(self, data):
        canonical = {"quality", "valuation", "profitability",
                     "risk", "recurring", "ai_exposure"}
        for stock in data["top_conviction"]:
            assert set(stock["factors"].keys()) == canonical

    def test_composite_score_in_range(self, data):
        for stock in data["top_conviction"]:
            assert 0 <= stock["composite_score"] <= 100

    def test_factor_scores_in_range(self, data):
        for stock in data["top_conviction"]:
            for factor, score in stock["factors"].items():
                assert 0 <= score <= 100, f"{stock['symbol']} {factor}={score} out of range"

    def test_proxies_disclosed(self, data):
        # The new pipeline must explicitly label its proxy approximations.
        assert "proxies_used" in data["scoring"]

    def test_results_sorted_desc(self, data):
        scores = [s["composite_score"] for s in data["top_conviction"]]
        assert scores == sorted(scores, reverse=True)
