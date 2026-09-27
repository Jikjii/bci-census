"""Local time for quiet hours and digests.

Python's zoneinfo needs the system time-zone database, and some minimal Lambda images ship
without it. Rather than let quiet hours slip by several hours, common zones fall back to
their daylight-saving rules below (US and EU rules as in force since 2007 and 1996).
"""

from __future__ import annotations

import datetime as dt
import logging

log = logging.getLogger(__name__)

HOUR = dt.timedelta(hours=1)
ZERO = dt.timedelta(0)

# zone: (standard UTC offset in hours, daylight-saving rule)
RULES = {
    "America/New_York": (-5, "us"), "America/Detroit": (-5, "us"), "America/Toronto": (-5, "us"),
    "America/Chicago": (-6, "us"), "America/Denver": (-7, "us"), "America/Phoenix": (-7, None),
    "America/Los_Angeles": (-8, "us"), "America/Vancouver": (-8, "us"), "America/Anchorage": (-9, "us"),
    "Pacific/Honolulu": (-10, None),
    "Europe/London": (0, "eu"), "Europe/Dublin": (0, "eu"), "Europe/Lisbon": (0, "eu"),
    "Europe/Stockholm": (1, "eu"), "Europe/Oslo": (1, "eu"), "Europe/Copenhagen": (1, "eu"),
    "Europe/Berlin": (1, "eu"), "Europe/Paris": (1, "eu"), "Europe/Amsterdam": (1, "eu"),
    "Europe/Brussels": (1, "eu"), "Europe/Zurich": (1, "eu"), "Europe/Madrid": (1, "eu"),
    "Europe/Rome": (1, "eu"), "Europe/Vienna": (1, "eu"), "Europe/Warsaw": (1, "eu"),
    "Europe/Helsinki": (2, "eu"), "Europe/Athens": (2, "eu"),
    "Asia/Dubai": (4, None), "Asia/Kolkata": (5.5, None), "Asia/Singapore": (8, None),
    "Asia/Shanghai": (8, None), "Asia/Hong_Kong": (8, None), "Asia/Taipei": (8, None),
    "Asia/Seoul": (9, None), "Asia/Tokyo": (9, None), "Australia/Brisbane": (10, None),
    "UTC": (0, None), "Etc/UTC": (0, None),
}


def _nth_sunday(year: int, month: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def _last_sunday(year: int, month: int) -> dt.date:
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - 6) % 7)


class RuleZone(dt.tzinfo):
    def __init__(self, name: str, std_hours: float, rule: str | None):
        self.name, self.std, self.rule = name, dt.timedelta(hours=std_hours), rule

    def _dst_at_utc(self, utc: dt.datetime) -> bool:
        """Is daylight time in effect at this naive UTC moment?"""
        year = utc.year
        if self.rule == "us":  # 2nd Sunday of March 2:00 standard to 1st Sunday of November 2:00 daylight
            start = dt.datetime.combine(_nth_sunday(year, 3, 2), dt.time(2)) - self.std
            end = dt.datetime.combine(_nth_sunday(year, 11, 1), dt.time(2)) - self.std - HOUR
        elif self.rule == "eu":  # last Sunday of March to last Sunday of October, 1:00 UTC
            start = dt.datetime.combine(_last_sunday(year, 3), dt.time(1))
            end = dt.datetime.combine(_last_sunday(year, 10), dt.time(1))
        else:
            return False
        return start <= utc < end

    def fromutc(self, moment: dt.datetime) -> dt.datetime:
        utc = moment.replace(tzinfo=None)
        offset = self.std + (HOUR if self._dst_at_utc(utc) else ZERO)
        return (utc + offset).replace(tzinfo=self)

    def utcoffset(self, moment: dt.datetime | None) -> dt.timedelta:
        if moment is None:
            return self.std
        wall = moment.replace(tzinfo=None)  # exact except in the repeated hour each autumn
        return self.std + (HOUR if self._dst_at_utc(wall - self.std) else ZERO)

    def dst(self, moment: dt.datetime | None) -> dt.timedelta:
        return self.utcoffset(moment) - self.std

    def tzname(self, moment: dt.datetime | None) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"RuleZone({self.name!r})"


def zone(name: str, use_system: bool = True) -> dt.tzinfo:
    if use_system:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:
            pass
    if name in RULES:
        return RuleZone(name, *RULES[name])
    log.warning("Time zone %s unavailable; using UTC for quiet hours and digests", name)
    return dt.timezone.utc
