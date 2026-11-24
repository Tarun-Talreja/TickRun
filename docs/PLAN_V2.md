# TickRun v2: plan to give the app market judgement

**Status:** parked 2026-11-22, except Phase 2 (valuation), which is being built first on branch `v2-valuation` to replace the drawdown-based buy target. Written 2026-11-10.

## The goal, stated honestly

You want the app to judge the market the way a fee-only fiduciary would. Three limits apply whatever we build:

- **It can't legally be a fiduciary.** It can follow the same process: evidence first, costs and risks stated, the cheap index option always on the table, and no pretending to be sure.
- **Judgement can't be claimed, only measured.** The app earns trust by showing its record against the S&P 500, not by sounding confident.
- **Its judgement is capped by its inputs.** Today it gets about 15 numbers from Yahoo and 10 headlines per stock, and a free AI model does all the reasoning. Most of this plan is about fixing that.

## The design principle

**Code computes and decides. The AI reads and explains.**

Today the AI picks the verdict, the confidence and the buy target, which is why 21% of ratings flip between runs. After this plan, the verdict comes from rules applied to checked numbers. The AI's job shrinks to what it is good at: reading news and filings, and explaining the result in plain English with a quote for every claim.

## The test of success: the Home summary

Every time you open the app, the summary at the top must be correct and easy to understand. Every phase below is judged against that.

Today's summary (2026-11-10) fails it in three ways:

- **Wrong date:** it says "CEG earnings TODAY". CEG reported yesterday.
- **Misleading finance:** for V, IBM, ETN and MKTX it says to buy before the ex-dividend date "to receive the dividend". A share price normally drops by about the dividend on that date, so this is not a gain.
- **Urging a trade around an event:** it says "size the order now" ahead of earnings and attaches "decide your number before the print" to dividend items. The summary should explain what the event means for the stock's case, not push an order on a date.

What the summary becomes:

- **Three parts, in plain English:**
  1. What changed since you last looked.
  2. What it means for the stocks in your plan.
  3. What the app is unsure about.
- **Built from checked facts only.** Each sentence is assembled from a stored fact with a source and a date. The AI may reword, but code compares its wording back against the facts and falls back to the plain version on any mismatch.
- **Freshness shown.** Each line carries its "as of" time. A line built on stale or flagged data is left out and listed under "not shown today, and why".
- **No urging.** It reports and explains. It never says buy, sell or size.
- **A quiet day says so.** "Nothing material changed" is a valid summary.
- **Reading level check.** Finance terms get a one-line explanation the first time they appear, and sentence length is checked by code.

**Done when:** a daily automated check re-verifies every sentence in the summary against its source, and I hand-check it for 14 straight days with zero errors.

## Phase 0: Foundations (structure, storage, new data sources)

**Structure**

1. **Strict layers:** collect, store, compute, judge, explain, show. The AI sits only in "explain" and can never write a rating.
2. **Replayable ratings:** each rating is saved with a fingerprint of its inputs and never edited, so any verdict can be re-run and audited.
3. **One ordered pipeline in place of 14 separate jobs,** with catch-up logic. The jobs write to the same files at once today, which caused the save conflicts, and GitHub's schedules run late.
4. **Checks at every handoff:** each stage validates what it receives and stops loudly on a failure.
5. **Source and date on every figure,** carried through to the page.
6. **News as a queue:** each item stored once, classified, and able to trigger a re-rate.

**Storage**

- Append-only history files in the repo, loaded into SQLite inside each job. No server, no account.
- Holds: filed figures by quarter, daily prices, every news item with its classification, analyst estimate snapshots, and every rating with its exact inputs.
- This is what lets the app answer "what did we know when we rated this?"

**New data sources (all free)**

| Source | What it adds |
|---|---|
| SEC EDGAR company facts | Filed financials, share counts, stock-based pay |
| SEC EDGAR 8-K and Form 4 | The company's own results release; insider trades from the source |
| FRED (Federal Reserve data, free key) | Rates, yield curve, credit spreads, inflation |
| Damodaran sector datasets (NYU) | Typical multiples, margins and cost of capital by industry |
| Vanguard's published VTI holdings | Exact overlap between picks and the core fund |
| Yahoo estimate trends | Direction of analyst profit forecasts (patchy) |

Not available free: earnings-call transcripts and point-in-time history. A paid data service could add both later if the free version shows its limits.

**Done when:** one pipeline run produces the whole site, every stored figure has a source and date, and a deliberately broken input stops the run with an alert.

## Phase 1: Trustworthy numbers (foundation)

Everything else depends on this.

- **Source:** SEC EDGAR's free "company facts" data, which is what companies actually filed. Yahoo stays as a cross-check and for prices.
- **Pull 5+ years of quarterly history per stock:** revenue, operating income, net income, operating cash flow, capital spending, stock-based pay, diluted share count, cash, debt, interest expense.
- **Cross-check:** where EDGAR and Yahoo disagree by more than a few percent, the figure is flagged and not used. This settles cases like MSFT's net debt.
- **Period labels:** every figure carries its quarter, so a June number can never again be shown as Q3 (the VST error).
- **Foreign filers (TSM, ASML):** EDGAR coverage is thinner, so these fall back to Yahoo and are marked lower-confidence.

**Done when:** every stock has a dated, cross-checked history file, and the 26-stock statement comparison I ran by hand runs automatically each day.

## Phase 2: Valuation (the biggest gap)

Replace "X% below the 52-week high" with what the business is worth.

- **Own-history range:** today's price against the stock's own 5-year range of P/E, EV/EBIT, price-to-sales and free-cash-flow yield.
- **What the price assumes:** a reverse cash-flow calculation, giving "today's price needs N% growth for 10 years". Then compare N with what the company has actually done.
- **Real cash yield:** free cash flow after stock-based pay, compared with the 10-year Treasury yield.
- **Cycle adjustment:** for cyclical companies (chips, memory, power producers), value on average margins over the cycle, not today's. This addresses the "12x forward earnings at the peak" trap.
- **Sector-specific measures:** banks on price to tangible book and return on equity; REITs on funds from operations; utilities and power producers on debt against cash earnings.
- **Output:** a low / base / high value range and the gap to today's price. The "Buy Target" label goes away.

**Done when:** every stock page shows a value range with its assumptions, and no target is derived from the 52-week high.

## Phase 3: Business quality and risk

A scorecard computed by code, each line with a pass, caution or fail:

- **Returns:** return on invested capital, and whether it is stable.
- **Earnings quality:** cash flow against reported profit, stock-based pay as a share of revenue, share count trend.
- **Balance sheet:** net debt against cash earnings, interest cover, debt coming due.
- **Dependence:** customer and supplier concentration, read from the annual report's risk section (the filing reader already exists).
- **Durability:** margin stability across the last downturn.

**Done when:** each stock has a scorecard where every line links to the filed figure.

## Phase 4: News judgement

Today news is 10 headlines read once a week. A professional asks different questions.

- **Is it material?** Each headline is sorted: results or guidance, deal, regulation, management change, financing, sector or macro, or noise.
- **Does it touch the thesis?** Each stock's thesis is stored as 2–3 checkable statements. News is tagged confirms, weakens or breaks against them.
- **Primary source, not the headline:** for results, read the company's own press release from EDGAR. The "revenue miss" headlines on VST were wrong; the release was right.
- **Company or market?** Compare the stock's move with its sector and the index on the same days. "Down 50%" means something different when the whole group fell 45%.
- **Analyst estimate direction:** whether profit forecasts are being raised or cut. Falling price with falling estimates is the classic trap.
- **Event-driven updates:** a material item re-rates the stock that day, not next week.
- **Market backdrop:** a small daily panel with index drawdown, interest rates, sector moves and how broad the selling is.

**Done when:** a material headline changes a stock's page within a day, and each fall is labelled company-specific, sector-wide or market-wide.

## Phase 5: Verdicts by rule

- **Three gates, in code:** quality (Phase 3), value (Phase 2), thesis intact (Phase 4). The verdict follows from the gates, so the same facts always give the same answer.
- **Stability:** a verdict changes only when a gate changes, and the page says which one and why.
- **Confidence from evidence:** based on data completeness and cross-check agreement, not on the AI's own opinion of itself.
- **The AI is checked end to end:** every figure in the whole note must trace to the data, not just the bull points. Three independent runs must agree on the news reading, or it is marked uncertain.

**Done when:** re-running a stock with unchanged data gives the same verdict 100% of the time.

## Phase 6: Portfolio-level judgement

A fiduciary judges the whole portfolio, not each stock alone. This uses only your plan file, not your wider finances.

- **Overlap:** how much of each pick you already own through VTI.
- **Linked bets:** stocks that move together are grouped, and your 15% cap applies to the group. VST and CEG are one bet.
- **Stress test:** what the plan loses if its largest group falls 50%.
- **Holding period per stock, not one fixed clock.** You invest long term, but how long depends on the stock. Each stock's thesis states what has to happen and roughly by when (a contract ramp, a cycle turn, a margin target), and the app derives an expected holding range from that: a steady compounder may be open-ended, a cyclical or event-driven case shorter.
- **Exit conditions, not dates.** Each stock lists what would end the case: the thesis breaks, the price runs well past the value range, or the expected window passes with no progress. The page shows which, if any, is close.
- **Rule conflicts:** the fixed "minimum hold 3 years" rule in your plan file is replaced by the per-stock range, and a flat 30% stop-loss is checked against each stock's normal swings.
- **Stale plan check:** flags when the plan's reasons no longer match current ratings.
- **The baseline, always shown:** what 100% index would have done. Most individual stocks trail the index, and the app should say so on the plan page.

**Done when:** the plan page shows overlap, groups, stress loss and the index baseline.

## Phase 7: Proof

- **Fixed scorecard:** one entry per rating change, measured against the S&P 500 and the sector at 3, 6 and 12 months. Pass and Red Flag are tracked too, since avoiding losers counts.
- **Known-outcome test set:** about 30 past cases (real bargains, value traps, accounting failures, cycle peaks). Each logic change must not make these worse.
- **Honest labelling:** ratings carry "unproven" until there are at least 6 months of scored results.

**Done when:** the Home page shows the app's record against the index, with sample sizes.

## Phase 8: How it speaks

Each stock gets a one-page decision brief: what it's worth and why, what could break it, what the app doesn't know, what would change the verdict, and how it compares with just buying the index. It says "meets your rules" or "doesn't", never "buy now".

## Order and size

| Order | Phase | Why here | Rough size |
|---|---|---|---|
| 0 | Summary quick fixes | The three errors on Home today; no need to wait | Small |
| 1 | 7 (scorecard part) | Start measuring now; the clock only runs forward | Small |
| 2 | 0, then 1 | Everything depends on them | Large |
| 3 | 2 | Biggest gap in judgement | Large |
| 4 | 3 | Reuses Phase 1 data | Medium |
| 5 | 5 | Needs 2 and 3 | Medium |
| 6 | 4 | Largest AI component | Large |
| 7 | 6 | Needs stable verdicts | Medium |
| 8 | 8, rest of 7 | Presentation and test set | Medium |

Each phase is planned, tested first, verified against real filings, and reported before the next begins.

## What stays out of reach

- **Free data has holes:** no earnings-call transcripts, limited analyst estimates, thin coverage of foreign filers.
- **No true backtest:** free sources don't keep "what was known on that day", so the record can only build going forward.
- **The free AI model is the weakest link** for reading news and filings. A stronger paid model on just that step would cost roughly cents per stock.
- **Markets stay uncertain.** A sound process improves the odds; it does not make any single call safe.

## Decisions needed from you

1. Is the order above right, or should valuation come before the data foundation?
2. Stay fully free, or allow a paid AI model for the reading step only?
3. Should the app keep suggesting new stocks (screener and radar), or focus only on judging the ones in your plan until the record exists?

## Appendix: every audit finding and where it gets fixed

| # | Finding | Fixed in |
|---|---|---|
| 1 | Buy targets are "X% below the 52-week high", not a valuation | Phase 2 |
| 2 | Watchlist stocks sit 34–42% below their own targets; Worth Researching stocks are "at target" by construction | Phase 2, 5 |
| 3 | 21% of back-to-back ratings change with no new information | Phase 5 |
| 4 | Track record double-counts (382 entries, 62 stocks), has no index comparison, ignores Pass | Phase 7 |
| 5 | News only counts on rating day; no re-rate on a major headline | Phase 4 |
| 6 | Only bull points are fact-checked; bear case, valuation text and thesis are not | Phase 5 |
| 7 | Mover explanations come from the AI and are not checked against the headlines | Phase 4 |
| 8 | Summary says "earnings TODAY" a day late: the day count is saved once and reused | Quick fix |
| 9 | Summary says buy before the ex-dividend date "to receive the dividend" | Quick fix |
| 10 | Summary and catalyst text say "size the order now" before earnings | Quick fix |
| 11 | Home says "Waiting for buy signals" | Phase 8 |
| 12 | Fixed 3-year hold in the rules file and the rating prompt | Quick fix, then Phase 6 |
| 13 | Saved plan is from June and contradicts current ratings; 5% international has nothing assigned | Phase 6 |
| 14 | Account page assumes a taxable account and sends VTI there, against the plan | Phase 6 |
| 15 | No check that planned deposits fit the yearly Roth contribution limit | Phase 6 |
| 16 | Linked positions (VST and CEG) counted separately under the 15% cap; overlap with VTI ignored | Phase 6 |
| 17 | Flat 30% stop-loss on stocks that swing 40–60% | Phase 6 |
| 18 | Screener scores banks, REITs and utilities on measures that don't apply to them | Phase 2 |
| 19 | Screener and radar reward a price fall with no check on falling profit forecasts | Phase 4 |
| 20 | Forward P/E taken at face value for cyclical companies at possible peak profits | Phase 2 |
| 21 | Share count always "unverified"; no stock-based pay, interest cover or debt maturity | Phase 1, 3 |
| 22 | Figures from different quarters shown together without labels (VST) | Phase 1 |
| 23 | Net debt disagrees between Yahoo's summary and the balance sheet (MSFT) | Phase 1 |
| 24 | Hedge-fund signal reads Yahoo's top-holders list, which is mostly index funds, and filings are 45+ days old | Phase 4: relabel as background or remove |
| 25 | Insider "bearish" label is driven by routine selling; only open-market buying carries information | Phase 4 |
| 26 | Radar keeps a new stock only if the AI rates it Worth Researching | Phase 5 |
| 27 | The free AI model does all the reasoning | Phase 5, plus the model decision |
| 28 | 14 jobs write the same files; schedules run hours late | Phase 0 |

## Audit coverage

Read line by line: the rating prompt and script, all post-rating checks, targets, pullback alerts, screener, radar and promotion, track record, portfolio analytics, account placement, quote refresh, research queue, daily summary, weekly digest, catalysts, movers, insider and hedge-fund signals, health checks.

Not read line by line in this audit: field news, the filing reader, the two evaluation scripts, SEC filings fetch, earnings calendar, watchlist sync, the dashboard builder, and the page code in `index.html`. These fetch, assemble or display data and make no rating decisions, but they can still show something wrong, so Phase 0 includes reviewing each one as it moves into the new pipeline.
