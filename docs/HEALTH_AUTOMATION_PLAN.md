# Health Automation Plan — Garmin CIRQA + Blood Panel

Status: **design / not yet built**
Author: research pass, 2026-08-24

---

## 0. The one thing to decide first: this repo is public

`Tarun-Talreja/TickRun` is a **public** repository with a public GitHub Pages site.
HRV, sleep stages, resting heart rate, menstrual/skin-temperature data, and a full
blood panel are among the most sensitive categories of personal data there are, and
GitHub history is effectively permanent — a later `git rm` does not remove a blob
that has already been cloned, forked, or indexed.

**Recommendation: build this in a separate private repo** (working name `Pulse`),
reusing TickRun's architecture but nothing of its publishing model.

| | TickRun (stocks) | Pulse (health) |
|---|---|---|
| Repo visibility | public | **private** |
| Raw data in git | yes (quotes are public info) | **no** — gitignored, or encrypted |
| Dashboard hosting | GitHub Pages (public URL) | local `python3 -m http.server`, or Pages on a private repo w/ auth |
| Secrets | none needed | Garmin OAuth tokens (GH Actions secret) |

If you'd rather keep one repo, the fallback is: private repo, Pages disabled,
and the dashboard opened locally. Do **not** put health JSON under `output/` in
TickRun — the `pages.yml` workflow copies `output/**` straight to the public site.

---

## 1. How to actually get the data out of Garmin

### 1a. Official Garmin Health API — not available to you

The Garmin Connect Developer Program requires a **legal entity** and explicitly
rejects personal-use applications. Approved use cases are research institutions,
corporate wellness platforms, and coaching products. There is no self-serve
personal API key. Treat this door as closed.

### 1b. Unofficial Connect client — the practical path

`cyberjunky/python-garminconnect` (2.9k★) wraps Garmin Connect's private mobile
API. It logs in via Garmin's SSO endpoint, exchanges the ticket for OAuth1+OAuth2
tokens, caches them at `~/.garminconnect/garmin_tokens.json` (mode 0600), and
auto-refreshes before each request. A full re-login is only needed when the
refresh token expires or is revoked.

**Important caveat (as of Aug 2026):** its auth dependency `matin/garth` was
**deprecated** after Garmin changed their auth flow and began Cloudflare-blocking
the mobile user-agent. Working community workarounds exist (browser user-agent
override; `curl_cffi` TLS fingerprint impersonation as used by
`diegoscarabelli/garmin-health-data`; Playwright headless token capture as used by
`garmin-connect-mcp`). This is an ongoing cat-and-mouse — **assume the sync will
break once or twice a year** and design for graceful failure + an alert, not for
permanent uptime.

### 1c. MFA is the real automation blocker

If your Garmin account has MFA enabled, you cannot do a cold headless login in CI.
The workable pattern:

1. Run `scripts/garmin_auth.py` **once locally**, enter the MFA code interactively.
2. Base64 the resulting token JSON into a GitHub Actions secret `GARMIN_TOKENS`.
3. CI writes it to disk, sets `GARMINTOKENS`, and the client refreshes silently.
4. When refresh finally fails, the workflow opens a GitHub issue titled
   "Garmin re-auth needed" (same pattern as `daily.yml`'s failure handler).

### 1d. Fallbacks worth knowing
- **Garmin Connect account data export** (Account Management Center) — full
  historical dump, manual, good for a one-time backfill of everything before
  the wearable era.
- **.FIT files** direct from the device over USB/MTP, parsed with
  `dtcooper/python-fitparse` or Garmin's official `garmin/fit-python-sdk`.
  Fully offline, immune to auth breakage, but manual.

### 1e. What CIRQA actually gives you

CIRQA Smart Band (launched July 2026, $199, no subscription) is screenless and
syncs everything to Garmin Connect, so the API surface is the normal Garmin one:

- Sleep: score, stages (deep/light/REM/awake), naps, overnight SpO2, respiration
- HRV: overnight RMSSD + Garmin's own HRV Status (balanced/unbalanced vs baseline)
- Body Battery (Firstbeat energy model), all-day stress
- Resting HR, all-day HR, steps, intensity minutes, calories
- Skin temperature (used for the women's-health features — also the best
  illness/overtraining early-warning signal in the whole dataset)
- 80+ activity types, HR zones per activity

Notably **absent vs a watch**: VO2max and Training Readiness generally need
GPS/run data, so those may be missing or degraded. My formulas below should
compute their own equivalents rather than depending on Garmin's.

---

## 2. Open source projects that already do parts of this

| Project | ★ | What it does | Verdict for you |
|---|---|---|---|
| [arpanghosh8453/garmin-grafana](https://github.com/arpanghosh8453/garmin-grafana) | 3.4k | Dockerized fetcher → InfluxDB → Grafana dashboards. Covers HR, steps heatmap, sleep + SpO2 + respiration + HRV, sleep-regularity heatmap, stress, Body Battery, sleep score, HR zones. | **Closest thing to "done".** Best option if you want visualization tomorrow with zero code. Weakness: it visualizes, it doesn't *score* — no Whoop-style recovery/strain, no blood panel, no narrative. |
| [tcgoetz/GarminDB](https://github.com/tcgoetz/GarminDB) | 3.3k | Downloads Connect + raw FIT into SQLite, keeps the raw JSON/FIT so the DB is regenerable. Jupyter notebooks for analysis. | **Best storage layer.** Mature (2017), handles backfill well. Good candidate to sit underneath your own analytics rather than reimplementing ingestion. |
| [cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect) | 2.9k | The API wrapper itself — ~46 health/wellness methods. | **Use this directly** if you want full control of the schema. |
| [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) | 1.1k | MCP server exposing Garmin data to an LLM. | **High leverage for you specifically** — lets Claude query your Garmin data conversationally without you building a query layer. |
| [diegoscarabelli/garmin-health-data](https://github.com/diegoscarabelli/garmin-health-data) | — | One CLI command → files + SQLite. Uses `curl_cffi` (survives the current Cloudflare block). | Good reference for the auth workaround. |
| [cyberjunky/home-assistant-garmin_connect](https://github.com/cyberjunky/home-assistant-garmin_connect) | 550 | Garmin → Home Assistant sensors. | Only if you already run HA. |
| [elkimek/get-based](https://github.com/elkimek/get-based) | — | Open-source **blood work** dashboard: AI PDF import, 287+ biomarkers, reference *and* optimal ranges, trend charts, derived markers (HOMA-IR, lipid ratios, NLR/PLR, De Ritis, hs-CRP/HDL). Local-first. | **Directly solves your blood-panel half.** Strong candidate to use as-is or lift the biomarker reference tables from. |
| [markwk/awesome-biomarkers](https://github.com/markwk/awesome-biomarkers) | — | Open database/directory of biomarkers and ranges. | Use as the reference-range data source. |

### The honest gap
Nothing open source does the **combination** you're describing: Garmin ingest +
Whoop-equivalent derived scores + blood panel + longitudinal correlation +
automated narrative. garmin-grafana + get-based covers ~70% with zero build.
The remaining 30% — the scoring engine and the cross-domain analytics — is the
part actually worth writing.

---

## 3. Rebuilding Whoop's formulas

Whoop's exact weights are proprietary — you get the score and the inputs, never
the weighting. But every *component* is published sports science, and the
reimplementation below is defensible and, unlike Whoop, fully inspectable.

### 3.1 Strain (0–21 scale)

Whoop's Strain is a logarithmic 0–21 scale (borrowed from the Borg RPE 6–20
scale). Underneath it is cardiovascular load. Reproduce with **Banister TRIMP**,
exponential variant:

```
TRIMP_exp = Σ over minutes:  duration_min × HRr × 0.64 × e^(1.92 × HRr)
where HRr = (HR - HR_rest) / (HR_max - HR_rest)     # HR reserve fraction
(0.64 / 1.92 are the male coefficients; 0.86 / 1.67 female)
```

Then map to 0–21 against your own rolling distribution:

```
strain = 21 × (ln(1 + TRIMP_day / k) / ln(1 + TRIMP_p99 / k))
where TRIMP_p99 = 99th percentile of your trailing 180-day TRIMP, k ≈ 50
```

This self-calibrates: a hard day for *you* scores ~18 regardless of fitness level,
which is exactly Whoop's behavior.

`HR_max`: prefer an observed trailing-12-month max over the 220−age estimate.

### 3.2 Recovery (0–100%)

Whoop's stated inputs, in order of weight: **HRV carries most of the predictive
value**, then resting HR and sleep performance (which contribute far less because
they overlap with what HRV already captures), plus respiratory rate, skin temp,
and SpO2 as modifiers.

Compute each input as a z-score against a **30-day rolling personal baseline**
(Whoop's stated comparison window), then blend:

```
z_hrv    = (HRV_last_night  - μ30_hrv)  / σ30_hrv          # higher = better
z_rhr    = (μ30_rhr - RHR_last_night)   / σ30_rhr          # lower  = better (sign flipped)
z_resp   = -|RespRate - μ30_resp|       / σ30_resp         # deviation either way = worse
z_temp   = -|SkinTemp - μ30_temp|       / σ30_temp         # deviation either way = worse
sleep_perf = min(1.0, sleep_actual_h / sleep_need_h)       # see 3.3

raw = 0.55·z_hrv + 0.20·z_rhr + 0.15·(2·sleep_perf − 1)·1.5 + 0.05·z_resp + 0.05·z_temp
recovery = 100 × Φ(raw)        # Φ = standard normal CDF → maps to a 0–100 percentile
```

Then Whoop's colour bands: **green ≥ 67%, yellow 34–66%, red < 34%**.

Two guardrails worth adding that Whoop does *not* expose:
- Suppress the score entirely for the first 30 days (no baseline = no signal).
  Show "building baseline, day n/30" instead of a fake number.
- Emit the *confidence interval*, not just the point estimate. If σ30_hrv is
  large, say so rather than pretending 71% and 64% are different days.

### 3.3 Sleep Performance & Sleep Need

```
sleep_need = baseline_need
           + sleep_debt_carryover × 0.5     # half of the last 4 nights' shortfall
           + strain_credit                  # ~ +6 min per strain point above 10
           − nap_credit                     # naps count at ~ 0.7 efficiency

baseline_need ≈ 7.6 h (population); refine to your own by finding the sleep
duration above which your next-morning HRV stops improving — a hinge regression
on your own data. This is a genuinely better number than Whoop's constant.

sleep_performance = 100 × sleep_actual / sleep_need
```

### 3.4 Sleep Consistency (circadian regularity)

Whoop's "Sleep Consistency" and Garmin's sleep-regularity heatmap both measure
bed/wake-time variance. Use the **Sleep Regularity Index (SRI)** — the published
academic version, which is better than either:

```
SRI = 100 × (2 × P(same sleep/wake state at time t on day d and day d+1) − 1)
      averaged over all minutes of the day, across the trailing 30 days
```

SRI is one of the strongest single predictors of all-cause mortality in the
sleep literature — arguably more actionable than duration.

### 3.5 Training load / injury risk — ACWR

Not a Whoop metric, but Garmin's Acute/Chronic Load and every S&C department use it:

```
acute   = EWMA(TRIMP, λ = 2/(7+1))     # 7-day exponentially weighted
chronic = EWMA(TRIMP, λ = 2/(28+1))    # 28-day
ACWR    = acute / chronic
```
Sweet spot 0.8–1.3; > 1.5 is the elevated-injury-risk zone. EWMA is the better
model over the older rolling-average version.

### 3.6 Banister fitness–fatigue (the "am I peaking?" model)

```
Performance(t) = p0 + k1·Σ TRIMP_i·e^(-(t-i)/τ1)  −  k2·Σ TRIMP_i·e^(-(t-i)/τ2)
                        └── fitness, τ1 ≈ 42 d ──┘     └── fatigue, τ2 ≈ 7 d ──┘
```
With ~6 months of data you can fit k1/k2/τ1/τ2 to your own HRV or performance
series by least squares. `andrewcooke/choochoo` has a reference implementation of
the impulse response calculation.

---

## 4. What this can do that neither Whoop nor Garmin does

This is where the project earns its existence. Garmin already ships Body Battery,
HRV Status, Sleep Score and Training Status — reimplementing those alone is not
worth your weekend.

1. **Lag-correlation engine.** For every behavioural variable (alcohol flag,
   last-meal time, workout end time, step count, screen-off time, caffeine),
   regress against next-morning HRV / recovery / deep sleep. Report only
   correlations that survive a multiple-comparison correction, with n and effect
   size. Output reads: *"Workouts ending after 8pm cost you 11ms of overnight
   HRV (n=23, p=0.004). Nothing else in your data comes close."* Neither Whoop
   nor Garmin does personalised causal-ish inference like this.

2. **Blood panel × wearable joint analysis.** The full-body checkup is a single
   point; the wearable is continuous. Join them:
   - ferritin / B12 / vitamin D ↔ HRV and Body Battery recharge rate
   - hs-CRP ↔ resting HR and skin temperature baseline
   - HbA1c / fasting glucose / HOMA-IR ↔ overnight HR curve shape
   - TSH ↔ resting HR trend
   - ApoB / Lp(a) — no wearable correlate, but the single most important number
     in a lipid panel for long-term risk, and usually not ordered by default.
     Worth checking whether your checkup includes it.

3. **Trend detection with honesty.** Day-to-day HRV noise is ~15–20%. Report
   Mann-Kendall trend tests over 30/90-day windows rather than green/red arrows,
   and explicitly say "no detectable change" when that's the truth.

4. **Weekly LLM narrative.** Same pattern as your existing `daily_brief.py` /
   `weekly_digest.py`: feed the week's numbers + deltas + surviving correlations
   to Claude, get back 5 sentences of "what changed and what to do about it."
   This is the piece that turns data into behaviour change.

5. **One store, no subscription, no vendor.** Whoop is $239/yr and their data
   leaves when you do. This is yours.

---

## 5. Proposed architecture (mirrors TickRun)

```
scripts/
  garmin_auth.py        # one-time interactive MFA login → token store
  garmin_sync.py        # daily pull: sleep, HRV, RHR, stress, body battery,
                        #   steps, SpO2, respiration, skin temp, activities
  garmin_backfill.py    # one-shot historical import (Connect export or API paging)
  metrics_engine.py     # TRIMP, strain, recovery, sleep need/perf, SRI, ACWR
  baselines.py          # 30/90/180-day rolling μ/σ per metric
  bloodwork.py          # parse uploaded panel PDF → biomarkers.json + ranges
  correlate.py          # lag-correlation engine w/ FDR correction
  health_brief.py       # weekly LLM narrative
  build_health_dashboard.py

data/                   # ALL GITIGNORED — raw personal data never committed
  garmin_raw/YYYY-MM-DD.json
  biomarkers.json
  baselines.json
  journal.json          # manual: alcohol, illness, travel, stress events

output/
  health_dashboard.json
  health_brief.json

.github/workflows/
  health_daily.yml      # 8am ET — sync yesterday, recompute scores
  health_weekly.yml     # Sun 6pm ET — baselines, correlations, LLM brief
```

Dashboard: a second React SPA in the same style as `index.html`, tabs for
**Today / Trends / Sleep / Training / Bloodwork / Correlations**.

### Build order
1. `garmin_auth.py` + `garmin_sync.py` + gitignore discipline → **prove the pipe works**
2. 30 days of passive collection (nothing meaningful computes before this)
3. `metrics_engine.py` + `baselines.py` → strain / recovery / sleep scores
4. `bloodwork.py` when the panel arrives
5. `correlate.py` + `health_brief.py` at ~90 days, when n is large enough to mean anything

Step 2 is not optional and cannot be shortcut. Every score in §3 is a comparison
against your own baseline; without the baseline they are noise with a number on it.

---

## 6. Honest caveats

- **Unofficial API = fragile.** Budget for breakage. Alerting on failure matters
  more than the happy path.
- **A wrist band is not a lab.** Optical HRV from a band is noisier than a chest
  strap; single-night values are close to meaningless, 7-day trends are not.
- **Not medical advice.** These scores are for spotting your own patterns. The
  blood panel is the doctor's to interpret — this project's job is to put the
  numbers next to each other over time, not to diagnose.
- **n=1 correlation is not causation**, and with 20 candidate behaviours you will
  find spurious "significant" results unless the FDR correction in §4.1 is
  actually implemented. It is the difference between insight and astrology.
