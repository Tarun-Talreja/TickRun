"""Foreign filers report financials in a different currency than their US quote.

Fixtures are the real yfinance values for TSM (TWD) and ASML (EUR) on 2026-11-05,
when TSM's NT$4.9T revenue reached the research prompt labelled as dollars.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from data_sanity import _check_ticker
from refresh_quotes import _normalize_money
from research_ticker import _extract_thesis

TSM = {
    "currency": "USD", "financialCurrency": "TWD", "marketCap": 1831344013312,
    "totalRevenue": 4944817029120, "ebitda": 3611427078144,
    "freeCashflow": 1203071877120, "totalCash": 4016980099072,
    "totalDebt": 818380013568, "enterpriseToRevenue": 2.316, "enterpriseToEbitda": 3.171,
}
ASML = {
    "currency": "USD", "financialCurrency": "EUR", "marketCap": 522876977152,
    "totalRevenue": 39473500160, "ebitda": 16181000192,
    "freeCashflow": 10374124544, "totalCash": 12735099904,
    "totalDebt": 1963000064, "enterpriseToRevenue": 731.206, "enterpriseToEbitda": 1783.775,
}


class TestNormalizeMoney:
    def test_tsm_converted_to_usd(self):
        m = _normalize_money(TSM, 0.03036)
        assert m["revenue_ttm"] == pytest.approx(150.1e9, rel=0.01)
        assert m["fcf_ttm"] == pytest.approx(36.5e9, rel=0.01)
        assert m["total_cash"] - m["total_debt"] < TSM["marketCap"]
        assert m["financial_currency"] == "TWD" and m["fx_rate"] == 0.03036

    def test_yahoo_enterprise_multiples_are_recomputed(self):
        m = _normalize_money(ASML, 1.1202)
        assert m["ev_ebitda"] == pytest.approx(28.2, abs=0.2)

    def test_missing_fx_blanks_money_rather_than_mislabel_it(self):
        m = _normalize_money(TSM, None)
        for field in ("revenue_ttm", "fcf_ttm", "total_cash", "total_debt", "ev_ebitda"):
            assert m[field] is None
        assert m["fx_rate"] is None

    def test_usd_filer_keeps_yahoo_values(self):
        info = {**ASML, "financialCurrency": "USD"}
        m = _normalize_money(info, 1.0)
        assert m["revenue_ttm"] == ASML["totalRevenue"]
        assert m["ev_ebitda"] == ASML["enterpriseToEbitda"]

    def test_input_not_mutated(self):
        before = dict(TSM)
        _normalize_money(TSM, 0.03)
        assert TSM == before


class TestSanityFlags:
    base = {"price": 100, "high_52w": 120, "low_52w": 80}

    def _msgs(self, **q):
        return " ".join(f["msg"] for f in _check_ticker("X", {**self.base, **q}))

    def test_net_cash_above_market_cap_flagged(self):
        assert "market cap" in self._msgs(total_cash=4e12, total_debt=8e11, market_cap=1.8e12)

    def test_absurd_ev_ebitda_flagged(self):
        assert "EV/EBITDA" in self._msgs(ev_ebitda=1783.8)

    def test_foreign_filer_gets_pe_caution(self):
        assert "EUR" in self._msgs(currency="USD", financial_currency="EUR", fx_rate=1.12)

    def test_missing_fx_flagged_high(self):
        flags = _check_ticker("X", {**self.base, "currency": "USD",
                                    "financial_currency": "EUR", "fx_rate": None})
        assert any(f["level"] == "high" for f in flags)

    def test_clean_usd_filer_not_flagged(self):
        assert not _check_ticker("X", {**self.base, "currency": "USD", "financial_currency": "USD",
                                       "fx_rate": 1.0, "total_cash": 5e9, "total_debt": 1e9,
                                       "market_cap": 1e11, "ev_ebitda": 20})


class TestThesisScrub:
    def test_aggregate_dollar_amounts_survive(self):
        t = _extract_thesis("THESIS: Growing fast with $92B FCF and $1.5 trillion backlog.")
        assert "$92B" in t and "$1.5 trillion" in t and "omitted" not in t

    def test_share_price_is_still_removed(self):
        t = _extract_thesis("THESIS: A buy below $181.60 on weakness.")
        assert "181" not in t and "omitted" in t
