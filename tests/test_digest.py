"""The home-screen summary may only state figures it was given, and must always exist."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from weekly_digest import already_written, current_movers, fallback_summary, narrative_facts, narrative_is_grounded

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


class TestNarrativeFacts:
    def test_hides_targets(self):
        assert narrative_facts({"buy_ready_at_target": ["GOOGL"], "movers": []}) == {"movers": []}


class TestFreshness:
    def test_movers_older_than_the_prices_are_left_out(self):
        sig = {"movers_updated": "2026-11-23T13:36:00Z", "price_movers": [{"ticker": "NVDA"}]}
        assert current_movers(sig, "2026-11-23T21:00:01Z") is None
        assert current_movers(sig, "2026-11-20T21:00:00Z")[0]["ticker"] == "NVDA"

    def test_rewritten_for_a_new_session_but_not_for_the_same_price(self):
        old = {"prices_as_of": "2026-11-20T21:00:00Z", "generated_at": "2026-11-23T14:00:00Z"}
        now = datetime(2026, 11, 23, 15, tzinfo=timezone.utc)
        assert already_written(old, "2026-11-20T21:00:00Z", now)
        assert not already_written(old, "2026-11-23T14:50:00Z", now)
        assert not already_written({}, "2026-11-23T14:50:00Z", now)
