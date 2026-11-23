"""The old targets follow the 52-week high and rating-day price, so they must not be shown."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from build_dashboard import without_targets


def test_target_and_its_pullback_wording_are_removed():
    out = without_targets({"ticker": "RDDT", "buy_target": 210.8, "buy_trigger_drawdown_pct": -20,
                           "next_action": "WAIT — Cheap for its growth. Revisit at 20% below the 52-week high."})
    assert "buy_target" not in out and "buy_trigger_drawdown_pct" not in out
    assert out["next_action"] == "WAIT — Cheap for its growth."


def test_other_fields_are_kept():
    stock = {"ticker": "VST", "next_action": "RESEARCH — Worth a look.", "price": 123.87}
    assert without_targets(stock) == stock
