# Daily Cowork Task Prompt

Copy this exact text into a Cowork scheduled task. Set frequency: weekdays at 8:00 AM.

---

Read tickers from `~/StockDashboard/watchlist.md` (ignore # comments and lines starting with ##).

For each ticker, fetch ONLY these exact URLs (don't browse around):
- `https://finance.yahoo.com/quote/{TICKER}/key-statistics`
- `https://finviz.com/quote.ashx?t={TICKER}`

Extract per ticker: current price, 1-day change %, 5-day change %, YTD change %, 52-week low, 52-week high, trailing P/E, forward P/E, RSI(14), 50-day MA, 200-day MA, next earnings date.

Also fetch Yahoo news page and grab article TITLES ONLY from the last 24 hours. Do not fetch article bodies. Do not summarize.

For market context, fetch current values of: SPY, QQQ, ^VIX, ^TNX.

Generate flags for any ticker where:
- next_earnings is within 7 days → "earnings_soon"
- |change_pct_1d| > 5 → "big_move"
- RSI > 70 or RSI < 30 → "rsi_extreme"
- price crossed ma_50 or ma_200 yesterday → "ma_cross"

Write output to `~/StockDashboard/output/daily.json` matching the schema in `~/StockDashboard/schemas/daily.schema.json` EXACTLY. No extra fields. No prose. No commentary.

After writing the local file, push it to the GitHub Gist at [YOUR_GIST_URL] using:
```
cd ~/StockDashboard/output
git add daily.json
git commit -m "daily $(date +%Y-%m-%d)"
git push
```

Do NOT:
- Summarize articles
- Add analysis or opinion
- Read yesterday's daily.json
- Fetch any URL not listed above
- Ask me for clarification — if data is missing, set the field to null and continue

Exit when done.
