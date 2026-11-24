"""When the market was last priced, and when that price stops being current.

A fetch time isn't a price time: on 2026-11-23 a job fetched before the open, so Friday's
closes carried Monday's timestamp and looked fresh through a 5% rally.
"""
from datetime import date, datetime, time, timedelta, timezone
from statistics import median_high
from zoneinfo import ZoneInfo

import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay,
                                    USMartinLutherKingJr, USMemorialDay, USPresidentsDay,
                                    USThanksgivingDay, nearest_workday, sunday_to_monday)
from pandas.tseries.offsets import CustomBusinessDay

NEW_YORK = ZoneInfo("America/New_York")
OPEN, CLOSE, EARLY_CLOSE = time(9, 30), time(16, 0), time(13, 0)
BELL_SLACK = timedelta(minutes=1)   # a last trade this near the bell is the close
GRACE = timedelta(minutes=45)   # time for a refresh to run after the open or the close


class _NyseHolidays(AbstractHolidayCalendar):
    rules = [
        Holiday("New Year", month=1, day=1, observance=sunday_to_monday),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


_SESSION = CustomBusinessDay(calendar=_NyseHolidays())


def _close(day: date) -> time:
    """1pm on July 3, Christmas Eve and the Friday after Thanksgiving."""
    after_thanksgiving = day.month == 11 and day.weekday() == 4 and 23 <= day.day <= 29
    early = after_thanksgiving or (day.month, day.day) in ((7, 3), (12, 24))
    return EARLY_CLOSE if early else CLOSE


def session_date(as_of: datetime) -> date:
    """The trading day a price belongs to, in New York."""
    return as_of.astimezone(NEW_YORK).date()


def previous_session(day: date) -> date:
    return (pd.Timestamp(day) - _SESSION).date()


def price_due_at(as_of: datetime) -> datetime:
    """When a price from `as_of` is out of date: 45 minutes past it in a session, or past the next open."""
    local = as_of.astimezone(NEW_YORK)
    day = pd.Timestamp(local.date())
    close = _close(local.date())
    bell = datetime.combine(local.date(), close, NEW_YORK) - BELL_SLACK
    if _SESSION.is_on_offset(day) and local < bell:
        if local.time() >= OPEN:
            return (local + GRACE).astimezone(timezone.utc)
        moment = OPEN
    else:
        day, moment = day + _SESSION, OPEN
    due = datetime.combine(day.date(), moment, NEW_YORK) + GRACE
    return due.astimezone(timezone.utc)


def prices_as_of(quotes: dict) -> str | None:
    """The market time most stocks were priced at, so one halted stock can't set it."""
    times = [q["price_time"] for q in quotes.values() if q.get("price_time")]
    if not times:
        return None
    return datetime.fromtimestamp(median_high(times), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
