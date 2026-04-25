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

### ❌ NOT DONE (Your Task in Claude Code)

**Phase 2 — GitHub Actions Automation**

1. Create public repo: `TickRun`
2. Set up `.github/workflows/daily.yml` — runs 8am ET weekdays
3. Set up `.github/workflows/weekly.yml` — runs 6pm ET Sundays
4. Auto-push JSON back to repo
5. Update dashboard to fetch from repo raw URLs (fixes CORS issues)

**Phase 3 — Intelligence Layer** (Post-automation)

1. Fetch top 5 weekly picks from JSON
2. Call Claude API to generate layman-friendly research briefs
3. Add RESEARCH tab to dashboard showing each pick with:
   - One-line thesis
   - Why the screen flagged it
   - Recent catalyst
   - Bear case
   - What to research further

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

### Cloud (GitHub - NOT YET CREATED)
```
github.com/Tarun-Talreja/TickRun/  [CREATE THIS]
├── .github/workflows/
│   ├── daily.yml               [NEW - you'll create]
│   └── weekly.yml              [NEW - you'll create]
├── fetch_daily.py              [COPY from local]
├── fetch_weekly.py             [COPY from local]
├── watchlist.md                [COPY from local]
├── output/                     [Will auto-populate]
│   ├── daily.json              [AUTO-COMMITTED by workflow]
│   └── weekly_screens.json     [AUTO-COMMITTED by workflow]
└── README.md
```

### Published (Web)
```
dashboard.jsx                   [React artifact, published URL on your phone]
                                 Fetches from: raw.githubusercontent.com/.../daily.json
                                             raw.githubusercontent.com/.../weekly_screens.json
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

## Your Claude Code Tasks (Next)

### Task 1: Create GitHub Repo (5 min)
1. Go to github.com/new
2. Name: `TickRun`
3. Public: YES
4. Add README: YES
5. Create

### Task 2: Push Local Files to GitHub (10 min)
In Claude Code terminal:
```bash
cd /Users/taruntalreja/Documents/Projects/StockDashboard
git init
git add fetch_daily.py fetch_weekly.py watchlist.md screen_rules.md output/
git commit -m "Initial commit: dashboard scripts and data"
git branch -M main
git remote add origin https://github.com/Tarun-Talreja/TickRun.git
git push -u origin main
```

### Task 3: Create GitHub Workflows (20 min)
Create `.github/workflows/daily.yml`:
```yaml
name: Fetch Daily Data
on:
  schedule:
    - cron: '0 13 * * 1-5'  # 8am ET = 1pm UTC, Mon-Fri
  workflow_dispatch:

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install yfinance requests
      - run: python fetch_daily.py
      - uses: stefanzweifel/git-auto-commit-action@v4
        with:
          commit_message: "Auto: daily data update"
```

Create `.github/workflows/weekly.yml`:
```yaml
name: Run Weekly Screener
on:
  schedule:
    - cron: '0 22 * * 0'  # 6pm ET = 10pm UTC, Sunday
  workflow_dispatch:

jobs:
  screen:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install yfinance pandas requests lxml
      - run: python fetch_weekly.py
      - uses: stefanzweifel/git-auto-commit-action@v4
        with:
          commit_message: "Auto: weekly screening run"
```

### Task 4: Update Dashboard Code (10 min)
Replace hardcoded Gist URLs with raw GitHub URLs:
```javascript
const DAILY_URL = "https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/daily.json";
const SCREENS_URL = "https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/weekly_screens.json";

// Update both the auto-fetch AND the manual paste fallback
```

### Task 5: Test (5 min)
1. Manually trigger workflow: GitHub repo → Actions → Daily → "Run workflow"
2. Watch it run live
3. Verify `output/daily.json` appears in repo
4. Copy raw URL, test fetch in browser console
5. Publish updated dashboard

## What You'll Know After Phase 2

- Repo will have fresh JSON every weekday morning + Sunday evening
- Dashboard automatically shows latest data
- Zero manual copy-paste needed
- Can check GitHub Actions logs if anything breaks
- Completely hands-off from here on

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
✅ One manual trigger test passes  

When you hit all 5, Phase 2 is done. Then we tackle Phase 3 (the intelligence layer) which is where Claude Code really shines.

---

## Questions to Ask Claude Code

When you open Claude Code with this file, good starting questions are:

1. "Create the `.github/workflows/daily.yml` file following the spec above"
2. "Help me push these local scripts to a new GitHub repo"
3. "Update the dashboard code to fetch from raw GitHub URLs instead of Gist"
4. "Test the workflows by manually triggering them and watching the Actions logs"
5. "What would Phase 3 (intelligence layer) look like in code?"

Claude Code can help you test scripts locally, commit to Git, and iterate on the workflows in ways that are much harder in this chat interface.

Good luck. You've got this.
