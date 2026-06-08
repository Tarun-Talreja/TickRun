#!/usr/bin/env python3
"""
scripts/research_ticker.py — Run the co-work research prompt on a ticker.

Loads current fundamentals from data/quotes_cache.json, injects them
into the structured research prompt, calls an LLM, and saves the result
to output/research/<TICKER>_<DATE>.md. Also updates watchlist.json.

Supports two providers (checked in order):
  1. NVIDIA NIM  — FREE tier, Llama-3.3-70B. Get key at https://build.nvidia.com
  2. Anthropic   — Paid, Claude Opus. Fallback if NVIDIA key not set.

Usage:
    # NVIDIA NIM (free — recommended)
    export NVIDIA_API_KEY=nvapi-...
    python3 scripts/research_ticker.py AAPL

    # Anthropic (paid fallback)
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 scripts/research_ticker.py AAPL

    # Save without updating watchlist
    python3 scripts/research_ticker.py AAPL --save-only

Setup (one time):
    pip install -r requirements.txt
    # Get free NVIDIA key at https://build.nvidia.com → top-right "Get API Key"
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

SCRIPT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "data", "watchlist.json")
QUOTES_PATH    = os.path.join(SCRIPT_DIR, "data", "quotes_cache.json")
PROMPT_PATH    = os.path.join(SCRIPT_DIR, "prompts", "stock_research.md")
OUTPUT_DIR     = os.path.join(SCRIPT_DIR, "output", "research")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Real-news grounding (free, via yfinance) — keeps the LLM from hallucinating.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from news_feed import get_recent_news as _recent_news
except Exception:
    def _recent_news(ticker: str) -> str:  # graceful fallback
        return "No recent news available."

# NVIDIA NIM settings
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
# Preferred → fallback. Heavy models may not be provisioned on free tier (404
# "Function not found for account"); we fall back to the universally-free 70B.
NVIDIA_MODEL_CHAIN = [
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",   # 253B reasoning flagship (if account has access)
    "meta/llama-3.3-70b-instruct",                # reliable free-tier default
]
NVIDIA_MODEL = NVIDIA_MODEL_CHAIN[0]   # may be overridden by --model

# Anthropic fallback settings
ANTHROPIC_MODEL = "claude-opus-4-7"

MAX_TOKENS = 4000   # 8-section structured prompt needs room to reach the verdict (section 8)

VERDICT_STRINGS = ["RESEARCH-WORTHY", "WATCHLIST", "PASS", "RED FLAG"]


# ── Provider detection ────────────────────────────────────────────────────────

def _detect_provider() -> tuple[str, str]:
    """Return (provider, api_key). Prefers NVIDIA NIM (free)."""
    nvidia_key = os.environ.get("NVIDIA_API_KEY")
    if nvidia_key:
        return "nvidia", nvidia_key

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        return "anthropic", anthropic_key

    print("❌  No API key found.")
    print()
    print("Option 1 — NVIDIA NIM (FREE, recommended):")
    print("  1. Go to https://build.nvidia.com")
    print("  2. Sign in → top-right menu → 'Get API Key'")
    print("  3. export NVIDIA_API_KEY=nvapi-...")
    print()
    print("Option 2 — Anthropic (paid):")
    print("  export ANTHROPIC_API_KEY=sk-ant-...")
    sys.exit(1)


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(provider: str, api_key: str, prompt: str) -> str:
    if provider == "nvidia":
        try:
            from openai import OpenAI, NotFoundError
        except ImportError:
            print("Missing dependency: pip install openai")
            sys.exit(1)

        client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)

        # Build the model attempt list: explicit NVIDIA_MODEL first (covers --model
        # override), then any remaining fallbacks in the chain.
        attempts = [NVIDIA_MODEL] + [m for m in NVIDIA_MODEL_CHAIN if m != NVIDIA_MODEL]
        last_err = None
        for model in attempts:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=MAX_TOKENS,
                    temperature=0.3,
                )
                if model != attempts[0]:
                    print(f"   (fell back to {model})")
                return response.choices[0].message.content
            except NotFoundError as exc:
                last_err = exc
                print(f"   {model} unavailable for this account — trying next...")
                continue
        raise RuntimeError(f"All NVIDIA models failed. Last error: {last_err}")

    elif provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            print("Missing dependency: pip install anthropic")
            sys.exit(1)

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    else:
        raise ValueError(f"Unknown provider: {provider}")


# ── Prompt building ───────────────────────────────────────────────────────────

def _load_prompt_template() -> str:
    with open(PROMPT_PATH) as f:
        content = f.read()
    parts = content.split("---")
    if len(parts) >= 3:
        return parts[1].strip()
    return content


def _fmt(value, suffix="", prefix="", none_str="unverified") -> str:
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
    fcf_str = (
        f"${fcf/1e6:.0f}M ({'positive' if fcf > 0 else 'negative'})"
        if fcf else "unverified"
    )

    cash = q.get("total_cash")
    debt = q.get("total_debt")
    if cash is not None and debt is not None:
        net = cash - debt
        net_str = f"${abs(net)/1e6:.0f}M {'net cash' if net >= 0 else 'net debt'}"
    else:
        net_str = "unverified"

    # 52-week high gate warning
    drawdown = q.get("drawdown_from_high")
    gate_warning = ""
    if drawdown is not None and drawdown > -10:
        gate_warning = (
            f"\n⚠ 52-WEEK HIGH GATE: {ticker} is only {abs(drawdown):.1f}% below its "
            f"52-week high of ${_fmt(q.get('high_52w'))}. "
            f"Per investment policy, stocks within 10% of their 52-week high MUST be "
            f"assigned WATCHLIST. Do not assign RESEARCH-WORTHY regardless of fundamentals.\n"
        )

    context = f"""
{gate_warning}[Live fundamentals — {q.get('fetched_at', 'unknown')}]
- Ticker: {ticker}
- Name: {q.get('name', ticker)}
- Price: ${_fmt(q.get('price'))}
- Market cap: {mcap_str}
- Revenue (TTM): {rev_str}
- Revenue growth (YoY): {_fmt(q.get('revenue_growth'), suffix='%')}
- Gross margin: {_fmt(q.get('gross_margin'), suffix='%')}
- Operating margin: {_fmt(q.get('op_margin'), suffix='%')}
- FCF (TTM): {fcf_str}
- Net cash / net debt: {net_str}
- Trailing P/E: {_fmt(q.get('pe'), suffix='x')}
- Forward P/E: {_fmt(q.get('forward_pe'), suffix='x')}
- EV/EBITDA: {_fmt(q.get('ev_ebitda'), suffix='x')}
- 52-week high: ${_fmt(q.get('high_52w'))} | Drawdown from high: {_fmt(drawdown, suffix='%')}

Note: Data from yfinance, may lag 1-7 days. Cross-check with company IR or SEC filings.

[Recent news headlines — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}]
{_recent_news(ticker)}

IMPORTANT GROUNDING RULES:
- Base your analysis ONLY on the fundamentals and news headlines above.
- For any claim NOT supported by the data or headlines above (specific contract values,
  management quotes, customer names, analyst targets), write "unverified" — do NOT invent it.
- Distinguish clearly between facts from the provided data vs. your general knowledge.
"""
    return template.replace("TICKER: {{TICKER}}", f"TICKER: {ticker}") + "\n" + context


# ── Verdict extraction + watchlist update ────────────────────────────────────

def _extract_verdict(text: str) -> str | None:
    for v in VERDICT_STRINGS:
        if v in text.upper():
            return v
    return None


def _extract_confidence(text: str) -> str | None:
    """Pull the CONFIDENCE: HIGH|MEDIUM|LOW line."""
    m = re.search(r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW)", text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _update_watchlist(ticker: str, verdict: str, output_file: str, confidence: str | None = None):
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    updated = False
    for candidate in wl.get("candidates", []):
        if candidate["ticker"] == ticker:
            candidate["verdict"]        = verdict
            candidate["research_file"]  = output_file
            candidate["last_researched"] = today
            candidate["status"]         = "research_complete"
            if confidence:
                candidate["confidence"] = confidence
            updated = True
            break

    if not updated:
        wl.setdefault("candidates", []).append({
            "ticker":          ticker,
            "name":            ticker,
            "theme":           "unknown",
            "status":          "research_complete",
            "thesis":          "",
            "added":           today,
            "verdict":         verdict,
            "next_action":     "Review the research output",
            "research_file":   output_file,
            "last_researched": today,
        })

    wl["last_updated"] = today
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(wl, f, indent=2)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", type=str, help="Ticker symbol (e.g. AAPL)")
    parser.add_argument("--save-only", action="store_true",
                        help="Save output but don't update watchlist.json")
    parser.add_argument("--model", type=str, default=None,
                        help="Override model (e.g. meta/llama-3.3-70b-instruct for faster results)")
    args = parser.parse_args()

    ticker   = args.ticker.upper()
    provider, api_key = _detect_provider()

    # Allow model override
    if args.model:
        global NVIDIA_MODEL, ANTHROPIC_MODEL
        if provider == "nvidia":
            NVIDIA_MODEL = args.model
        else:
            ANTHROPIC_MODEL = args.model

    if not os.path.exists(QUOTES_PATH):
        print("No quotes cache. Run: python3 scripts/refresh_quotes.py")
        sys.exit(1)

    with open(QUOTES_PATH) as f:
        quotes = json.load(f)

    model_label = NVIDIA_MODEL if provider == "nvidia" else ANTHROPIC_MODEL
    print(f"🔬  Researching {ticker} via {provider.upper()} ({model_label})...")

    prompt = _build_prompt(ticker, quotes)
    text   = _call_llm(provider, api_key, prompt)

    today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename  = f"{ticker}_{today}.md"
    out_path  = os.path.join(OUTPUT_DIR, filename)

    with open(out_path, "w") as f:
        f.write(f"# Research: {ticker} — {today}  (model: {model_label})\n\n")
        f.write(text)

    print(f"\n{text}\n")

    verdict = _extract_verdict(text)
    confidence = _extract_confidence(text)
    if verdict:
        conf_str = f" (confidence: {confidence})" if confidence else ""
        print(f"✅  Verdict: {verdict}{conf_str}")
        if not args.save_only:
            _update_watchlist(ticker, verdict, f"output/research/{filename}", confidence)
            print(f"📝  Updated watchlist.json → {ticker} = {verdict}{conf_str}")
    else:
        print("⚠   Could not extract a clear verdict from the response.")

    print(f"💾  Saved → {out_path}")


if __name__ == "__main__":
    main()
