"""The bear check downgrades only on a named break backed by an exact quote."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from bear_check import bear_prompt, verified_break

SOURCE = """[Live fundamentals — 2026-11-06]
- Revenue growth (latest quarter vs a year ago, NOT trailing-twelve-month): -12.0%
- Market cap: $50.0B

[Recent news headlines — 2026-11-06]
- [2026-11-05] Acme restates three years of results after audit review (Reuters)
- [2026-11-04] Acme shares fall with the market (Yahoo)
"""


def bear(kind, evidence):
    return f"Short-seller argument.\nBREAK: {kind}\nEVIDENCE: {evidence}"


class TestVerifiedBreak:
    def test_headline_event_with_exact_quote(self):
        text = bear("BUSINESS_EVENT", "Acme restates three years of results after audit review")
        assert verified_break(text, SOURCE) == "BUSINESS_EVENT"

    def test_data_quote_ignores_case_spacing_and_quotes(self):
        text = bear("THESIS_CONTRADICTED",
                    '"revenue growth (latest quarter vs a year  ago, NOT trailing-twelve-month): -12.0%"')
        assert verified_break(text, SOURCE) == "THESIS_CONTRADICTED"

    def test_none_never_downgrades(self):
        assert verified_break(bear("NONE", "none"), SOURCE) is None

    def test_invented_quote_does_not_count(self):
        text = bear("BUSINESS_EVENT", "Acme loses its largest customer")
        assert verified_break(text, SOURCE) is None

    def test_event_must_come_from_a_headline(self):
        text = bear("BUSINESS_EVENT", "Market cap: $50.0B")
        assert verified_break(text, SOURCE) is None

    def test_data_break_must_come_from_the_data(self):
        text = bear("DATA_CONTRADICTION", "Acme shares fall with the market")
        assert verified_break(text, SOURCE) is None

    def test_scrap_of_a_line_does_not_count(self):
        assert verified_break(bear("THESIS_CONTRADICTED", "-12"), SOURCE) is None

    def test_contradiction_can_quote_two_lines(self):
        text = bear("DATA_CONTRADICTION",
                    "- Market cap: $50.0B; - Revenue growth (latest quarter vs a year ago, "
                    "NOT trailing-twelve-month): -12.0%")
        assert verified_break(text, SOURCE) == "DATA_CONTRADICTION"

    def test_every_quoted_line_must_be_real(self):
        text = bear("DATA_CONTRADICTION", "- Market cap: $50.0B; - Revenue (TTM): $900000M")
        assert verified_break(text, SOURCE) is None

    def test_thesis_break_may_also_quote_the_note(self):
        text = bear("THESIS_CONTRADICTED",
                    "Revenue growth (latest quarter vs a year ago, NOT trailing-twelve-month): "
                    "-12.0%; Revenue growth (YoY): 26.1%")
        assert verified_break(text, SOURCE) == "THESIS_CONTRADICTED"

    def test_thesis_break_needs_a_real_data_line(self):
        text = bear("THESIS_CONTRADICTED", "Revenue growth (YoY): 26.1%; none")
        assert verified_break(text, SOURCE) is None

    def test_markdown_labels_still_parse(self):
        text = ("Argument.\n**BREAK:** BUSINESS_EVENT\n"
                "**EVIDENCE:** Acme restates three years of results after audit review")
        assert verified_break(text, SOURCE) == "BUSINESS_EVENT"

    def test_old_formats_and_missing_text_do_nothing(self):
        assert verified_break("CHANGES VERDICT: YES", SOURCE) is None
        assert verified_break("BEAR_SEVERITY: THESIS-BREAKING", SOURCE) is None
        assert verified_break(None, SOURCE) is None


class TestBearPrompt:
    def test_gets_the_data_and_the_whole_note(self):
        note = "x" * 5000 + "THE END OF THE NOTE"
        prompt = bear_prompt("ACME", note, SOURCE)
        assert "THE END OF THE NOTE" in prompt
        assert "Market cap: $50.0B" in prompt
        assert "Acme restates" in prompt


class TestEvalPlants:
    def test_planted_headline_lands_in_the_headlines(self):
        from bear_eval import apply_plant
        planted = apply_plant(SOURCE, {"headline": "Acme loses its largest customer"})
        text = bear("BUSINESS_EVENT", "Acme loses its largest customer")
        assert verified_break(text, planted) == "BUSINESS_EVENT"
        assert verified_break(text, SOURCE) is None

    def test_planted_line_replaces_the_real_one(self):
        from bear_eval import apply_plant
        planted = apply_plant(SOURCE, {"set_line": ["- Market cap", "- Market cap: $9.0B"]})
        assert "- Market cap: $9.0B" in planted and "$50.0B" not in planted


class TestEvalThresholds:
    def test_passes_at_the_bar(self):
        from bear_eval import passed
        assert passed(caught=17, planted=18, false_alarms=1, clean=38)

    def test_missing_too_many_breaks_fails(self):
        from bear_eval import passed
        assert not passed(caught=14, planted=18, false_alarms=0, clean=38)

    def test_too_many_false_alarms_fails(self):
        from bear_eval import passed
        assert not passed(caught=18, planted=18, false_alarms=3, clean=38)
