#!/usr/bin/env python3
"""
scripts/note_checks.py — Code checks on a finished note, for what prompts couldn't fix.

The model was told not to use figures from memory and did anyway: NVDA's note gave a
$35B quarter when it was $96B, MSFT's quoted Azure growth from two years ago, and MU
was rated RED FLAG twice because its real figures looked wrong to the model.

So a bull point resting on a figure or year that isn't in the data or headlines is
removed, and a RED FLAG has to quote a headline. A real bull point can be lost when
the model worked a figure out itself. That's the better mistake: this list feeds a
decision about real money.
"""

import re
from datetime import datetime, timezone

from fact_check import find_unsupported
from fall_check import in_headlines

_BULL_RE = re.compile(r"(^##\s*5\..*?$)(.*?)(?=^##\s*6)", re.MULTILINE | re.DOTALL)
_YEAR_RE = re.compile(r"(?<![\d$.,])(20[012]\d)(?![\d%])")
_EVIDENCE_RE = re.compile(r"^[\s*_#-]*RED_FLAG_EVIDENCE[\s*_]*:[\s*_]*(.+)$", re.MULTILINE)
_SERIOUS_RE = re.compile(
    r"fraud|short (?:seller|report|call)|culper|hindenburg|muddy waters|investigat|probe|sec\b|"
    r"lawsuit|going concern|bankrupt|default|restat|delist|accounting|allegation|subpoena",
    re.IGNORECASE)

RED_FLAG_RULE = """
RED FLAG needs real evidence. If your verdict is RED FLAG, put this line just before the
final lines: RED_FLAG_EVIDENCE: <one headline copied exactly from the list above>
It must report fraud, an investigation, a short-seller report, a going-concern doubt, a
restatement or a default. A figure that looks wrong to you is not evidence.
"""

RED_FLAG_RETRY = """

YOUR PREVIOUS ANSWER WAS REJECTED. You gave RED FLAG with no headline to support it. The
figures above match the company's reported statements, so they are real, however much
they differ from what you remember. Write the note again and rate the company on them.
"""


def _old_years(line: str, source: str, this_year: int) -> list[str]:
    return [y for y in _YEAR_RE.findall(line) if int(y) < this_year and y not in source]


def scrub_bull_case(text: str, source: str, this_year: int | None = None) -> tuple[str, list[str]]:
    """The note without bull points that rest on memory, and what was removed."""
    this_year = this_year or datetime.now(timezone.utc).year
    match = _BULL_RE.search(text)
    if not match:
        return text, []
    removed, lines = [], []
    for line in match.group(2).split("\n"):
        bad = (find_unsupported(line, source) + _old_years(line, source, this_year)
               if line.lstrip().startswith("-") else [])
        if bad:
            removed.extend(bad)
            line = f"- Removed: this point relied on {', '.join(bad)}, which isn't in the data or headlines."
        lines.append(line)
    return text[:match.start(2)] + "\n".join(lines) + text[match.end(2):], removed


def verified_red_flag(text: str, source: str) -> bool:
    quotes = _EVIDENCE_RE.findall(text)
    quote = in_headlines(quotes[-1], source) if quotes else None
    return bool(quote and _SERIOUS_RE.search(quote))


def final_confidence(confidence: str | None, *, no_news: bool, fall_unexplained: bool,
                     red_flag_rejected: bool, removed: list[str]) -> str | None:
    if no_news or fall_unexplained or red_flag_rejected:
        return "LOW"
    return "MEDIUM" if removed and confidence == "HIGH" else confidence


def warnings_section(*, no_news: bool, fall_unexplained: bool, red_flag_rejected: bool,
                     removed: list[str]) -> str:
    lines = []
    if no_news:
        lines.append("- No headlines were found for this stock, so this rating did not use any news.")
    if fall_unexplained:
        lines.append("- This stock fell hard and the note gives no reason backed by a headline.")
    if red_flag_rejected:
        lines.append("- The model gave RED FLAG twice with no headline to support it, so it was "
                     "replaced with WATCHLIST. Read this note with care.")
    if removed:
        lines.append(f"- Bull points were removed for using {', '.join(removed)}, not found in the data.")
    if not lines:
        return ""
    return "\n\n---\n\n## Rating warnings\n\n" + "\n".join(lines) + "\n"
