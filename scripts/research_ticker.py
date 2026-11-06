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

# NVIDIA NIM model chain lives in llm_client.py — one list shared by every
# script, so a model retirement is a one-line fix instead of a 10-week outage.
from llm_client import NVIDIA_CHAT_MODELS as NVIDIA_MODEL_CHAIN, chat as _nim_chat
from fact_check import fact_check_section, find_unsupported, source_block
NVIDIA_MODEL = NVIDIA_MODEL_CHAIN[0]   # may be overridden by --model

# Anthropic fallback settings
ANTHROPIC_MODEL = "claude-opus-4-7"

MAX_TOKENS = 4000   # 8-section structured prompt needs room to reach the verdict (section 8)

# Without a client timeout a single slow generation can hang until the whole
# workflow is cancelled, which is what left most of the watchlist stale.
LLM_TIMEOUT_SECONDS = 90

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
            import openai  # noqa: F401
        except ImportError:
            print("Missing dependency: pip install openai")
            sys.exit(1)

        # Explicit NVIDIA_MODEL first (covers --model override), then the chain.
        # llm_client.chat falls through on ANY per-model API error — the old
        # loop here only caught NotFound/timeouts, so a 410 Gone crashed it.
        attempts = [NVIDIA_MODEL] + [m for m in NVIDIA_MODEL_CHAIN if m != NVIDIA_MODEL]
        sysmsg = (
            "detailed thinking off. You are a disciplined equity analyst. Follow the "
            "requested output structure exactly and ALWAYS end with the mandated "
            "VERDICT: and CONFIDENCE: lines."
        )
        text, model = _nim_chat(
            api_key,
            [{"role": "system", "content": sysmsg}, {"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS, temperature=0.3,
            timeout=LLM_TIMEOUT_SECONDS, models=attempts,
        )
        print(f"   (answered by {model})")
        return text

    elif provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            print("Missing dependency: pip install anthropic")
            sys.exit(1)

        client = anthropic.Anthropic(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS, max_retries=1)
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
    """Extract the actual LLM-facing instructions from prompts/stock_research.md.

    BUG THIS REPLACES: the file has a leading '# Title' + human copy-paste note,
    then the real prompt (persona -> numbered sections -> closing remarks). It
    used to be delimited by exactly two '---' lines, and content.split("---")[1]
    grabbed the middle. Adding Section 10 introduced a THIRD '---' fence, which
    shifted every index — parts[1] became the 142-char human note ("Copy
    everything between the ` markers into Claude...") instead of the prompt.
    The model was never receiving the persona, the portfolio context, or the
    9 numbered section instructions; it only ever saw the live-fundamentals
    block appended in _build_prompt plus the 4 mandatory output lines. That is
    the actual reason research came back as unstructured prose with no
    section headers — not a model-compliance problem.

    Fix: anchor on the first stable content marker ("You are my fundamental
    research analyst") rather than counting dividers, so adding or removing
    '---' fences elsewhere in the file can't silently break this again.
    """
    with open(PROMPT_PATH) as f:
        content = f.read()
    anchor = "You are my fundamental research analyst"
    idx = content.find(anchor)
    if idx == -1:
        raise RuntimeError(
            f"{PROMPT_PATH}: could not find the prompt anchor {anchor!r} — "
            f"the template structure changed and _load_prompt_template needs updating."
        )
    return content[idx:].strip()


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

    report_cur = q.get("financial_currency")
    currency_note = ""
    if report_cur and report_cur != q.get("currency"):
        currency_note = (
            f"\nCurrency: reports in {report_cur}; revenue, FCF, cash and debt above are "
            f"converted to USD. Trailing P/E comes from Yahoo and may mix currencies, "
            f"so do not build the case on it.\n"
        )

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
- Revenue growth (latest quarter vs a year ago, NOT trailing-twelve-month): {_fmt(q.get('revenue_growth'), suffix='%')}
- Gross margin: {_fmt(q.get('gross_margin'), suffix='%')}
- Operating margin: {_fmt(q.get('op_margin'), suffix='%')}
- FCF (TTM): {fcf_str}
- Net cash / net debt: {net_str}
- Trailing P/E: {_fmt(q.get('pe'), suffix='x')}
- Forward P/E (usually NEXT fiscal year's estimate, so it reads lower than this year's): {_fmt(q.get('forward_pe'), suffix='x')}
- EV/EBITDA: {_fmt(q.get('ev_ebitda'), suffix='x')}
- 52-week high: ${_fmt(q.get('high_52w'))} | Drawdown from high: {_fmt(drawdown, suffix='%')}

Note: Data from yfinance, may lag 1-7 days. Cross-check with company IR or SEC filings.
{currency_note}
[Recent news headlines — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}]
{_recent_news(ticker)}

IMPORTANT GROUNDING RULES:
- Base your analysis ONLY on the fundamentals and news headlines above.
- For any claim NOT supported by the data or headlines above (specific contract values,
  management quotes, customer names, analyst targets), write "unverified" — do NOT invent it.
- Distinguish clearly between facts from the provided data vs. your general knowledge.
- Do NOT quote peers' multiples or historical averages: you were not given them, and
  figures from memory are often out of date. Compare qualitatively or write "unverified".

MANDATORY OUTPUT FORMAT — your response MUST end with these four lines, EXACTLY,
as the very last lines, with nothing after them:
VERDICT: <one of: RESEARCH-WORTHY | WATCHLIST | PASS | RED FLAG>
CONFIDENCE: <one of: HIGH | MEDIUM | LOW>
THESIS: <one sentence, durable language only — NEVER a specific dollar price.
  Use multiples/%/growth rates instead (e.g. "15x forward earnings for 40% growth"
  not "$148 is cheap") since a dollar figure goes stale the moment the price moves.>
BUY_TRIGGER_DRAWDOWN_PCT: <integer, e.g. -20. The % drawdown from the 52-week high
  that would make this a good entry. Use 0 if the current price already clears your
  bar. This drives a LIVE buy-target price recomputed from the current 52-week high
  every time quotes refresh — so it must be a durable judgment, not today's price.>
"""
    return template.replace("TICKER: {{TICKER}}", f"TICKER: {ticker}") + "\n" + context


# ── Verdict extraction + watchlist update ────────────────────────────────────

def _extract_verdict(text: str) -> str | None:
    # Prefer the explicit "VERDICT: X" line (forced format)
    m = re.search(r"VERDICT:\s*(RESEARCH-WORTHY|WATCHLIST|PASS|RED FLAG)", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Fallback: any verdict string appearing in the text
    for v in VERDICT_STRINGS:
        if v in text.upper():
            return v
    return None


def _extract_confidence(text: str) -> str | None:
    """Pull the CONFIDENCE: HIGH|MEDIUM|LOW line."""
    m = re.search(r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW)", text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _extract_thesis(text: str) -> str | None:
    """Pull the THESIS: line — durable language only, never a dollar price."""
    m = re.search(r"THESIS:\s*(.+)", text)
    if not m:
        return None
    thesis = m.group(1).strip()
    # Strip a leading dollar figure if the model ignored the instruction — better
    # to show nothing than to persist a price that will be wrong within days.
    # Company-level amounts like "$92B FCF" are not prices, so they stay.
    thesis = re.sub(
        r"\$\d[\d,]*\.?\d*(?![\d,.])(?!\s*(?:[BMT]\b|billion|million|trillion))",
        "[price omitted — see live data]", thesis,
    )
    return thesis or None


def _extract_drawdown_trigger(text: str) -> float | None:
    """Pull BUY_TRIGGER_DRAWDOWN_PCT: — the durable, self-updating buy-target basis."""
    m = re.search(r"BUY_TRIGGER_DRAWDOWN_PCT:\s*(-?\d+(?:\.\d+)?)", text)
    if not m:
        return None
    pct = float(m.group(1))
    # Sanity clamp: a trigger outside [-90, 0] is not a usable drawdown target.
    return pct if -90 <= pct <= 0 else None


def _anchor_trigger(ticker: str, drawdown_trigger_pct: float | None, quotes: dict) -> float | None:
    """Turn "0 = today's price is fine" into today's actual drawdown.

    A stored 0 made the target follow the live price, so the name read "at
    target" forever, including after a further 13% drop. Locking in the drawdown
    keeps the judgment fixed, so later moves show up as a real gap.
    """
    if drawdown_trigger_pct != 0:
        return drawdown_trigger_pct
    return quotes.get("tickers", {}).get(ticker, {}).get("drawdown_from_high") or 0.0


def _live_buy_target(ticker: str, drawdown_trigger_pct: float | None, quotes: dict) -> float | None:
    """Recompute a buy target from the CURRENT 52-week high — never a stale price."""
    if drawdown_trigger_pct is None:
        return None
    q = quotes.get("tickers", {}).get(ticker, {})
    # 0 = no pullback gate ("buy at current levels"). Using the drawdown formula
    # would anchor the target to the 52-week high and render a buy-ready name as
    # a large fake discount, so anchor to the live price instead.
    if drawdown_trigger_pct == 0:
        price = q.get("price")
        return round(price, 2) if price else None
    high_52w = q.get("high_52w")
    if not high_52w:
        return None
    return round(high_52w * (1 + drawdown_trigger_pct / 100), 2)


def _bear_check(provider, api_key, ticker, bull_text, news_block) -> str | None:
    """Devil's-advocate second pass: argue AGAINST the buy to surface blind spots."""
    prompt = (
        f"Below is a bullish research note that concluded {ticker} is worth buying. "
        f"You are a skeptical short-seller. In 2-3 sentences, give the STRONGEST "
        f"specific argument AGAINST buying {ticker} right now — the thing the bull "
        f"case is most likely underweighting. Base it ONLY on the note and these "
        f"headlines; if you have no real counter-argument, say 'No strong bear case "
        f"from available data.'\n\n"
        f"Then step out of the short-seller role and grade your own argument neutrally. "
        f"End with exactly one line:\n"
        f"BEAR_SEVERITY: THESIS-BREAKING — a specific fact in the note or headlines shows "
        f"the thesis is false or its data is wrong (e.g. figures that cannot be true, a "
        f"reported event that removes the core business case).\n"
        f"BEAR_SEVERITY: MATERIAL — a real, specific risk the note underweights.\n"
        f"BEAR_SEVERITY: ORDINARY — a normal risk for this kind of stock.\n"
        f"Every stock has real risks, so most arguments are MATERIAL or ORDINARY. Valuation "
        f"concerns, speculation, concentration, competition and anything marked unverified "
        f"are never THESIS-BREAKING."
        f"\n\nHeadlines:\n{news_block}\n\nBullish note:\n{bull_text[:2500]}"
    )
    try:
        return _call_llm(provider, api_key, prompt)
    except Exception:
        return None


def _bear_flips_verdict(bear_text: str | None) -> bool:
    """True only if the bear case shows the thesis itself is wrong.

    This used to ask "CHANGES VERDICT: YES/NO" straight after telling the model
    to be a short-seller. It said YES in 75 of 75 notes, so every RESEARCH-WORTHY
    call was downgraded and the app could never show a name as buy-ready.
    """
    if not bear_text:
        return False
    return bool(re.search(r"BEAR_SEVERITY:\s*THESIS-BREAKING", bear_text, re.IGNORECASE))


def _synthesize_next_action(final_verdict: str, thesis: str | None, drawdown_pct: float | None) -> str:
    """Deterministic, durable next_action — no dollar figures, so it never goes stale."""
    t = thesis or "see thesis"
    if final_verdict == "RESEARCH-WORTHY":
        return f"RESEARCH — {t} Current levels already clear the entry bar."
    if final_verdict == "WATCHLIST":
        if drawdown_pct is not None and drawdown_pct < 0:
            return f"WAIT — {t} Revisit at {abs(drawdown_pct):.0f}% below the 52-week high."
        return f"WAIT — {t}"
    if final_verdict == "RED FLAG":
        return f"AVOID — {t}"
    return f"DROP — {t}"


def _update_watchlist(
    ticker: str, verdict: str, output_file: str,
    confidence: str | None = None, bear: str | None = None,
    thesis: str | None = None, drawdown_trigger_pct: float | None = None,
    live_buy_target: float | None = None,
    unsupported_figures: list[str] | None = None,
):
    with open(WATCHLIST_PATH) as f:
        wl = json.load(f)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Policy: a bear-case check that explicitly says it changes the call
    # downgrades RESEARCH-WORTHY -> WATCHLIST automatically. Storing the bear
    # text without acting on it (the previous behavior) meant 8 names were
    # shown as buy-ready even though their own self-critique said not to buy.
    downgraded = verdict == "RESEARCH-WORTHY" and _bear_flips_verdict(bear)
    final_verdict = "WATCHLIST" if downgraded else verdict

    next_action = _synthesize_next_action(final_verdict, thesis, drawdown_trigger_pct)

    updated = False
    for candidate in wl.get("candidates", []):
        if candidate["ticker"] == ticker:
            candidate["verdict"]         = final_verdict
            candidate["llm_verdict"]     = verdict          # raw model output, kept for transparency
            candidate["bear_downgraded"] = downgraded
            candidate["research_file"]   = output_file
            candidate["last_researched"] = today
            candidate["status"]          = "research_complete"
            candidate["unsupported_figures"] = unsupported_figures or []
            if confidence:
                candidate["confidence"] = confidence
            if bear:
                candidate["bear_check"] = bear.strip()
            # Overwrite the stale hand-written content every time real research
            # runs — this was the actual gap: verdict/confidence updated but
            # thesis/buy_target/next_action stayed frozen at whatever was first
            # written, even across dozens of re-research runs.
            if thesis:
                candidate["thesis"] = thesis
            candidate["next_action"] = next_action
            if drawdown_trigger_pct is not None:
                # Durable primitive — target_alerts.py recomputes buy_target from
                # this + the live 52-week high on every quote refresh, so the
                # target self-heals instead of rotting as a fixed dollar figure.
                candidate["buy_trigger_drawdown_pct"] = drawdown_trigger_pct
            if live_buy_target is not None:
                candidate["buy_target"] = live_buy_target
            updated = True
            break

    if not updated:
        wl.setdefault("candidates", []).append({
            "ticker":          ticker,
            "name":            ticker,
            "theme":           "unknown",
            "status":          "research_complete",
            "thesis":          thesis or "",
            "added":           today,
            "verdict":         final_verdict,
            "llm_verdict":     verdict,
            "bear_downgraded": downgraded,
            "next_action":     next_action,
            "buy_trigger_drawdown_pct": drawdown_trigger_pct,
            "buy_target":      live_buy_target,
            "research_file":   output_file,
            "last_researched": today,
            "unsupported_figures": unsupported_figures or [],
        })

    wl["last_updated"] = today
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(wl, f, indent=2)

    return final_verdict, downgraded


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", type=str, help="Ticker symbol (e.g. AAPL)")
    parser.add_argument("--save-only", action="store_true",
                        help="Save output but don't update watchlist.json")
    parser.add_argument("--model", type=str, default=None,
                        help="Override model (e.g. deepseek-ai/deepseek-v4.1-flash for faster results)")
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

    # Fail before anything is saved: a note with no verdict was being committed
    # and counted as landed while the watchlist kept the old research.
    verdict = _extract_verdict(text)
    if not verdict:
        print(f"❌  No verdict in the response for {ticker} — nothing saved.")
        sys.exit(1)

    today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename  = f"{ticker}_{today}.md"
    out_path  = os.path.join(OUTPUT_DIR, filename)

    with open(out_path, "w") as f:
        f.write(f"# Research: {ticker} — {today}  (model: {model_label})\n\n")
        f.write(text)

    print(f"\n{text}\n")

    confidence = _extract_confidence(text)
    thesis = _extract_thesis(text)
    drawdown_trigger_pct = _anchor_trigger(ticker, _extract_drawdown_trigger(text), quotes)
    live_buy_target = _live_buy_target(ticker, drawdown_trigger_pct, quotes)

    # Devil's-advocate pass only for buy-ready names — surfaces blind spots
    bear = None
    if verdict == "RESEARCH-WORTHY":
        print("🐻  Running bear-case check...")
        bear = _bear_check(provider, api_key, ticker, text, _recent_news(ticker))
        if bear:
            with open(out_path, "a") as f:
                f.write(f"\n\n---\n\n## Bear-Case Check (devil's advocate)\n\n{bear}\n")
            print(f"\n{bear}\n")

    unsupported = find_unsupported(f"{text}\n{bear or ''}", source_block(prompt))
    with open(out_path, "a") as f:
        f.write(fact_check_section(unsupported))
    print(f"🔎  Fact-check: {len(unsupported)} figure(s) not in the source data: {unsupported}")

    conf_str = f" (confidence: {confidence})" if confidence else ""
    print(f"✅  Verdict: {verdict}{conf_str}")
    if thesis:
        print(f"📄  Thesis: {thesis}")
    if not args.save_only:
        final_verdict, downgraded = _update_watchlist(
            ticker, verdict, f"output/research/{filename}", confidence, bear,
            thesis=thesis, drawdown_trigger_pct=drawdown_trigger_pct,
            live_buy_target=live_buy_target, unsupported_figures=unsupported,
        )
        if downgraded:
            print(f"⚠️  Bear check flipped the call — downgraded {verdict} → {final_verdict}")
        print(f"📝  Updated watchlist.json → {ticker} = {final_verdict}{conf_str}")

    print(f"💾  Saved → {out_path}")


if __name__ == "__main__":
    main()
