"""Code checks that catch what the model does despite the prompt."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from bear_check import HEADLINES_MARKER
from note_checks import final_confidence, scrub_bull_case, verified_red_flag, warnings_section
from research_batch import has_new_results

SOURCE = (f"- Latest reported quarter: revenue $96.20B\n- FCF (TTM): $127.0B\n"
          f"{HEADLINES_MARKER} — 2026-11-06]\n"
          "- [2026-10-30] Cerebras fell after Culper Research issued a short call (Yahoo)\n"
          "- [2026-11-05] Micron plunges 17% amid chip selloff (Seeking Alpha)\n")


def _note(*bullets):
    return "## 5. The bull case\n" + "\n".join(bullets) + "\n\n## 6. The bear case\n$999B risk\n"


class TestBullCase:
    def test_memory_figure_is_removed(self):
        text, removed = scrub_bull_case(_note("- Quarter revenue was ~$35.1B."), SOURCE, 2026)
        assert removed == ["$35.1B"]
        assert "35.1B." not in text.split("Removed")[0] and "Removed" in text

    def test_supported_point_stays(self):
        note = _note("- Latest quarter revenue was $96.2B with FCF of $127B.")
        assert scrub_bull_case(note, SOURCE, 2026) == (note, [])

    def test_stale_year_is_removed(self):
        _, removed = scrub_bull_case(_note("- Azure growth accelerated in Q1 FY2024."), SOURCE, 2026)
        assert removed == ["2024"]

    def test_this_year_is_fine(self):
        assert scrub_bull_case(_note("- Guidance was raised for 2026."), SOURCE, 2026)[1] == []

    def test_bear_case_is_left_alone(self):
        text, removed = scrub_bull_case(_note("- Fine point."), SOURCE, 2026)
        assert removed == [] and "$999B risk" in text

    def test_note_without_the_section_is_unchanged(self):
        assert scrub_bull_case("no sections", SOURCE, 2026) == ("no sections", [])


class TestRedFlag:
    def test_short_report_headline_counts(self):
        text = "RED_FLAG_EVIDENCE: Cerebras fell after Culper Research issued a short call\nVERDICT: RED FLAG"
        assert verified_red_flag(text, SOURCE)

    def test_no_evidence_fails_as_with_mu(self):
        assert not verified_red_flag("VERDICT: RED FLAG", SOURCE)

    def test_a_price_drop_is_not_evidence(self):
        assert not verified_red_flag("RED_FLAG_EVIDENCE: Micron plunges 17% amid chip selloff", SOURCE)

    def test_invented_headline_fails(self):
        assert not verified_red_flag("RED_FLAG_EVIDENCE: Micron under SEC fraud investigation", SOURCE)


class TestConfidence:
    def _final(self, confidence="HIGH", no_news=False, fall=False, rejected=False, removed=()):
        return final_confidence(confidence, no_news=no_news, fall_unexplained=fall,
                                red_flag_rejected=rejected, removed=list(removed))

    def test_clean_note_keeps_it(self):
        assert self._final() == "HIGH"

    def test_removed_points_cost_high(self):
        assert self._final(removed=["$35B"]) == "MEDIUM"

    def test_removed_points_leave_low_alone(self):
        assert self._final("LOW", removed=["$35B"]) == "LOW"

    def test_missing_evidence_means_low(self):
        assert self._final(no_news=True) == self._final(fall=True) == self._final(rejected=True) == "LOW"


def test_warnings_explain_each_problem():
    text = warnings_section(no_news=False, fall_unexplained=True, red_flag_rejected=True, removed=["$35B"])
    assert "fell hard" in text and "WATCHLIST" in text and "$35B" in text
    assert warnings_section(no_news=False, fall_unexplained=False, red_flag_rejected=False, removed=[]) == ""


class TestNewResults:
    NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)

    def _stamp(self, when):
        return int(when.timestamp())

    def test_earnings_after_the_rating_requeues(self):
        c = {"rated_next_earnings": self._stamp(self.NOW - timedelta(days=1)), "last_researched": "2026-11-07"}
        assert has_new_results(c, {}, self.NOW)

    def test_waits_for_headlines_to_appear(self):
        c = {"rated_next_earnings": self._stamp(self.NOW - timedelta(hours=1)), "last_researched": "2026-11-07"}
        assert not has_new_results(c, {}, self.NOW)

    def test_rating_after_the_report_is_not_requeued(self):
        c = {"rated_next_earnings": self._stamp(self.NOW - timedelta(days=5)), "last_researched": "2026-11-09"}
        assert not has_new_results(c, {}, self.NOW)

    def test_new_quarter_requeues_as_when_yahoo_catches_up(self):
        c = {"rated_quarter_end": "2026-06-30"}
        assert has_new_results(c, {"latest_quarter_end": "2026-09-30"}, self.NOW)

    def test_same_quarter_does_not(self):
        c = {"rated_quarter_end": "2026-09-30"}
        assert not has_new_results(c, {"latest_quarter_end": "2026-09-30"}, self.NOW)
