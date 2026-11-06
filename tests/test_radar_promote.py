"""Radar picks get researched; only strong results stay on the watchlist."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from radar_promote import MAX_ADDS, add_to_markdown, choose, split_results

CARD = {"tracked": False, "rating": None, "new": True}


class TestChoose:
    def test_takes_untracked_unrated_cards_in_order(self):
        cards = [{**CARD, "ticker": "A"}, {**CARD, "ticker": "B", "tracked": True},
                 {**CARD, "ticker": "C", "rating": "PASS"}, {**CARD, "ticker": "D"}]
        assert choose(cards, 5) == ["A", "D"]

    def test_respects_the_limit(self):
        assert choose([{**CARD, "ticker": t} for t in "ABCD"], 2) == ["A", "B"]


class TestSplitResults:
    def test_keeps_only_worth_researching_up_to_the_cap(self):
        results = {f"T{i}": "RESEARCH-WORTHY" for i in range(MAX_ADDS + 1)}
        keep, drop = split_results({**results, "X": "PASS", "Y": None})
        assert len(keep) == MAX_ADDS
        assert set(drop) == {f"T{MAX_ADDS}", "X", "Y"}


class TestMarkdown:
    TEXT = "## Candidates to watch\nMETA\n\n## Index benchmarks (always include)\nSPY\n"

    def test_adds_a_discovered_section_once(self):
        once = add_to_markdown(self.TEXT, ["ABC"])
        twice = add_to_markdown(once, ["DEF"])
        assert twice.count("## Discovered by the radar") == 1
        assert "ABC\n" in twice and "DEF\n" in twice

    def test_does_not_add_a_ticker_twice(self):
        once = add_to_markdown(self.TEXT, ["ABC"])
        assert add_to_markdown(once, ["ABC"]).count("ABC") == 1
