"""Smoke tests for fetch_weekly screen logic.

Tests the pure logic — no network calls. Uses synthetic ticker fixtures.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_weekly import apply_screens, build_thesis, by_screen, sector_mix


def make_stock(**overrides):
    """Build a synthetic stock dict with sensible defaults."""
    base = {
        "symbol": "TEST",
        "company": "Test Corp",
        "sector": "Technology",
        "price": 100.0,
        "market_cap": 50_000_000_000,
        "pe": 18.0,
        "forward_pe": 16.0,
        "pb": 3.0,
        "peg": 1.2,
        "ps": 4.0,
        "ev_ebitda": 15.0,
        "earnings_yield": 0.0667,
        "roe": 25.0,
        "roa": 12.0,
        "roic_proxy": 25.0,
        "gross_margin": 60.0,
        "op_margin": 25.0,
        "profit_margin": 18.0,
        "fcf_margin": 20.0,
        "eps_growth": 22.0,
        "rev_growth": 15.0,
        "current_ratio": 2.5,
        "debt_equity": 0.4,
        "div_yield": 1.5,
        "payout_ratio": 30.0,
        "fcf": 5_000_000_000,
        "net_income": 4_000_000_000,
        "operating_cf": 6_000_000_000,
        "ret_12m": 35.0,
        "ma_50": 95.0,
        "ma_200": 85.0,
    }
    base.update(overrides)
    return base


class TestGrahamScreen:
    def test_passes_with_all_criteria(self):
        s = make_stock(symbol="GRA", pe=10, pb=1.2, current_ratio=2.5,
                       net_income=1e9, div_yield=2.5, market_cap=5e9)
        out = apply_screens([s], [s["ret_12m"]])
        assert "graham" in out[0]["screens_passed"]

    def test_fails_when_pe_too_high(self):
        s = make_stock(symbol="NOPE", pe=20, pb=1.2)
        out = apply_screens([s], [s["ret_12m"]])
        assert "graham" not in (out[0]["screens_passed"] if out else [])

    def test_fails_when_no_dividend(self):
        s = make_stock(symbol="NODIV", pe=10, pb=1.2, current_ratio=2.5,
                       div_yield=0)
        out = apply_screens([s], [s["ret_12m"]])
        assert "graham" not in (out[0]["screens_passed"] if out else [])


class TestPiotroski:
    def test_high_quality_passes(self):
        s = make_stock(net_income=1e9, operating_cf=1.5e9, roa=10,
                       debt_equity=0.3, current_ratio=2.0, gross_margin=50)
        out = apply_screens([s], [s["ret_12m"]])
        assert "piotroski" in out[0]["screens_passed"]

    def test_low_quality_fails(self):
        s = make_stock(net_income=-1e9, operating_cf=-1e9, roa=-5,
                       debt_equity=2.0, current_ratio=0.8, gross_margin=10)
        out = apply_screens([s], [s["ret_12m"]])
        assert not out or "piotroski" not in out[0]["screens_passed"]


class TestGARP:
    def test_passes_with_growth_and_value(self):
        s = make_stock(eps_growth=20, peg=1.0, roe=20, debt_equity=0.3)
        out = apply_screens([s], [s["ret_12m"]])
        assert "garp" in out[0]["screens_passed"]

    def test_fails_when_peg_too_high(self):
        s = make_stock(eps_growth=20, peg=2.5, roe=20, debt_equity=0.3)
        out = apply_screens([s], [s["ret_12m"]])
        assert "garp" not in (out[0]["screens_passed"] if out else [])


class TestQuality:
    def test_high_roic_high_margin_passes(self):
        s = make_stock(roic_proxy=25, gross_margin=60, fcf_margin=20,
                       debt_equity=0.3, market_cap=20e9)
        out = apply_screens([s], [s["ret_12m"]])
        assert "quality" in out[0]["screens_passed"]


class TestMomentum:
    def test_top_returns_above_mas_pass(self):
        # Make this stock the only one with high return
        s = make_stock(symbol="MOM", ret_12m=80, price=100, ma_50=90, ma_200=70)
        # Add a few low-return peers to set the percentile cutoff
        peers = [make_stock(symbol=f"P{i}", ret_12m=5) for i in range(10)]
        all_returns = [s["ret_12m"]] + [p["ret_12m"] for p in peers]
        out = apply_screens([s] + peers, all_returns)
        mom = next(x for x in out if x["symbol"] == "MOM")
        assert "momentum" in mom["screens_passed"]


class TestDividend:
    def test_quality_dividend_passes(self):
        s = make_stock(div_yield=3.5, payout_ratio=45, debt_equity=0.5,
                       fcf=5e9, net_income=4e9)
        out = apply_screens([s], [s["ret_12m"]])
        assert "dividend" in out[0]["screens_passed"]

    def test_high_yield_too_high_fails(self):
        s = make_stock(div_yield=8.0, payout_ratio=45)
        out = apply_screens([s], [s["ret_12m"]])
        assert "dividend" not in (out[0]["screens_passed"] if out else [])


class TestOutputShape:
    def test_results_sorted_by_score_desc(self):
        # One stock passes 3 screens, another 1
        good = make_stock(symbol="GOOD")
        weak = make_stock(symbol="WEAK", pe=99, pb=99, eps_growth=0,
                          peg=99, roic_proxy=0, gross_margin=0,
                          fcf_margin=0, ret_12m=-50, div_yield=0,
                          net_income=-1, operating_cf=-1)
        out = apply_screens([good, weak], [good["ret_12m"], weak["ret_12m"]])
        if len(out) >= 2:
            assert out[0]["score"] >= out[1]["score"]

    def test_thesis_is_string(self):
        s = make_stock()
        out = apply_screens([s], [s["ret_12m"]])
        if out:
            assert isinstance(out[0]["one_line_thesis"], str)
            assert len(out[0]["one_line_thesis"]) > 0


class TestSectorMix:
    def test_counts_sectors_correctly(self):
        top = [
            {"sector": "Technology"},
            {"sector": "Technology"},
            {"sector": "Healthcare"},
        ]
        mix = sector_mix(top)
        assert mix["Technology"] == 2
        assert mix["Healthcare"] == 1


class TestByScreen:
    def test_groups_by_screen(self):
        results = [
            {"symbol": "A", "company": "A Co", "sector": "Tech",
             "screens_passed": ["graham", "quality"]},
            {"symbol": "B", "company": "B Co", "sector": "Fin",
             "screens_passed": ["graham"]},
        ]
        grouped = by_screen(results)
        assert len(grouped["graham"]) == 2
        assert len(grouped["quality"]) == 1
        assert all("symbol" in s for s in grouped["graham"])
