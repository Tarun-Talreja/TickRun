#!/usr/bin/env python3
"""
generate_research.py — AI Research Briefs for TickRun's Top Picks

Reads output/weekly_screens.json (the composite-ranked top conviction
list), and for each pick calls the Claude API to produce a structured
research brief that highlights the **indirect AI / data-center / power
exposure narrative** alongside the traditional thesis/catalyst/bear
case framing.

Hardening since v1:
- Strict response-schema validation; retries on JSON parse failures
- Bounded exponential backoff on API errors
- Tone tuned toward "specific & honest about uncertainty," not
  "no hedging" (the old prompt pushed the model toward overconfidence)
- Records partial success per pick — one bad response no longer drops
  the entire run

Usage:
    ANTHROPIC_API_KEY=sk-... python3 generate_research.py [--top N]

Requirements:
    pip3 install anthropic tenacity
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

try:
    import anthropic
except ImportError:
    print("Missing dependency: pip3 install anthropic")
    sys.exit(1)

try:
    from tenacity import retry, stop_after_attempt, wait_exponential
    _HAS_TENACITY = True
except ImportError:
    _HAS_TENACITY = False

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
WEEKLY_PATH = os.path.join(SCRIPT_DIR, "output", "weekly_screens.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "research_briefs.json")

MODEL_ID = "claude-opus-4-7"
MAX_TOKENS = 700

REQUIRED_FIELDS = (
    "one_line_thesis",
    "ai_exposure_narrative",
    "why_it_screened",
    "valuation_note",
    "bear_case",
    "research_focus",
)


# ── Prompt construction ──────────────────────────────────────

def build_prompt(pick: dict) -> str:
    sym       = pick["symbol"]
    name      = pick.get("name", sym)
    sector    = pick.get("sector", "Unknown")
    industry  = pick.get("industry", "Unknown")
    price     = pick.get("price", "—")
    mcap      = pick.get("market_cap")
    mcap_str  = f"${mcap/1e9:.1f}B" if mcap else "n/a"
    composite = pick.get("composite_score", 0.0)
    factors   = pick.get("factors", {})
    metrics   = pick.get("metrics", {})
    summary   = pick.get("summary", "")
    ai_evidence = pick.get("ai_evidence", [])
    proxy_notes = pick.get("proxy_notes", [])

    factor_lines = "\n".join(
        f"  - {k}: {v}/100"
        for k, v in factors.items()
    )

    metric_lines = []
    for label, key, suffix in [
        ("EV/EBITDA", "ev_ebitda", "x"), ("Forward P/E", "forward_pe", "x"),
        ("FCF yield", "fcf_yield", "%"), ("FCF margin", "fcf_margin", "%"),
        ("Gross margin", "gross_margin", "%"), ("Op margin", "op_margin", "%"),
        ("ROIC*", "roic_proxy", "%"), ("Debt/EBITDA", "debt_to_ebitda", "x"),
        ("Rev growth", "rev_growth", "%"), ("12M return", "ret_12m", "%"),
    ]:
        v = metrics.get(key)
        if v is not None:
            metric_lines.append(f"  - {label}: {v}{suffix}")
    metrics_str = "\n".join(metric_lines) if metric_lines else "  (limited metrics available)"

    proxy_str = ""
    if proxy_notes:
        proxy_str = (
            "\n\n[Note: ROIC* is a ROE-based proxy because true ROIC is not in "
            "the data source. Treat as approximate.]"
        )

    ai_evidence_str = (
        ", ".join(ai_evidence) if ai_evidence else "no direct industry/keyword match"
    )

    return f"""You are an experienced fundamental equity analyst writing for a retail investor running a long-term Roth IRA. You favor mid- and small-cap companies that sell into durable enterprise spending trends — especially the AI / data-center / power / networking buildout. You are honest about what you don't know.

## Stock under review

- Symbol: {sym}
- Name: {name}
- Sector / industry: {sector} / {industry}
- Market cap: {mcap_str} (current price ${price})

## Why our screener surfaced it (composite score: {composite}/100)

Factor sub-scores (z-scored within Russell mid+small universe):
{factor_lines}

Quantitative snapshot:
{metrics_str}{proxy_str}

AI-exposure evidence found in the business summary / industry mapping:
  {ai_evidence_str}

Business description (verbatim from issuer / data provider):
\"\"\"
{summary[:1200]}
\"\"\"

## Your task

Produce a research brief in the JSON schema below. Be specific and concrete; cite numbers from the snapshot above when they support a point. When data is missing or the relationship is unclear, say so explicitly — uncertainty is information. Avoid generic platitudes ("strong management team", "well-positioned for growth") unless you can back them with a number.

The "ai_exposure_narrative" field is the most important one: explain in plain English what this company actually sells (or builds, or operates) that benefits from AI / data-center / hyperscaler / enterprise-software / power-grid spending. If the AI tie is weak or speculative, say so.

Return ONLY a JSON object — no markdown fences, no preamble, no commentary — with these exact fields:

{{
  "one_line_thesis": "One punchy sentence: what this company is and why it might be undervalued. Max 25 words.",
  "ai_exposure_narrative": "2-3 sentences in plain English: what they sell into the AI/data-center/power/enterprise-software thesis, who their customers are, and how durable that demand looks. If the AI exposure is weak or indirect, state that honestly.",
  "why_it_screened": "1-2 sentences explaining which factors drove the composite (look at the factor sub-scores) and what that combination implies about the stock's character.",
  "valuation_note": "1 sentence on valuation: is it cheap relative to its growth and quality, or just cheap because something is broken? Cite the specific multiple if helpful.",
  "bear_case": "1-2 sentences on the single biggest specific risk. Concrete and falsifiable, not generic.",
  "research_focus": ["3 specific things to verify before buying — not generic advice; things specific to this company's situation, customers, or balance sheet"]
}}"""


# ── Robust parsing ───────────────────────────────────────────

def extract_json(text: str) -> dict:
    """Pull a JSON object out of an LLM response, tolerating fences /
    leading prose. Raises ValueError if nothing parses."""
    s = text.strip()
    # Strip ``` fences if present
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    # Try direct parse first
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Fall back to first top-level {...} match
    match = re.search(r"\{.*\}", s, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("no JSON object found in response")


def validate_brief(obj: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for f in REQUIRED_FIELDS:
        if f not in obj:
            errors.append(f"missing:{f}")
        elif obj[f] is None or obj[f] == "":
            errors.append(f"empty:{f}")
    rf = obj.get("research_focus")
    if not isinstance(rf, list) or len(rf) < 1:
        errors.append("research_focus_not_list_or_empty")
    return (len(errors) == 0), errors


# ── API call with retries ────────────────────────────────────

def _call_claude(client, prompt: str) -> str:
    msg = client.messages.create(
        model=MODEL_ID,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


if _HAS_TENACITY:
    _call_claude = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )(_call_claude)


def generate_brief(client, pick: dict, max_retries: int = 2) -> dict:
    prompt = build_prompt(pick)
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            raw = _call_claude(client, prompt)
            obj = extract_json(raw)
            ok, errors = validate_brief(obj)
            if ok:
                return obj
            last_err = f"validation: {errors}"
            # Repair attempt — append corrective instruction and retry
            prompt = (
                build_prompt(pick)
                + f"\n\nIMPORTANT: your previous response was missing fields: {errors}. "
                "Return ONLY a complete JSON object with all required fields filled."
            )
        except Exception as exc:
            last_err = str(exc)
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(last_err or "unknown failure")


# ── Main entry point ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=5,
                        help="Number of picks to generate briefs for")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set. Run: export ANTHROPIC_API_KEY=...")
        sys.exit(1)

    print("🧠 TickRun Research Brief Generator")
    print(f"   Output: {OUTPUT_PATH}\n")

    with open(WEEKLY_PATH) as f:
        weekly = json.load(f)
    picks = weekly.get("top_conviction", [])[: args.top]
    if not picks:
        print("No picks in weekly_screens.json — run fetch_weekly.py first.")
        sys.exit(1)

    print(f"Generating briefs for top {len(picks)} picks "
          f"(screens from {weekly.get('last_updated', '?')})…\n")

    client = anthropic.Anthropic(api_key=api_key)
    briefs: list[dict] = []
    errors: list[tuple[str, str]] = []

    for i, pick in enumerate(picks, 1):
        sym = pick["symbol"]
        print(f"  [{i}/{len(picks)}] {sym} ({pick.get('name', sym)})…", end=" ", flush=True)
        try:
            brief = generate_brief(client, pick)
            entry = {
                "symbol":    sym,
                "name":      pick.get("name"),
                "sector":    pick.get("sector"),
                "industry":  pick.get("industry"),
                "price":     pick.get("price"),
                "market_cap": pick.get("market_cap"),
                "composite_score": pick.get("composite_score"),
                "factors":   pick.get("factors"),
                "ai_evidence": pick.get("ai_evidence", []),
                **brief,
            }
            briefs.append(entry)
            print("✓")
        except Exception as exc:
            errors.append((sym, str(exc)))
            print(f"✗ ({exc})")

    output = {
        "last_updated":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "screens_updated": weekly.get("last_updated"),
        "model":           MODEL_ID,
        "picks":           briefs,
        "errors":          [{"symbol": s, "error": e} for s, e in errors],
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Wrote {len(briefs)} briefs ({len(errors)} failed) → {OUTPUT_PATH}")
    if errors:
        print("\n⚠ Failures:")
        for sym, err in errors:
            print(f"   {sym}: {err}")


if __name__ == "__main__":
    main()
