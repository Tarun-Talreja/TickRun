"""The operating margin must come from the reported quarter, not Yahoo's summary."""
import os
import sys
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from refresh_quotes import _latest_op_margin


def _ticker(rows: dict) -> SimpleNamespace:
    columns = pd.to_datetime(["2026-09-30", "2026-06-30"])
    return SimpleNamespace(quarterly_income_stmt=pd.DataFrame(rows, index=columns).T)


def test_uses_reported_latest_quarter_over_yahoo_summary():
    t = _ticker({"Operating Income": [12988, 18775], "Total Revenue": [64601, 60801]})
    assert _latest_op_margin(t, {"operatingMargins": 0.354}) == 20.1


def test_keeps_a_reported_operating_loss():
    t = _ticker({"Operating Income": [-47, 2266], "Total Revenue": [7504, 11122]})
    assert _latest_op_margin(t, {"operatingMargins": 0.087}) == -0.6


def test_falls_back_when_statement_has_no_operating_income():
    t = _ticker({"Total Revenue": [100, 90]})
    assert _latest_op_margin(t, {"operatingMargins": 0.25}) == 25.0


def test_none_when_nothing_is_available():
    t = SimpleNamespace(quarterly_income_stmt=pd.DataFrame())
    assert _latest_op_margin(t, {}) is None
