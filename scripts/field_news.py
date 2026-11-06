#!/usr/bin/env python3
"""
scripts/field_news.py — What changed this week in each field the app follows.

Pulls recent headlines per theme and asks the model for a short briefing. The model
may only use those headlines, and code enforces it: a summary without a real source,
or with a figure its sources don't contain, is dropped and the headlines are shown
instead. A missing summary is fine. A made-up one is not.

Usage:
    export NVIDIA_API_KEY=nvapi-...
    python3 scripts/field_news.py
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fact_check import find_unsupported
from io_utils import load_json
from llm_client import chat

SCRIPT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES_PATH = os.path.join(SCRIPT_DIR, "data", "themes.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "data", "field_news.json")

FEED_URL = "https://news.google.com/rss/search?q={query}+when:7d&hl=en-US&gl=US&ceid=US:en"
HEADERS = {"User-Agent": "Mozilla/5.0 (TickRun field news)"}
MAX_HEADLINES = 12
WORKERS = 4
# Stock-tip listicles are about tickers, not about the field.
_LISTICLE_RE = re.compile(
    r"\b\d+\s+(?:\w+\s+){0,3}stocks?\b|should you buy|buy now|price target|top picks", re.IGNORECASE)


def parse_feed(xml_bytes: bytes) -> list[dict]:
    """Newest-first headlines from a feed, without duplicates or stock-tip lists."""
    try:
        items = ET.fromstring(xml_bytes).iter("item")
    except ET.ParseError:
        return []
    found = {}
    for item in items:
        source = item.findtext("source") or ""
        title = (item.findtext("title") or "").removesuffix(f" - {source}").strip()
        if not title or title in found or _LISTICLE_RE.search(title):
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        except ValueError:
            continue
        found[title] = {"title": title, "source": source, "date": published,
                        "link": item.findtext("link") or ""}
    return sorted(found.values(), key=lambda h: h["date"], reverse=True)


def fetch_headlines(query: str) -> list[dict]:
    try:
        response = requests.get(FEED_URL.format(query=quote(query)), headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"⚠ feed failed for {query!r}: {str(exc)[:120]}")
        return []
    return parse_feed(response.content)[:MAX_HEADLINES]


def _prompt(field: str, headlines: list[dict]) -> str:
    numbered = "\n".join(f"{i}. [{h['date']}] {h['title']} ({h['source']})"
                         for i, h in enumerate(headlines, 1))
    return f"""These are this week's headlines about {field}.

In 1-2 plain sentences, say what actually changed in this field. Use ONLY these
headlines. Add nothing from memory, and give no opinion on any stock.

Reply with exactly these three lines:
SUMMARY: <the sentences>
SOURCES: <numbers of the headlines you used, e.g. 2, 5>
COMPANIES: <public companies named in those headlines, separated by ;, or none>

Headlines:
{numbered}
"""


def _line(label: str, text: str) -> str:
    match = re.search(rf"^[\s*_]*{label}[\s*_]*:[\s*_]*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def brief_field(field: str, headlines: list[dict], ask) -> dict:
    """Briefing for one field; falls back to bare headlines if it can't be trusted."""
    fallback = {"summary": None, "sources": headlines, "companies": []}
    if not headlines:
        return fallback
    try:
        text = ask(_prompt(field, headlines))
    except RuntimeError as exc:
        print(f"⚠ no briefing for {field}: {str(exc)[:120]}")
        return fallback

    summary = _line("SUMMARY", text)
    picks = {int(n) for n in re.findall(r"\d+", _line("SOURCES", text))}
    sources = [h for i, h in enumerate(headlines, 1) if i in picks]
    cited = " ".join(h["title"] for h in sources)
    if not summary or not sources or find_unsupported(summary, cited):
        print(f"⚠ dropped the summary for {field}: not backed by its sources")
        return fallback

    named = [c.strip() for c in _line("COMPANIES", text).split(";")]
    all_titles = " ".join(h["title"] for h in headlines).lower()
    companies = [c for c in named if c and c.lower() != "none" and c.lower() in all_titles]
    return {"summary": summary, "sources": sources, "companies": companies}


def _brief_theme(item: tuple[str, dict], key: str) -> tuple[str, dict]:
    theme_id, theme = item
    def ask(prompt: str) -> str:
        text, _ = chat(key, [{"role": "user", "content": prompt}], max_tokens=1500, temperature=0.2)
        return text
    headlines = fetch_headlines(theme["news_query"])
    return theme_id, {"name": theme["name"], **brief_field(theme["name"], headlines, ask)}


def main() -> None:
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        print("❌ NVIDIA_API_KEY not set")
        sys.exit(1)
    themes = load_json(THEMES_PATH).get("themes", {})
    with ThreadPoolExecutor(WORKERS) as pool:
        fields = dict(pool.map(lambda item: _brief_theme(item, key), themes.items()))

    with_news = sum(1 for f in fields.values() if f["sources"])
    summarised = sum(1 for f in fields.values() if f["summary"])
    print(f"📰 {with_news}/{len(fields)} fields have headlines, {summarised} summarised")
    if not with_news:
        print("❌ No headlines for any field, so the feed is probably down. Keeping the last briefing.")
        sys.exit(1)

    with open(OUTPUT_PATH, "w") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "fields": fields}, f, indent=2)


if __name__ == "__main__":
    main()
