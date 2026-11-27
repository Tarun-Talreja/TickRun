"""The Home summary must be re-verified from raw sources, and one wrong claim must fail it."""
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import summary_check as sc
from weekly_digest import EARNINGS_DAYS, TOP_MOVERS, summary

TODAY = date(2026, 11, 24)
AS_OF = "2026-11-23T21:00:01Z"                       # Monday's close
STAMP = lambda day: int(datetime(day.year, day.month, day.day, 21, tzinfo=timezone.utc).timestamp())  # noqa: E731


def q(pct, earnings=None):
    return {"status": "ok", "pct_change_1d": pct, "next_earnings": STAMP(earnings) if earnings else None}


QUOTES = {"SPY": q(4.7), "QQQ": q(7.0), "NVDA": q(31.48), "CRDO": q(22.63), "AAPL": q(0.4),
          "MRVL": q(1.0, date(2026, 12, 1)), "MU": q(2.0, date(2026, 12, 17))}
MARKET = {"session": "2026-11-23", "changes": {"SPY": 4.71, "QQQ": 7.0}}
NEWS = {"NVDA": [{"title": "Trump sealed deal for Nvidia to rehire Jensen Huang as CEO", "publisher": "CNBC", "date": "2026-11-23"}]}
MOVERS = [{"ticker": "NVDA", "pct": 31.48, "reason": "Nov 23 headline: “Trump sealed deal for Nvidia to rehire Jensen Huang as CEO” (CNBC). The whole market moved the same way (x)."},
          {"ticker": "CRDO", "pct": 22.63, "reason": "No clear company headline found for this move."}]
EARNINGS = [{"ticker": "MRVL", "date": "2026-12-01", "days_until": 7}]


def run(text=None, quotes=QUOTES, news=NEWS, market=MARKET):
    text = text or summary({t: v for t, v in quotes.items()}, AS_OF, MOVERS, EARNINGS)
    claims, failures, _ = sc.check(text, quotes, market, news, AS_OF, TODAY)
    return claims, failures


def test_a_correct_summary_passes_with_many_claims():
    claims, failures = run()
    assert failures == [] and claims >= 12


def test_each_kind_of_wrong_claim_fails():
    good = summary(QUOTES, AS_OF, MOVERS, EARNINGS)
    cases = {
        "weekday": good.replace("Mon Nov 23", "Tue Nov 23"),
        "index": good.replace("rose 4.7%", "rose 3.7%"),
        "direction": good.replace("the Nasdaq 100 rose", "the Nasdaq 100 fell"),
        "mover": good.replace("NVDA +31.5%", "NVDA +21.5%"),
        "headline": good.replace("rehire Jensen Huang", "fire Jensen Huang"),
        "earnings date": good.replace("MRVL Tue Dec 1", "MRVL Wed Dec 2"),
        "banned word": good.replace("Earnings next", "You should buy before earnings next"),
        "unknown text": good + " Analysts expect more.",
    }
    for name, text in cases.items():
        assert run(text)[1], f"{name} was not caught"


def test_a_bigger_mover_left_out_fails():
    quotes = {**QUOTES, "AMD": q(25.0)}
    assert any("AMD" in f for f in run(quotes=quotes)[1])


def test_earnings_list_must_be_complete_and_inside_the_window():
    quotes = {**QUOTES, "CRDO": q(22.63, date(2026, 12, 2))}
    assert any("CRDO reports" in f for f in run(quotes=quotes)[1])
    text = summary(QUOTES, AS_OF, MOVERS, EARNINGS).replace("MRVL Tue Dec 1.", "MRVL Tue Dec 1, MU Thu Dec 17.")
    assert any("MU" in f and "outside" in f for f in run(text)[1])


def test_headline_must_be_from_the_move_and_not_an_opinion():
    old = {"NVDA": [{**NEWS["NVDA"][0], "date": "2026-11-10"}]}
    assert run(news=old)[1]
    opinion = "Nvidia price prediction: more upside?"
    news = {"NVDA": [{"title": opinion, "publisher": "X", "date": "2026-11-23"}]}
    movers = [{**MOVERS[0], "reason": f"Nov 23 headline: “{opinion}” (X). The whole market"}]
    assert any("opinion" in f for f in sc.check(summary(QUOTES, AS_OF, movers, EARNINGS), QUOTES, MARKET, news, AS_OF, TODAY)[1])


def test_summary_day_must_match_the_prices():
    text = summary(QUOTES, "2026-11-20T21:00:00Z", MOVERS, EARNINGS)
    assert any("prices are from" in f for f in run(text)[1])


def test_streak_counts_error_free_days_in_a_row():
    days = {}
    for day, fails in (("2026-11-23", []), ("2026-11-24", ["x"]), ("2026-11-25", []), ("2026-11-26", [])):
        days = sc.record(days, day, 10, fails, "t")
    assert sc.streak(days) == 2
    days = sc.record(days, "2026-11-26", 10, ["x"], "t")        # one bad run spoils its day
    assert sc.streak(days) == 0 and sc.status(days)["latest"]["failed_runs"] == 1


def test_constants_match_the_builder():
    assert sc.TOP_MOVERS == TOP_MOVERS and sc.EARNINGS_DAYS == EARNINGS_DAYS
