"""Labels come from filed facts and quoted events; a missing figure is never a pass."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from categories import category
from company_events import filing_events, headline_events, newer_results
from quality_check import quality

Y = ("2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31")
GOOD = {"annual": {"revenue": dict.fromkeys(Y, 100), "net_income": dict.fromkeys(Y, 10),
                   "operating_cash_flow": dict.fromkeys(Y, 15), "capex": dict.fromkeys(Y, 3),
                   "diluted_shares": dict.fromkeys(Y[1:], 50)},
        "ttm": {"net_income": {"value": 11}, "revenue": {"value": 105}, "operating_cash_flow": {"value": 15}}}
QUOTE = {"total_debt": 20, "total_cash": 5, "sector": "Technology"}


def changed(**annual):
    return {**GOOD, "annual": {**GOOD["annual"], **annual}}


def test_good_business_is_solid():
    assert category(quality(GOOD, QUOTE), {})["key"] == "solid"


def test_one_miss_is_still_solid_but_named_and_two_are_weak():
    loss = changed(net_income={**dict.fromkeys(Y, 10), Y[0]: -1})
    one = category(quality(loss, QUOTE), {})
    assert one["key"] == "solid" and "lost money in 2022" in one["why"]
    two = category(quality(loss, {**QUOTE, "total_debt": 500}), {})
    assert two["key"] == "weak" and "33.0 years" in two["why"]


def test_missing_figures_are_unknown_not_passed():
    assert category(quality(changed(capex={}, diluted_shares={}), QUOTE), {})["key"] == "unknown"
    assert category(None, None)["key"] == "unknown"


def test_profit_missing_in_recent_years_is_unknown():
    r = quality(changed(net_income={y: 10 for y in Y[:2]}), QUOTE)
    assert r["checks"][0]["ok"] is None


def test_debt_check_skips_lenders():
    assert quality(GOOD, {**QUOTE, "sector": "Real Estate"})["checks"][3]["ok"] is None


def test_serious_event_wins_and_is_quoted():
    c = category(quality(GOOD, QUOTE), {"serious": [{"date": "2026-11-19", "source": "CNBC", "text": "Short seller report"}]})
    assert c["key"] == "serious" and "CNBC" in c["why"]


RECENT = {"form": ["8-K", "8-K", "10-Q", "8-K"], "filingDate": ["2026-11-17", "2026-11-01", "2026-08-26", "2026-01-01"],
          "items": ["2.02,9.01", "4.02", "", "4.02"], "accessionNumber": ["a", "b", "c", "d"]}


def test_filing_items():
    events = filing_events(RECENT, date(2026, 11, 24))
    assert [e["date"] for e in events] == ["2026-11-01"]
    assert newer_results(RECENT) == "2026-11-17"
    assert newer_results({**RECENT, "filingDate": ["2026-08-20", "x", "2026-08-26", "x"]}) is None


def test_headlines_that_count():
    def hit(title):
        return bool(headline_events([{"date": "2026-11-20", "title": title}], date(2026, 11, 24)))
    assert hit("AMD shares fall after short seller report on China links")
    assert hit("Acme withdraws full-year guidance")
    assert not hit("Visa launches fraud prevention tool") and not hit("Law firm reminds Acme investors of fraud deadline")
    assert not hit("Eli Lilly lifts revenue outlook") and not hit("Could Acme restate earnings?")


def test_years_of_losses_fail_alone():
    assert category(quality(changed(net_income={**dict.fromkeys(Y[:3], -5), Y[3]: 10}), QUOTE), {})["key"] == "weak"


def test_distorted_cash_and_listing_jump_are_unknown():
    r = quality(changed(operating_cash_flow={**dict.fromkeys(Y, 15), Y[2]: -9},
                        diluted_shares={Y[1]: 10, Y[2]: 20, Y[3]: 40}), QUOTE)
    assert [r["checks"][i]["ok"] for i in (1, 2, 3)] == [None, None, None]
