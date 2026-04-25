"""Smoke tests for composite scoring + hard gates + AI exposure."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from composite import (
    ai_exposure_score,
    passes_hard_gates,
    recurring_score,
    score_universe,
    winsorized_zscore,
)


def make_record(**overrides):
    """Healthy mid-cap stock with all the right ingredients."""
    base = {
        "symbol":          "TEST",
        "name":            "Test Corp",
        "sector":          "Industrials",
        "industry":        "Specialty Industrial Machinery",
        "summary":         "We make widgets for data center operators and hyperscalers.",
        "quote_type":      "EQUITY",
        "status":          "ok",
        "errors":          [],
        "price":           50.0,
        "market_cap":      4_000_000_000,
        "pe":              18.0,
        "forward_pe":      16.0,
        "pb":              3.0,
        "peg":             1.4,
        "ps":              2.0,
        "ev_ebitda":       12.0,
        "ev_sales":        2.5,
        "fcf_yield":       6.5,
        "earnings_yield_proxy": 0.083,
        "roe":             18.0,
        "roa":             10.0,
        "roic_proxy":      18.0,
        "gross_margin":    52.0,
        "op_margin":       18.0,
        "net_margin":      14.0,
        "fcf_margin":      15.0,
        "eps_growth":      14.0,
        "rev_growth":      11.0,
        "current_ratio":   2.1,
        "debt_equity":     0.4,
        "debt_to_ebitda":  1.8,
        "net_debt_to_ebitda": 1.5,
        "short_pct_float": 4.0,
        "beta":            1.1,
        "div_yield":       1.2,
        "payout_ratio":    20.0,
        "fcf":             400_000_000,
        "ebitda":          550_000_000,
        "net_income":      350_000_000,
        "operating_cf":    480_000_000,
        "total_debt":      900_000_000,
        "total_cash":      300_000_000,
        "revenue":         2_500_000_000,
        "ret_12m":         18.0,
        "ma_50":           48.0,
        "ma_200":          44.0,
        "proxy_notes":     ["earnings_yield_proxy=1/EV_EBITDA", "roic_proxy=ROE"],
        "fetched_at":      "2026-04-25T00:00:00Z",
    }
    base.update(overrides)
    return base


class TestHardGates:
    def test_healthy_passes(self):
        ok, reason = passes_hard_gates(make_record())
        assert ok, reason

    def test_too_small_mcap_rejected(self):
        ok, reason = passes_hard_gates(make_record(market_cap=100_000_000))
        assert not ok and "mcap" in reason

    def test_too_large_mcap_rejected(self):
        ok, reason = passes_hard_gates(make_record(market_cap=50_000_000_000))
        assert not ok and "mcap" in reason

    def test_weak_liquidity_rejected(self):
        ok, reason = passes_hard_gates(make_record(current_ratio=0.7))
        assert not ok and reason == "weak_liquidity"

    def test_over_leveraged_rejected(self):
        ok, reason = passes_hard_gates(make_record(debt_to_ebitda=8.0))
        assert not ok and reason == "over_leveraged"

    def test_meme_short_interest_rejected(self):
        ok, reason = passes_hard_gates(make_record(short_pct_float=35.0))
        assert not ok and reason == "meme_short_interest"

    def test_no_cash_generation_rejected(self):
        ok, reason = passes_hard_gates(make_record(fcf=-1, operating_cf=-1))
        assert not ok and reason == "no_cash_generation"

    def test_failed_status_rejected(self):
        ok, reason = passes_hard_gates(make_record(status="failed"))
        assert not ok and reason == "fetch_failed"

    def test_non_equity_rejected(self):
        ok, reason = passes_hard_gates(make_record(quote_type="ETF"))
        assert not ok and "quote_type" in reason


class TestAIExposure:
    def test_industry_match_scores(self):
        rec = make_record(industry="Semiconductor Equipment & Materials", summary="")
        score, evidence = ai_exposure_score(rec)
        assert score >= 35
        assert any("industry:" in e for e in evidence)

    def test_keyword_match_scores(self):
        rec = make_record(
            industry="Specialty Industrial Machinery",
            summary="We design liquid cooling systems and power management equipment for hyperscale data centers.",
        )
        score, evidence = ai_exposure_score(rec)
        assert score > 25
        kws = [e for e in evidence if e.startswith("kw:")]
        assert len(kws) >= 2

    def test_zero_exposure_for_unrelated(self):
        rec = make_record(
            industry="Restaurants",
            summary="We operate quick-service restaurants in the southeastern United States.",
        )
        score, _ = ai_exposure_score(rec)
        assert score == 0


class TestRecurringScore:
    def test_software_subscription_high(self):
        assert recurring_score(make_record(industry="Software—Application")) >= 85
        assert recurring_score(make_record(industry="Software—Infrastructure")) >= 85

    def test_high_gross_margin_partial_credit(self):
        rec = make_record(industry="Specialty Retail", gross_margin=72.0)
        assert recurring_score(rec) >= 40

    def test_default_low(self):
        rec = make_record(industry="Restaurants", gross_margin=20.0)
        assert recurring_score(rec) <= 30


class TestZscore:
    def test_higher_is_better_ranking(self):
        out = winsorized_zscore([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                                higher_is_better=True)
        assert out[0] < out[-1]

    def test_lower_is_better_ranking(self):
        out = winsorized_zscore([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                                higher_is_better=False)
        assert out[0] > out[-1]

    def test_missing_returns_neutral(self):
        out = winsorized_zscore([None, 1.0, 2.0, 3.0, 4.0, 5.0], higher_is_better=True)
        assert out[0] == 50.0

    def test_few_values_all_neutral(self):
        out = winsorized_zscore([1.0, 2.0], higher_is_better=True)
        assert all(v == 50.0 for v in out)


class TestScoreUniverse:
    def test_filters_and_scores(self):
        records = [
            make_record(symbol="HEALTHY"),
            make_record(symbol="WEAK", current_ratio=0.5),  # gated out
            make_record(symbol="MEME", short_pct_float=35.0),  # gated out
            make_record(symbol="LARGE", market_cap=50_000_000_000),  # gated out
        ]
        out = score_universe(records)
        assert len(out) == 1
        assert out[0]["symbol"] == "HEALTHY"
        assert "composite_score" in out[0]
        assert "factors" in out[0]

    def test_factor_keys_present(self):
        out = score_universe([make_record()])
        assert set(out[0]["factors"]) == {
            "quality", "valuation", "profitability", "risk", "recurring", "ai_exposure"
        }

    def test_results_sorted_desc(self):
        records = [
            make_record(symbol="LO", roic_proxy=2, gross_margin=15, ev_ebitda=40, fcf_yield=0.5),
            make_record(symbol="HI", roic_proxy=35, gross_margin=70, ev_ebitda=8,  fcf_yield=10),
            make_record(symbol="MID", roic_proxy=15, gross_margin=40, ev_ebitda=20, fcf_yield=4),
        ]
        out = score_universe(records)
        # LO and HI both pass gates; HI should rank above LO.
        scores = {r["symbol"]: r["composite_score"] for r in out}
        assert scores["HI"] > scores["LO"]
