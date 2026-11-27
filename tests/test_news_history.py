"""The news history keeps every headline once, newest first, and never writes outside its folder."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import news_history as nh


def item(title, day="2026-11-23", publisher="CNBC", url="u"):
    return {"title": title, "publisher": publisher, "date": day, "url": url}


def test_new_items_are_added_once_newest_first():
    merged, added = nh.merge([], [item("a", "2026-11-20"), item("b", "2026-11-23"), item("a", "2026-11-20")], "2026-11-24")
    assert added == 2 and [i["title"] for i in merged] == ["b", "a"] and merged[0]["seen_on"] == "2026-11-24"
    again, added = nh.merge(merged, [item("b", "2026-11-23", url="other-url")], "2026-11-25")
    assert added == 0 and again == merged                      # same story, new link: not a new headline


def test_same_title_on_another_day_or_publisher_is_kept():
    merged, added = nh.merge([], [item("a"), item("a", "2026-11-24"), item("a", publisher="Reuters")], "d")
    assert added == 3


def test_unusable_items_are_skipped():
    merged, added = nh.merge([], [item(""), item("x", "yesterday"), {"title": "y"}, item("ok")], "d")
    assert added == 1 and merged[0]["title"] == "ok"


def test_files_are_per_ticker_and_only_rewritten_on_news(tmp_path):
    d = str(tmp_path)
    assert nh.add_cache({"news": {"NVDA": [item("a")], "BRK.B": [item("b")], "../evil": [item("c")], "AMD": []}}, "d1", d) == 2
    assert sorted(os.listdir(d)) == ["BRK.B.json", "NVDA.json"]
    stamp = os.stat(os.path.join(d, "NVDA.json")).st_mtime_ns
    assert nh.add_cache({"news": {"NVDA": [item("a")]}}, "d2", d) == 0
    assert os.stat(os.path.join(d, "NVDA.json")).st_mtime_ns == stamp
    assert nh.read("NVDA", d)[0]["seen_on"] == "d1" and nh.read("../evil", d) == []


def test_file_is_valid_json_with_one_headline_per_line(tmp_path):
    nh.add_cache({"news": {"NVDA": [item("a"), item("b", "2026-11-24")]}}, "d", str(tmp_path))
    text = open(tmp_path / "NVDA.json").read()
    assert len(json.loads(text)) == 2 and text.count("\n") == 4


def test_backfill_keeps_the_earliest_day_a_headline_was_seen(tmp_path):
    snaps = [("2026-06-08", {"news": {"NVDA": [item("a")]}}), ("2026-06-09", {"news": {"NVDA": [item("a"), item("b")]}})]
    assert nh.backfill(str(tmp_path), snaps) == (2, 2)
    seen = {i["title"]: i["seen_on"] for i in nh.read("NVDA", str(tmp_path))}
    assert seen == {"a": "2026-06-08", "b": "2026-06-09"}


def test_curly_quotes_and_case_do_not_make_a_new_headline():
    merged, added = nh.merge([], [item("How to protect your portfolio if you\u2019re worried"),
                                   item("how to protect your  portfolio if you're worried")], "d")
    assert added == 1
