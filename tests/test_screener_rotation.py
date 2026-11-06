"""Discovery must keep surfacing new names, not the same 15 every week."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from screener import MAX_PER_SECTOR, MAX_WEEKS_SHOWN, company_key, pick_discoveries, update_history

TODAY = "2026-11-07"


def stock(ticker, sector="Tech", name=None):
    return {"ticker": ticker, "sector": sector, "name": name or f"{ticker} Holdings", "price": 10.0}


class TestPickDiscoveries:
    def test_skips_tracked_tickers(self):
        picks = pick_discoveries([stock("A"), stock("B")], {"A"}, set(), {}, TODAY, 5)
        assert [p["ticker"] for p in picks] == ["B"]

    def test_skips_other_share_class_of_a_tracked_company(self):
        goog = stock("GOOG", name="Alphabet Inc.")
        assert pick_discoveries([goog], {"GOOGL"}, {company_key("Alphabet Inc.")}, {}, TODAY, 5) == []

    def test_keeps_one_share_class_when_neither_is_tracked(self):
        ranked = [stock("FOXA", name="Fox Corporation"), stock("FOX", name="Fox Corporation")]
        assert [p["ticker"] for p in pick_discoveries(ranked, set(), set(), {}, TODAY, 5)] == ["FOXA"]

    def test_caps_each_sector(self):
        ranked = [stock(f"T{i}", "Energy") for i in range(MAX_PER_SECTOR + 2)] + [stock("X", "Health")]
        picks = pick_discoveries(ranked, set(), set(), {}, TODAY, 20)
        assert sum(p["sector"] == "Energy" for p in picks) == MAX_PER_SECTOR
        assert "X" in [p["ticker"] for p in picks]

    def test_resting_name_is_skipped_until_its_rest_ends(self):
        history = {"A": {"rest_until": "2026-12-01"}, "B": {"rest_until": "2026-11-01"}}
        picks = pick_discoveries([stock("A"), stock("B")], set(), set(), history, TODAY, 5)
        assert [p["ticker"] for p in picks] == ["B"]

    def test_respects_the_limit(self):
        ranked = [stock(f"T{i}", f"S{i}") for i in range(9)]
        assert len(pick_discoveries(ranked, set(), set(), {}, TODAY, 4)) == 4


class TestUpdateHistory:
    def test_first_sighting_records_date_and_price(self):
        history = update_history({}, [stock("A")], TODAY)
        assert history["A"]["first_seen"] == TODAY
        assert history["A"]["first_price"] == 10.0
        assert history["A"]["weeks_shown"] == 1

    def test_does_not_change_the_input(self):
        before = {"A": {"first_seen": "2026-10-01", "first_price": 8.0, "weeks_shown": 1}}
        update_history(before, [stock("A")], TODAY)
        assert before["A"]["weeks_shown"] == 1

    def test_keeps_the_original_first_price(self):
        before = {"A": {"first_seen": "2026-10-01", "first_price": 8.0, "weeks_shown": 1}}
        assert update_history(before, [stock("A")], TODAY)["A"]["first_price"] == 8.0

    def test_rests_after_the_maximum_weeks(self):
        before = {"A": {"first_seen": "2026-10-01", "first_price": 8.0, "weeks_shown": MAX_WEEKS_SHOWN - 1}}
        after = update_history(before, [stock("A")], TODAY)["A"]
        assert after["rest_until"] > TODAY
        assert after["weeks_shown"] == 0

    def test_name_off_the_list_starts_its_count_again(self):
        before = {"A": {"first_seen": "2026-10-01", "first_price": 8.0, "weeks_shown": 2}}
        assert update_history(before, [], TODAY)["A"]["weeks_shown"] == 0

    def test_second_run_on_the_same_day_does_not_count_twice(self):
        once = update_history({}, [stock("A")], TODAY)
        assert update_history(once, [stock("A")], TODAY)["A"]["weeks_shown"] == 1
