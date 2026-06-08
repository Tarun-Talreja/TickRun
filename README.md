```
 _____ _     _    ____
|_   _(_) __| | _|  _ \ _   _ _ __
  | | | |/ _` |/ / |_) | | | | '_ \
  | | | | (_| |<  |  _ <| |_| | | | |
  |_| |_|\__,_|\_\_| \_\\__,_|_| |_|

  AI-grounded stock research dashboard · zero cost · runs itself
```

**TickRun** — a personal, news-grounded research dashboard for a Roth IRA satellite portfolio.
It tracks a curated watchlist, pulls live data + filings + news, runs **LLM research grounded
in real sources** (not hallucination), and surfaces what's worth your attention — every day,
automatically, for $0.

**Live dashboard:** https://tarun-talreja.github.io/TickRun/

> 📐 New here? Read **[ARCHITECTURE.md](ARCHITECTURE.md)** — it doubles as a guide to the
> AI patterns (RAG, grounding, structured output, self-critique) the app is built on.

---

## What it does

- **Live data** — prices + fundamentals refresh every 30 min during market hours (`yfinance`)
- **LLM research** — grounded analysis per ticker with a verdict, **confidence rating**, and a
  **bear-case counter-argument** (free, via NVIDIA NIM)
- **Why it moved** — detects intraday >3% moves and explains the reason from real news, same-day
- **SEC filings** — monitors EDGAR for 13D/13G stakes, insider Form 4s, and 8-Ks (early smart money)
- **News feed** — recent headlines per ticker, clickable to the source
- **Portfolio analytics** — P&L, allocation drift, theme concentration, tax-free dividend projection
- **Discovery screener** — weekly professional multi-factor scan of the S&P 500 (suggest-only)
- **Trust guards** — data-sanity checks flag bad data; everything labels its own confidence

## What it is *not*

- A trading system — it never executes trades
- A prediction engine — it surfaces stocks *worth researching*
- Connected to your brokerage — by design (see the security note below)

---

## How a stock enters the app

```
watchlist.md  →  sync_watchlist.py  →  data/watchlist.json  →  full pipeline
   ↑
   You (or research) add it. Nothing is auto-added — the discovery
   screener only SUGGESTS; you approve before anything is tracked.
```

---

## The AI research pipeline (RAG)

A raw LLM hallucinates. TickRun grounds every call in **retrieved real data** first:

```
fundamentals (yfinance) ─┐
news headlines (yfinance)─┼─→ grounded prompt ─→ LLM ─→ VERDICT + CONFIDENCE + bear case
SEC filings (EDGAR) ──────┘                              │
                                                          └─→ watchlist.json → dashboard
```

- **Grounding rules** force the model to label anything not in the data as "unverified."
- **Structured output** forces a parseable `VERDICT:` / `CONFIDENCE:` line.
- **Self-critique** runs a second pass that argues *against* each buy-ready call.
- **Model fallback** — tries the heavy 253B model, degrades to a fast 70B if unavailable.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full diagram + the AI concepts.

---

## Discovery screener — professional multi-factor model

Weekly S&P 500 scan, scored the way a fundamental/quant investor screens:

| Factor | Weight | Measures |
|--------|--------|----------|
| **Quality** | 35% | ROE, gross & operating margin, positive free cash flow |
| **Value** | 30% | EV/EBITDA earnings yield, FCF yield, forward P/E, PEG |
| **Growth** | 20% | revenue & earnings growth |
| **Health** | 15% | debt/equity, current ratio |

Hard disqualifiers (auto-reject): sub-$2B cap, unprofitable without hypergrowth, over-levered,
cash-burning. Tags which classic screens each name passes — **Magic Formula, GARP, Quality,
Dividend Quality**. Output is **suggest-only**.

---

## Repo structure

```
TickRun/
├── watchlist.md                ← your tickers (source of truth)
├── index.html                  ← the dashboard SPA (served by GitHub Pages)
├── prompts/stock_research.md   ← the grounded research prompt
├── scripts/
│   ├── sync_watchlist.py        ← watchlist.md → watchlist.json
│   ├── refresh_quotes.py        ← live prices + fundamentals
│   ├── news_feed.py             ← per-ticker news (free)
│   ├── sec_filings.py           ← SEC EDGAR monitor
│   ├── move_explainer.py        ← detect + explain price moves (LLM)
│   ├── data_sanity.py           ← flag bad/unreliable data
│   ├── research_ticker.py       ← 🧠 grounded LLM research (verdict/confidence/bear)
│   ├── research_batch.py        ← daily research queue
│   ├── target_alerts.py         ← names at research buy-target
│   ├── portfolio_analytics.py   ← P&L, allocation, concentration, dividends
│   ├── track_record.py          ← did past calls work? (eval)
│   ├── screener.py              ← professional discovery screener
│   ├── weekly_digest.py         ← plain-English Sunday summary
│   └── build_dashboard.py       ← assembles output/dashboard.json
├── .github/workflows/
│   ├── daily.yml                ← every 30 min, market hours (quotes/news/SEC/movers)
│   ├── research.yml             ← 7am ET weekdays (LLM research)
│   ├── weekly.yml               ← Sun 6pm ET (full rebuild + digest)
│   ├── screener.yml             ← Sat 8am ET (S&P 500 discovery)
│   └── pages.yml                ← deploy dashboard to GitHub Pages
├── data/                        ← committed state (watchlist, caches, signals)
├── output/                      ← dashboard.json + research notes + analytics
└── legacy/                      ← the original 7-screen S&P 500 screener (archived)
```

---

## Cost

| Item | Cost |
|------|------|
| GitHub Actions | $0 (free tier) |
| Yahoo Finance data | $0 |
| SEC EDGAR | $0 |
| NVIDIA NIM (LLM) | $0 (free tier) |
| GitHub Pages hosting | $0 |
| **Total** | **$0** |

---

## Data sources

- **Yahoo Finance** (`yfinance`) — prices, fundamentals, earnings, news
- **SEC EDGAR** — filings (13D/G, Form 4, 8-K)
- **Wikipedia** — S&P 500 constituents (discovery screener)
- **NVIDIA NIM** — free LLM inference for research, move explanations, digest

---

## Setup

```bash
# 1. Clone + install
pip install -r requirements.txt

# 2. Add your tickers
edit watchlist.md

# 3. (Optional) enable LLM research — get a FREE key at https://build.nvidia.com
export NVIDIA_API_KEY=nvapi-...          # locally
# In GitHub: add it as a repo secret named NVIDIA_API for the workflows

# 4. Run the pipeline locally
python scripts/sync_watchlist.py
python scripts/refresh_quotes.py
python scripts/build_dashboard.py
python -m http.server 8080   # open http://localhost:8080
```

The GitHub Actions then keep everything updated automatically — no server, no maintenance.

---

## Security & compliance notes

- **No brokerage connection.** TickRun never logs into or trades on your account. Holdings are
  entered manually (or via CSV export). This is deliberate — credentials never touch automation.
- **Roth IRA, passive holds.** Designed for buy-and-hold research, not day trading.
- **Secrets** live only in GitHub Actions secrets / your shell env — never in the repo.

---

> **Reminder**: This is a research aid, not financial advice. The LLM outputs are grounded but
> not infallible — every verdict shows its confidence and a counter-argument for a reason.
> Deploy capital only after your own due diligence. Never give automation tools access to your brokerage.
