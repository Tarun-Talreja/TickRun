"""Every figure in a research note must trace back to the data the model was given."""
import os
import sys
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from fact_check import find_unsupported, fact_check_section, source_block
from refresh_quotes import _ttm_fcf

SOURCE = """[Live fundamentals]
- Market cap: $522.9B
- Revenue (TTM): $44213M
- Operating margin: 44.4%
- Forward P/E: 21.4x
- Drawdown from high: -22.5%
[Recent news headlines]
- ASML plans a 30% capacity increase
"""


class TestFindUnsupported:
    def test_figures_from_the_source_pass(self):
        assert find_unsupported("Trades at 21.4x with 44.4% margins and a $522.9B cap.", SOURCE) == []

    def test_rounding_passes(self):
        assert find_unsupported("About 21x forward, 44% margins, $44.2B revenue.", SOURCE) == []

    def test_units_are_normalized(self):
        assert find_unsupported("Revenue of $44.2 billion.", SOURCE) == []

    def test_news_figures_count_as_source(self):
        assert find_unsupported("Capacity rises 30%.", SOURCE) == []

    def test_negative_source_matches_positive_claim(self):
        assert find_unsupported("Down 22.5% from the high.", SOURCE) == []

    def test_invented_peer_multiple_is_caught(self):
        assert find_unsupported("Peers like NVDA trade at ~30x.", SOURCE) == ["30x"]

    def test_wrong_money_figure_is_caught(self):
        assert find_unsupported("FCF of $42B.", SOURCE) == ["$42B"]

    def test_kinds_do_not_cross_match(self):
        assert find_unsupported("A 21.4% gain.", SOURCE) == ["21.4%"]

    def test_duplicates_reported_once(self):
        assert find_unsupported("30x then 30x again and 44.4%.", SOURCE) == ["30x"]

    def test_plain_numbers_ignored(self):
        assert find_unsupported("8/10 theme fit, 3 risks, 2-hour deep dive.", SOURCE) == []


class TestSection:
    def test_lists_unsupported(self):
        s = fact_check_section(["30x", "$42B"])
        assert "30x" in s and "$42B" in s

    def test_clean_note(self):
        assert "traced" in fact_check_section([])


def test_source_block_excludes_prompt_instructions():
    prompt = "Rule: 99x\n[Live fundamentals — now]\n- PE: 20x\nIMPORTANT GROUNDING RULES:\n15x example"
    block = source_block(prompt)
    assert "20x" in block and "99x" not in block and "15x" not in block


class TestTtmFcf:
    def _ticker(self, values):
        cols = pd.to_datetime(["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"][:len(values)])
        return SimpleNamespace(quarterly_cashflow=pd.DataFrame([values], index=["Free Cash Flow"], columns=cols))

    def test_sums_latest_four_quarters(self):
        assert _ttm_fcf(self._ticker([10, 20, 30, 40, 999])) == 100

    def test_fewer_than_four_quarters_is_unknown(self):
        assert _ttm_fcf(self._ticker([10, 20])) is None

    def test_no_fcf_row_is_unknown(self):
        assert _ttm_fcf(SimpleNamespace(quarterly_cashflow=pd.DataFrame())) is None
