#!/usr/bin/env python3
"""
scripts/health_alert.py — Tell the owner when part of the app stops working.

Keeps one open GitHub issue, which GitHub emails: opened when something breaks, updated
when the list changes, closed when everything recovers. So a problem arrives without
anyone looking at the app, and a problem that lasts doesn't send a mail every day.

Usage (needs GH_TOKEN):
    python3 scripts/health_alert.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import load_json

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PATH = os.path.join(SCRIPT_DIR, "output", "dashboard.json")

LABEL = "app-health"
SITE_URL = "https://tarun-talreja.github.io/TickRun/"
# Clears itself as the queue runs, and a re-rate would otherwise open an issue each time.
NOT_ALERTED = {"Ratings"}


def problems_from(stages: list[dict]) -> list[str]:
    lines = []
    for s in stages:
        if s["status"] == "ok" or s["name"] in NOT_ALERTED:
            continue
        detail = f" ({s['detail']})" if s.get("detail") else ""
        lines.append(f"- **{s['name']}**: {s['status']}{detail}. {s.get('affects') or ''}".rstrip())
    return lines


def issue_body(problems: list[str], failed_runs: list[str]) -> str:
    parts = []
    if problems:
        parts += ["**Not working:**", *problems]
    if failed_runs:
        parts += ["", "**Jobs that failed in the last day:**", *[f"- {r}" for r in failed_runs]]
    parts += ["", f"[Open the app]({SITE_URL}). This closes itself once everything recovers."]
    return "\n".join(parts)


def decide(body: str | None, open_issue: dict | None) -> str:
    """create, update, close or nothing. body is None when everything is healthy."""
    if body is None:
        return "close" if open_issue else "nothing"
    if not open_issue:
        return "create"
    return "nothing" if open_issue["body"].strip() == body.strip() else "update"


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _failed_runs(now: datetime) -> list[str]:
    since = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    runs = json.loads(_gh("run", "list", "--status", "failure", "--created", f">={since}",
                          "--limit", "50", "--json", "workflowName"))
    return sorted({r["workflowName"] for r in runs})


def main():
    now = datetime.now(timezone.utc)
    problems = problems_from(load_json(DASHBOARD_PATH).get("health", {}).get("stages", []))
    failed = _failed_runs(now)
    body = issue_body(problems, failed) if problems or failed else None

    _gh("label", "create", LABEL, "--force", "--color", "B60205",
        "--description", "Part of the app has stopped working")
    issues = json.loads(_gh("issue", "list", "--label", LABEL, "--state", "open",
                            "--json", "number,body"))
    issue = issues[0] if issues else None
    action = decide(body, issue)
    print(f"{len(problems)} problem(s), {len(failed)} failed job(s): {action}")

    if action == "create":
        _gh("issue", "create", "--title", "TickRun: part of the app is not working",
            "--label", LABEL, "--body", body)
    elif action == "update":
        _gh("issue", "edit", str(issue["number"]), "--body", body)
        _gh("issue", "comment", str(issue["number"]), "--body", f"The list changed:\n\n{body}")
    elif action == "close":
        _gh("issue", "close", str(issue["number"]), "--comment", "Everything is working again.")


if __name__ == "__main__":
    main()
