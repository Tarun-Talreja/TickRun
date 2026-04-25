# Execution Checklist

Work through in order. Don't skip steps. Check off as you go.

## Phase 1 — Prove the UI works (today, 20 min, $0)

- [ ] Open claude.ai in browser, start a new chat
- [ ] Paste the contents of `dashboard.jsx` and say: "Create this as a published React artifact. Do not modify the code."
- [ ] When artifact renders, verify sample data shows up in Today / Screens / Watchlist tabs
- [ ] Open on phone in browser (same Claude account, just navigate to the artifact)
- [ ] Verify it's readable on mobile. Scroll every tab.
- [ ] If it looks good: click "Publish" on the artifact in the claude.ai sidebar
- [ ] Copy the published URL. Save to phone home screen as a web app.

**Decision point**: Does the UI feel useful? If not, iterate on the design before moving on.

## Phase 2 — Set up local folder + Gist (30 min, $0)

- [ ] Create folder `~/StockDashboard` on your computer
- [ ] Copy files into it: `watchlist.md`, `holdings.md`, `screen_rules.md`, `schemas/` folder, `prompts/` folder
- [ ] Edit `watchlist.md` to your actual tickers (keep ≤20)
- [ ] Sign into github.com
- [ ] Create a new Gist: https://gist.github.com/
- [ ] Filename: `daily.json` · Content: `{}` (empty JSON for now). Create as PUBLIC gist.
- [ ] In the Gist, click Raw. Copy that URL — it looks like `https://gist.githubusercontent.com/USERNAME/GISTID/raw/daily.json`
- [ ] Add a second file to the same Gist: `weekly_screens.json` with `{}`
- [ ] Copy its raw URL too
- [ ] Clone the Gist to your local `~/StockDashboard/output` folder:
  ```
  git clone https://gist.github.com/USERNAME/GISTID.git ~/StockDashboard/output
  ```
- [ ] Test you can push: edit daily.json, `git add -A && git commit -m "test" && git push`

## Phase 3 — Manual dry run (15 min, minimal tokens)

Before automating, run the task once manually to see what output looks like.

- [ ] Open Claude.ai in a regular chat (NOT Cowork yet)
- [ ] Paste the contents of `prompts/daily_task.md` 
- [ ] Replace `[YOUR_GIST_URL]` with your actual Gist URL
- [ ] Replace the "push to Gist" step with "just show me the JSON" (you'll paste it manually)
- [ ] Run it. Watch what it produces.
- [ ] Paste the output JSON into your dashboard artifact's CONFIG tab → "Manual paste" field
- [ ] Verify it renders correctly

## Phase 4 — Connect dashboard to Gist (5 min, $0)

- [ ] In the published dashboard (on phone or computer), go to CONFIG tab
- [ ] Paste your Gist raw URLs for daily.json and weekly_screens.json
- [ ] Click refresh
- [ ] Note: URLs are not saved between sessions — you'll re-paste, OR hard-code them into the artifact source after you know they work

## Phase 5 — Set up Cowork automation (20 min)

Only do this after Phases 1–4 are working.

- [ ] Open Claude Desktop app → Cowork
- [ ] Create a new project called "StockDashboard"
- [ ] Grant access to `~/StockDashboard` folder only
- [ ] Create scheduled task #1:
  - [ ] Paste contents of `prompts/daily_task.md`
  - [ ] Schedule: Weekdays, 8:00 AM
  - [ ] Replace `[YOUR_GIST_URL]` with your actual Gist
- [ ] Create scheduled task #2:
  - [ ] Paste contents of `prompts/weekly_task.md`
  - [ ] Schedule: Weekly, Sunday 6:00 PM
- [ ] Let the daily task run tomorrow morning. Verify it writes the JSON and pushes to Gist.
- [ ] Open dashboard on phone → data should be fresh

## Phase 6 — Use it for a month before deploying capital (4 weeks, $0)

- [ ] Week 1: Just watch. Don't trade. Get familiar with what the dashboard shows.
- [ ] Week 2: Pick 3 stocks it surfaces. Research each one yourself — read the 10-Q, check why it's "cheap," compare to 2 peers.
- [ ] Week 3: Continue observing. Notice which screens trigger most often. Adjust `screen_rules.md` if needed (and re-run weekly task manually).
- [ ] Week 4: If you still have conviction on one researched name, deploy $500 of your $10k. Keep the remaining $9,500 in VTI or cash.

## Guardrails

- Never give Cowork access to your brokerage account
- Never commit `holdings.md` to the Gist — keep it local only
- Don't open the dashboard 20 times a day. Once in the morning, once mid-day. That's it.
- When a new stock is "flagged," add it to watchlist to observe — don't buy on first sight
- If the market crashes, DO NOT PANIC SELL. Stocks on sale are what Roth IRAs are for.

## Red flags that something's broken

- Dashboard shows last updated > 48 hours ago → Cowork task isn't running (laptop asleep? app closed?)
- Screens returning the same 5 stocks for weeks → Finviz probably changed its HTML. Re-examine the prompt.
- You're checking the dashboard >5x/day → step away from the screen, go for a walk
- You're about to trade on a tip from Twitter → re-read the "why Twitter is bad" conversation
