"""The backtest must never see the future or mix share counts from before and after a split."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from backtest_valuation import as_of, forward, group_of, quarter_growth, split_factor, split_since_filing

ROW = {"start": "2019-01-01", "end": "2019-12-31", "val": 1, "form": "10-K", "filed": "2020-02-01"}


def test_rows_filed_later_are_hidden():
    facts = {"Revenues": {"USD": [ROW, {**ROW, "val": 2, "filed": "2021-02-01"}]}}
    rows = as_of(facts, "2020-06-01")["facts"]["us-gaap"]["Revenues"]["units"]["u"]
    assert [r["val"] for r in rows] == [1]
    assert as_of(facts, "2020-01-01")["facts"]["us-gaap"] == {}


def test_splits_after_the_date_restore_that_days_price():
    splits = {"2021-07-20": 4.0, "2024-06-10": 10.0}
    assert split_factor(splits, "2020-01-01") == 40 and split_factor(splits, "2022-01-01") == 10
    assert split_factor(splits, "2025-01-01") == 1


def test_split_between_filing_and_date_is_skipped():
    known = as_of({"Revenues": {"USD": [ROW]}}, "2020-06-01")
    assert split_since_filing(known, {"2020-05-01": 4.0}, "2020-06-01")
    assert not split_since_filing(known, {"2020-07-01": 4.0}, "2020-06-01")


def test_return_starts_the_next_session_and_needs_a_full_window():
    days = pd.bdate_range("2020-01-01", "2021-06-30")
    adj = pd.Series(range(100, 100 + len(days)), index=days, dtype=float)
    day = pd.Timestamp("2020-01-31")
    start = adj[adj.index > day].iloc[0]
    assert forward(adj, day, 365) == pytest.approx(adj[:"2021-02-02"].iloc[-1] / start - 1)
    assert forward(adj, pd.Timestamp("2021-01-31"), 365) is None


def test_groups():
    ok = {"status": "ok", "buy_below": 100}
    assert [group_of(ok, p) for p in (99, 125, 126)] == ["below", "close", "expensive"]
    assert group_of({"status": "market_expects_decline"}, 1) == "decline"


def test_quarter_growth():
    q = lambda s, e, v: {"start": s, "end": e, "val": v, "form": "10-Q", "filed": e}  # noqa: E731
    f = as_of({"Revenues": {"USD": [q("2019-04-01", "2019-06-30", 100), q("2020-04-01", "2020-06-30", 106)]}}, "2020-08-01")
    assert quarter_growth(f) == pytest.approx(6.0)
