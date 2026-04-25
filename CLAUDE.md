# TT Dashboard — Claude Code Context

## What We've Built

A personal stock screening dashboard for a $10k Roth IRA using the core-satellite approach:
- **Core ($7-8k):** VTI + VXUS (passive, never touch)
- **Satellite ($2-3k):** Individual stocks guided by screening system

## Current Status

### ✅ DONE
1. **Published Dashboard** (React/Tailwind)
   - File: `/mnt/user-data/outputs/dashboard.jsx`
   - URL: (bookmarked on your phone)
   - Live data: manually pasted via CONFIG tab
   - Features: TODAY | SCREENS | WATCHLIST | CONFIG tabs
   - Design: Dark theme, JetBrains Mono numbers, responsive

2. **Daily Data Pipeline** (`fetch_daily.py`)
   - File: `/Users/taruntalreja/Documents/Projects/StockDashboard/fetch_daily.py`
   - Fetches: SPY, QQQ, VIX, 10Y yield, 17 watchlist tickers
   - Outputs: `output/daily.json` with live prices, RSI, MA50/200, 24h news, earnings dates
   - Flags: earnings_soon, big_move, rsi_extreme
   - Time to run: ~2 minutes
   - Status: TESTED AND WORKING ✅

3. **Weekly Screener** (`fetch_weekly.py`)
   - File: `/Users/taruntalreja/Documents/Projects/StockDashboard/fetch_weekly.py`
   - Screens: All 503 S&P 500 stocks against 7 criteria
   - Outputs: `output/weekly_screens.json` with top 20 conviction picks
   - Screens: Graham Defensive, Magic Formula, Piotroski, GARP, Quality, Momentum, Dividend Quality
   - Time to run: 15-20 minutes (slow, but one-time weekly)
   - Status: TESTED, DIVIDEND YIELD BUG FIXED ✅

4. **Local Folder Structure**
   - Path: `/Users/taruntalreja/Documents/Projects/StockDashboard/`
   - Files: watchlist.md, screen_rules.md, prompts/, schemas/, output/
   - Schemas: Strict JSON validation for daily.json and weekly_screens.json

5. **GitHub Pages Deployment**
   - File: `/Users/taruntalreja/Documents/Projects/StockDashboard/index.html`
   - Live URL: `https://tarun-talreja.github.io/TickRun/`
   - Status: Deployed to GitHub Pages ✅
   - Auto-fetches from raw GitHub URLs, refreshes every 5 minutes
   - Bookmarked on phone — persistent, always live

### ✅ PHASE 2 COMPLETE — GitHub Actions Automation

1. ✅ Public repo created: `github.com/Tarun-Talreja/TickRun`
2. ✅ `.github/workflows/daily.yml` — runs 8am ET weekdays, auto-commits daily.json
3. ✅ `.github/workflows/weekly.yml` — runs 6pm ET Sundays, auto-commits weekly_screens.json
4. ✅ Dashboard updated to fetch from raw GitHub URLs (no manual paste needed)
5. ✅ GitHub Pages workflow created for live hosting
6. ✅ All workflows tested and running automatically

**Phase 2 Evidence:**
- Daily data: Last updated 2026-04-25 01:13:30 UTC (8am ET) ✅
- Weekly data: Last updated 2026-04-24 13:22 UTC (6pm ET Sunday) ✅
- Auto-commits visible in git log ✅
- Dashboard fetching from `raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/` ✅

### ❌ NOT DONE (Your Task in Claude Code)

**Phase 3 — Intelligence Layer** (Next)

1. Fetch top 5 weekly picks from `output/weekly_screens.json`
2. Call Claude API to generate layman-friendly research briefs for each
3. Add RESEARCH tab to dashboard showing each pick with:
   - One-line thesis (why screen flagged it)
   - Recent catalyst or news
   - Bear case (what could go wrong)
   - Key metrics to research (ROIC, payout ratio, etc)
   - Next earnings date
4. Integrate research generation into a scheduled workflow (optional: weekly or on-demand)

## Key Files & Paths

### Local (Your Mac)
```
/Users/taruntalreja/Documents/Projects/StockDashboard/
├── fetch_daily.py              [WORKING - runs locally]
├── fetch_weekly.py             [WORKING - runs locally, dividend bug fixed]
├── watchlist.md                [17 tickers: AAPL, MSFT, etc]
├── screen_rules.md             [7 screen thresholds]
├── output/
│   ├── daily.json              [~35KB, timestamp-updated]
│   └── weekly_screens.json     [~120KB, timestamp-updated]
├── prompts/
│   ├── daily_task.md           [prompt for Cowork - NOT NEEDED for GitHub Actions]
│   └── weekly_task.md          [prompt for Cowork - NOT NEEDED for GitHub Actions]
└── schemas/
    ├── daily.schema.json
    └── weekly_screens.schema.json
```

### Cloud (GitHub - LIVE)
```
github.com/Tarun-Talreja/TickRun/  [✅ CREATED & LIVE]
├── .github/workflows/
│   ├── daily.yml               [✅ ACTIVE - runs 8am ET Mon-Fri]
│   ├── weekly.yml              [✅ ACTIVE - runs 6pm ET Sunday]
│   └── pages.yml               [✅ ACTIVE - deploys to GitHub Pages]
├── fetch_daily.py              [✅ WORKING]
├── fetch_weekly.py             [✅ WORKING]
├── watchlist.md                [✅ DEPLOYED]
├── screen_rules.md             [✅ DEPLOYED]
├── output/                     [✅ AUTO-POPULATED]
│   ├── daily.json              [✅ AUTO-COMMITTED daily, last: Apr 25 01:13]
│   └── weekly_screens.json     [✅ AUTO-COMMITTED weekly, last: Apr 24 13:22]
├── index.html                  [✅ GitHub Pages entry point]
└── README.md
```

### Published (Web - LIVE)
```
✅ LIVE DASHBOARD at: https://tarun-talreja.github.io/TickRun/
   - Auto-fetches from: raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/daily.json
   - Auto-fetches from: raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/weekly_screens.json
   - Refreshes every 5 minutes
   - Shows: TODAY | SCREENS | WATCHLIST tabs
   - Bookmarked on your phone — persistent, always accessible
```

## What GitHub Actions Will Do

**Daily Workflow (8am ET, Mon-Fri)**
1. Checkout repo
2. Install Python + yfinance
3. Run `fetch_daily.py`
4. Auto-commit `output/daily.json` to repo
5. Dashboard fetches updated JSON on next page load

**Weekly Workflow (6pm ET, Sunday)**
1. Checkout repo
2. Install Python + yfinance + pandas
3. Run `fetch_weekly.py`
4. Auto-commit `output/weekly_screens.json` to repo
5. Dashboard reflects new screens on Monday morning

## The 7 Screens Explained

| Screen | Logic | Example |
|--------|-------|---------|
| **Graham Defensive** | P/E<15, P/B<1.5, CR>2, dividend positive 5Y | Old-school value: LEN, VICI |
| **Magic Formula** | High earnings yield + high ROIC | APA, ADBE, ALL |
| **Piotroski** | 5+ of 9 fundamental quality signals | NVDA, AMAT, ANET, AVGO |
| **GARP** | EPS growth>15%, PEG<1.5, ROE>15% | NVDA, FIX, EME, INCY, INTU |
| **Quality** | ROIC>15%, gross margin>40%, low debt | NVDA, ANET, AVGO |
| **Momentum** | Top 20% 12M return, price above MAs | NVDA, LRCX, AMAT |
| **Dividend** | Yield 2-6%, payout<60%, FCF positive | NVDA only |

**Top Conviction Picks (from last run):**
1. NVDA — 5/7 screens (Piotroski, GARP, Quality, Momentum, Dividend)
2. APA — 4/7 screens (Magic Formula, Piotroski, Quality, Momentum)
3. ADBE — 3/7 screens (Magic Formula, Piotroski, Quality)

## Dashboard Fetch Logic (Will Update)

Current (manual paste):
```
CONFIG tab → paste JSON → Load daily.json
```

After Phase 2 (auto-fetch):
```javascript
// Raw GitHub URLs (CORS-enabled)
const DAILY_URL = "https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/daily.json"
const SCREENS_URL = "https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/weekly_screens.json"

// Dashboard fetches on load + refresh
fetch(DAILY_URL).then(r => r.json()).then(data => renderTodayTab(data))
```

## Your Claude Code Tasks (Phase 3 — Next)

### Phase 3: Intelligence Layer — Add AI-Generated Research Briefs

**Goal:** Transform top 5 stock picks into actionable research briefs using Claude API

#### Task 1: Create `generate_research.py` script
```python
# Read output/weekly_screens.json
# Extract top 5 from top_conviction list
# For each pick, call Claude API to generate:
#   - one_line_thesis (why this stock matters)
#   - catalyst (recent news or event)
#   - bear_case (downside risks)
#   - research_focus (what to dig into — ROIC, margin trend, FCF, etc)
# Output: research_briefs.json with structure:
{
  "picks": [
    {
      "symbol": "BRK.B",
      "company": "Berkshire Hathaway",
      "screens_passed": ["graham", "piotroski"],
      "one_line_thesis": "Market-beating compounder trading at single-digit valuation",
      "catalyst": "1Q earnings beat expectations, share buyback continues",
      "bear_case": "Large cap limits growth; economic slowdown hits insurance underwriting",
      "research_focus": ["intrinsic value estimate", "insurance float quality", "derivative positions"],
      "next_earnings": "2026-04-30"
    }
  ]
}
```

**API Call Pattern:**
```python
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=500,
    messages=[{
        "role": "user",
        "content": f"""Generate a research brief for {symbol} ({company}) which passed screens: {screens}.
        
        Current price: ${price}, Earnings: {earnings_date}
        
        Return JSON with: one_line_thesis, catalyst, bear_case, research_focus (array of 3 items)
        Keep it layman-friendly, not jargon-heavy."""
    }]
)
```

#### Task 2: Create GitHub Actions workflow for research generation
Create `.github/workflows/research.yml`:
```yaml
name: Generate Research Briefs
on:
  schedule:
    - cron: '0 8 * * 1'  # Monday 8am ET (after Sunday weekly screens)
  workflow_dispatch:

jobs:
  research:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install anthropic
      - run: python generate_research.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - uses: stefanzweifel/git-auto-commit-action@v4
        with:
          commit_message: "Auto: research briefs updated"
          file_pattern: output/research_briefs.json
```

#### Task 3: Add RESEARCH tab to dashboard
In `index.html`, add new tab:
```javascript
// Add RESEARCH tab navigation
// Fetch output/research_briefs.json
// Render cards showing:
//   - Stock symbol + company
//   - Screens passed
//   - One-line thesis
//   - Catalyst
//   - Bear case
//   - Research focus (bullet list)
//   - Next earnings date
```

#### Task 4: Deploy updated dashboard
1. Update `index.html` with RESEARCH tab code
2. Commit and push to main
3. GitHub Pages will auto-deploy

## What You'll Know After Phase 3

- Dashboard now shows AI-generated research for top picks
- Weekly research briefs auto-generate on Monday mornings
- Dashboard is a complete decision-making tool, not just data display
- You have layman-friendly context for each top pick
- No manual research needed — it's automated

## What Comes After (Phase 3)

Once automation is solid, build the Intelligence Layer:
- Post-process top picks with Claude API call
- Generate research briefs (business model, bear case, catalysts)
- Add RESEARCH tab to dashboard
- This is where the dashboard becomes actually useful for decision-making

## Debug Commands You'll Need

```bash
# Test scripts locally
python fetch_daily.py
python fetch_weekly.py

# Check GitHub Actions logs
# Go to: github.com/Tarun-Talreja/TickRun/actions

# Manually trigger a workflow
# Go to: Actions tab → select workflow → "Run workflow" button

# View raw JSON URLs
# https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/daily.json
# https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/weekly_screens.json
```

## Key Learnings So Far

1. **Gist fetch doesn't work** — CORS blocks GitHub Gist API. Raw GitHub URLs work fine.
2. **yfinance dividend yields sometimes wrong** — fixed by capping at 20% (bug in data provider)
3. **S&P 500 screens take time** — but weekly is manageable. No need to optimize further.
4. **Manual paste works fine** — but automation is worth it once, saves 2 min/day forever.
5. **Dashboard is plumbing** — next phase (research briefs) is where value lives.

## Success Criteria for Phase 2

✅ GitHub repo created and public  
✅ `fetch_daily.py` and `fetch_weekly.py` in repo  
✅ Both workflows triggering on schedule  
✅ Auto-commits working (check Actions logs)  
✅ Dashboard fetches from raw URLs without manual paste  
✅ GitHub Pages live at https://tarun-talreja.github.io/TickRun/  
✅ One manual trigger test passes  

**Phase 2 is COMPLETE.** Moving to Phase 3 (Intelligence Layer).

---

## Success Criteria for Phase 3

✅ `generate_research.py` reads weekly_screens.json  
✅ Claude API calls generate briefs for top 5 picks  
✅ `research_briefs.json` auto-commits to repo  
✅ Dashboard loads research data and renders RESEARCH tab  
✅ Research tab shows thesis, catalyst, bear case, research focus  
✅ Workflow runs automatically every Monday 8am ET  
✅ Dashboard is a complete decision-making tool  

When you hit all 7, the screener is production-ready.

---

## Questions to Ask Claude Code (Phase 3)

When you open Claude Code with this file, focus on Phase 3:

1. "Create `generate_research.py` — read weekly_screens.json, call Claude API for top 5, output research_briefs.json"
2. "Set up the ANTHROPIC_API_KEY secret in GitHub repo settings"
3. "Create the `.github/workflows/research.yml` to auto-generate briefs Monday 8am ET"
4. "Add RESEARCH tab to index.html that fetches and displays research_briefs.json"
5. "Test locally: run `generate_research.py` with a few picks, verify JSON output"
6. "Deploy updated dashboard with RESEARCH tab live"

Claude Code excels at iterating on API integrations, testing locally, and deploying to GitHub. It's the perfect tool for Phase 3.

---

## Deployment Checklist

- [ ] Push latest `index.html` to main branch
- [ ] Set ANTHROPIC_API_KEY secret: github.com/Tarun-Talreja/TickRun/settings/secrets/actions
- [ ] Add research.yml workflow to .github/workflows/
- [ ] Test locally: `python generate_research.py`
- [ ] Manually trigger research.yml in Actions → verify output
- [ ] Check dashboard at https://tarun-talreja.github.io/TickRun/ — RESEARCH tab live
- [ ] Verify Monday 8am ET the next week research auto-generates

You're close. One more phase and this is a real tool.
