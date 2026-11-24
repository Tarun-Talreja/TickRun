"""Every conflict must follow from the plan's own numbers, and nothing may suggest a trade."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from plan_review import conflicts, linked_groups, overlap, stress

PLAN = {"last_updated": "2026-06-08", "thematic": [{"ticker": "VST", "target_dollars": 1500}, {"ticker": "CEG", "target_dollars": 1500},
                                                  {"ticker": "MSFT", "target_dollars": 1200}],
        "target_allocation": {"international_pct": 5}, "deployment_plan": {"total": 14000, "cash_reserve": 700},
        "rules": {"account_type": "Roth IRA", "max_single_position_pct": 15, "trim_trigger_pct": 20, "stop_loss_pct": 30}}
MARKET = {"corr": {"VST": {"CEG": .8, "MSFT": .2}, "CEG": {"VST": .8, "MSFT": .3}, "MSFT": {"VST": .2, "CEG": .3}},
          "worst_fall": {"VST": -48.8, "MSFT": -20.0}, "now": {}}
DAY = date(2026, 11, 24)


def titles(plan=PLAN, market=MARKET, day=DAY):
    return [c["title"] for c in conflicts(plan, market, day)]


def test_all_known_conflicts_are_found():
    assert len(titles()) == 6


def test_linked_pair_over_the_limit():
    c = next(c for c in conflicts(PLAN, MARKET, DAY) if "one bet" in c["title"])
    assert "21%" in c["fact"] and "0.80" in c["fact"]


def test_only_stocks_past_the_stop_are_named():
    c = next(c for c in conflicts(PLAN, MARKET, DAY) if "stop-loss" in c["title"])
    assert "VST 49%" in c["fact"] and "MSFT" not in c["fact"]


def test_fixed_plan_has_no_conflicts():
    plan = {**PLAN, "last_updated": "2026-11-20", "international": [{"ticker": "VXUS"}],
            "deployment_plan": {"total": 7500, "cash_reserve": 0},
            "thematic": [{"ticker": "MSFT", "target_dollars": 1000}],
            "rules": {**PLAN["rules"], "trim_trigger_pct": 15}}
    assert titles(plan) == []


def test_unknown_year_says_so():
    assert "Yearly limit not checked" in titles(day=date(2028, 1, 2))


def test_groups_join_through_a_shared_link():
    corr = {"A": {"B": .7}, "B": {"A": .7, "C": .7}, "C": {"B": .7}, "D": {}}
    assert linked_groups(list("ACBD"), corr) == [["A", "B", "C"]]


def test_stress_and_overlap():
    assert stress(PLAN, [["CEG", "VST"]])[0] == {"names": ["CEG", "VST"], "pct": 10.7}
    rows = overlap(PLAN, {"MSFT": .0533, "TSLA": .0155})
    assert rows[2]["pct"] == 5.3 and rows[0]["pct"] is None and rows[0]["below_pct"] in (1.5, 1.6)


def test_limit_does_not_apply_to_money_already_there():
    assert not any("one year allows" in t for t in titles({**PLAN, "money_already_in_account": True}))
