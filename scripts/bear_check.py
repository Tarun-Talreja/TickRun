#!/usr/bin/env python3
"""
scripts/bear_check.py — Second pass that can downgrade a RESEARCH-WORTHY call.

WHY IT WORKS THIS WAY
Asking the model to judge its own argument failed in both directions. "Does this
change the verdict?" came back YES in 75 of 75 notes; a three-level severity grade
came back MATERIAL every time. Either way the answer carried no information.

So the model no longer grades anything. It names one of three specific breaks and
copies the line that proves it, and code checks that line really is in the data or
headlines. It also sees the data now: it used to get only the first 2,500
characters of the note, so it could not catch a figure that contradicted the data.
"""

import re

# Bump when the research prompt, bear check or verdict rules change. Every rating
# made under an older number goes back in the research queue on its own. Without
# this, six stocks kept a downgrade from a check that had already been replaced.
RATING_VERSION = 4   # 4: bull points from memory removed, RED FLAG needs a headline

BREAK_TYPES = ("DATA_CONTRADICTION", "THESIS_CONTRADICTED", "BUSINESS_EVENT")
MIN_EVIDENCE_CHARS = 12   # shorter than this matches by luck, not because it's a real line
HEADLINES_MARKER = "[Recent news headlines"

_BREAK_RE = re.compile(r"^[\s*_#-]*BREAK[\s*_]*:[\s*_]*([A-Z_]+)", re.MULTILINE)
_EVIDENCE_RE = re.compile(r"^[\s*_#-]*EVIDENCE[\s*_]*:[\s*_]*(.+)$", re.MULTILINE)


def bear_prompt(ticker: str, note: str, source: str) -> str:
    return f"""Below is the data and headlines a research note on {ticker} was given, then the note.

First, in 2-3 sentences, give the strongest specific argument against buying {ticker}.

Then decide whether one of these three breaks is present. Most notes have none, and
a strong argument is not a break. Answer NONE unless one clearly applies:

DATA_CONTRADICTION: two figures in the DATA cannot both be true (a margin above 100%,
or net cash several times the market cap). A figure that looks unusually large or
small is not a contradiction, and neither is a figure that differs from what you
remember: this data is newer than your memory. Gross margin is trailing twelve
months and operating margin is the latest quarter, so they may sit close together.

THESIS_CONTRADICTED: the note's central claim says the opposite of the DATA (the note
says revenue is growing fast, the DATA shows it shrinking). A figure that points the
same way but is larger or smaller than the note says is not a contradiction.

BUSINESS_EVENT: a HEADLINE reports something that has already happened and removes
the core business case: fraud charges, restated results, an auditor resigning,
bankruptcy, losing the largest customer, or withdrawn guidance.

These are never breaks: valuation, a risk that might happen later, customer
concentration, competition, cycles, geopolitics, share-price falls, analyst changes,
lawsuits or investigations with no finding yet, and anything marked unverified.

End with exactly these two lines:
BREAK: <NONE, DATA_CONTRADICTION, THESIS_CONTRADICTED or BUSINESS_EVENT>
EVIDENCE: <the exact line copied from the DATA or HEADLINES, or none. Separate two lines with ;>

DATA AND HEADLINES:
{source}

NOTE:
{note}
"""


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def _evidence_scope(break_type: str, source: str) -> str:
    """Events must come from a headline; contradictions must come from the data."""
    data, _, headlines = source.partition(HEADLINES_MARKER)
    return headlines if break_type == "BUSINESS_EVENT" else data


def verified_break(bear_text: str | None, source: str) -> str | None:
    """The break type, but only if its quoted evidence really is in the source."""
    if not bear_text:
        return None
    kind = _BREAK_RE.findall(bear_text)
    quote = _EVIDENCE_RE.findall(bear_text)
    if not kind or not quote or kind[-1] not in BREAK_TYPES:
        return None
    # A contradiction needs two lines, so a quote may hold several, split by ";".
    parts = [_normalise(p).strip(' "“”\'`*-') for p in quote[-1].split(";")]
    scope = _normalise(_evidence_scope(kind[-1], source))
    found = [len(p) >= MIN_EVIDENCE_CHARS and p in scope for p in parts]
    # Two data lines must both be real. Other breaks need one real line, since
    # the model often adds the note's own claim beside it.
    real = all(found) if kind[-1] == "DATA_CONTRADICTION" else any(found)
    return kind[-1] if real else None
