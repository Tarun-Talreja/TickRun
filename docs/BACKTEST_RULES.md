# Backtest of the buy-below price: rules fixed before any result was seen (2026-11-24)

- **Formula:** exactly the code in scripts/valuation.py, unchanged.
- **Data:** only SEC rows filed on or before each test date, that day's price and 10-year Treasury yield, and beta from the five years before. Yahoo cross-checks and power-company guidance can't be replayed, so they are left out.
- **Dates:** the last trading day of Feb, May, Aug, Nov, 2013 to 2025. Entry is the NEXT trading day's close.
- **Sets:** the followed stocks, and the app's 430-company screen. Both are today's lists, so failed companies are missing. Raw returns are flattered; the comparison within the list is less so.
- **Groups:** below (price <= buy-below), close (<= 25% above), expensive (> 25% above), decline, none.
- **Main measure:** the "below" group's total return minus the same-date average of every stock in the set that had a buy-below price (below + close + expensive), over 1 and 3 years. SPY is reported too, but the list's bias makes it a weaker test.
- **Passes only if** the 90% interval for both 1 and 3 years is above 0 in the 430-company set. The interval resamples calendar years, because stocks on one date move together. Fewer than 100 "below" observations or 30 different stocks means "not enough evidence", not a pass.
- **Also reported:** per-year results, medians, and whether cheaper-ranked stocks did better than dearer ones.

## Result (2026-11-24): did not pass

Before the run, figures from mismatched periods were fixed (found while building the quality checks, with no result seen).

430-company screen, 420 replayed, "below" group against other priced stocks on the same dates:

| | Cases | Stocks | Average | Median | Beat others | 90% interval |
|---|---|---|---|---|---|---|
| 1 year | 130 | 61 | +2.0 points | -1.6 | 47% | -3.1 to +8.0 |
| 3 years | 112 | 52 | +22.0 points | +2.4 | 53% | -1.0 to +45.9 |

- Both intervals include 0, so it fails. The 3-year average rests on a few big winners (2014, 2017); 2018 to 2021 were negative.
- Cheaper-ranked stocks did no better than dearer ones (rank correlation about 0).
- Stocks the formula could not price did better on average than the priced ones, also driven by a few winners.
- Followed stocks: 18 "below" cases in all, too few to judge.

The formula was not changed afterwards to make it pass. It is shown as background with a warning.
