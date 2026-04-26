# Watchlist System Fix Plan

**Date:** 2026-04-25
**Author:** TickRun pivot team
**Status:** Awaiting confirmation

## Why this plan exists

The first run of the watchlist surfaced POWL, ALAB, ONTO, QLYS as RESEARCH-WORTHY. After web-verifying with current April 2026 data:
- 3 of 4 names were trading at or near 52-week highs
- 1 name (QLYS) was a confirmed value trap with declining NRR
- POWL had short interest +199% in 2 weeks (smart money exiting)
- ALAB had 151 insider sells, 0 buys in 6 months (CEO dumped $122M)
- The "indirect AI beneficiary" thesis worked, but the screen had no awareness of entry price, sentiment, or whether the trade was already crowded

**Root cause:** The watchlist was built around fundamental quality + theme keywords. It had zero awareness of:
1. Where the stock is in its multi-year price cycle
2. What insiders, hedge funds, and shorts are doing
3. Whether the thesis is consensus or contrarian
4. Whether the user could enter at a sane price

**Result:** The system surfaced "good companies at bad prices" — the worst kind of recommendation for a Path 3 retail investor.

---

## The 5 fixes (ranked by impact)

### Fix 1: "% from 52-week high" gate (CRITICAL)

**Problem:** Screen has no awareness of where in the price cycle a name sits.

**Solution:** Add a soft gate to `composite.py` (or its replacement) and a hard rule to research_ticker.py:

- Names within 10% of 52-week high → automatic verdict downgrade to WATCHLIST with note "WAIT for pullback"
- Names within 25% of 52-week high → eligible for RESEARCH-WORTHY only if other signals exceptional
- Names down 30%+ from 52-week high → eligible for RESEARCH-WORTHY (this is where opportunities live)

**Implementation:** ~15 minutes
- Already have `drawdown_from_high` field in quotes_cache.json
- Add a guard in `scripts/research_ticker.py` that prepends warning to prompt
- Add a filter to `scripts/build_dashboard.py` that flags positions
- Cost: zero (uses existing data)

**Why this is #1:** The single biggest failure mode of the original screen.

---

### Fix 2: Insider activity tracking (HIGH)

**Problem:** The system has zero visibility into what insiders are doing. Catastrophic — ALAB's 151:0 sell:buy ratio in 6 months would have been an instant disqualifier.

**Solution:** Add `scripts/insider_check.py` that:
- For each watchlist ticker, fetches insider activity from a free source
- Computes 6-month sell:buy ratio
- Flags any ticker with:
  - Buy ratio = 0% over 6 months → RED FLAG (insiders refuse to buy)
  - Sell:buy ratio > 5:1 → bearish signal
  - Insider buys present + sells absent → bullish signal

**Free data sources:**
- OpenInsider.com (scrape-friendly)
- SEC EDGAR Form 4 filings (XML, free, official)
- Finviz (free with rate limits)

**Implementation:** ~2 hours
- Cost: zero (free APIs/scrapers)
- Adds 30 seconds per ticker

**Why this is #2:** Insider behavior is the single most reliable smart-money signal. Free to access. Should never have been omitted.

---

### Fix 3: Short interest + change tracking (HIGH)

**Problem:** POWL's short interest +199% in 2 weeks should have been an automatic alert. The system missed it entirely.

**Solution:** Add `scripts/short_interest_check.py` that:
- Pulls bi-weekly short interest data (FINRA publishes free)
- Computes:
  - Short interest as % of float
  - 2-week change in short interest
  - Days-to-cover (short interest ÷ avg daily volume)
- Flags:
  - SI% of float >10% AND rising → bearish institutional bet
  - 2-week change >50% → smart money positioning for downside
  - Days-to-cover >5 → squeeze potential (could be bullish or bearish depending on context)

**Free data sources:**
- FINRA Reg SHO daily files (https://regsho.finra.org/)
- Yahoo Finance (in `info["shortPercentOfFloat"]`)
- StockAnalysis.com (free)

**Implementation:** ~2 hours
- Already partially available in yfinance (need to extend `refresh_quotes.py`)
- Cost: zero

**Why this is #3:** Combined with Fix 2, this is the institutional-positioning lens that the user-level workflow desperately needed.

---

### Fix 4: Universe expansion + market cap stratification (MEDIUM)

**Problem:** The original screen restricted to $300M-$10B market cap. This systematically excluded MSFT, GOOGL, META, AMZN — the names that, on this date, are the most attractive AI-thematic plays at -20-25% from highs.

**Solution:** Restructure the universe into bands:
- **Mega-cap quality (>$100B):** lower bar for inclusion (must be down 15%+ from 52w high to surface). MSFT/GOOGL/META/AMZN should be considered when on sale.
- **Large-cap conviction ($10B-$100B):** standard fundamental bar + thematic match
- **Mid/small-cap thematic ($300M-$10B):** the original screen's universe, but with the new gates

**Why split?** Different market cap tiers require different research methodologies:
- Mega-caps: macro/sector flows matter more than company-specific catalysts
- Mid-caps: company catalysts dominate
- Small-caps: management/execution dominates

**Implementation:** ~3-4 hours
- Update `data/themes.json` to allow theme-eligible mega-caps
- Add `cap_tier` field to watchlist entries
- Modify `build_dashboard.py` to surface "mega-cap on sale" as a distinct signal type

---

### Fix 5: Hedge fund conviction signal (MEDIUM)

**Problem:** The system had no awareness of where smart money is rotating IN (Ackman → UBER, Druckenmiller → DOCU, Einhorn → DLTR). These would have been your highest-conviction adds in Q1 2026.

**Solution:** Add `scripts/hedge_fund_signal.py` that:
- Pulls latest 13F filings (45-day delay, but useful)
- For each ticker on watchlist, identifies any "name brand" hedge fund (Pershing, Greenlight, Duquesne, Berkshire, etc.) initiating a NEW position >$10M
- Flags conviction-confirming events: "Ackman bought 30M shares" → bullish data point

**Free data sources:**
- WhaleWisdom (free tier)
- HedgeFollow.com
- 13F filings on SEC EDGAR (free, official, but slower to parse)
- Stockcircle.com

**Implementation:** ~3-4 hours
- Quarterly cadence (not weekly)
- Cost: zero
- Most useful: detect NEW positions, not existing holdings

**Why this is #5:** Important but not as time-sensitive as the others. 13F data is 45-day delayed.

---

## Phased rollout

### Phase 1 (this weekend, ~3 hours): Critical fixes
- [ ] **Fix 1:** Add "% from 52-week high" gate to `research_ticker.py` and `build_dashboard.py`
- [ ] **Fix 4 (partial):** Allow mega-caps in watchlist; update themes.json (already done in this commit)
- [ ] Update co-work prompt (`prompts/stock_research.md`) to include current price context and require explicit "entry price" verdict
- [ ] Re-rank existing watchlist with new gates

**Acceptance:** Re-running the dashboard surfaces no name within 10% of its 52-week high as RESEARCH-WORTHY.

### Phase 2 (next week, ~4 hours): Smart money signals
- [ ] **Fix 2:** Build `scripts/insider_check.py` (OpenInsider scrape or SEC EDGAR XML)
- [ ] **Fix 3:** Extend `refresh_quotes.py` to capture short interest + 2-week change
- [ ] Surface both signals in `build_dashboard.py` and the UI
- [ ] Add a "smart money signals" tab to the dashboard

**Acceptance:** Dashboard shows insider buy/sell ratio and short interest trend per watchlist name. ALAB-style red flags get surfaced automatically.

### Phase 3 (week after, ~4 hours): Hedge fund tracking
- [ ] **Fix 5:** Build `scripts/hedge_fund_signal.py` for 13F monitoring
- [ ] Surface "new positions by name-brand funds" in dashboard
- [ ] Quarterly automated run

**Acceptance:** When Ackman initiates a new position in a small/mid-cap, dashboard surfaces it within 24 hours of 13F filing.

---

## What this prevents (specific failure modes)

| Failure mode | Old system | Fixed system |
|--------------|-----------|--------------|
| Recommends stock at 52-week high | ❌ Yes (POWL, ONTO) | ✅ Auto-downgrades to WATCHLIST |
| Misses insider dumping | ❌ Yes (ALAB) | ✅ RED FLAG when 0 buys + heavy sells |
| Misses short interest spike | ❌ Yes (POWL +199%) | ✅ Bearish alert + auto-downgrade |
| Excludes mega-cap AI plays on sale | ❌ Yes (MSFT, GOOGL, META) | ✅ Eligible when down 15%+ from high |
| Misses smart money rotation | ❌ Yes (Ackman → UBER) | ✅ Surfaces new 13F positions |
| Recommends value trap with declining NRR | ❌ Yes (QLYS) | ⚠️ Needs separate fix (NRR data not in yfinance — requires LLM extraction from 10-K) |

---

## Out of scope (acknowledged, not fixing now)

- **NRR/customer retention extraction from 10-Ks** (needs LLM cost — defer)
- **Earnings surprise tracking** (low signal-to-noise)
- **Options flow data** (paid sources only — defer)
- **Sector-rotation models** (overengineering — keep it simple)
- **Backtest engine** (the market doesn't repeat exactly; backtest results overfit)

---

## Cost summary

| Fix | Time | Money | Data source |
|-----|------|-------|-------------|
| Fix 1: 52w high gate | 15 min | $0 | yfinance (already have) |
| Fix 2: Insider tracking | 2 hr | $0 | OpenInsider / SEC EDGAR |
| Fix 3: Short interest | 2 hr | $0 | FINRA / yfinance |
| Fix 4: Cap stratification | 3-4 hr | $0 | yfinance |
| Fix 5: Hedge fund 13F | 3-4 hr | $0 | WhaleWisdom / SEC EDGAR |
| **Total Phase 1-3** | **~10-12 hrs** | **$0** | All free sources |

---

## Decision needed

Confirm to proceed with Phase 1 (this weekend, 3 hours)?

- **Yes** → I'll implement Fix 1 + the prompt update in the next commit
- **Yes but skip the dashboard refactor** → just fix the data layer, keep current UI
- **Modify** → tell me which fix to deprioritize or what to add

Phases 2 and 3 can be queued for the following weekends.
