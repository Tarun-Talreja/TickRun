"""The home-screen summary is built from saved data and never from prices that moved on."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from weekly_digest import current_movers, summary

QUOTES = {"SPY": {"pct_change_1d": 4.7}, "QQQ": {"pct_change_1d": -1.2}}
NVDA = {"ticker": "NVDA", "pct": 31.48,
        "reason": "Nov 23 headline: \u201cHuang rehired\u201d (CNBC). The whole market moved the same way (x)."}
EARNINGS = [{"ticker": "MRVL", "date": "2026-12-01", "days_until": 8},
            {"ticker": "MU", "date": "2026-12-17", "days_until": 24}]


def test_market_movers_headline_and_earnings():
    out = summary(QUOTES, "2026-11-23T21:00:01Z", [{"ticker": "QQQ", "pct": 7.0}, NVDA], EARNINGS)
    assert "Mon Nov 23: the S&P 500 rose 4.7% and the Nasdaq 100 fell 1.2%." in out
    assert "NVDA +31.5%" in out and "Huang rehired" in out and "QQQ" not in out
    assert "MRVL Tue Dec 1" in out and "MU" not in out


def test_nothing_to_say():
    assert summary({}, None, None, []) is None


def test_movers_older_than_the_prices_are_left_out():
    sig = {"movers_updated": "2026-11-23T13:36:00Z", "price_movers": [{"ticker": "NVDA"}]}
    assert current_movers(sig, "2026-11-23T21:00:01Z") is None
    assert current_movers(sig, "2026-11-20T21:00:00Z")[0]["ticker"] == "NVDA"
