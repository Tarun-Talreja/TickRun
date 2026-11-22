"""The buy-below price must come from the business's cash and earnings, never from the 52-week high."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from valuation import (MARGIN_OF_SAFETY, cash_flow_is_distorted, combine, dcf_per_share,
                       discount_rate, growth_rate, implied_growth, is_cyclical, normalised_margin,
                       terminal_share)


class TestDcf:
    def test_no_growth_is_a_mid_year_perpetuity(self):
        # 0% forever at 10% is 10x the cash flow; arriving mid-year adds half a year's return.
        assert dcf_per_share(1.0, growth=0.0, rate=0.10, terminal=0.0) == pytest.approx(10 * 1.1 ** 0.5, rel=1e-6)

    def test_terminal_share_is_a_fraction_of_the_total(self):
        assert 0.4 < terminal_share(1.0, 0.05, 0.09) < 0.8

    def test_more_growth_is_worth_more(self):
        assert dcf_per_share(1.0, 0.10, 0.09) > dcf_per_share(1.0, 0.03, 0.09)

    def test_implied_growth_inverts_the_value(self):
        value = dcf_per_share(2.0, growth=0.08, rate=0.09)
        assert implied_growth(value, 2.0, rate=0.09) == pytest.approx(0.08, abs=1e-3)

    def test_no_implied_growth_without_positive_cash(self):
        assert implied_growth(100, -1.0, rate=0.09) is None


class TestInputs:
    def test_growth_is_capped(self):
        assert growth_rate({"2021": 10, "2026": 100}) == 0.15

    def test_shrinking_revenue_counts_as_no_growth(self):
        assert growth_rate({"2021": 100, "2026": 80}) == 0.0

    def test_growth_needs_three_years(self):
        assert growth_rate({"2025": 100, "2026": 110}) is None

    def test_normalised_margin_uses_recent_years_and_ttm(self):
        values = {"2022": 90, "2023": 10, "2024": 20, "2025": 30}
        revenue = {"2022": 100, "2023": 100, "2024": 100, "2025": 100}
        assert normalised_margin(values, revenue, 3, ttm=40, ttm_revenue=100) == pytest.approx(0.25)

    def test_cyclical_uses_more_years(self):
        values = {"2022": 90, "2023": 10, "2024": 20, "2025": 30}
        revenue = {y: 100 for y in values}
        assert normalised_margin(values, revenue, 6) == pytest.approx(0.375)

    def test_margin_not_dollars_so_growth_is_not_punished(self):
        # A company that grew 10x at a steady 20% margin normalises to 20%, not a tiny average.
        assert normalised_margin({"2023": 2, "2024": 8, "2025": 20}, {"2023": 10, "2024": 40, "2025": 100}, 3) \
            == pytest.approx(0.2)

    def test_cyclical_when_a_year_lost_money_or_margins_swing(self):
        revenue = {"2021": 100, "2022": 100, "2023": 100}
        assert is_cyclical({"2021": 30, "2022": -5, "2023": 25}, revenue)
        assert is_cyclical({"2021": 37, "2022": 16, "2023": 54}, revenue)
        assert not is_cyclical({"2021": 30, "2022": 28, "2023": 33}, revenue)

    def test_riskier_stocks_are_discounted_more(self):
        assert discount_rate(0.04, 1.6) > discount_rate(0.04, 1.0) > discount_rate(0.04, 0.8)

    def test_beta_is_clamped_and_defaults_to_average(self):
        assert discount_rate(0.04, 5.0) == 0.04 + 2.0 * 0.05
        assert discount_rate(0.04, None) == 0.09

    def test_cash_flow_distorted_when_negative_beside_a_profit(self):
        # CEG: operating cash flow -$5.3B in a year it earned $1.6B.
        assert cash_flow_is_distorted({"2023": -5.3, "2024": -2.5, "2025": 4.2},
                                      {"2023": 1.6, "2024": 3.75, "2025": 2.3})
        assert not cash_flow_is_distorted({"2024": 4.6, "2025": 4.1}, {"2024": 2.7, "2025": 0.9})


class TestCombine:
    def test_buy_below_is_base_value_less_the_margin(self):
        out = combine({"cash_flow": 100.0, "own_multiple": 120.0}, price=90.0)
        assert out["status"] == "ok"
        assert out["base"] == 110.0 and out["low"] == 100.0 and out["high"] == 120.0
        assert out["buy_below"] == round(110.0 * (1 - MARGIN_OF_SAFETY), 2)

    def test_one_method_is_not_enough(self):
        out = combine({"cash_flow": 100.0, "own_multiple": None}, price=90.0)
        assert out["status"] == "no_reliable_price" and out["buy_below"] is None

    def test_methods_that_disagree_give_no_price(self):
        out = combine({"cash_flow": 40.0, "own_multiple": 160.0}, price=90.0)
        assert out["status"] == "no_reliable_price" and "disagree" in out["reason"]

    def test_data_problems_block_the_price(self):
        out = combine({"cash_flow": 100.0, "own_multiple": 110.0}, price=90.0,
                      problems=["SEC and Yahoo revenue differ by 30%"])
        assert out["status"] == "no_reliable_price" and "30%" in out["reason"]


class TestValueTicker:
    TODAY = __import__("datetime").date(2026, 11, 22)

    def _record(self, **over):
        years = {"2023-12-31": 0, "2024-12-31": 0, "2025-12-31": 0}
        annual = {
            "revenue": {"2021-12-31": 50, "2023-12-31": 70, "2025-12-31": 100},
            "operating_cash_flow": {y: 30 for y in years}, "capex": {y: 10 for y in years},
            "stock_comp": {y: 2 for y in years},
            "net_income": {"2021-12-31": 10, "2022-12-31": 12, "2023-12-31": 15, "2024-12-31": 15, "2025-12-31": 15},
            "diluted_shares": {y: 10 for y in ("2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31")},
            "operating_income": {"2023-12-31": 20, "2024-12-31": 21, "2025-12-31": 22},
        }
        ttm = {"revenue": {"end": "2026-09-30", "value": 105},
               "operating_cash_flow": {"end": "2026-09-30", "value": 30},
               "capex": {"end": "2026-09-30", "value": 10}, "stock_comp": {"end": "2026-09-30", "value": 2},
               "net_income": {"end": "2026-09-30", "value": 15},
               "diluted_shares": {"end": "2026-09-30", "value": 10}}
        return {"annual": {**annual, **over.pop("annual", {})}, "ttm": {**ttm, **over.pop("ttm", {})}}

    PRICES = {"2021-12-31": 20.0, "2022-12-31": 24.0, "2023-12-31": 30.0,
              "2024-12-31": 30.0, "2025-12-31": 30.0}

    def test_prices_a_healthy_company(self):
        from valuation import value_ticker
        out = value_ticker(self._record(), {"price": 40.0, "revenue_ttm": 104}, self.PRICES, 0.042,
                           self.TODAY, beta=1.2)
        assert out["status"] == "ok" and out["buy_below"] == round(out["base"] * 0.75, 2)
        assert out["inputs"]["median_past_pe"] == 20.0
        assert out["inputs"]["discount_rate"] == 0.102 and not out["inputs"]["cyclical"]

    def test_missing_beta_is_said(self):
        from valuation import value_ticker
        out = value_ticker(self._record(), {"price": 20.0}, self.PRICES, 0.042, self.TODAY)
        assert any("beta" in n for n in out["notes"])

    def test_stale_figures_block_the_price(self):
        from valuation import value_ticker
        rec = self._record(ttm={"revenue": {"end": "2025-12-31", "value": 100}})
        out = value_ticker(rec, {"price": 20.0}, self.PRICES, 0.042, self.TODAY)
        assert out["status"] == "no_reliable_price" and "days old" in out["reason"]

    def test_sec_and_yahoo_disagreeing_blocks_the_price(self):
        from valuation import value_ticker
        out = value_ticker(self._record(), {"price": 20.0, "revenue_ttm": 160}, self.PRICES, 0.042, self.TODAY)
        assert "differ by" in out["reason"]

    def test_distorted_cash_flow_leaves_one_method(self):
        from valuation import value_ticker
        rec = self._record(annual={"operating_cash_flow": {"2023-12-31": -5, "2024-12-31": 30, "2025-12-31": 30}})
        out = value_ticker(rec, {"price": 20.0}, self.PRICES, 0.042, self.TODAY)
        assert out["status"] == "no_reliable_price" and out["notes"]

    def test_foreign_filer_gets_no_price(self):
        from valuation import value_ticker
        out = value_ticker({"annual": {}, "ttm": {}}, {"price": 20.0}, {}, 0.042, self.TODAY)
        assert "foreign" in out["reason"]


def test_no_buy_price_when_the_market_expects_decline():
    out = combine({"cash_flow": 70.0, "own_multiple": 50.0}, price=25.0, implied=-0.18)
    assert out["status"] == "market_expects_decline" and out["buy_below"] is None
    assert "shrink" in out["reason"]


def test_eps_from_profit_and_shares_when_the_eps_field_stopped():
    from valuation import eps_by_year
    assert eps_by_year({"2025": 100.0, "2024": 80.0}, {"2025": 50.0, "2024": 40.0}) == {"2024": 2.0, "2025": 2.0}


class TestCompanyMeasure:
    TODAY = __import__("datetime").date(2026, 11, 22)
    ENTRY = {"filed": "2026-11-06", "url": "u",
             "measure": {"name": "Adjusted FCF", "kind": "cash_flow_total", "low": 4.3e9, "high": 4.7e9,
                         "mid": 4.5e9, "quote": "q"}}

    def test_values_on_the_company_figure_with_one_method(self):
        from valuation import TERMINAL_GROWTH, dcf_per_share, value_from_measure
        out = value_from_measure(self.ENTRY, shares=3.4e8, price=160.0, rate=0.118, today=self.TODAY)
        expected = dcf_per_share(4.5e9 / 3.4e8, TERMINAL_GROWTH, 0.118)
        assert out["status"] == "ok" and out["base"] == round(expected, 2)
        assert out["inputs"]["growth_used"] == TERMINAL_GROWTH

    def test_price_below_the_no_growth_value_is_flagged(self):
        from valuation import value_from_measure
        out = value_from_measure(self.ENTRY, shares=3.4e8, price=115.0, rate=0.118, today=self.TODAY)
        assert out["status"] == "market_expects_decline"

    def test_earnings_per_share_is_used_as_is(self):
        from valuation import value_from_measure
        entry = {**self.ENTRY, "measure": {**self.ENTRY["measure"], "kind": "earnings_per_share", "mid": 12.65}}
        out = value_from_measure(entry, shares=None, price=150.0, rate=0.105, today=self.TODAY)
        assert out["inputs"]["per_share"] == 12.65

    def test_missing_figure_gives_no_price(self):
        from valuation import value_from_measure
        out = value_from_measure({"filed": "2026-11-06", "measure": None}, 3.4e8, 115.0, 0.118, self.TODAY)
        assert out["status"] == "no_reliable_price" and "wasn't found" in out["reason"]

    def test_old_release_gives_no_price(self):
        from valuation import value_from_measure
        out = value_from_measure({**self.ENTRY, "filed": "2026-05-01"}, 3.4e8, 115.0, 0.118, self.TODAY)
        assert "too old" in out["reason"]


class TestFairMultiple:
    def test_slow_growth_caps_a_rich_history(self):
        from valuation import fair_multiple
        # MKTX-like: 31x history, 3.6% growth now, 8.91% required return.
        pe, why = fair_multiple([28.0, 31.1, 34.0], g_now=0.036, rate=0.0891)
        assert pe == pytest.approx(1.036 / (0.0891 - 0.036)) and "ceiling" in why

    def test_fast_growth_is_still_capped(self):
        from valuation import GROWTH_GAP, fair_multiple
        # TW-like: 53x history; 19% growth is capped 3 points below the rate.
        pe, _ = fair_multiple([50.0, 53.0, 60.0], g_now=0.19, rate=0.0891)
        assert pe == pytest.approx((1 + 0.0891 - GROWTH_GAP) / GROWTH_GAP)

    def test_modest_history_is_kept(self):
        from valuation import fair_multiple
        assert fair_multiple([14.0, 15.0, 16.0], g_now=0.06, rate=0.10) == (15.0, None)

    def test_unknown_growth_uses_the_widest_ceiling(self):
        from valuation import GROWTH_GAP, fair_multiple
        pe, _ = fair_multiple([50.0, 53.0, 60.0], g_now=None, rate=0.10)
        assert pe == pytest.approx((1 + 0.10 - GROWTH_GAP) / GROWTH_GAP)

    def test_needs_three_years(self):
        from valuation import fair_multiple
        assert fair_multiple([20.0, 25.0], 0.05, 0.09) == (None, None)

    def test_latest_growth(self):
        from valuation import latest_growth
        assert latest_growth({"2023": 100, "2024": 110, "2025": 121}) == pytest.approx(0.1)
        assert latest_growth({"2025": 121}) is None
