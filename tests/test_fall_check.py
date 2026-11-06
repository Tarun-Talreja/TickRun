"""A stock that fell hard must have the fall explained by a real headline."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from bear_check import HEADLINES_MARKER
from fall_check import FALL_THRESHOLD_PCT, cap_confidence, fall_rule, verified_fall_reason

SOURCE = (f"- Revenue: $3B\n{HEADLINES_MARKER} — 2026-11-06]\n"
          "- [2026-10-30] Reddit stock plunges 29% after weak outlook (CNBC)\n\nRULES: be careful")


def _note(reason, evidence):
    return f"WHY_IT_FELL: {reason}\nFALL_EVIDENCE: {evidence}\nVERDICT: PASS"


def test_rule_only_for_big_falls():
    assert fall_rule(FALL_THRESHOLD_PCT - 1)
    assert fall_rule(-5) == ""
    assert fall_rule(None) == ""


def test_reason_backed_by_a_headline_is_kept():
    note = _note("Weak outlook.", "Reddit stock plunges 29% after weak outlook")
    assert verified_fall_reason(note, SOURCE) == "Weak outlook."


def test_evidence_match_ignores_case_and_quotes():
    note = _note("Weak outlook.", '"reddit STOCK plunges 29% after weak outlook"')
    assert verified_fall_reason(note, SOURCE) == "Weak outlook."


def test_invented_evidence_is_rejected():
    note = _note("Fraud.", "Reddit accused of fraud by regulators")
    assert verified_fall_reason(note, SOURCE) is None


def test_evidence_from_the_data_section_is_not_a_headline():
    assert verified_fall_reason(_note("Revenue.", "- Revenue: $3B"), SOURCE) is None


def test_evidence_from_the_rules_after_the_headlines_is_rejected():
    assert verified_fall_reason(_note("x", "RULES: be careful"), SOURCE) is None


def test_missing_lines_mean_unexplained():
    assert verified_fall_reason("VERDICT: PASS", SOURCE) is None


def test_unknown_reason_is_unexplained():
    assert verified_fall_reason(_note("unknown", "none"), SOURCE) is None


def test_confidence_capped_only_when_something_is_missing():
    assert cap_confidence("HIGH", no_news=True, fall_unexplained=False) == "LOW"
    assert cap_confidence("MEDIUM", no_news=False, fall_unexplained=True) == "LOW"
    assert cap_confidence("HIGH", no_news=False, fall_unexplained=False) == "HIGH"
