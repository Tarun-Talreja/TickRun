"""Past Home summaries, one entry per day, so a missed one can still be read."""
import json
import os

from io_utils import load_json

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_PATH = os.path.join(SCRIPT_DIR, "data", "summary_history.json")
KEPT_DAYS = 60
# Price moves are already in the summary and would repeat under the next morning's date.
KEPT_KINDS = {"verdict_change", "sec_stake", "data_warning", "catalyst"}


def with_summary(days: dict, day: str, narrative: str, prices_as_of: str) -> dict:
    """The day's latest summary replaces its earlier ones."""
    return _trim({**days, day: {**days.get(day, {}), "narrative": narrative, "prices_as_of": prices_as_of}})


def with_changes(days: dict, day: str, items: list[dict]) -> dict:
    """Changes seen at any time that day are added, never replaced."""
    old = days.get(day, {}).get("changes", [])
    seen = {c["headline"] for c in old}
    new = [{"headline": i["headline"], "detail": i.get("detail")} for i in items
           if i["kind"] in KEPT_KINDS and i["headline"] not in seen]
    return _trim({**days, day: {**days.get(day, {}), "changes": [*old, *new]}}) if new else days


def _trim(days: dict) -> dict:
    return dict(sorted(days.items())[-KEPT_DAYS:])


def load_days() -> dict:
    return load_json(HISTORY_PATH).get("days", {})


def save_days(days: dict) -> None:
    with open(HISTORY_PATH, "w") as f:
        json.dump({"days": days}, f, indent=1)
