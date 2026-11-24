"""A mover's reason is a dated headline that fits the move, never a guess."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from catalyst_calendar import _plan, _urgency
from daily_brief import _mover_items
from move_explainer import NO_HEADLINE, explain

RALLY = {"SPY": {"pct_change_1d": 4.7}, "QQQ": {"pct_change_1d": 7.0}}


def _n(title, date="2026-11-23"):
    return {"title": title, "date": date, "publisher": "Reuters"}


def _explain(pct, *news, quotes=RALLY):
    return explain(pct, list(news), quotes, "2026-11-23", "2026-11-20")


def test_company_news_is_shown_on_a_rally_day():
    out = _explain(31.5, _n("Trump sealed deal for Nvidia to rehire Jensen Huang as CEO"))
    assert "rehire Jensen Huang" in out and "Nov 23" in out and "+7.0%" in out


def test_opposite_direction_headlines_are_ignored():
    out = _explain(18.4, _n("Marvell target lowered at Susquehanna ahead of earnings"),
                   _n("Vertiv Slides as Solid Earnings Clash With Technicals"))
    assert NO_HEADLINE in out


def test_opinion_and_quote_pages_are_ignored():
    assert NO_HEADLINE in _explain(8.0, _n("Eaton: A Great Quarter (NYSE:ETN)"),
                                   _n("Talen Energy (TLN) Stock forecasts"),
                                   _n("What Is Behind The Rise In Vertiv Earnings?"))


def test_old_headlines_are_ignored_but_last_sessions_earnings_count():
    assert NO_HEADLINE in _explain(9.0, _n("Eaton signs deal", "2026-11-20"))
    assert "beats" in _explain(9.0, _n("Eaton beats on Q3 earnings", "2026-11-20"))


def test_no_claim_of_no_news_and_no_market_note_on_a_quiet_day():
    assert _explain(9.0, quotes={}) == NO_HEADLINE


def test_brief_says_how_old_the_rating_is():
    mover = {"ticker": "NVDA", "primary_pct": 31.5, "reason": "x"}
    assert "Nov 18" in _mover_items([mover], {}, {"NVDA": "2026-11-18"})[0]["action"]


def test_dividends_are_never_urgent_or_a_reason_to_buy():
    assert _urgency(1, "ex_dividend", "WATCHLIST", None) == "low"
    assert "no reason to buy" in _plan({"type": "ex_dividend"}, {})
