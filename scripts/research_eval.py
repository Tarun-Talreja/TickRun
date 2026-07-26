#!/usr/bin/env python3
"""
scripts/research_eval.py — Score research output quality, deterministically.

Turns "does the research look better now?" into a number, so a prompt or model
change can be judged by evidence instead of by reading a few samples and
guessing. This is what an eval harness is: a fixed rubric applied consistently,
so scores are comparable across runs.

Deliberately NOT an LLM-as-judge. An LLM judging LLM output adds its own
variance and cost on every eval run, which defeats the purpose of a stable
yardstick. Every check here is regex/structure-based and free to run as often
as you want — against every file in output/research/, not a sample.

SCORING (100 points)
  Structure   30 — are all 9 required sections present, in order, non-empty?
  Format      20 — do the 4 mandatory machine-readable lines parse correctly?
  Substance   25 — is the ANALYSIS specific, or well-formatted filler? Bull
                    bullets must carry numbers/dates and avoid banned hedging
                    ("could", "well-positioned"); bear case must not be a
                    generic ("competition"). Added after every file scored ~98
                    on structure while every bull case was empty platitudes.
  Groundedness 15 — do specific numeric claims in the text (revenue growth,
                    margins, P/E, market cap) match quotes_cache.json within
                    tolerance? This is the direct, checkable proxy for
                    hallucination: a number in the text that contradicts the
                    data it was given to work with.
  Bear check  10 — for RESEARCH-WORTHY calls, is there a real bear-case section
                    and does it look like a genuine counter-argument rather
                    than a one-line dismissal?

Usage:
    python3 scripts/research_eval.py                  # score every file, print a report
    python3 scripts/research_eval.py --file output/research/TLN_2026-07-25.md
    python3 scripts/research_eval.py --compare-before 2026-07-25   # baseline vs after that date
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_DIR   = os.path.join(SCRIPT_DIR, "output", "research")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
OUTPUT_PATH    = os.path.join(SCRIPT_DIR, "output", "research_eval.json")

REQUIRED_SECTIONS = [
    (1,  r"what.{0,20}(actually )?do"),
    (2,  r"theme fit"),
    (3,  r"quality snapshot"),
    (4,  r"valuation"),
    (5,  r"bull case"),
    (6,  r"bear case"),
    (7,  r"(three things|verify).{0,20}(before )?buying"),
    (8,  r"verdict"),
    (9,  r"confidence"),
]

NUMERIC_TOLERANCE = 0.15   # allow 15% relative difference before flagging a mismatch


def _load(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}


def _ticker_from_filename(path: str) -> str:
    return os.path.basename(path).split("_")[0]


def _score_structure(text: str) -> tuple[float, list[str]]:
    """40 pts: are the 9 numbered sections present as actual headers, in order?"""
    notes = []
    found_positions = []
    for num, pattern in REQUIRED_SECTIONS:
        m = re.search(rf"##\s*{num}\.\s*.*?{pattern}", text, re.IGNORECASE)
        if m:
            found_positions.append(m.start())
        else:
            notes.append(f"missing section {num} ({pattern})")

    present = len(found_positions)
    in_order = present == len(REQUIRED_SECTIONS) and found_positions == sorted(found_positions)
    score = 30 * (present / len(REQUIRED_SECTIONS))
    if present == len(REQUIRED_SECTIONS) and not in_order:
        score -= 5
        notes.append("sections present but out of order")
    return round(max(score, 0), 1), notes


def _score_format(text: str) -> tuple[float, list[str]]:
    """25 pts: the 4 mandatory machine-readable lines, each worth 6.25."""
    checks = {
        "VERDICT":                  r"VERDICT:\s*(RESEARCH-WORTHY|WATCHLIST|PASS|RED FLAG)",
        "CONFIDENCE":               r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW)",
        "THESIS":                   r"THESIS:\s*(.+)",
        "BUY_TRIGGER_DRAWDOWN_PCT": r"BUY_TRIGGER_DRAWDOWN_PCT:\s*(-?\d+)",
    }
    notes, hits = [], 0
    for name, pattern in checks.items():
        if re.search(pattern, text):
            hits += 1
        else:
            notes.append(f"missing/malformed {name} line")
    return round(20 * hits / len(checks), 1), notes


def _extract_numeric_claims(text: str) -> list[tuple[str, float]]:
    """Pull (label, value) pairs for claims that are directly checkable against
    quotes_cache — growth/margin percentages and multiples. Free text is full
    of numbers that aren't checkable (dates, backlog $, employee counts); this
    intentionally targets only the handful of fields we can verify."""
    claims = []
    for label, pattern in [
        ("revenue_growth", r"revenue growth[^.\n]{0,25}?(-?\d+(?:\.\d+)?)\s*%"),
        ("gross_margin",   r"gross margin[^.\n]{0,25}?(\d+(?:\.\d+)?)\s*%"),
        ("op_margin",      r"operating margin[^.\n]{0,25}?(-?\d+(?:\.\d+)?)\s*%"),
        ("forward_pe",     r"forward P/?E[^.\n]{0,25}?(-?\d+(?:\.\d+)?)\s*x"),
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                claims.append((label, float(m.group(1))))
            except ValueError:
                pass
    return claims


def _score_groundedness(text: str, ticker: str, quotes: dict) -> tuple[float, list[str]]:
    """20 pts: do numeric claims in the prose match what was actually provided?
    This only checks claims the text chose to restate — it cannot catch a
    fabricated qualitative claim (a fake contract, a fake quote), only a
    numeric one that contradicts the input data. That's a real limit, noted
    rather than hidden: see the module docstring."""
    q = quotes.get("tickers", {}).get(ticker, {})
    field_map = {
        "revenue_growth": q.get("revenue_growth"),
        "gross_margin":   q.get("gross_margin"),
        "op_margin":      q.get("op_margin"),
        "forward_pe":     q.get("forward_pe"),
    }
    claims = _extract_numeric_claims(text)
    if not claims:
        # Nothing checkable was restated in prose — neutral, not a penalty;
        # this is common when the model correctly relies on the structured
        # quality-snapshot section instead of repeating numbers in prose.
        return 15.0, ["no restated numeric claims to check (neutral)"]

    notes, matched = [], 0
    for label, claimed in claims:
        actual = field_map.get(label)
        if actual is None:
            continue
        denom = max(abs(actual), 1.0)
        if abs(claimed - actual) / denom <= NUMERIC_TOLERANCE:
            matched += 1
        else:
            notes.append(f"{label}: text says {claimed}, data says {actual:.1f}")
    checked = [c for c in claims if field_map.get(c[0]) is not None]
    if not checked:
        return 15.0, ["no checkable claims overlapped with cached fields (neutral)"]
    return round(15 * matched / len(checked), 1), notes


# NOTE: first pass only matched a few exact phrases ("positions it well") and
# missed the model's actual wording ("positions the company FOR continued
# growth"). A hand-picked phrase list is doomed to underfit — the model
# paraphrases. Widened to match the PATTERN of vague growth-speak (verb +
# "for/to" + growth-word) rather than fixed phrases, since that's what
# actually recurred: "positions X for growth", "drives further growth",
# "provides opportunities", "enables it to invest ... driving growth".
HEDGE_WORDS = (
    r"\b(could|might|may|potentially|possibly|if successful|"
    r"well[- ]positioned|strong position|"
    r"positions?\s+(?:the\s+company|it)?\s*(?:well\s+)?for|"
    r"(?:drives?|driving|drove)\s+\w*\s*(?:growth|innovation|value|demand)|"
    r"(?:enables?|allows?)\s+(?:it|the company)?\s*to\s+(?:invest|capitalize|expand)|"
    r"provides?\s+(?:additional\s+)?(?:growth\s+)?opportunit|"
    r"further\s+growth|continued\s+growth|long[- ]term\s+growth)\b"
)
GENERIC_BEAR = (
    r"\b(competition|competitive\s+(?:pressure|products|landscape)|"
    r"more\s+competitive|competitors?\s+(?:develop|could|might)|"
    r"fails?\s+to\s+achieve\s+profitability|execution\s+risk|market\s+conditions|"
    r"downturn\s+in\s+the\s+(?:market|industry))\b"
)


def _score_substance(text: str) -> tuple[float, list[str]]:
    """25 pts: is the ANALYSIS actually specific, or structurally-perfect filler?

    Added after a review found 15/15 files scoring ~98/100 on structure while
    every single bull case was hedged platitudes with no numbers — exactly what
    the prompt explicitly bans. Structure compliance was being mistaken for
    quality. A well-formed empty answer should not outscore a rough useful one.
    """
    notes = []
    bull = re.search(r"##\s*5\..*?\n(.*?)##\s*6\.", text, re.DOTALL)
    bear = re.search(r"##\s*6\.[^\n]*\n(.*?)(?:##\s*6b\.|##\s*7\.)", text, re.DOTALL)

    score = 0.0
    if bull:
        bullets = [b for b in bull.group(1).split("\n")
                   if b.strip().startswith(("*", "-")) or re.match(r"^\s*\d[.)]", b)]
        if bullets:
            # 15 pts: share of bullets carrying a concrete, checkable figure
            concrete = sum(1 for b in bullets if re.search(r"\d|\$", b))
            score += 15 * (concrete / len(bullets))
            if concrete == 0:
                notes.append("bull case has no numbers/dates — all bullets are unfalsifiable")
            # 5 pts: penalise hedging language the prompt bans outright
            hedged = sum(1 for b in bullets if re.search(HEDGE_WORDS, b, re.I))
            score += 5 * (1 - hedged / len(bullets))
            if hedged:
                notes.append(f"{hedged}/{len(bullets)} bull bullets use banned hedging language")
    else:
        notes.append("no bull case section found")

    # 5 pts: bear case must not be a banned generic
    if bear:
        if re.search(GENERIC_BEAR, bear.group(1), re.I):
            notes.append("bear case relies on a banned generic risk (competition/profitability)")
        else:
            score += 5
    else:
        notes.append("no bear case section found")

    return round(score, 1), notes


def _score_bear_check(text: str, verdict: str | None) -> tuple[float, list[str]]:
    """15 pts: RESEARCH-WORTHY calls should carry a substantive bear-case pass."""
    if verdict != "RESEARCH-WORTHY":
        return 10.0, ["not RESEARCH-WORTHY — bear check not required"]
    m = re.search(r"Bear-Case Check.*?\n\n(.+?)(?:\n\nCHANGES VERDICT|\Z)", text, re.DOTALL)
    if not m:
        return 0.0, ["no bear-case check section found"]
    body = m.group(1).strip()
    if len(body.split()) < 15:
        return 3.0, ["bear-case present but too short to be a real counter-argument"]
    return 15.0, []


def score_file(path: str, quotes: dict) -> dict:
    with open(path) as f:
        text = f.read()
    ticker = _ticker_from_filename(path)
    verdict_m = re.search(r"VERDICT:\s*(RESEARCH-WORTHY|WATCHLIST|PASS|RED FLAG)", text)
    verdict = verdict_m.group(1) if verdict_m else None

    s_struct, n_struct = _score_structure(text)
    s_fmt,    n_fmt     = _score_format(text)
    s_ground, n_ground  = _score_groundedness(text, ticker, quotes)
    s_bear,   n_bear     = _score_bear_check(text, verdict)
    s_sub,    n_sub       = _score_substance(text)
    total = round(s_struct + s_fmt + s_ground + s_bear + s_sub, 1)

    return {
        "file": os.path.relpath(path, SCRIPT_DIR),
        "ticker": ticker,
        "verdict": verdict,
        "score": total,
        "breakdown": {
            "structure": s_struct, "format": s_fmt,
            "groundedness": s_ground, "bear_check": s_bear, "substance": s_sub,
        },
        "notes": n_struct + n_fmt + n_ground + n_bear + n_sub,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="Score a single research file")
    ap.add_argument("--compare-before", metavar="YYYY-MM-DD",
                    help="Split results into before/after this date and report both averages")
    args = ap.parse_args()

    quotes = _load(QUOTES_PATH)

    if args.file:
        files = [args.file]
    else:
        files = sorted(glob.glob(os.path.join(RESEARCH_DIR, "*.md")))
    if not files:
        print("No research files found.")
        sys.exit(0)

    results = [score_file(f, quotes) for f in files]

    if args.file:
        r = results[0]
        print(f"{r['ticker']} — {r['score']}/100")
        for k, v in r["breakdown"].items():
            print(f"  {k:14s} {v}")
        if r["notes"]:
            print("  notes:")
            for n in r["notes"]:
                print(f"    - {n}")
        return

    avg = round(sum(r["score"] for r in results) / len(results), 1)
    print(f"📊 Scored {len(results)} research files — average {avg}/100\n")

    for dim in ("structure", "format", "groundedness", "bear_check", "substance"):
        dim_avg = round(sum(r["breakdown"][dim] for r in results) / len(results), 1)
        print(f"  {dim:14s} avg {dim_avg}")

    if args.compare_before:
        before, after = [], []
        for r, f in zip(results, files):
            date_m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
            if not date_m:
                continue
            (before if date_m.group(1) < args.compare_before else after).append(r["score"])
        b_avg = round(sum(before) / len(before), 1) if before else None
        a_avg = round(sum(after) / len(after), 1) if after else None
        print(f"\n  BEFORE {args.compare_before}: {len(before)} files, avg {b_avg}")
        print(f"  AFTER  {args.compare_before}: {len(after)} files, avg {a_avg}")
        if b_avg is not None and a_avg is not None:
            print(f"  DELTA: {a_avg - b_avg:+.1f}")

    print("\nWorst 5:")
    for r in sorted(results, key=lambda r: r["score"])[:5]:
        print(f"  {r['score']:5.1f}  {r['ticker']:6s} {os.path.basename(r['file'])}")

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(results), "average": avg, "results": results,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n✅ Eval report → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
