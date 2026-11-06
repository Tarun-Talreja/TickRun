#!/usr/bin/env python3
"""
scripts/bear_eval.py — Does the bear check tell real breaks from ordinary risks?

Runs the live check on real notes (should pass), the same notes with one planted
break (should be caught), and ordinary bad news (should pass). Planted text exists
only in memory for this run. It is never saved to a note or shown in the app.

Runs in CI, where the key lives: Actions -> "Bear Check Eval".
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from glob import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bear_check import HEADLINES_MARKER, bear_prompt, verified_break
from fact_check import source_block
from research_ticker import OUTPUT_DIR, QUOTES_PATH, SCRIPT_DIR, _build_prompt, _call_llm

CASES_PATH = os.path.join(SCRIPT_DIR, "tests", "fixtures_bear_cases.json")
TRIALS = 2
WORKERS = 4
MIN_CATCH_RATE = 0.85        # free models are noisy, so allow the odd miss
MAX_FALSE_ALARM_RATE = 0.05


def passed(caught: int, planted: int, false_alarms: int, clean: int) -> bool:
    return caught / planted >= MIN_CATCH_RATE and false_alarms / clean <= MAX_FALSE_ALARM_RATE


def _latest_note(ticker: str) -> str:
    path = max(glob(os.path.join(OUTPUT_DIR, f"{ticker}_2*.md")))
    with open(path) as f:
        return re.split(r"\n---\n\n## (?:Bear-Case Check|Fact-check)", f.read())[0]


@lru_cache(maxsize=None)
def _real_source(ticker: str) -> str:
    with open(QUOTES_PATH) as f:
        return source_block(_build_prompt(ticker, json.load(f)))


def apply_plant(source: str, case: dict) -> str:
    """Return source with the case's one planted line or headline."""
    if "set_line" in case:
        prefix, line = case["set_line"]
        lines = [line if ln.startswith(prefix) else ln for ln in source.split("\n")]
        return "\n".join(lines)
    if "headline" in case:
        head, marker, rest = source.partition(HEADLINES_MARKER)
        title, newline, news = rest.partition("\n")
        return f"{head}{marker}{title}{newline}- [2026-11-06] {case['headline']} (Reuters)\n{news}"
    return source


def _run(job: tuple[dict, bool]) -> tuple[str, bool, str | None, str]:
    case, want_break = job
    source = apply_plant(_real_source(case["ticker"]), case)
    key = os.environ["NVIDIA_API_KEY"]
    text = _call_llm("nvidia", key, bear_prompt(case["ticker"], _latest_note(case["ticker"]), source))
    found = verified_break(text, source)
    return case["id"], want_break, found, text[-260:].replace("\n", " | ")


def main() -> None:
    with open(CASES_PATH) as f:
        cases = json.load(f)
    jobs = [({"id": f"real_{t}", "ticker": t}, False) for t in cases["real_notes"]]
    jobs += [(c, True) for c in cases["planted_breaks"]]
    jobs += [(c, False) for c in cases["hard_negatives"]]

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(_run, jobs * TRIALS))

    wrong = [r for r in results if bool(r[2]) != r[1]]
    caught = sum(1 for r in results if r[1] and r[2])
    planted = sum(1 for r in results if r[1])
    false_alarms = sum(1 for r in results if not r[1] and r[2])
    for case_id, want_break, found, tail in wrong:
        print(f"WRONG {case_id}: expected {'break' if want_break else 'none'}, got {found}\n      {tail}")
    print(f"\nBreaks caught: {caught}/{planted}")
    print(f"False alarms:  {false_alarms}/{len(results) - planted}")
    sys.exit(0 if passed(caught, planted, false_alarms, len(results) - planted) else 1)


if __name__ == "__main__":
    main()
