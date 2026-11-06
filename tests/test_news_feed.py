"""Per-stock headlines: they must reach the research, and a broken feed must be loud."""
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import news_feed
from news_feed import NO_NEWS, NewsUnavailable, company_terms, pick_news, short_name


def _h(title, source="Yahoo Finance", date="2026-11-06"):
    return {"title": title, "source": source, "date": date, "link": "http://x"}


@pytest.mark.parametrize("raw,short", [
    ("Reddit, Inc.", "Reddit"), ("Vistra Corp.", "Vistra"), ("Vertiv Holdings Co", "Vertiv"),
    ("Eaton Corporation plc", "Eaton"), ("Lumentum Holdings Inc.", "Lumentum"),
])
def test_short_name_drops_legal_suffixes(raw, short):
    assert short_name(raw) == short


def test_aliases_replace_names_nobody_uses():
    assert company_terms("TSM", "Taiwan Semiconductor Manufacturing Company")[0] == "TSMC"


def test_one_letter_ticker_is_not_a_search_term():
    assert "V" not in company_terms("V", "Visa Inc.")


def test_keeps_only_headlines_about_the_company():
    items = [_h("Reddit shares plunge"), _h("EU charges TikTok over algorithms")]
    assert [n["title"] for n in pick_news(items, ["Reddit"], 5)] == ["Reddit shares plunge"]


def test_constellation_energy_does_not_pick_up_constellation_brands():
    items = [_h("Constellation Brands cuts forecast"), _h("Constellation Energy beats")]
    terms = company_terms("CEG", "Constellation Energy Corporation")
    assert [n["title"] for n in pick_news(items, terms, 5)] == ["Constellation Energy beats"]


def test_older_earnings_story_outranks_newer_filler():
    items = [_h("Reddit highlights gaming communities", date="2026-11-06"),
             _h("Reddit stock plunges after weak guidance", source="CNBC", date="2026-10-30")]
    assert pick_news(items, ["Reddit"], 1)[0]["date"] == "2026-10-30"


def test_shown_newest_first_and_in_the_dashboard_shape():
    items = [_h("Reddit misses", date="2026-10-01"), _h("Reddit beats", date="2026-11-01")]
    picked = pick_news(items, ["Reddit"], 5)
    assert [n["date"] for n in picked] == ["2026-11-01", "2026-10-01"]
    assert set(picked[0]) == {"title", "publisher", "date", "url"}


def test_broken_feed_raises_instead_of_looking_like_no_news(monkeypatch):
    def down(*_):
        raise NewsUnavailable("feed down")
    monkeypatch.setattr(news_feed, "_search", down)
    with pytest.raises(NewsUnavailable):
        news_feed.get_recent_news("RDDT", name="Reddit, Inc.")
    assert news_feed.fetch_news("RDDT", name="Reddit, Inc.") == []


def test_quiet_stock_says_so(monkeypatch):
    monkeypatch.setattr(news_feed, "_search", lambda *_: [])
    assert news_feed.get_recent_news("RDDT", name="Reddit, Inc.") == NO_NEWS


def test_block_page_counts_as_a_failure(monkeypatch):
    class Page:
        content = b"<html>unusual traffic</html>"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(news_feed.requests, "get", lambda *a, **k: Page())
    monkeypatch.setattr(news_feed, "RETRY_WAIT_SECONDS", 0)
    with pytest.raises(NewsUnavailable):
        news_feed._search("x")


def test_network_error_counts_as_a_failure(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no route")
    monkeypatch.setattr(news_feed.requests, "get", boom)
    monkeypatch.setattr(news_feed, "RETRY_WAIT_SECONDS", 0)
    with pytest.raises(NewsUnavailable):
        news_feed._search("x")
