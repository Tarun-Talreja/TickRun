"""The home-screen summary may only state figures it was given, and must always exist."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from weekly_digest import fallback_summary, narrative_is_grounded

FACTS = {"movers": [{"ticker": "AMD", "pct": -17.3}],
         "field_news": {"Networking": "Marvell agreed to buy Lumentum for $115 billion."}}


class TestGrounded:
    def test_figures_from_the_facts_pass(self):
        assert narrative_is_grounded("AMD fell 17.3% and Marvell's deal is worth $115 billion.", FACTS)

    def test_invented_figure_fails(self):
        assert not narrative_is_grounded("AMD fell 40% this week.", FACTS)


class TestFallback:
    def test_uses_checked_field_summaries(self):
        fields = {"a": {"name": "Networking", "summary": "Marvell buys Lumentum."},
                  "b": {"name": "Empty", "summary": None}}
        assert fallback_summary(fields) == "Networking: Marvell buys Lumentum."

    def test_limits_length(self):
        fields = {str(i): {"name": f"F{i}", "summary": f"S{i}."} for i in range(9)}
        assert fallback_summary(fields).count(":") == 3

    def test_nothing_to_say(self):
        assert fallback_summary({}) is None
