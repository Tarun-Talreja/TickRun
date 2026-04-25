```
 _____ _     _    ____
|_   _(_) __| | _|  _ \ _   _ _ __
  | | | |/ _` |/ / |_) | | | | '_ \
  | | | | (_| |<  |  _ <| |_| | | | |
  |_| |_|\__,_|\_\_| \_\\__,_|_| |_|

  S&P 500 stock screener · zero extra cost · runs itself
```

**TickRun** — a personal stock screener for your Roth IRA satellite portfolio.
Math filters 500 stocks down to 15 candidates every Sunday. You do the human research.

---

## What it does

- **Weekly**: screens all S&P 500 stocks against 7 fundamental criteria → top picks
- **Daily**: checks your watchlist for news, earnings, big moves, RSI extremes
- **Dashboard**: React app (published on Claude.ai) reads the JSON — no server needed
- **Automation**: GitHub Actions runs the scripts on schedule, commits the output

## What it is not

- A trading system — it never executes trades
- A prediction engine — it surfaces stocks *worth researching*
- Connected to your brokerage — by design

---

## The 7 Screens

| Screen | What it finds | Best for |
|--------|--------------|----------|
| Graham Defensive | Cheap + financially safe | Deep value |
| Magic Formula | Cheap + high ROIC | Quality value combo |
| Piotroski F-Score | Fundamentally improving | Confirming value picks |
| GARP | Growing but not overpriced | Peter Lynch compounders |
| Quality | High-return businesses | Buy-and-hold |
| Momentum | Trending up with support | Trend followers |
| Dividend Quality | Safe, growing dividends | Income focus |

Multi-screen overlap = stronger conviction than any single screen.

---

## Architecture

```
GitHub Actions (schedule)
    │
    ├── fetch_daily.py   → output/daily.json          (weekdays 8am ET)
    └── fetch_weekly.py  → output/weekly_screens.json (Sundays 6pm ET)
                │
                └── raw.githubusercontent.com URLs
                            │
                     Dashboard (React artifact)
                      published on claude.ai
                      bookmarked on your phone
```

## Repo structure

```
TickRun/
├── fetch_daily.py              ← watchlist data, ~2 min to run
├── fetch_weekly.py             ← S&P 500 screener, ~15 min to run
├── watchlist.md                ← your tickers (keep ≤20)
├── screen_rules.md             ← thresholds for the 7 screens
├── .github/workflows/
│   ├── daily.yml               ← runs 8am ET Mon-Fri
│   └── weekly.yml              ← runs 6pm ET Sundays
├── output/
│   ├── daily.json              ← auto-committed by Actions
│   └── weekly_screens.json     ← auto-committed by Actions
├── schemas/                    ← JSON validation schemas
└── prompts/                    ← Cowork task prompts (optional)
```

---

## Cost

| Item | Cost |
|------|------|
| GitHub Actions | $0 (free tier) |
| Yahoo Finance data | $0 |
| GitHub raw URL hosting | $0 |
| Claude.ai dashboard hosting | $0 |
| **Total** | **$0** |

---

## Data sources

- **Yahoo Finance** via `yfinance` — prices, fundamentals, earnings dates
- **Wikipedia** — S&P 500 constituent list (weekly screener)

---

## Setup

See [EXECUTION_CHECKLIST.md](EXECUTION_CHECKLIST.md) — work through it in order.

Short version:
1. Fork/clone this repo
2. Add your tickers to `watchlist.md`
3. Trigger a workflow manually to verify output
4. Paste the raw JSON URLs into your dashboard CONFIG tab
5. Done — data updates itself from here

---

> **Reminder**: This is a research aid, not financial advice.
> Deploy capital only after your own due diligence.
> Never give automation tools access to your brokerage.
