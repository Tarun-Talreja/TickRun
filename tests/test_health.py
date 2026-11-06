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
    out = build_health(now, field_news=FRESH, quotes=quotes, research=research, catalysts=FRESH,
                       news=FRESH, sec=FRESH, screener=FRESH)
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
