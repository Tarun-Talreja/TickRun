"""Company-reported cash flow must be read word for word from the filed earnings release."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from company_measures import MEASURES, find_measure, release_text

# Wording copied from the filed releases (VST 2026-11-06, TLN 2026-11-03, CEG 2026-11-09).
VST = ("Other, net 5 5 - - 5 5 Adjusted free cash flow before growth guidance $ 4,300 $ 4,700 "
       "$ (170) $ (170) $ 4,130 $ 4,530 ___________")
TLN = ("Reaffirming 2026 Adjusted EBITDA and Adjusted Free Cash Flow guidance ranges to $2,050 million - "
       "$2,200 million and $1,225 million - $1,325 million, respectively. Introducing 2027")
CEG = ("Raising midpoint and narrowing full-year Adjusted (non-GAAP) Operating Earnings guidance range "
       "to $12.50 - $12.80 per share Agreed to Acquire")


def test_vst_consolidated_range_in_millions():
    out = find_measure("VST", VST)
    assert (out["low"], out["high"], out["mid"]) == (4300e6, 4700e6, 4500e6)
    assert out["kind"] == "cash_flow_total" and "4,300" in out["quote"]


def test_tln_takes_the_cash_flow_range_not_ebitda():
    out = find_measure("TLN", TLN)
    assert (out["low"], out["high"]) == (1225e6, 1325e6)


def test_ceg_earnings_per_share():
    out = find_measure("CEG", CEG)
    assert (out["low"], out["high"], out["kind"]) == (12.50, 12.80, "earnings_per_share")


def test_changed_wording_gives_nothing():
    assert find_measure("VST", "Adjusted free cash flow guidance was updated") is None


def test_company_without_a_rule_gives_nothing():
    assert "AAPL" not in MEASURES and find_measure("AAPL", VST) is None


def test_release_text_strips_markup_and_entities():
    html = "<p>Guidance&#160;range&nbsp;to $12.50 &#8211; $12.80</p>"
    assert release_text(html) == "Guidance range to $12.50 - $12.80"
