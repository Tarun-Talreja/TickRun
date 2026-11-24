"""A stock's label, from filed facts and serious events only.

It describes the business, not whether to buy. The buy-below price is not used: it failed
its test (docs/BACKTEST_RULES.md), and the AI's rating isn't either, since it flips between runs.
"""

MAX_FAILED = 1
MIN_KNOWN = 4
LABELS = {"serious": "Serious news", "weak": "Fails checks", "solid": "Passes checks", "unknown": "Not enough data"}


def category(quality: dict | None, events: dict | None) -> dict:
    serious = (events or {}).get("serious", [])
    if serious:
        newest = max(serious, key=lambda e: e["date"])
        return _label("serious", f"{newest['text']} ({newest['source']}, {newest['date']})")
    if not quality:
        return _label("unknown", "No US filings with the figures needed")
    failed = [c for c in quality["checks"] if c["ok"] is False]
    if len(failed) > MAX_FAILED or any(c.get("chronic") for c in failed):
        return _label("weak", f"Fails {len(failed)} of {quality['known']} checks: "
                              + "; ".join(f"{c['name'].lower()} ({c['detail']})" for c in failed))
    if quality["known"] < MIN_KNOWN:
        return _label("unknown", f"Only {quality['known']} of 5 checks have figures")
    missed = f". Misses: {failed[0]['name'].lower()} ({failed[0]['detail']})" if failed else ""
    return _label("solid", f"Passes {quality['passed']} of {quality['known']} checks{missed}")


def _label(key: str, why: str) -> dict:
    return {"key": key, "label": LABELS[key], "why": why}
