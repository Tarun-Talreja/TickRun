"""Each stage must report whether it truly worked, not just whether a job ran."""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from health import build_health
from io_utils import load_json

WEDNESDAY = datetime(2026, 11, 4, 18, 0, tzinfo=timezone.utc)
SUNDAY = datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc)
FRESH = "2026-11-04T17:00:00Z"


def _stages(now=WEDNESDAY, quotes=FRESH, research=None):
    research = research or {"ran_at": FRESH, "attempted": 8, "landed": 7}
    out = build_health(now, ratings=(1, 1), quotes=quotes, research=research, catalysts=FRESH,
                       sec=FRESH, self_test={"ran_at": FRESH, "checks": []},
                       content={"News": (FRESH, 5, 6), "Screener": (FRESH, 428), "Field news": (FRESH, 16, 16)})
    return {s["name"]: s for s in out["stages"]}


class TestHealth:
    def test_fresh_stages_are_ok(self):
        assert all(s["status"] == "ok" for s in _stages().values())

    def test_old_quotes_are_stale(self):
        assert _stages(quotes="2026-11-02T17:00:00Z")["Quotes"]["status"] == "stale"

    def test_friday_close_is_fine_on_sunday(self):
        assert _stages(now=SUNDAY, quotes="2026-11-06T22:00:00Z")["Quotes"]["status"] == "ok"

    def test_missing_timestamp_is_unknown(self):
        assert _stages(research={"ran_at": None})["Research"]["status"] == "unknown"

    def test_research_that_ran_but_landed_nothing_is_failing(self):
        s = _stages(research={"ran_at": FRESH, "attempted": 8, "landed": 0})["Research"]
        assert s["status"] == "failing" and s["detail"] == "0/8 tickers"

    def test_research_with_most_tickers_failed_is_failing(self):
        assert _stages(research={"ran_at": FRESH, "attempted": 8, "landed": 3})["Research"]["status"] == "failing"

    def test_research_detail_shows_the_count(self):
        assert _stages()["Research"]["detail"] == "7/8 tickers"


class TestLoadJson:
    def test_missing_file_gives_default(self, tmp_path):
        assert load_json(str(tmp_path / "x.json"), {"a": 1}) == {"a": 1}
        assert load_json(str(tmp_path / "x.json")) == {}

    def test_corrupt_file_gives_default(self, tmp_path, capsys):
        path = tmp_path / "x.json"
        path.write_text("{not json")
        assert load_json(str(path), []) == []
        assert "x.json" in capsys.readouterr().out

    def test_reads_json(self, tmp_path):
        path = tmp_path / "x.json"
        path.write_text(json.dumps({"a": 1}))
        assert load_json(str(path)) == {"a": 1}


class TestRatings:
    def test_all_current_is_ok(self):
        now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
        stage = build_health(now, quotes=None, research={}, catalysts=None, sec=None,
                             ratings=(54, 54))["stages"][-1]
        assert (stage["name"], stage["status"], stage["detail"]) == ("Ratings", "ok", "54/54 on current logic")

    def test_behind_is_stale(self):
        now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
        stage = build_health(now, quotes=None, research={}, catalysts=None, sec=None,
                             ratings=(40, 54))["stages"][-1]
        assert stage["status"] == "stale"


def _content(name, *counts):
    stages = build_health(WEDNESDAY, quotes=None, research={}, catalysts=None, sec=None,
                          content={name: (FRESH, *counts)})["stages"]
    return next(s for s in stages if s["name"] == name)


class TestContent:
    def test_on_time_but_empty_is_failing(self):
        stage = _content("News", 0, 54)
        assert (stage["status"], stage["detail"]) == ("failing", "0/54 have data")

    def test_the_insider_outage_would_have_shown(self):
        assert _content("Insider data", 0, 30)["status"] == "failing"

    def test_a_few_gaps_are_fine(self):
        assert _content("Insider data", 25, 30)["status"] == "ok"

    def test_too_few_results_is_failing(self):
        assert _content("Screener", 12)["status"] == "failing"
        assert _content("Radar", 0)["status"] == "failing"

    def test_empty_list_is_failing_except_for_a_calm_day_of_movers(self):
        assert _content("Prices", 0, 0)["status"] == "failing"
        assert _content("Movers", 0, 0)["status"] == "ok"

    def test_old_data_stays_stale_rather_than_failing(self):
        stages = build_health(WEDNESDAY, quotes=None, research={}, catalysts=None, sec=None,
                              content={"News": ("2026-11-01T00:00:00Z", 0, 54)})["stages"]
        assert next(s for s in stages if s["name"] == "News")["status"] == "stale"

    def test_every_part_says_what_it_affects(self):
        assert _content("Insider data", 0, 30)["affects"]


class TestSelfTest:
    def _stage(self, result):
        stages = build_health(WEDNESDAY, quotes=None, research={}, catalysts=None, sec=None,
                              self_test=result)["stages"]
        return next(s for s in stages if s["name"] == "Self-test")

    def test_a_failed_source_is_named(self):
        stage = self._stage({"ran_at": FRESH, "checks": [{"name": "Stock news", "ok": False}]})
        assert (stage["status"], stage["detail"]) == ("failing", "failed: Stock news")

    def test_never_run_is_not_ok(self):
        assert self._stage(None)["status"] == "unknown"
