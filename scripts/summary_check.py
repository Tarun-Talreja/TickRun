#!/usr/bin/env python3
"""
scripts/summary_check.py — Check the Home summary against its sources, claim by claim.

weekly_digest.py builds the summary from saved facts. This reads the finished TEXT and
re-derives every claim from the raw files, so a bug in the builder can't also hide in the
check: index and mover percentages against the saved quotes, the quoted headline against
the saved news, earnings dates against Yahoo's own earnings dates, weekdays against the
calendar, and wording against a list of words the summary must never use. Text that
matches no known sentence form fails too, so nothing unchecked can slip in.

Each run is recorded per trading day. The v2 plan's test of the summary is 14 error-free
days in a row, and Home shows that count.

Output: data/summary_checks.json
"""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import load_json
from market_time import NEW_YORK, previous_session, session_date
from move_explainer import _OPINION_RE, _contradicts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKS_PATH = os.path.join(ROOT, "data", "summary_checks.json")

PCT_TOLERANCE = 0.06      # a percentage shown to one decimal can differ from the raw one by rounding
INDEX_TOLERANCE = 0.3     # SPY's quote against the same day's close from the market panel
MOVE_FLOOR = 5.0          # a day's move this big belongs in the summary
TOP_MOVERS = 4            # what weekly_digest lists; a test keeps the two equal
EARNINGS_DAYS = 10
NEEDED_DAYS = 14
BENCHMARKS = {"SPY", "QQQ", "VTI", "VOO", "DIA", "IWM"}
KEPT_DAYS = 90
KEPT_FAILURES = 5
# The summary reports. It never urges, and never speaks of "today" (it can be read any day).
BANNED = re.compile(r"\b(?:buy|sell|size|today|tonight|dividend|guarantee\w*|should|will)\b", re.IGNORECASE)

_TICK = r"[A-Z][A-Z.\-]*"
_WEEKDAY, _DATE = r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (?:[A-Z][a-z]{2}) \d{1,2}", r"[A-Z][a-z]{2} \d{1,2}"
_MARKET = (rf"(?P<day>{_WEEKDAY}): the S&P 500 (?P<spy_dir>rose|fell) (?P<spy>\d+\.\d)% "
           rf"and the Nasdaq 100 (?P<qqq_dir>rose|fell) (?P<qqq>\d+\.\d)%\.")
_MOVERS = rf"Biggest moves you follow: (?P<movers>{_TICK} [+-]\d+\.\d%(?:, {_TICK} [+-]\d+\.\d%)*)\."
_HEADLINE = (rf"(?P<h_tick>{_TICK}), (?P<h_date>{_DATE}) headline: “(?P<h_title>.+)”"
             rf"(?: \((?P<h_pub>[^()]*)\))?\.")
_EARNINGS = rf"Earnings next: (?P<earnings>{_TICK} {_WEEKDAY}(?:, {_TICK} {_WEEKDAY})*)\."
SUMMARY_RE = re.compile(rf"(?:{_MARKET})?(?: ?{_MOVERS}(?: {_HEADLINE})?)?(?: ?{_EARNINGS})?")


def _label(day: date) -> str:
    return f"{day:%a %b} {day.day}"


def _short(day: date) -> str:
    return f"{day:%b} {day.day}"


def _ny_date(timestamp: float) -> date:
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(NEW_YORK).date()


def _earnings_date(label: str, today: date) -> date | None:
    """The date a "Tue Dec 1" label means: the year, within a year of today, that fits its weekday."""
    for year in (today.year, today.year + 1, today.year - 1):
        try:
            day = datetime.strptime(f"{label} {year}", "%a %b %d %Y").date()
        except ValueError:
            continue
        if abs((day - today).days) <= 200:
            return day
    return None


def followed_stocks(quotes: dict) -> dict[str, dict]:
    return {t: q for t, q in quotes.items()
            if q.get("status") == "ok" and t not in BENCHMARKS and not t.startswith("^")}


def check(narrative: str, quotes: dict, market: dict, news: dict, prices_as_of: str, today: date
          ) -> tuple[int, list[str], list[str]]:
    """(claims verified, failures, notes). Every claim is re-derived from the raw sources."""
    failures, notes, claims = [], [], 0
    match = SUMMARY_RE.fullmatch(narrative.strip())
    if not match:
        return 0, [f"text matches no known sentence form: {narrative[:120]!r}"], notes
    g = match.groupdict()
    session = session_date(datetime.fromisoformat(prices_as_of.replace("Z", "+00:00")))
    stocks = followed_stocks(quotes)

    def fail(text: str) -> None:
        failures.append(text)

    title_free = narrative.replace(g["h_title"], "") if g.get("h_title") else narrative
    for word in BANNED.findall(title_free):
        fail(f"forbidden word in the summary: {word!r}")
    claims += 1

    if g["day"]:
        claims += 1
        if g["day"] != _label(session):
            fail(f"summary day {g['day']!r} but the prices are from {_label(session)}")
        for name, ticker in (("spy", "SPY"), ("qqq", "QQQ")):
            raw = quotes.get(ticker, {}).get("pct_change_1d")
            shown = float(g[name]) * (1 if g[f"{name}_dir"] == "rose" else -1)
            claims += 1
            if raw is None or abs(raw - shown) > PCT_TOLERANCE:
                fail(f"{ticker} shown as {shown:+.1f}% but its quote says {raw}")
            elif (raw >= 0) != (g[f"{name}_dir"] == "rose") and abs(raw) >= 0.05:
                fail(f"{ticker} word {g[f'{name}_dir']!r} doesn't fit {raw:+.2f}%")
            close = (market.get("changes") or {}).get(ticker)
            if market.get("session") == session.isoformat() and close is not None:
                claims += 1
                if abs(close - shown) > INDEX_TOLERANCE:
                    fail(f"{ticker} shown as {shown:+.1f}% but the daily close says {close:+.1f}%")

    listed: dict[str, float] = {}
    if g["movers"]:
        for token in g["movers"].split(", "):
            ticker, pct = token.split(" ")
            listed[ticker] = float(pct.rstrip("%"))
        for ticker, shown in listed.items():
            claims += 1
            raw = stocks.get(ticker, {}).get("pct_change_1d")
            if raw is None:
                fail(f"{ticker} isn't a followed stock with a price")
            elif abs(raw - shown) > PCT_TOLERANCE:
                fail(f"{ticker} shown as {shown:+.1f}% but its quote says {raw:+.2f}%")
        big = {t: q["pct_change_1d"] for t, q in stocks.items()
               if q.get("pct_change_1d") is not None and abs(q["pct_change_1d"]) >= MOVE_FLOOR}
        smallest = min((abs(p) for p in listed.values()), default=0)
        for ticker, pct in sorted(big.items(), key=lambda kv: -abs(kv[1])):
            if ticker in listed:
                continue
            if len(listed) < TOP_MOVERS or abs(pct) > smallest + PCT_TOLERANCE:
                fail(f"{ticker} moved {pct:+.1f}% but isn't in the list of biggest moves")
        claims += 1
    elif any(abs(q.get("pct_change_1d") or 0) >= MOVE_FLOOR for q in stocks.values()):
        notes.append("big moves exist but the movers line was left out (their reasons predate the prices)")

    if g["h_title"]:
        claims += 1
        ticker = g["h_tick"]
        if ticker not in listed:
            fail(f"headline is about {ticker}, which isn't one of the listed movers")
        items = [n for n in news.get(ticker, []) if n.get("title") == g["h_title"]]
        shown_day = g["h_date"]
        item = next((n for n in items if n.get("date") and _short(date.fromisoformat(n["date"])) == shown_day), None)
        if item is None:
            fail(f"headline for {ticker} not found in the saved news for {shown_day}: {g['h_title'][:60]!r}")
        else:
            claims += 1
            if g["h_pub"] and (item.get("publisher") or "") != g["h_pub"]:
                fail(f"headline publisher {g['h_pub']!r} but the saved news says {item.get('publisher')!r}")
            published = date.fromisoformat(item["date"])
            if published not in (session, previous_session(session)):
                fail(f"headline is from {published}, not the move's day {session} or the session before")
            if published > session:
                fail(f"headline is from {published}, after the prices")
        if _OPINION_RE.search(g["h_title"]):
            fail("the quoted headline is an opinion piece or quote page")
        if ticker in listed and _contradicts(g["h_title"], listed[ticker]):
            fail(f"the quoted headline describes the opposite move to {ticker}'s {listed[ticker]:+.1f}%")

    if g["earnings"]:
        window_end = today + timedelta(days=EARNINGS_DAYS + 1)
        shown_tickers = set()
        for token in g["earnings"].split(", "):
            ticker, label = token.split(" ", 1)
            shown_tickers.add(ticker)
            claims += 1
            day = _earnings_date(label, today)
            stamp = stocks.get(ticker, {}).get("next_earnings")
            if day is None or _label(day) != label:
                fail(f"{label!r} isn't a real date and weekday")
            elif stamp is None or _ny_date(stamp) != day:
                fail(f"{ticker} earnings shown as {label} but Yahoo says {_ny_date(stamp) if stamp else 'nothing'}")
            elif not today <= day <= window_end:
                fail(f"{ticker} earnings {label} is outside the next {EARNINGS_DAYS} days")
        for ticker, q in stocks.items():
            stamp = q.get("next_earnings")
            if stamp and today <= _ny_date(stamp) <= today + timedelta(days=EARNINGS_DAYS) and ticker not in shown_tickers:
                fail(f"{ticker} reports {_label(_ny_date(stamp))} but isn't in the earnings list")
        claims += 1
    return claims, failures, notes


def record(days: dict, day: str, claims: int, failures: list[str], checked_at: str) -> dict:
    """The run added to its trading day. A day is error-free only if every run that day passed."""
    old = days.get(day, {"runs": 0, "failed_runs": 0})
    entry = {"runs": old["runs"] + 1, "failed_runs": old["failed_runs"] + (1 if failures else 0),
             "claims": claims, "checked_at": checked_at, "failures": failures[:KEPT_FAILURES]}
    return dict(sorted({**days, day: entry}.items())[-KEPT_DAYS:])


def streak(days: dict) -> int:
    """Error-free trading days in a row, ending with the latest."""
    count = 0
    for _, entry in sorted(days.items(), reverse=True):
        if entry["runs"] and not entry["failed_runs"]:
            count += 1
        else:
            break
    return count


def status(days: dict) -> dict:
    latest_day = max(days) if days else None
    latest = days.get(latest_day) if latest_day else None
    return {"streak": streak(days), "needed": NEEDED_DAYS, "day": latest_day, "latest": latest}


def run(digest: dict, quotes: dict, news: dict, today: date | None = None,
        path: str = CHECKS_PATH, now: datetime | None = None) -> tuple[int, list[str]]:
    """Check this digest's summary, record the run, and return (claims, failures)."""
    now = now or datetime.now(timezone.utc)
    today = today or now.astimezone(NEW_YORK).date()
    claims, failures, notes = check(digest["narrative"], quotes.get("tickers", {}), quotes.get("market", {}),
                                    news.get("news", {}), digest["prices_as_of"], today)
    day = session_date(datetime.fromisoformat(digest["prices_as_of"].replace("Z", "+00:00"))).isoformat()
    days = record(load_json(path).get("days", {}), day, claims, failures, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    with open(path, "w") as f:
        json.dump({"days": days}, f, indent=1)
    for note in notes:
        print(f"ℹ {note}")
    for failure in failures:
        print(f"❌ summary check: {failure}")
    print(f"{'✅' if not failures else '⚠'} Summary check: {claims} claims, {len(failures)} failure(s); "
          f"{streak(days)} error-free day(s) in a row")
    return claims, failures
