#!/usr/bin/env python3
"""
scripts/fall_check.py — A stock that fell hard must have the fall explained.

RDDT's note called it reasonably valued without mentioning that it had just dropped
29% on weak guidance. A big fall is the most important fact about a stock, so a note
must give the reason and quote the headline it comes from. Code checks the quote is
real. With no verified reason, the stock page says so and confidence drops to LOW.
"""

import re

from bear_check import HEADLINES_MARKER, MIN_EVIDENCE_CHARS, _normalise

FALL_THRESHOLD_PCT = -25.0
# The quote has to be about a fall. VST's note cited a headline saying shares rose and
# invented the reason for its fall, and a real quote alone let that through.
_DOWN_RE = re.compile(
    r"\b(?:plunge\w*|sinks?|sank|falls?|fell|drops?|tumbl\w+|slump\w*|slides?|selloff|sell-off|"
    r"rout|crash\w*|declin\w+|weak\w*|miss(?:es)?|cuts?|lower\w*|down|worr\w+|concerns?|fears?|"
    r"squeez\w+|hit|hurt\w*|loses?|losses)\b", re.IGNORECASE)
_UP_RE = re.compile(r"\b(?:rises?|rose|surg\w+|soar\w*|jumps?|rall\w+|climbs?|gains?|pops?)\b",
                    re.IGNORECASE)

_REASON_RE = re.compile(r"^[\s*_#-]*WHY_IT_FELL[\s*_]*:[\s*_]*(.+)$", re.MULTILINE)
_EVIDENCE_RE = re.compile(r"^[\s*_#-]*FALL_EVIDENCE[\s*_]*:[\s*_]*(.+)$", re.MULTILINE)


def fall_rule(drawdown: float | None) -> str:
    """Extra instruction for the prompt, only for stocks that fell hard."""
    if drawdown is None or drawdown > FALL_THRESHOLD_PCT:
        return ""
    return f"""
THIS STOCK IS {abs(drawdown):.0f}% BELOW ITS HIGH. Explain why, using the headlines above.
Put these two lines just before the final lines of your response:
WHY_IT_FELL: <one plain sentence, or unknown if the headlines don't explain it>
FALL_EVIDENCE: <one headline copied exactly from the list above, or none>
Let the reason shape your verdict: a cheap multiple after a fall is not a bargain if
the reason for the fall also breaks the thesis.
"""


def _headlines_only(source: str) -> str:
    return source.partition(HEADLINES_MARKER)[2].split("\n\n")[0]


def in_headlines(quote: str, source: str) -> str | None:
    """The quote, normalised, if it really is one of the headlines given to the model."""
    quote = _normalise(quote).strip(' "“”\'`*-')
    if len(quote) < MIN_EVIDENCE_CHARS or quote not in _normalise(_headlines_only(source)):
        return None
    return quote


def verified_fall_reason(text: str, source: str) -> str | None:
    """The stated reason, but only if its quoted headline is really in the list."""
    reasons, quotes = _REASON_RE.findall(text), _EVIDENCE_RE.findall(text)
    if not reasons or not quotes:
        return None
    quote = in_headlines(quotes[-1], source)
    if not quote or not _DOWN_RE.search(quote) or _UP_RE.search(quote):
        return None
    return reasons[-1].strip()


