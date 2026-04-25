#!/usr/bin/env python3
"""
generate_research.py — AI Research Briefs for Top Stock Picks

Reads output/weekly_screens.json, takes the top 5 conviction picks,
calls the Claude API for a structured research brief on each, and writes
output/research_briefs.json.

Usage:
    ANTHROPIC_API_KEY=sk-... python3 generate_research.py

Requirements:
    pip3 install anthropic

Runtime: ~30 seconds for 5 picks.
"""

import json
import os
import sys
from datetime import datetime, timezone

try:
    import anthropic
except ImportError:
    print("Missing dependency. Run: pip3 install anthropic")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEEKLY_PATH = os.path.join(SCRIPT_DIR, "output", "weekly_screens.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "research_briefs.json")
TOP_N = 5

SCREEN_LABELS = {
    "graham":        "Graham Defensive (cheap + safe)",
    "magic_formula": "Magic Formula (cheap + high ROIC)",
    "piotroski":     "Piotroski (improving fundamentals)",
    "garp":          "GARP (growth at a reasonable price)",
    "quality":       "Quality (high-return business)",
    "momentum":      "Momentum (trending up with support)",
    "dividend":      "Dividend Quality (safe, growing income)",
}


def load_top_picks():
    with open(WEEKLY_PATH) as f:
        data = json.load(f)
    picks = data.get("top_conviction", [])[:TOP_N]
    screens_updated = data.get("last_updated", "unknown")
    return picks, screens_updated


def screen_descriptions(screens_passed):
    return [SCREEN_LABELS.get(s, s) for s in screens_passed]


def build_prompt(pick):
    sym = pick["symbol"]
    company = pick["company"]
    sector = pick["sector"]
    price = pick.get("price", "unknown")
    score = pick["score"]
    screens = screen_descriptions(pick["screens_passed"])
    thesis = pick.get("one_line_thesis", "")
    metrics = pick.get("metrics", {})

    m_lines = []
    if metrics.get("pe"):      m_lines.append(f"P/E: {metrics['pe']}")
    if metrics.get("pb"):      m_lines.append(f"P/B: {metrics['pb']}")
    if metrics.get("peg"):     m_lines.append(f"PEG: {metrics['peg']}")
    if metrics.get("roe"):     m_lines.append(f"ROE: {metrics['roe']}%")
    if metrics.get("div_yield"): m_lines.append(f"Div yield: {metrics['div_yield']}%")
    if metrics.get("ret_12m"): m_lines.append(f"12M return: {metrics['ret_12m']}%")
    if metrics.get("gross_margin"): m_lines.append(f"Gross margin: {metrics['gross_margin']}%")
    if metrics.get("fcf_margin"):   m_lines.append(f"FCF margin: {metrics['fcf_margin']}%")
    if metrics.get("debt_equity"):  m_lines.append(f"Debt/equity: {metrics['debt_equity']}")

    metrics_str = " · ".join(m_lines) if m_lines else "metrics unavailable"

    return f"""You are a clear-eyed fundamental equity analyst writing for a retail investor running a long-term Roth IRA.

Stock: {sym} ({company}) — {sector}
Current price: ${price}
Screens passed ({score}/7): {", ".join(screens)}
Key metrics: {metrics_str}
Screener thesis: {thesis}

Write a brief research summary in JSON format. Be direct. No hedging phrases like "may" or "could" — state what the numbers actually say. Assume the reader is intelligent but not a finance professional.

Return ONLY a JSON object with exactly these fields:
{{
  "one_line_thesis": "One punchy sentence: what kind of company this is and why it appears cheap/quality/growing. Max 20 words.",
  "why_screened": "1-2 sentences explaining which specific screens it passed and what that combination means about the stock's character.",
  "recent_catalyst": "1 sentence on the most likely current catalyst or reason for attention. If nothing notable, say 'No obvious catalyst — steady business'.",
  "bear_case": "1-2 sentences on the single biggest risk or reason this could be a value trap. Be specific.",
  "research_focus": ["3 specific things to research before buying — not generic advice, but things specific to this company and its current situation"]
}}

Return only the JSON, no markdown fences, no explanation."""


def generate_brief(client, pick):
    prompt = build_prompt(pick)
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Strip markdown fences if model adds them anyway
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        print("Run: export ANTHROPIC_API_KEY=your-key-here")
        sys.exit(1)

    print("🧠 TickRun Research Brief Generator")
    print(f"   Output: {OUTPUT_PATH}\n")

    picks, screens_updated = load_top_picks()
    if not picks:
        print("No picks found in weekly_screens.json")
        sys.exit(1)

    print(f"Generating briefs for top {len(picks)} picks (screens from {screens_updated})...\n")

    client = anthropic.Anthropic(api_key=api_key)
    briefs = []
    errors = []

    for i, pick in enumerate(picks, 1):
        sym = pick["symbol"]
        print(f"  [{i}/{len(picks)}] {sym} ({pick['company']})...", end=" ", flush=True)
        try:
            brief = generate_brief(client, pick)
            entry = {
                "symbol":         sym,
                "company":        pick["company"],
                "sector":         pick["sector"],
                "price":          pick.get("price"),
                "score":          pick["score"],
                "screens_passed": pick["screens_passed"],
                "next_earnings":  pick.get("next_earnings"),
                "one_line_thesis":  brief.get("one_line_thesis", ""),
                "why_screened":     brief.get("why_screened", ""),
                "recent_catalyst":  brief.get("recent_catalyst", ""),
                "bear_case":        brief.get("bear_case", ""),
                "research_focus":   brief.get("research_focus", []),
            }
            briefs.append(entry)
            print("✓")
        except Exception as e:
            errors.append((sym, str(e)))
            print(f"✗ ({e})")

    output = {
        "last_updated":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "screens_updated": screens_updated,
        "model":           "claude-opus-4-7",
        "picks":           briefs,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Done. {len(briefs)} briefs written to {OUTPUT_PATH}")
    if errors:
        print(f"\n⚠ {len(errors)} failed:")
        for sym, err in errors:
            print(f"   {sym}: {err}")


if __name__ == "__main__":
    main()
