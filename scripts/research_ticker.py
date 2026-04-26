#!/usr/bin/env python3
"""
scripts/research_ticker.py — Run the co-work research prompt on a ticker.

Loads current fundamentals from data/quotes_cache.json, injects them
into the structured research prompt, calls Claude, and saves the result
to output/research/<TICKER>_<DATE>.md. Also updates watchlist.json with
the verdict.

Usage:
    python3 scripts/research_ticker.py POWL
    python3 scripts/research_ticker.py ALAB --save-only   # save without updating watchlist

Requirements:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

try:
    import anthropic
except ImportError:
    print("Missing dependency: pip install anthropic")
    sys.exit(1)

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
PROMPT_PATH    = os.path.join(SCRIPT_DIR, "prompts", "stock_research.md")
OUTPUT_DIR     = os.path.join(SCRIPT_DIR, "output", "research")
os.makedirs(OUTPUT_DIR, exist_ok=True)

MODEL_ID   = "claude-opus-4-7"
MAX_TOKENS = 1200

VERDICT_STRINGS = [
    "RESEARCH-WORTHY",
    "WATCHLIST",
    "PASS",
    "RED FLAG",
]


def _load_prompt_template() -> str:
    with open(PROMPT_PATH) as f:
        content = f.read()
    # Extract the prompt between the --- markers
    parts = content.split("---")
    if len(parts) >= 3:
        return parts[1].strip()
    return content


def _format_metric(value, suffix="", prefix="", none_str="unverified") -> str:
    if value is None:
        return none_str
    if isinstance(value, float):
        return f"{prefix}{value:,.1f}{suffix}"
    return f"{prefix}{value}{suffix}"


def _build_prompt(ticker: str, quotes: dict) -> str:
    template = _load_prompt_template()
    q = quotes.get("tickers", {}).get(ticker, {})

    mcap = q.get("market_cap")
    mcap_str = f"${mcap/1e9:.1f}B" if mcap else "unverified"

    rev = q.get("revenue_ttm")
    rev_str = f"${rev/1e6:.0f}M" if rev else "unverified"

    fcf = q.get("fcf_ttm")
    fcf_str = f"${fcf/1e6:.0f}M ({'positive' if fcf and fcf > 0 else 'negative'})" if fcf else "unverified"

    cash = q.get("total_cash")
    debt = q.get("total_debt")
    if cash is not None and debt is not None:
        net = cash - debt
        net_str = f"${abs(net)/1e6:.0f}M {'net cash' if net >= 0 else 'net debt'}"
    else:
        net_str = "unverified"

    # 52-week high gate warning
    high_gate_warning = ""
    drawdown = q.get("drawdown_from_high")
    if drawdown is not None and drawdown > -10:
        high_gate_warning = (
            f"\n⚠ 52-WEEK HIGH GATE: {ticker} is only {abs(drawdown):.1f}% below its "
            f"52-week high of ${_format_metric(q.get('high_52w'))}. "
            f"Per investment policy, stocks within 10% of their 52-week high MUST be assigned "
            f"WATCHLIST (not RESEARCH-WORTHY). Include 'WAIT for pullback — near 52-week high' "
            f"in the next_action. Do not assign RESEARCH-WORTHY regardless of fundamentals.\n"
        )

    context = f"""
{high_gate_warning}[Current data from quotes cache — as of {q.get('fetched_at', 'unknown')}]
- Ticker: {ticker}
- Name: {q.get('name', ticker)}
- Price: ${_format_metric(q.get('price'))}
- Market cap: {mcap_str}
- Revenue (TTM): {rev_str}
- Revenue growth (YoY): {_format_metric(q.get('revenue_growth'), suffix='%')}
- Gross margin: {_format_metric(q.get('gross_margin'), suffix='%')}
- Operating margin: {_format_metric(q.get('op_margin'), suffix='%')}
- FCF (TTM): {fcf_str}
- Net cash / net debt: {net_str}
- Trailing P/E: {_format_metric(q.get('pe'), suffix='x')}
- Forward P/E: {_format_metric(q.get('forward_pe'), suffix='x')}
- EV/EBITDA: {_format_metric(q.get('ev_ebitda'), suffix='x')}
- 52-week high: ${_format_metric(q.get('high_52w'))} | Current drawdown: {_format_metric(q.get('drawdown_from_high'), suffix='%')}

Note: These figures come from yfinance and may lag by 1-7 days. Cross-check with the company's IR page or SEC filings for precision.

[Your task — follow the structure below exactly]
"""
    return template.replace("TICKER: {{TICKER}}", f"TICKER: {ticker}") + "\n" + context


def _extract_verdict(text: str) -> str | None:
    for v in VERDICT_STRINGS:
        if v in text.upper():
            return v
    return None


def _update_watchlist(ticker: str, verdict: str, output_file: str):
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    updated = False
    for candidate in wl.get("candidates", []):
        if candidate["ticker"] == ticker:
            candidate["verdict"] = verdict
            candidate["research_file"] = output_file
            candidate["last_researched"] = today
            updated = True
            break

    if not updated:
        wl.setdefault("candidates", []).append({
            "ticker": ticker,
            "name": ticker,
            "theme": "unknown",
            "status": "researching",
            "thesis": "",
            "added": today,
            "verdict": verdict,
            "next_action": "Review the research output",
            "research_file": output_file,
            "last_researched": today,
        })

    wl["last_updated"] = today
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(wl, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", type=str, help="Ticker symbol to research (e.g. POWL)")
    parser.add_argument("--save-only", action="store_true",
                        help="Save output but don't update watchlist.json")
    args = parser.parse_args()

    ticker = args.ticker.upper()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set. Run: export ANTHROPIC_API_KEY=...")
        sys.exit(1)

    if not os.path.exists(QUOTES_PATH):
        print("No quotes cache found. Run: python3 scripts/refresh_quotes.py first.")
        sys.exit(1)

    with open(QUOTES_PATH) as f:
        quotes = json.load(f)

    print(f"🔬 Researching {ticker}...")
    prompt = _build_prompt(ticker, quotes)

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=MODEL_ID,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{ticker}_{today}.md"
    output_path = os.path.join(OUTPUT_DIR, filename)

    with open(output_path, "w") as f:
        f.write(f"# Research: {ticker} — {today}\n\n")
        f.write(text)

    print(f"\n{text}\n")

    verdict = _extract_verdict(text)
    if verdict:
        print(f"✅ Verdict: {verdict}")
        if not args.save_only:
            _update_watchlist(ticker, verdict, f"output/research/{filename}")
            print(f"📝 Updated watchlist.json")
    else:
        print("⚠ Could not extract a clear verdict from the response.")

    print(f"💾 Saved → {output_path}")


if __name__ == "__main__":
    main()
