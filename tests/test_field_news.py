"""Field briefings may only say what their cited headlines say."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from field_news import best_headlines, brief_field, parse_feed

FEED = b"""<?xml version="1.0"?><rss><channel>
<item><title>Alliant targets 1 GW of new data-center contracts - Reuters</title>
  <link>https://example.com/a</link><pubDate>Fri, 30 Oct 2026 12:00:00 GMT</pubDate>
  <source url="https://reuters.com">Reuters</source></item>
<item><title>Alliant targets 1 GW of new data-center contracts - Reuters</title>
  <link>https://example.com/dup</link><pubDate>Fri, 30 Oct 2026 12:00:00 GMT</pubDate>
  <source url="https://reuters.com">Reuters</source></item>
<item><title>3 Stocks To Buy For Data Center Power - Motley Fool</title>
  <link>https://example.com/b</link><pubDate>Sat, 31 Oct 2026 12:00:00 GMT</pubDate>
  <source url="https://fool.com">Motley Fool</source></item>
<item><title>Eaton lifts transformer output by 20% - Bloomberg</title>
  <link>https://example.com/c</link><pubDate>Sun, 01 Nov 2026 12:00:00 GMT</pubDate>
  <source url="https://bloomberg.com">Bloomberg</source></item>
</channel></rss>"""

HEADLINES = [
    {"title": "Alliant targets 1 GW of new data-center contracts", "source": "Reuters", "date": "2026-10-30", "link": "a"},
    {"title": "Eaton lifts transformer output by 20%", "source": "Bloomberg", "date": "2026-11-01", "link": "c"},
]


def reply(text):
    return lambda prompt: text


class TestParseFeed:
    def test_strips_publisher_drops_duplicates_and_listicles(self):
        assert [h["title"] for h in parse_feed(FEED)] == [
            "Eaton lifts transformer output by 20%",
            "Alliant targets 1 GW of new data-center contracts",
        ]

    def test_dates_are_iso(self):
        assert parse_feed(FEED)[0]["date"] == "2026-11-01"

    def test_bad_feed_gives_nothing(self):
        assert parse_feed(b"<html>blocked") == []


class TestBriefField:
    def test_good_summary_keeps_its_sources_and_companies(self):
        out = brief_field("Power", HEADLINES, reply(
            "SUMMARY: Eaton lifted transformer output by 20% as demand grows.\n"
            "SOURCES: 2\nCOMPANIES: Eaton; Alliant"))
        assert out["summary"].startswith("Eaton lifted")
        assert [s["link"] for s in out["sources"]] == ["c"]
        assert out["companies"] == ["Eaton", "Alliant"]

    def test_figure_not_in_cited_headlines_drops_the_summary(self):
        out = brief_field("Power", HEADLINES, reply(
            "SUMMARY: Eaton lifted output by 45%.\nSOURCES: 2\nCOMPANIES: Eaton"))
        assert out["summary"] is None
        assert out["sources"] == HEADLINES

    def test_summary_with_no_real_source_is_dropped(self):
        out = brief_field("Power", HEADLINES, reply("SUMMARY: Big news.\nSOURCES: 9\nCOMPANIES: none"))
        assert out["summary"] is None

    def test_company_not_in_the_headlines_is_removed(self):
        out = brief_field("Power", HEADLINES, reply(
            "SUMMARY: Eaton expanded.\nSOURCES: 2\nCOMPANIES: Eaton; Siemens"))
        assert out["companies"] == ["Eaton"]

    def test_model_failure_still_shows_headlines(self):
        def boom(prompt):
            raise RuntimeError("all models failed")
        out = brief_field("Power", HEADLINES, boom)
        assert out["summary"] is None and out["sources"] == HEADLINES

    def test_no_headlines_makes_no_call(self):
        def boom(prompt):
            raise AssertionError("should not call")
        assert brief_field("Power", [], boom)["sources"] == []


def item(title, source="Local Paper", day="2026-11-05"):
    return {"title": title, "source": source, "date": day, "link": "x"}


class TestBestHeadlines:
    def test_drops_transcripts_and_report_spam(self):
        junk = ["BILL Q1 2027 Earnings Call Transcript", "Marex Q3 Earnings Call Highlights",
                "Reprocessed Medical Devices Market Size Outlook 2033",
                "Top 10 Transformer Manufacturers in 2026"]
        kept = best_headlines([item(t) for t in junk] + [item("Eaton wins order")], 5)
        assert [h["title"] for h in kept] == ["Eaton wins order"]

    def test_drops_low_value_sources(self):
        assert best_headlines([item("Stock faces test", "ad-hoc-news.de"), item("Press item", "openPR.com")], 5) == []

    def test_trusted_source_beats_a_newer_story(self):
        items = [item("Newer", day="2026-11-06"), item("Solid", "Reuters", "2026-11-03")]
        assert [h["title"] for h in best_headlines(items, 5)] == ["Solid", "Newer"]

    def test_respects_the_limit(self):
        assert len(best_headlines([item(f"Story {i}") for i in range(9)], 4)) == 4
