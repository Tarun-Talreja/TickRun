#!/usr/bin/env python3
"""
scripts/fact_check.py — Trace every figure in a research note back to its source.

THE PROBLEM THIS SOLVES
The model is told to use only the data it is given, and it still adds numbers
of its own: "NVDA ~30x" in an ASML note while the app showed NVDA at 11x, or a
"10-year average" margin it was never shown. The eval harness scores structure
and could not see this: TSM scored 97.5/100 with its revenue wrong by 30x.

So: pull every $ amount, percentage and multiple out of the note, and report any
that match nothing in the data block. This proves a figure came from the source,
not that the source is right, and it reports derived figures too (a PEG the
model worked out). Treat a listed figure as unverified, not as false.
"""

import re

# A claim this close to a source figure is the same figure, rounded.
REL_TOLERANCE = 0.02
ROUNDING_TOLERANCE = 0.5   # "21x" for 21.4x, "44%" for 44.4%

_FIGURE_RE = re.compile(
    r"(?<![\w.])(?:"
    r"\$\s?(?P<money>\d[\d,]*\.?\d*)\s?(?P<unit>trillion|billion|million|[TBM])?\b"
    r"|(?P<num>\d[\d,]*\.?\d*)\s?(?P<sym>%|x\b)"
    r")",
    re.IGNORECASE,
)
_UNIT_SCALE = {"t": 1e12, "b": 1e9, "m": 1e6}


def _figures(text: str) -> list[tuple[str, float, str]]:
    """Return (kind, value, as_written) for each figure in text."""
    found = []
    for m in _FIGURE_RE.finditer(text):
        label = m.group(0).rstrip(".,")
        if m.group("money"):
            unit = (m.group("unit") or "")[:1].lower()
            value = float(m.group("money").replace(",", "").rstrip(".")) * _UNIT_SCALE.get(unit, 1)
            found.append(("money", value, label))
        else:
            value = float(m.group("num").replace(",", "").rstrip("."))
            found.append((m.group("sym").lower(), value, label))
    return found


def _matches(kind: str, claim: float, source: float) -> bool:
    if abs(claim - source) <= abs(source) * REL_TOLERANCE:
        return True
    return kind != "money" and abs(claim - source) <= ROUNDING_TOLERANCE


def find_unsupported(text: str, source: str) -> list[str]:
    """Figures in text that match nothing of the same kind in source."""
    known = _figures(source)
    unsupported = []
    for kind, value, label in _figures(text):
        supported = any(k == kind and _matches(kind, value, v) for k, v, _ in known)
        if not supported and label not in unsupported:
            unsupported.append(label)
    return unsupported


def source_block(prompt: str) -> str:
    """The data the model was given, without the prompt's instructions and examples."""
    start = max(prompt.find("[Live fundamentals"), 0)
    end = prompt.find("IMPORTANT GROUNDING RULES")
    return prompt[start:end if end != -1 else len(prompt)]


def fact_check_section(unsupported: list[str]) -> str:
    if not unsupported:
        return "\n\n---\n\n## Fact-check\n\nEvery figure traced to the source data.\n"
    return (
        "\n\n---\n\n## Fact-check\n\n"
        "These figures were NOT in the data given to the model. They may be derived "
        "or come from its memory, so verify them before relying on them:\n\n"
        + "".join(f"- {figure}\n" for figure in unsupported)
    )
