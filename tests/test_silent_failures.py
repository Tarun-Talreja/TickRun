"""Each silent failure found on 2026-11-06, so none can come back unnoticed."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from health_alert import decide, issue_body, problems_from
from insider_check import _classify, count_trades
from sec_filings import NOTABLE_FORMS, is_stake
from self_test import run_check, unknown_stake_forms


def _trades(*rows):
    return pd.DataFrame([{"Text": t, "Value": v, "Transaction": ""} for t, v in rows])


class TestInsiders:
    def test_reads_the_text_column_when_transaction_is_blank(self):
        df = _trades(("Sale at price 325.75 per share.", 100.0),
                     ("Purchase at price 20 per share.", 50.0))
        assert count_trades(df) == (1, 1, 50.0, 100.0)

    def test_awards_gifts_and_exercises_are_not_trades(self):
        df = _trades(("Stock Award(Grant) at price 0.00 per share.", 0.0),
                     ("Stock Gift at price 0.00 per share.", 0.0),
                     ("Conversion of Exercise of derivative security", 0.0),
                     ("", 0.0))
        assert count_trades(df)[:2] == (0, 0)

    def test_unreadable_table_is_reported(self):
        assert count_trades(pd.DataFrame({"Shares": [1]})) is None

    def test_routine_selling_is_not_a_warning(self):
        assert _classify(0, 12, 0.0, 5e6) == "SELLING"

    def test_no_trades_stays_no_data(self):
        assert _classify(0, 0, None, None) == "NO_DATA"


class TestSecStakes:
    def test_current_form_names_are_recognised(self):
        assert {"SCHEDULE 13G", "SCHEDULE 13G/A", "SCHEDULE 13D", "SCHEDULE 13D/A"} <= set(NOTABLE_FORMS)

    def test_both_names_count_as_stakes(self):
        assert is_stake("SCHEDULE 13G/A") and is_stake("SC 13D") and not is_stake("8-K")

    def test_self_test_catches_a_future_rename(self):
        assert unknown_stake_forms(["4", "SCHEDULE 13G", "BENEFICIAL 13G"]) == ["BENEFICIAL 13G"]


class TestSelfTest:
    def test_a_crash_is_a_failed_check(self):
        def crash():
            raise RuntimeError("Yahoo is down")
        assert run_check("Yahoo", crash) == {"name": "Yahoo", "ok": False, "detail": "Yahoo is down"}

    def test_clean_check_passes(self):
        assert run_check("Yahoo", lambda: None)["ok"]


class TestAlert:
    STAGES = [{"name": "News", "status": "failing", "detail": "0/54 have data", "affects": "No news"},
              {"name": "Quotes", "status": "ok"},
              {"name": "Ratings", "status": "stale", "detail": "2/54"}]

    def test_lists_broken_parts_but_not_a_running_rerate(self):
        lines = problems_from(self.STAGES)
        assert len(lines) == 1 and "News" in lines[0] and "No news" in lines[0]

    def test_opens_one_issue(self):
        assert decide("broken", None) == "create"

    def test_a_lasting_problem_does_not_repeat(self):
        assert decide("broken", {"body": "broken\n"}) == "nothing"

    def test_a_new_problem_updates_the_issue(self):
        assert decide("worse", {"body": "broken"}) == "update"

    def test_closes_on_recovery(self):
        assert decide(None, {"body": "broken"}) == "close"

    def test_quiet_when_healthy(self):
        assert decide(None, None) == "nothing"

    def test_failed_jobs_are_listed(self):
        assert "Daily LLM Research" in issue_body([], ["Daily LLM Research"])
