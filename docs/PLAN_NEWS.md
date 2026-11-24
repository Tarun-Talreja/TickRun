# Plan: telling company news from market moves

**Status:** proposed 2026-11-24, steps 1 and 5 built 2026-11-24. Replaces the order inside Phase 4 of PLAN_V2.md.

## What you would see

For each big move, three facts and one honest limit:

> NVDA rose 31.5%. Its group rose about 18% and the market 4.7%, so most of it was shared, and 13 points were its own.
> News that could change its value: CEO change (CNBC, Nov 23).
> Not known yet: whether this changes profits.

(The group figure is an illustration, not measured.)

## Steps

| Step | What it does | How it's checked |
|---|---|---|
| 1. Split each move | Compares the stock with the S&P 500 and a sector fund on the same day. Pure arithmetic, no AI. | Tests, plus 10 moves worked by hand |
| 2. Sort the headlines | Rules put each into results, guidance, deal, management, legal, financing, or noise. Price recaps and opinion are noise. | 100 real headlines labelled by hand. Wrongly called important: under 10% |
| 3. Read the primary source | For results and deals, finds the company's SEC filing (8-K) from those days and links it. | Every link opened for 10 stocks |
| 4. Flag the valuation | Important news newer than the filed figures adds a warning beside the buy-below price. Fraud, a restatement, or withdrawn guidance hides the price until reviewed. | Tests with known past cases |
| 5. Market panel on Home | Index moves, 10-year Treasury yield, how many followed stocks rose, best and worst group. | Compared with a second source for 5 days |
| 6. Redo ratings | Important news puts that stock first in the rating queue. | Queue tests |

## Rules it follows

- Code sorts and calculates. AI is not used in any step.
- A headline is never called the cause. The page says what moved together and what was reported.
- A stock with no fitting sector fund shows the market comparison only.
- When sources fail, the page says so instead of "no news".

## Order

1 and 5 first (arithmetic only), then 2, 3, 4, 6. Each step goes live only after its check passes.

## What it still won't do

- Judge how much a piece of news is worth in dollars. No value is changed by a headline, only flagged.
- Catch news that the headline feed or SEC filings miss.
- Predict the next move.
