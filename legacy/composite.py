#!/usr/bin/env python3
"""
composite.py — Multi-factor composite scoring for the TickRun universe.

Reads data/fundamentals.json, applies hard exclusion gates, scores each
surviving ticker on six factors (Quality, Valuation, Recurring,
Profitability, Risk, AI Exposure), and writes the top 25 candidates
(sorted by composite score) to output/weekly_screens.json.

Scoring works in two stages:

1.  HARD GATES — boolean filters that drop a ticker outright. These
    enforce the user's investability rules (mcap band, balance-sheet
    health, listing quality, ETF exclusion, meme-stock floor).

2.  COMPOSITE — six factor sub-scores in 0–100, combined with weights:

        Score = 0.20·Quality + 0.20·Valuation + 0.15·Profitability
              + 0.10·Risk + 0.15·Recurring + 0.20·AI_Exposure

    Each sub-score is a winsorized z-score within the surviving
    universe, mapped to 0–100. Missing values default to 50 (neutral)
    so partial data degrades gracefully rather than excluding the
    ticker.

The output mirrors the original schema but adds factor sub-scores,
proxy disclosures, and an AI-exposure narrative slot.

Usage:
    python3 composite.py [--top N]
"""

import argparse
import json
import math
import os
import statistics as stats
import sys
from datetime import datetime, timezone

SCRIPT_DIR        = os.path.dirname(os.path.abspath(__file__))
FUNDAMENTALS_PATH = os.path.join(SCRIPT_DIR, "data", "fundamentals.json")
OUTPUT_PATH       = os.path.join(SCRIPT_DIR, "output", "weekly_screens.json")
os.makedirs(os.path.join(SCRIPT_DIR, "output"), exist_ok=True)

# ── Hard gates ───────────────────────────────────────────────
MIN_MARKET_CAP =   300_000_000
MAX_MARKET_CAP = 10_000_000_000
MIN_CURRENT_RATIO = 1.0
MAX_DEBT_TO_EBITDA = 5.0
MAX_SHORT_PCT_FLOAT = 20.0   # Crude meme-stock floor

# ── Factor weights ───────────────────────────────────────────
WEIGHTS = {
    "quality":       0.20,
    "valuation":     0.20,
    "profitability": 0.15,
    "risk":          0.10,
    "recurring":     0.15,
    "ai_exposure":   0.20,
}

# ── AI-exposure heuristic ────────────────────────────────────
# Sub-industries with structural exposure to the AI/data-center/power/
# networking buildout. Membership earns a base AI score (0..40); the
# rest comes from keyword matches in the business summary.
AI_INDUSTRY_SCORES = {
    # Direct picks-and-shovels
    "Semiconductors": 35,
    "Semiconductor Equipment & Materials": 40,
    "Semiconductor Equipment": 40,
    "Electronic Equipment, Instruments & Components": 30,
    "Computer Hardware": 30,
    "Networking Equipment": 35,
    "Communication Equipment": 30,
    "Electronic Components": 30,
    # Software / enterprise-IT layer
    "Software—Application": 25,
    "Software—Infrastructure": 35,
    "Information Technology Services": 25,
    # Data-center adjacent
    "REIT—Specialty": 30,
    "REIT—Office": 10,
    "REIT—Industrial": 15,
    # Power and grid (data-center power demand)
    "Utilities—Regulated Electric": 25,
    "Utilities—Independent Power Producers": 30,
    "Utilities—Renewable": 20,
    "Electrical Equipment & Parts": 35,
    "Specialty Industrial Machinery": 25,
    "Engineering & Construction": 25,
    # Cooling / thermal management
    "Building Products & Equipment": 20,
}

AI_KEYWORDS = (
    ("data center",          12),
    ("data-center",          12),
    ("hyperscale",           14),
    ("hyperscaler",          14),
    ("artificial intelligence", 12),
    (" ai ",                  8),
    ("machine learning",      8),
    ("gpu",                  10),
    ("accelerator",           8),
    ("cloud computing",       8),
    ("cloud infrastructure", 10),
    ("transformer",           8),  # power-side, but also the LLM term
    ("power management",      8),
    ("thermal management",   10),
    ("liquid cooling",       12),
    ("fiber",                 6),
    ("optical interconnect", 12),
    ("high-speed connectivity", 8),
    ("switching",             6),
    ("electrical grid",       6),
    ("substation",            8),
    ("backup power",          6),
    ("ups system",            8),
    ("colocation",           14),
)

# Sub-industries with reliably recurring/contractual revenue (rough
# v1 heuristic — refined in Phase B with LLM tagging).
RECURRING_INDUSTRIES = {
    "Software—Application":      85,
    "Software—Infrastructure":   90,
    "Information Technology Services": 70,
    "Specialty Business Services": 65,
    "Insurance—Property & Casualty": 70,
    "Insurance—Life":            75,
    "REIT—Specialty":            80,
    "REIT—Industrial":           75,
    "REIT—Residential":          75,
    "REIT—Office":               70,
    "REIT—Healthcare":           70,
    "Telecom Services":          70,
    "Utilities—Regulated Electric": 80,
    "Utilities—Regulated Gas":   80,
    "Utilities—Renewable":       70,
    "Waste Management":          80,
    "Asset Management":          60,
    "Capital Markets":           50,
    "Banks—Regional":            45,
}

# ── Hard-gate evaluation ─────────────────────────────────────

def passes_hard_gates(rec: dict) -> tuple[bool, str]:
    """True if the ticker survives the boolean exclusion gates."""
    if rec.get("status") == "failed":
        return False, "fetch_failed"
    if rec.get("quote_type", "EQUITY") != "EQUITY":
        return False, f"quote_type={rec.get('quote_type')}"
    mc = rec.get("market_cap")
    if mc is None:
        return False, "no_market_cap"
    if mc < MIN_MARKET_CAP or mc > MAX_MARKET_CAP:
        return False, "outside_mcap_band"
    cr = rec.get("current_ratio")
    if cr is not None and cr < MIN_CURRENT_RATIO:
        return False, "weak_liquidity"
    dte = rec.get("debt_to_ebitda")
    if dte is not None and dte > MAX_DEBT_TO_EBITDA:
        return False, "over_leveraged"
    fcf = rec.get("fcf") or 0
    op_inc = rec.get("operating_cf") or 0
    if fcf <= 0 and op_inc <= 0:
        return False, "no_cash_generation"
    sp = rec.get("short_pct_float")
    if sp is not None and sp > MAX_SHORT_PCT_FLOAT:
        return False, "meme_short_interest"
    return True, ""


# ── AI-exposure scoring ──────────────────────────────────────

def ai_exposure_score(rec: dict) -> tuple[float, list[str]]:
    """Return (score 0–100, list of matched evidence strings)."""
    industry = rec.get("industry", "")
    summary  = (rec.get("summary") or "").lower()

    base = AI_INDUSTRY_SCORES.get(industry, 0)
    matched: list[str] = []
    if base:
        matched.append(f"industry:{industry}")

    keyword_total = 0
    for kw, weight in AI_KEYWORDS:
        if kw in summary:
            matched.append(f"kw:{kw.strip()}")
            keyword_total += weight
    keyword_total = min(keyword_total, 60)

    raw = base + keyword_total
    return min(raw, 100.0), matched


def recurring_score(rec: dict) -> float:
    """Heuristic recurring-revenue proxy by sub-industry."""
    industry = rec.get("industry", "")
    if industry in RECURRING_INDUSTRIES:
        return float(RECURRING_INDUSTRIES[industry])
    # Modest credit for businesses with high gross margins (often
    # subscription-like economics) — caps at 40 to avoid double-counting
    # with the standalone Quality factor.
    gm = rec.get("gross_margin")
    if gm and gm > 60:
        return 45.0
    if gm and gm > 45:
        return 35.0
    return 25.0


# ── Z-score helpers ──────────────────────────────────────────

def winsorized_zscore(values: list[float | None], higher_is_better: bool = True) -> list[float]:
    """Convert a list of nullable floats to 0–100 z-scores. Missing → 50."""
    real = [v for v in values if v is not None and not math.isnan(v)]
    if len(real) < 5:
        return [50.0] * len(values)

    # Winsorize at the 5th and 95th percentile to soften outliers.
    real_sorted = sorted(real)
    lo = real_sorted[int(0.05 * len(real_sorted))]
    hi = real_sorted[int(0.95 * len(real_sorted))]
    clipped = [min(max(v, lo), hi) for v in real]
    mean = stats.mean(clipped)
    sd   = stats.pstdev(clipped) or 1.0

    out: list[float] = []
    for v in values:
        if v is None or math.isnan(v):
            out.append(50.0)
            continue
        v_clip = min(max(v, lo), hi)
        z = (v_clip - mean) / sd
        # Map z (typically -2..+2) → 0..100 with center at 50.
        score = 50.0 + (z * 20.0 if higher_is_better else -z * 20.0)
        out.append(max(0.0, min(100.0, score)))
    return out


# ── Composite assembly ───────────────────────────────────────

def score_universe(records: list[dict]) -> list[dict]:
    surviving = []
    for r in records:
        passes, reason = passes_hard_gates(r)
        if not passes:
            continue
        surviving.append({**r, "_gate_reason": reason})

    # Build factor input vectors (positionally aligned with `surviving`).
    quality_inputs   = [s.get("roic_proxy")   for s in surviving]   # higher better
    quality2         = [s.get("gross_margin") for s in surviving]
    val_ev_ebitda    = [s.get("ev_ebitda")    for s in surviving]   # lower better
    val_pe           = [s.get("forward_pe") or s.get("pe") for s in surviving]
    val_fcf_yield    = [s.get("fcf_yield")    for s in surviving]   # higher better
    prof_op_margin   = [s.get("op_margin")    for s in surviving]
    prof_fcf_margin  = [s.get("fcf_margin")   for s in surviving]
    risk_de          = [s.get("debt_equity")  for s in surviving]   # lower better
    risk_dte         = [s.get("debt_to_ebitda") for s in surviving]

    z_roic    = winsorized_zscore(quality_inputs, higher_is_better=True)
    z_gross   = winsorized_zscore(quality2,        higher_is_better=True)
    z_evebit  = winsorized_zscore(val_ev_ebitda,   higher_is_better=False)
    z_pe      = winsorized_zscore(val_pe,           higher_is_better=False)
    z_fcfy    = winsorized_zscore(val_fcf_yield,   higher_is_better=True)
    z_opm     = winsorized_zscore(prof_op_margin,  higher_is_better=True)
    z_fcfm    = winsorized_zscore(prof_fcf_margin, higher_is_better=True)
    z_de      = winsorized_zscore(risk_de,          higher_is_better=False)
    z_dte     = winsorized_zscore(risk_dte,         higher_is_better=False)

    scored = []
    for i, s in enumerate(surviving):
        ai_score, ai_evidence = ai_exposure_score(s)
        recur = recurring_score(s)

        quality_factor       = (z_roic[i] + z_gross[i]) / 2.0
        valuation_factor     = (z_evebit[i] + z_pe[i] + z_fcfy[i]) / 3.0
        profitability_factor = (z_opm[i] + z_fcfm[i]) / 2.0
        risk_factor          = (z_de[i] + z_dte[i]) / 2.0
        recurring_factor     = recur
        ai_factor            = ai_score

        composite = (
            WEIGHTS["quality"]       * quality_factor
            + WEIGHTS["valuation"]   * valuation_factor
            + WEIGHTS["profitability"] * profitability_factor
            + WEIGHTS["risk"]        * risk_factor
            + WEIGHTS["recurring"]   * recurring_factor
            + WEIGHTS["ai_exposure"] * ai_factor
        )

        scored.append({
            "symbol":   s["symbol"],
            "name":     s.get("name"),
            "sector":   s.get("sector"),
            "industry": s.get("industry"),
            "price":    s.get("price"),
            "market_cap": s.get("market_cap"),
            "summary":  (s.get("summary") or "")[:600],
            "factors": {
                "quality":       round(quality_factor, 1),
                "valuation":     round(valuation_factor, 1),
                "profitability": round(profitability_factor, 1),
                "risk":          round(risk_factor, 1),
                "recurring":     round(recurring_factor, 1),
                "ai_exposure":   round(ai_factor, 1),
            },
            "composite_score": round(composite, 1),
            "ai_evidence":     ai_evidence,
            "metrics": {
                "pe":            s.get("pe"),
                "forward_pe":    s.get("forward_pe"),
                "ev_ebitda":     s.get("ev_ebitda"),
                "ev_sales":      s.get("ev_sales"),
                "fcf_yield":     s.get("fcf_yield"),
                "fcf_margin":    s.get("fcf_margin"),
                "gross_margin":  s.get("gross_margin"),
                "op_margin":     s.get("op_margin"),
                "roic_proxy":    s.get("roic_proxy"),
                "debt_to_ebitda": s.get("debt_to_ebitda"),
                "debt_equity":   s.get("debt_equity"),
                "current_ratio": s.get("current_ratio"),
                "rev_growth":    s.get("rev_growth"),
                "eps_growth":    s.get("eps_growth"),
                "ret_12m":       s.get("ret_12m"),
                "div_yield":     s.get("div_yield"),
            },
            "proxy_notes": s.get("proxy_notes", []),
            "data_status": s.get("status", "ok"),
        })

    scored.sort(key=lambda x: -x["composite_score"])
    return scored


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=25, help="Number of picks in top_conviction")
    args = parser.parse_args()

    with open(FUNDAMENTALS_PATH) as f:
        data = json.load(f)

    records = data["tickers"]
    print(f"📐 Scoring {len(records)} fundamentals records…")

    ranked = score_universe(records)
    print(f"   Surviving hard gates: {len(ranked)}")

    top = ranked[: args.top]
    print(f"   Top {len(top)} by composite:")
    for r in top[:10]:
        f = r["factors"]
        print(f"   {r['symbol']:<6} {r['composite_score']:5.1f}  "
              f"Q={f['quality']:.0f} V={f['valuation']:.0f} "
              f"P={f['profitability']:.0f} R={f['risk']:.0f} "
              f"Rec={f['recurring']:.0f} AI={f['ai_exposure']:.0f}  "
              f"({r['industry']})")

    # Sector mix on top 25
    sector_mix: dict[str, int] = {}
    for r in top:
        sector_mix[r["sector"]] = sector_mix.get(r["sector"], 0) + 1

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe":     f"Russell mid+small ({data['universe_size']} sourced, {data['ok'] + data['partial']} fetched, {len(ranked)} survived gates)",
        "scoring": {
            "weights":    WEIGHTS,
            "hard_gates": {
                "market_cap_band": [MIN_MARKET_CAP, MAX_MARKET_CAP],
                "min_current_ratio": MIN_CURRENT_RATIO,
                "max_debt_to_ebitda": MAX_DEBT_TO_EBITDA,
                "max_short_pct_float": MAX_SHORT_PCT_FLOAT,
                "must_generate_cash": True,
            },
            "ai_exposure_method": "Industry score (0-40) + summary keyword matches (capped 60)",
            "recurring_method":   "Sub-industry whitelist proxy (v1)",
            "proxies_used": {
                "roic_proxy":      "ROE (yfinance ROIC unavailable)",
                "earnings_yield_proxy": "1 / EV_EBITDA",
                "recurring":       "Sub-industry heuristic, not actual subscription % of revenue",
            },
        },
        "top_conviction":   top,
        "sector_mix_top25": sector_mix,
        "total_passes":     len(ranked),
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Wrote top {len(top)} → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
