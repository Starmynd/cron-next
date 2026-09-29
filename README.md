# cron-next

Parse cron expressions and show the next scheduled run times from the
terminal. One file, standard library only.

Useful when you inherit a crontab and want to know what `"*/15 9-17 * * 1-5"`
actually resolves to, or when checking that a job really fires when you think
it does.

## Features

- Full 5-field syntax: `*`, lists (`1,15`), ranges (`9-17`), steps (`*/5`, `9-17/2`)
- Vixie cron day semantics: restricted day-of-month **and** day-of-week match
  with OR (documented behavior, faithfully reproduced)
- Day-of-week 7 normalized to 0 (Sunday)
- `--from "YYYY-MM-DD HH:MM"` to compute from an arbitrary point in time
- Clear error messages for malformed expressions

## Usage

```console
$ cron-next "*/15 9-17 * * 1-5" -n 3
2026-09-29 09:00 Tue
2026-09-29 09:15 Tue
2026-09-29 09:30 Tue

$ cron-next "0 12 1 * *" -n 2 --from "2026-01-31 12:00"
2026-02-01 12:00 Sun
2026-03-01 12:00 Sun

$ cron-next --test
selftest: failures=0
```

## How it works

Times are found by scanning forward minute by minute from the start point
(capped at a two-year horizon), so leap years and month lengths are handled by
the calendar itself rather than by date arithmetic.

## Testing

```console
$ python3 cron_next.py --test
```

Covers ranges, steps, lists, weekday normalization, dom/dow OR semantics,
February edge cases and malformed expressions.

## License

MIT
