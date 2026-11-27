#!/usr/bin/env python3
"""
scripts/news_history.py — Keep every headline ever seen about each stock.

data/news_cache.json holds only the latest few headlines per stock, so older ones drop
out. This keeps them, one file per stock (data/news_history/TICKER.json), deduplicated by
title, publisher and date, with the day each was first seen. The AI analysis reads it to
connect today's news to earlier days.

The first run can be seeded from git, which holds a snapshot of the news cache for every
commit since June 2026:  python3 scripts/news_history.py --backfill

Usage:  python3 scripts/news_history.py            (adds what the current cache holds)
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import load_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(ROOT, "data", "news_cache.json")
HISTORY_DIR = os.path.join(ROOT, "data", "news_history")
CACHE_REL = "data/news_cache.json"

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _norm(text: str) -> str:
    """Case, spacing and curly-versus-straight quotes differ between copies of one headline."""
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return " ".join(text.casefold().split())


def _key(item: dict) -> tuple:
    return (_norm(item["title"]), _norm(item.get("publisher") or ""), item["date"])


def clean(item: dict) -> dict | None:
    """The item in stored form, or None when it has no usable title or date."""
    title, day = (item.get("title") or "").strip(), item.get("date") or ""
    if not title or not _DATE_RE.match(day):
        return None
    return {"title": title, "publisher": (item.get("publisher") or "").strip(), "date": day,
            "url": item.get("url") or ""}


def merge(existing: list[dict], items: list[dict], seen_on: str) -> tuple[list[dict], int]:
    """The history with any new items added (newest first), and how many were new."""
    known = {_key(i) for i in existing}
    fresh = []
    for raw in items:
        item = clean(raw)
        if item and _key(item) not in known:
            known.add(_key(item))
            fresh.append({**item, "seen_on": seen_on})
    merged = sorted([*existing, *fresh], key=lambda i: (i["date"], i["title"]), reverse=True)
    return merged, len(fresh)


def recent(items: list[dict], today, days: int = 30, limit: int = 12) -> list[dict]:
    """The newest headlines from the last `days` days, for the stock page. Newest first."""
    first, last = (today - timedelta(days=days)).isoformat(), (today + timedelta(days=1)).isoformat()
    keep = [i for i in items if first <= i["date"] <= last]
    keep.sort(key=lambda i: (i["date"], i["title"]), reverse=True)
    return [{k: i.get(k, "") for k in ("date", "title", "publisher", "url")} for i in keep[:limit]]


def as_rows(items: list[dict]) -> list[list[str]]:
    """[date, title, publisher, url] per headline: the dashboard file is pretty-printed, so
    named fields cost twice the space."""
    return [[i["date"], i["title"], i["publisher"], i["url"]] for i in items]


def _path(ticker: str, directory: str) -> str | None:
    return os.path.join(directory, f"{ticker}.json") if _TICKER_RE.match(ticker) else None


def read(ticker: str, directory: str = HISTORY_DIR) -> list[dict]:
    path = _path(ticker, directory)
    return load_json(path, []) if path else []


def _write(path: str, items: list[dict]) -> None:
    # One headline per line, so a day's additions are a few lines in git.
    with open(path, "w", encoding="utf-8") as f:
        f.write("[\n" + ",\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n]\n")


def add_cache(cache: dict, seen_on: str, directory: str = HISTORY_DIR) -> int:
    """Add one snapshot of the news cache; returns the number of new headlines."""
    os.makedirs(directory, exist_ok=True)
    total = 0
    for ticker, items in (cache.get("news") or {}).items():
        path = _path(ticker, directory)
        if not path or not items:
            continue
        merged, added = merge(load_json(path, []), items, seen_on)
        if added:
            _write(path, merged)
            total += added
    return total


def git_snapshots(repo: str = ROOT):
    """(day first committed, cache) for every committed version of the news cache, oldest first."""
    log = subprocess.run(["git", "log", "--reverse", "--format=%H %cI", "--", CACHE_REL],
                         cwd=repo, capture_output=True, text=True, check=True).stdout.split("\n")
    commits = [line.split() for line in log if line.strip()]
    batch = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, capture_output=True, check=True,
                           input="".join(f"{sha}:{CACHE_REL}\n" for sha, _ in commits).encode()).stdout
    pos = 0
    for sha, committed in commits:
        header_end = batch.index(b"\n", pos)
        parts = batch[pos:header_end].split()
        size = int(parts[2]) if len(parts) == 3 and parts[1] == b"blob" else 0
        body = batch[header_end + 1: header_end + 1 + size]
        pos = header_end + 1 + size + 1
        try:
            yield committed[:10], json.loads(body)
        except ValueError:
            continue


def backfill(directory: str = HISTORY_DIR, snapshots=None) -> tuple[int, int]:
    """Seed the history from git. Returns (snapshots read, headlines added)."""
    seen, added = 0, 0
    for day, cache in (snapshots if snapshots is not None else git_snapshots()):
        added += add_cache(cache, day, directory)
        seen += 1
    return seen, added


def main() -> None:
    if "--backfill" in sys.argv:
        seen, added = backfill()
        print(f"✅ News history: read {seen} snapshots from git, added {added} headlines")
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    added = add_cache(load_json(CACHE_PATH), today)
    print(f"✅ News history: {added} new headline(s)")


if __name__ == "__main__":
    main()
