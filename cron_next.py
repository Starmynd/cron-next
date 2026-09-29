#!/usr/bin/env python3
"""cron-next - parse cron expressions and show the next scheduled run times.

Supports the standard five fields: minute hour day-of-month month day-of-week,
with *, lists (a,b), ranges (a-b) and steps (a-b/n or */n). Follows Vixie cron
semantics: if both day-of-month and day-of-week are restricted, a run happens
when EITHER matches.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

FIELD_NAMES = ("minute", "hour", "day-of-month", "month", "day-of-week")
FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))

DAYS_IN_MONTH = {
    1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
}


class CronError(ValueError):
    pass


def _parse_field(spec: str, low: int, high: int, name: str) -> set[int]:
    values: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise CronError(f"empty list item in {name}")
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError:
                raise CronError(f"bad step '{step_s}' in {name}")
            if step < 1:
                raise CronError(f"step must be >= 1 in {name}")
        if part in ("*", ""):
            if "/" in spec and step == 1 and part == "":
                raise CronError(f"missing step in {name}")
            start, end = low, high
        elif "-" in part:
            a, b = part.split("-", 1)
            try:
                start, end = int(a), int(b)
            except ValueError:
                raise CronError(f"bad range '{part}' in {name}")
        else:
            try:
                start = int(part)
            except ValueError:
                raise CronError(f"bad number '{part}' in {name}")
            end = start if step == 1 else high
        if start < low or end > high or start > end:
            raise CronError(f"value out of range [{low}-{high}] in {name}: '{part}'")
        values.update(range(start, end + 1, step))
    return values


def parse(expr: str) -> list[set[int]]:
    """Parse a cron expression into per-field sets of allowed values.

    Returns [minutes, hours, days_of_month, months, days_of_week].
    Day-of-week 7 is normalized to 0 (Sunday); '*' for dom/dow is kept as full
    range so restrictedness can be checked.
    """
    fields = expr.split()
    if len(fields) != 5:
        raise CronError(f"expected 5 fields, got {len(fields)}")
    parsed = [
        _parse_field(f, low, high, name)
        for f, (low, high), name in zip(fields, FIELD_RANGES, FIELD_NAMES)
    ]
    dom, dow = parsed[2], parsed[4]
    if 7 in dow:
        dow.add(0)
        dow.discard(7)
    return parsed


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_month(year: int, month: int) -> int:
    if month == 2 and _is_leap(year):
        return 29
    return DAYS_IN_MONTH[month]


def matches(parsed: list[set[int]], dt: datetime) -> bool:
    minute, hour, dom, mon, dow = (
        parsed[0], parsed[1], parsed[2], parsed[3], parsed[4],
    )
    if dt.minute not in minute or dt.hour not in hour or dt.month not in mon:
        return False
    dom_star = parsed[2] == set(range(1, 32))
    dow_star = parsed[4] == set(range(0, 7))
    cron_dow = (dt.weekday() + 1) % 7  # cron: 0 = Sunday
    dom_ok = dt.day in dom
    dow_ok = cron_dow in dow
    if dom_star and dow_star:
        return True
    if dom_star:
        return dow_ok
    if dow_star:
        return dom_ok
    return dom_ok or dow_ok  # Vixie OR semantics


def next_runs(expr: str, count: int = 1, start: datetime | None = None,
              horizon_days: int = 366 * 2) -> list[datetime]:
    """Return the next `count` run times strictly after `start`."""
    parsed = parse(expr)
    cur = (start or datetime.now()).replace(second=0, microsecond=0)
    limit = cur + timedelta(days=horizon_days)
    out: list[datetime] = []
    while len(out) < count:
        cur += timedelta(minutes=1)
        if cur > limit:
            raise CronError(f"no matching time within {horizon_days} days")
        if matches(parsed, cur):
            out.append(cur)
    return out


def _selftest() -> int:
    cases = [
        ("*/5 * * * *", "2026-01-01 00:00", 1, ["2026-01-01 00:05"]),
        ("*/15 9-17 * * 1-5", "2026-01-01 00:00", 3,
         ["2026-01-01 09:00", "2026-01-01 09:15", "2026-01-01 09:30"]),
        ("0 0 1 1 *", "2026-06-15 10:00", 1, ["2027-01-01 00:00"]),
        ("30 4 1,15 * *", "2026-02-01 04:31", 2,
         ["2026-02-15 04:30", "2026-03-01 04:30"]),
        ("0 9-17/2 * * *", "2026-03-10 12:00", 2,
         ["2026-03-10 13:00", "2026-03-10 15:00"]),
        ("0 0 * * 7", "2026-03-10 00:00", 1, ["2026-03-15 00:00"]),  # 7=Sunday
        ("0 0 13 * 5", "2026-05-01 00:00", 3,
         ["2026-05-08 00:00", "2026-05-13 00:00",
          "2026-05-15 00:00"]),  # dom OR dow (13th or any Friday)
        ("59 23 31 12 *", "2026-01-01 00:00", 1, ["2026-12-31 23:59"]),
        ("0 12 1 * *", "2026-01-31 12:00", 2,
         ["2026-02-01 12:00", "2026-03-01 12:00"]),  # Feb has 28 days
    ]
    failed = 0
    for expr, start_s, n, want in cases:
        start = datetime.strptime(start_s, "%Y-%m-%d %H:%M")
        got = [d.strftime("%Y-%m-%d %H:%M") for d in next_runs(expr, n, start)]
        if got != want:
            failed += 1
            print(f"FAIL {expr!r} from {start_s}: got {got}, want {want}")
        else:
            print(f"PASS {expr!r} -> {got[0]}")
    for bad in ["* * * *", "61 * * * *", "* 25 * * *", "*/0 * * * *", "a * * * *"]:
        try:
            parse(bad)
            failed += 1
            print(f"FAIL invalid expr accepted: {bad!r}")
        except CronError:
            print(f"PASS rejects {bad!r}")
    print(f"selftest: failures={failed}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="cron-next",
        description="Show the next run times of a cron expression.",
    )
    ap.add_argument("expr", nargs="?", help='cron expression, e.g. "*/15 9-17 * * 1-5"')
    ap.add_argument("-n", type=int, default=1, help="how many run times to show")
    ap.add_argument("--from", dest="start", metavar="\"YYYY-MM-DD HH:MM\"",
                    help="start counting from this time (default: now)")
    ap.add_argument("--test", action="store_true", help="run self-test")
    args = ap.parse_args(argv)

    if args.test:
        return _selftest()
    if not args.expr:
        ap.error("a cron expression is required (or use --test)")

    start = None
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
    try:
        for dt in next_runs(args.expr, max(1, args.n), start):
            print(dt.strftime("%Y-%m-%d %H:%M %a"))
    except (CronError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
