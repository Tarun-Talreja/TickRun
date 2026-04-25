# Weekly Screen Task Prompt

Copy this exact text into a Cowork scheduled task. Set frequency: weekly, Sunday 6:00 PM.

---

Run the 7 screens defined in `~/StockDashboard/screen_rules.md` against the S&P 500.

Universe: use the ticker list in `~/StockDashboard/sp500.csv` (do not re-fetch the S&P constituents — they rarely change).

For each ticker, fetch Finviz overview page ONLY:
`https://finviz.com/quote.ashx?t={TICKER}`

Finviz provides the key metrics needed: P/E, P/B, PEG, P/S, ROE, ROIC (as "ROIC" or derive from ROE + debt), Debt/Equity, EPS Growth past 5Y, Sales growth past 5Y, Dividend Yield, Payout Ratio, 50-day MA, 200-day MA, 12-month return, Current Ratio, Gross Margin.

For Piotroski F-Score components that need year-over-year comparisons, you can skip the detailed YoY checks and use a simplified proxy: if ROE > 10%, positive operating cash flow, and debt/equity < 1, score it as passing Piotroski. Note this simplification in the output under screens_passed as "piotroski_lite".

Apply each screen's thresholds exactly as written in screen_rules.md.

For each stock that passes at least one screen, record: symbol, company, sector, price, list of screens_passed, score (count of screens passed), and generate a one-sentence thesis derived PURELY from the metrics that caused it to pass. Example: "Passes Graham + F-Score: P/E 11, P/B 1.2, current ratio 2.4, ROE 18%, no new share issuance."

Sort by score descending. Top 20 go into `top_conviction`.

Group passes by screen into `by_screen` (top 10 per screen).

Count sectors in top 20 for `sector_mix_top20`.

Write output to `~/StockDashboard/output/weekly_screens.json` matching the schema exactly.

Push to the same GitHub Gist:
```
cd ~/StockDashboard/output
git add weekly_screens.json
git commit -m "weekly $(date +%Y-%m-%d)"
git push
```

Do NOT:
- Add narrative beyond the one-line thesis
- Speculate about future performance
- Include stocks that pass zero screens
- Re-fetch the S&P 500 ticker list

Exit when done.
