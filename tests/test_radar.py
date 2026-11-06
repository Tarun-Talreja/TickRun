"""A stock reaches the radar when separate reasons line up, and every reason is real."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from radar import (build_card, tracked_tickers, build_radar, match_company, news_reasons, on_sale, scorecard,
                   updated_log, watch_outs)

TODAY = "2026-11-07"


def stock(ticker="XYZ", **over):
    return {"ticker": ticker, "name": f"{ticker} Systems Inc.", "sector": "Tech", "score": 72.0,
            "quality": 28.0, "price": 50.0, "drawdown_pct": -10.0, "forward_pe": 18.0,
            "rev_growth": 0.2, "fcf": 1e9, "debt_equity": 50.0, **over}


NEWS = {"fields": {"power": {
    "name": "Power Grid",
    "companies": ["XYZ Systems"],
    "sources": [{"title": "XYZ Systems wins grid order", "source": "Reuters", "date": "2026-11-05", "link": "https://a"}],
}}}


class TestMatchCompany:
    universe = [stock("MSFT", name="Microsoft Corporation"), stock("AMZN", name="Amazon.com, Inc."),
                stock("META", name="Meta Platforms, Inc."), stock("GM", name="General Motors Company"),
                stock("GE", name="General Electric Company")]

    def test_exact_after_suffixes(self):
        assert match_company("Microsoft", self.universe) == "MSFT"

    def test_short_name_of_a_longer_company(self):
        assert match_company("Meta", self.universe) == "META"
        assert match_company("Amazon", self.universe) == "AMZN"

    def test_ambiguous_name_matches_nothing(self):
        assert match_company("General", self.universe) is None

    def test_unknown_company_matches_nothing(self):
        assert match_company("Agility Robotics", self.universe) is None


class TestWatchOuts:
    def test_clean_stock_has_none(self):
        assert watch_outs(stock()) == []

    def test_huge_growth_warns_of_peak_earnings(self):
        assert any("peak" in w for w in watch_outs(stock(rev_growth=3.8)))

    def test_very_low_forward_pe_warns_of_peak_earnings(self):
        assert any("peak" in w for w in watch_outs(stock(forward_pe=4.0)))

    def test_cash_burn_and_debt(self):
        out = " ".join(watch_outs(stock(fcf=-1e8, debt_equity=250.0)))
        assert "cash" in out and "debt" in out

    def test_missing_figures_are_fine(self):
        assert watch_outs(stock(forward_pe=None, rev_growth=None, fcf=None, debt_equity=None)) == []


class TestBuildCard:
    def test_reasons_come_with_their_source(self):
        card = build_card(stock(), news_reasons(NEWS["fields"], [stock()]), {}, {}, set(), {})
        news = next(r for r in card["reasons"] if r["kind"] == "field_news")
        assert "Power Grid" in news["text"]
        assert news["link"] == "https://a"

    def test_ambiguous_name_is_not_credited_to_either_company(self):
        fields = {"f": {"name": "Field", "companies": ["General"], "sources": []}}
        universe = [stock("GM", name="General Motors Company"), stock("GE", name="General Electric Company")]
        assert news_reasons(fields, universe) == {}

    def test_quiet_stock_has_only_what_is_true(self):
        card = build_card(stock(score=40, quality=10), {}, {"XYZ": {}}, {}, set(), {})
        assert card["reasons"] == []

    def test_quality_on_sale_needs_quality(self):
        assert on_sale(stock(drawdown_pct=-30.0))
        assert not on_sale(stock(drawdown_pct=-30.0, quality=10.0))
        assert not on_sale(stock(drawdown_pct=-10.0))

    def test_new_flag_clears_once_logged(self):
        assert build_card(stock(), {}, {}, {}, set(), {})["new"]
        assert not build_card(stock(), {}, {"XYZ": {"first_seen": "2026-10-01"}}, {}, set(), {})["new"]

    def test_stays_new_for_a_week(self):
        log = {"XYZ": {"first_seen": "2026-11-03"}}
        assert build_card(stock(), {}, log, {}, set(), {}, today=TODAY)["new"]
        assert not build_card(stock(), {}, log, {}, set(), {}, today="2026-11-11")["new"]

    def test_insider_buying_counts(self):
        insiders = {"XYZ": {"buys": 3, "sells": 0, "buy_value": 900000.0}}
        card = build_card(stock(), {}, {}, insiders, set(), {})
        assert any(r["kind"] == "insider" for r in card["reasons"])

    def test_insider_selling_does_not_count(self):
        insiders = {"XYZ": {"buys": 1, "sells": 9, "buy_value": 1000.0}}
        card = build_card(stock(), {}, {}, insiders, set(), {})
        assert not any(r["kind"] == "insider" for r in card["reasons"])

    def test_shows_a_known_rating(self):
        card = build_card(stock(), {}, {"XYZ": {"rating": "PASS"}}, {}, set(), {})
        assert card["rating"] == "PASS"
        assert build_card(stock(), {}, {}, {}, {"XYZ"}, {"XYZ": "WATCHLIST"})["rating"] == "WATCHLIST"


class TestBuildRadar:
    def test_needs_two_reasons(self):
        out = build_radar([stock("ONE", score=40, quality=10), stock("TWO", score=80, drawdown_pct=-30.0)], {}, {}, {}, set(), {})
        assert [c["ticker"] for c in out["cards"]] == ["TWO"]

    def test_more_reasons_rank_first(self):
        universe = [stock("AAA", score=95), stock("XYZ", score=71, drawdown_pct=-30.0)]
        out = build_radar(universe, NEWS, {"AAA": {"first_seen": "2026-01-01"}}, {}, set(), {})
        assert out["cards"][0]["ticker"] == "XYZ"

    def test_caps_each_sector(self):
        universe = [stock(f"T{i}", score=80, drawdown_pct=-30.0) for i in range(8)]
        assert len(build_radar(universe, {}, {}, {}, set(), {})["cards"]) == 3

    def test_on_sale_list_skips_tracked(self):
        universe = [stock("A", drawdown_pct=-40.0), stock("B", drawdown_pct=-30.0)]
        out = build_radar(universe, {}, {}, {}, {"A"}, {})
        assert [c["ticker"] for c in out["on_sale"]] == ["B"]


class TestLogAndScorecard:
    def test_logs_first_sighting_once(self):
        card = {"ticker": "A", "price": 10.0, "reasons": [{"kind": "new"}]}
        log = updated_log({}, [card], TODAY, 500.0)
        assert log["A"] == {"first_seen": TODAY, "price": 10.0, "spy": 500.0, "signals": ["new"]}
        assert updated_log(log, [{**card, "price": 99.0}], "2026-12-01", 600.0)["A"]["price"] == 10.0

    def test_does_not_change_the_input(self):
        log = {}
        updated_log(log, [{"ticker": "A", "price": 10.0, "reasons": []}], TODAY, 500.0)
        assert log == {}

    def test_too_early_means_no_score(self):
        log = {"A": {"first_seen": "2026-11-01", "price": 10.0, "spy": 500.0}}
        assert scorecard(log, {"A": 20.0}, 500.0, TODAY)["4w"]["count"] == 0

    def test_excess_return_against_spy(self):
        log = {"A": {"first_seen": "2026-10-01", "price": 10.0, "spy": 500.0}}
        card = scorecard(log, {"A": 12.0}, 550.0, TODAY)
        assert card["4w"] == {"count": 1, "avg_excess_pct": 10.0}
        assert card["12w"]["count"] == 0


class TestTrackedTickers:
    def test_other_share_class_counts_as_tracked(self):
        universe = [stock("GOOG", name="Alphabet Inc."), stock("HWM", name="Howmet Aerospace Inc.")]
        candidates = [{"ticker": "GOOGL", "name": "Alphabet Inc."}]
        assert tracked_tickers(candidates, universe) == {"GOOGL", "GOOG"}
