# TickRun — QA Audit Report

**Date:** 2026-04-24
**Scope:** fetch_daily.py, fetch_weekly.py, GitHub Actions workflows, index.html, JSON schemas, output data

---

## Executive Summary

The system **works end-to-end** (verified live on GitHub Pages) but has several silent-failure risks that could degrade data quality without anyone noticing. Top concerns:

1. **yfinance `.info` is rate-limited in CI** — produces silent `None`-filled records that fail all screens but still get counted as "fetched"
2. **Deprecated GitHub Actions versions** in `pages.yml` (configure-pages@v3, deploy-pages@v1) — will break when GitHub sunsets them
3. **No JSON schema validation** — schemas exist as docs but nothing enforces them
4. **No test suite** — screen logic could regress invisibly
5. **Workflow doesn't alert on failure** — stale JSON could persist for days
6. **Heavily-biased fallback ticker list** — the 100-stock fallback in `fetch_weekly.py` has 30+ utilities, would skew screens badly if Wikipedia fetch ever fails

---

## Findings by Severity

### 🔴 CRITICAL (fix before Phase 3)

**C-1. yfinance `.info` silent failures in CI**
- Location: [fetch_weekly.py:79](fetch_weekly.py#L79), [fetch_daily.py:53](fetch_daily.py#L53)
- Issue: `yf.Ticker(symbol).info` frequently returns `{}` from GitHub Actions IPs (rate limiting). Currently we check `if info` falsy and skip, but partial returns (e.g. `info` has `currentPrice` but not `pe`) silently produce records with `None` for most fields. Stock won't pass any screens but counts as "fetched."
- Impact: Silent data degradation. Top conviction list could be empty or wrong without warning.
- Fix: Add explicit field-presence check + retry with exponential backoff + log per-ticker which fields are missing.

**C-2. Deprecated GitHub Actions in pages.yml**
- Location: [.github/workflows/pages.yml](.github/workflows/pages.yml)
- Issue: Uses `actions/checkout@v3`, `actions/configure-pages@v3`, `actions/upload-pages-artifact@v1`, `actions/deploy-pages@v1` — all sunset or deprecated.
- Fix: Bump to checkout@v4, configure-pages@v5, upload-pages-artifact@v3, deploy-pages@v4.

**C-3. Pages workflow uploads entire repo**
- Location: [.github/workflows/pages.yml](.github/workflows/pages.yml) `path: '.'`
- Issue: Publishes Python scripts, watchlist, schemas to public Pages site. Not a secret leak (everything is in a public repo) but bloated and confusing.
- Fix: Restrict to `index.html` + `output/` (the only files the dashboard needs).

### 🟠 HIGH (fix this week)

**H-1. No JSON schema validation in CI**
- Schemas in `schemas/` are documentation only. Nothing checks that workflow output matches.
- Fix: Add `jsonschema` validation step to both workflows; fail loudly if shape drifts.

**H-2. No test suite**
- Zero coverage on screen logic, flag computation, ticker parsing, or thesis builder.
- Risk: A subtle change to the Piotroski conditions or Magic Formula ranking could silently change picks.
- Fix: Add `pytest` smoke tests for `apply_screens()`, `compute_flags()`, `read_watchlist()` with known fixtures.

**H-3. Heavily-biased fallback list**
- Location: [fetch_weekly.py:63](fetch_weekly.py#L63)
- The "FALLBACK_100" has 30+ utility companies at the tail (NEE, DUK, SO, D, EXC, XEL, WEC, ED, ETR, FE, PPL, ES, AEE, LNT, EVRG, NI, CMS, NRG, AES, PNW, OTTR, AVA, NWE, POR).
- Impact: If Wikipedia ever fails, dividend screen will be flooded with utilities and other screens will show distorted sector mix.
- Fix: Replace bottom 30 with a balanced sector mix (or hardcode top 100 by market cap from a known good snapshot).

**H-4. No failure alerting**
- If a workflow errors, you'd only notice when you look at the dashboard and see stale data.
- Fix: Add a step that posts to your personal email / Slack / GitHub issue on failure.

**H-5. Earnings date parsing likely broken in newer yfinance**
- Location: [fetch_daily.py:90](fetch_daily.py#L90)
- yfinance changed `t.calendar` from a DataFrame to a dict in 0.2.30+. The current code checks `cal.empty` which raises AttributeError on dicts → caught silently → always returns None.
- Fix: Handle both shapes; verify against a fresh yfinance install.

**H-6. Cron schedule is fixed UTC, drifts during DST**
- `'0 13 * * 1-5'` = 1pm UTC = 8am EST (winter) / 9am EDT (summer)
- Currently runs at 9am ET in summer, 8am ET in winter. Off by an hour half the year.
- Fix: Either accept the drift (low impact) or use two cron entries with conditional skip.

### 🟡 MEDIUM

**M-1. `prev_close` operator precedence is fragile**
- Location: [fetch_daily.py:60](fetch_daily.py#L60)
- Reads correctly today but easy to misread / break in future edits.
- Fix: Wrap the ternary in parentheses for clarity.

**M-2. Magic Formula threshold is absolute, not percentile**
- Location: [fetch_weekly.py:200](fetch_weekly.py#L200)
- Picks top 30 by combined rank regardless of universe size. With 500 stocks = top 6%; with 100 stocks = top 30%.
- Fix: Use a percentile (e.g. top 10%) instead of fixed 30.

**M-3. `__pycache__/` and `.DS_Store` tracked in git**
- Should be in .gitignore (`.DS_Store` is missing from `.gitignore`).
- `__pycache__` should be removed from index.

**M-4. `dashboard.jsx` is dead code**
- 25KB file, no longer used (replaced by `index.html`).
- README still references it.
- Fix: Remove `dashboard.jsx`, update README.

**M-5. No retry on transient yfinance failures**
- Single network blip = ticker dropped for the week.
- Fix: Wrap `fetch_fundamentals` in `tenacity` retry decorator (3 attempts, exponential backoff).

**M-6. Watchlist tickers fetched serially**
- 17 tickers × ~10s each = ~3 minutes daily
- Fix: Use `concurrent.futures.ThreadPoolExecutor(max_workers=5)`.

### 🟢 LOW / Polish

- L-1. `output/README.txt` is a placeholder, can be deleted
- L-2. `EXECUTION_CHECKLIST.md` references "Cowork" workflow — outdated, replace with GitHub Actions instructions
- L-3. `prompts/` directory references Cowork-era workflow — keep for reference or archive
- L-4. README mentions Finviz as a data source — never actually used
- L-5. `build_thesis` uses raw value when interpolating `s.get('pe','—')` — formats inconsistently between numbers and dashes

---

## Recommended Plan

**Phase 2.5 — QA Hardening (do before Phase 3):**

| # | Task | Severity | Est |
|---|------|----------|-----|
| 1 | Bump GitHub Actions versions | C-2 | 5 min |
| 2 | Restrict Pages upload to index.html + output/ | C-3 | 5 min |
| 3 | Add JSON schema validation to workflows | H-1 | 20 min |
| 4 | Add pytest smoke test suite | H-2 | 45 min |
| 5 | Add yfinance retry + per-ticker error logging | C-1, M-5 | 30 min |
| 6 | Replace fallback list with sector-balanced top 100 | H-3 | 15 min |
| 7 | Fix earnings date for new yfinance API | H-5 | 15 min |
| 8 | Add workflow failure → GitHub Issue auto-create | H-4 | 15 min |
| 9 | Cleanup: .DS_Store, __pycache__, dashboard.jsx | M-3, M-4 | 10 min |
| 10 | Parallelize watchlist fetch | M-6 | 15 min |

**Total: ~3 hours of focused work to make this production-grade.**

Then Phase 3 (intelligence layer) builds on a solid foundation.
