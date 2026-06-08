# TickRun — Claude Code Context

## What This Is

A personal stock research dashboard for a $14k Roth IRA (F-1 STEM OPT — passive investing only,
no day trading, no options/margin). The system screens for U.S. stocks that are undervalued but
growing, especially indirect AI/data-center/infrastructure beneficiaries, and produces a curated
watchlist with automated smart-money signals.

**Brokerage:** Robinhood Roth IRA
**Key benefits:** No capital gains tax ever. No PDT rule (Roth IRA exempt). Tax-free compounding.
**2026 contribution limit:** $7,000/year max across all Roth accounts.

**Live dashboard:** https://tarun-talreja.github.io/TickRun/

---

## Architecture

### Data flow
```
scripts/refresh_quotes.py    ← fetches prices + fundamentals via yfinance
scripts/insider_check.py     ← 6-month insider buy/sell ratios via yfinance (weekly)
scripts/hedge_fund_signal.py ← institutional holders + conviction fund detection (quarterly)
scripts/pullback_alerts.py   ← generates pullback alerts from quotes
scripts/earnings_calendar.py ← upcoming earnings for watchlist names
scripts/build_dashboard.py   ← assembles output/dashboard.json from all sources
index.html                   ← React SPA that reads output/dashboard.json
```

### Key data files
```
data/watchlist.json          ← curated candidates with verdict, thesis, buy_target
data/portfolio.json          ← holdings (core VOO + thematic picks), rules
data/themes.json             ← 9 investment themes with colors
data/quotes_cache.json       ← current prices/fundamentals (auto-refreshed daily)
data/insider_signals.json    ← insider buy/sell signals (auto-refreshed weekly)
data/hedge_fund_signals.json ← conviction fund holders (auto-refreshed quarterly)
data/hedge_fund_snapshot.json← previous quarter's holder set (for new-position diffing)
output/dashboard.json        ← assembled dashboard data (read by index.html)
output/alerts.json           ← pullback alerts + stale research
output/earnings_calendar.json← upcoming earnings
```

### GitHub Actions
```
.github/workflows/daily.yml       ← 6pm ET weekdays: quotes + alerts + dashboard rebuild
.github/workflows/weekly.yml      ← 6pm ET Sundays: quotes + insider check + full rebuild
.github/workflows/hedge_fund.yml  ← Feb/May/Aug/Nov 15: quarterly 13F signal run
.github/workflows/pages.yml       ← deploys index.html + dashboard.json to GitHub Pages
```

---

## Watchlist System

### Verdict taxonomy
- **RESEARCH-WORTHY** — strong fundamentals + good entry price → buy candidate
- **WATCHLIST** — good business, bad price or unclear entry → monitor
- **PASS** — disqualified (declining NRR, value trap, etc.)
- **RED FLAG** — institutional exit, fraud risk, do not buy

### 5 quality gates (all implemented)
1. **52-week high gate** — names within 10% of 52w high auto-downgrade to WATCHLIST
   (mega-caps get -15% threshold since they rarely fall more)
2. **Insider tracking** — 6-month sell:buy ratio; 0 buys = RED_FLAG signal
3. **Short interest** — short % of float + days-to-cover surfaced per name
4. **Cap stratification** — dynamic cap_tier (mega/large/mid/small); mega-caps down 15%+
   surface as "MEGA-CAP ON SALE" in Signals tab
5. **Hedge fund conviction** — cross-matches 18 name-brand funds; diffs quarterly
   snapshots to detect NEW 13F positions

### To research a new ticker
```bash
export ANTHROPIC_API_KEY=sk-...
python3 scripts/refresh_quotes.py          # make sure cache is fresh
python3 scripts/research_ticker.py TICKER  # calls Claude, updates watchlist.json
```
The co-work prompt is at `prompts/stock_research.md`. Uses claude-opus-4-7 by default.

---

## Current Portfolio Plan

- **Core (60%):** $8,400 VOO — deployed in one tranche
- **Thematic (35%):** ~$4,900 across GOOGL, MSFT, UBER (staged entry around earnings)
- **International (5%):** deferred
- **Rules:** no options, no margin, no leveraged ETFs, max 15% per position

### Staged buy schedule (as of 2026-04-25)
| Ticker | Amount | Trigger |
|--------|--------|---------|
| VOO    | $8,400 | ASAP — core anchor |
| GOOGL  | $1,500 | Apr 30 (post Apr 29 earnings) |
| MSFT   | $1,200 | Apr 30 (post Apr 29 earnings) |
| UBER   | $700   | May 7 |
| META   | $1,000 | May 30+ (post Apr 29 earnings) |

---

## Investment Constraints (IMPORTANT)

- **Visa:** F-1 STEM OPT — passive investing only. Day trading = unauthorized employment.
  Maximum ~2 trades per week to avoid pattern day trader classification.
- **Account:** Roth IRA at Fidelity. Tax-advantaged. No RMDs.
- **30-day rule:** Verify with broker before selling — may apply to certain mutual funds.
- **No selling** within 30 days of purchase for mutual funds (ETFs/stocks likely fine).

---

## Running Locally

```bash
# Install dependencies
pip install yfinance tenacity

# Refresh quotes for watchlist + portfolio
python3 scripts/refresh_quotes.py

# Run all signals
python3 scripts/insider_check.py       # weekly cadence
python3 scripts/hedge_fund_signal.py   # quarterly cadence
python3 scripts/pullback_alerts.py
python3 scripts/earnings_calendar.py

# Rebuild dashboard
python3 scripts/build_dashboard.py

# Serve dashboard locally
python3 -m http.server 8080
# open http://localhost:8080
```

---

## Key Learnings / Non-Obvious Decisions

1. **Switched from 906-ticker composite screener to curated watchlist** — original screener
   mixed incomparable sectors and had a weak AI-exposure factor (10/100 points). The pivot to
   a hand-curated watchlist + LLM co-work prompt produces higher-signal output.

2. **Original screener output was unactionable** — POWL, ALAB, ONTO, QLYS all surfaced at/near
   52-week highs with bearish institutional signals (ALAB: 151 insider sells, 0 buys; POWL: short
   interest +199% in 2 weeks). All 4 were downgraded after web research.

3. **Mega-caps added to watchlist** — MSFT (-21.5% from ATH), GOOGL (29x P/E), META (-25%)
   were better AI plays than the mid-cap names the screener found.

4. **UBER thesis** — Bill Ackman's #1 position (18.5% of Pershing Square). 50% of bookings
   are delivery (insulated from autonomous vehicle FUD). Target $105 per Ackman.

5. **Legacy files archived to `legacy/`** — fetch_daily.py, fetch_weekly.py, composite.py,
   universe.py, and associated screens/schemas are no longer used but kept for reference.

6. **yfinance dividend yield bug** — returns raw decimal (0.019 = 1.9%). Fixed in refresh_quotes.py
   by multiplying by 100 only when value < 1.

7. **VOO over VTI** — Buffett-endorsed, 95% same holdings, 0.03% expense ratio, S&P 500.
   Same outcome, simpler mental model.
