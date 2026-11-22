"""Filed figures must come from the series a company still reports, over the right period."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from sec_facts import annual_series, latest_value, pick_concept, ttm


def _row(start, end, val, form="10-K", filed="2026-02-01"):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed}


def _facts(**tags):
    return {"facts": {"us-gaap": {t: {"units": {"USD": rows}} for t, rows in tags.items()}}}


class TestAnnual:
    def test_keeps_only_full_years(self):
        rows = [_row("2025-01-01", "2025-12-31", 100), _row("2025-10-01", "2025-12-31", 30)]
        assert annual_series(rows) == {"2025-12-31": 100}

    def test_restated_figure_from_the_latest_filing_wins(self):
        rows = [_row("2024-01-01", "2024-12-31", 90, filed="2025-02-01"),
                _row("2024-01-01", "2024-12-31", 95, filed="2026-02-01")]
        assert annual_series(rows) == {"2024-12-31": 95}

    def test_ignores_quarterly_filings(self):
        rows = [_row("2025-01-01", "2025-12-31", 100, form="10-Q")]
        assert annual_series(rows) == {}


class TestPickConcept:
    def test_picks_the_series_still_being_filed(self):
        facts = _facts(
            Revenues=[_row("2009-07-01", "2010-06-30", 62)],
            RevenueFromContractWithCustomerExcludingAssessedTax=[_row("2025-07-01", "2026-06-30", 331)],
        )
        name, _ = pick_concept(facts, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"])
        assert name == "RevenueFromContractWithCustomerExcludingAssessedTax"

    def test_prefers_the_first_name_when_both_are_current(self):
        facts = _facts(Revenues=[_row("2025-01-01", "2025-12-31", 177)],
                       RevenueFromContractWithCustomerExcludingAssessedTax=[_row("2025-01-01", "2025-12-31", 175)])
        name, _ = pick_concept(facts, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"])
        assert name == "Revenues"

    def test_none_when_no_name_is_filed(self):
        assert pick_concept(_facts(), ["Revenues"]) == (None, [])


class TestTtm:
    def test_full_year_plus_this_year_minus_last_year(self):
        rows = [
            _row("2025-01-01", "2025-12-31", 100),
            _row("2025-01-01", "2025-09-30", 70, form="10-Q", filed="2025-11-01"),
            _row("2026-01-01", "2026-09-30", 85, form="10-Q", filed="2026-11-01"),
        ]
        assert ttm(rows) == {"end": "2026-09-30", "value": 115}

    def test_latest_annual_when_no_newer_quarter(self):
        rows = [_row("2025-01-01", "2025-12-31", 100),
                _row("2025-01-01", "2025-09-30", 70, form="10-Q", filed="2025-11-01")]
        assert ttm(rows) == {"end": "2025-12-31", "value": 100}

    def test_none_when_last_year_is_missing(self):
        rows = [_row("2025-01-01", "2025-12-31", 100),
                _row("2026-01-01", "2026-09-30", 85, form="10-Q", filed="2026-11-01")]
        assert ttm(rows) is None


def test_latest_value_takes_the_newest_period():
    rows = [_row("2025-01-01", "2025-12-31", 350), _row("2026-07-01", "2026-09-30", 340, form="10-Q")]
    assert latest_value(rows) == {"end": "2026-09-30", "value": 340}
