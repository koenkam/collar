"""Next earnings dates from Nasdaq's public calendar."""
import datetime
import json
import time
import urllib.request

URL = "https://api.nasdaq.com/api/calendar/earnings?date={date}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Accept": "application/json",
}
HORIZON_DAYS = 120
ATTEMPTS = 3


def fetch_day(day, timeout=10, attempts=3):
    """Symbols reporting on this day, mapped to Nasdaq's time label."""
    last = None
    for i in range(attempts):
        try:
            request = urllib.request.Request(URL.format(date=day.strftime("%Y-%m-%d")), headers=HEADERS)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rows = ((payload or {}).get("data") or {}).get("rows") or []
            return {str(r.get("symbol", "")).upper(): r.get("time") or "" for r in rows if r.get("symbol")}
        except Exception as e:
            last = e
            if i + 1 < attempts:
                time.sleep(0.4 * (i + 1))
    raise last


def fetch_next_earnings(symbols, start, horizon_days=HORIZON_DAYS, attempts=ATTEMPTS, pause=0.2):
    """Earliest earnings date on or after `start` for each symbol.

    Weekdays are read until every symbol has a date or the horizon ends.
    A day that still fails after `attempts` tries is skipped. Returns
    ({symbol: date}, failed). `failed` is true when any day could not be read,
    so a missing symbol may simply have been on a day the calendar omitted.
    """
    wanted, seen = [], set()
    for symbol in symbols:
        key = str(symbol or "").strip().upper()
        if key and key not in seen:
            seen.add(key)
            wanted.append(key)
    found = {}
    failed = False
    day = start
    last = start + datetime.timedelta(days=horizon_days)
    while day <= last and len(found) < len(wanted):
        if day.weekday() >= 5:
            day += datetime.timedelta(days=1)
            continue
        try:
            rows = fetch_day(day, attempts=attempts)
        except Exception as e:
            print(f"Earnings calendar {day}: {e}")
            failed = True
        else:
            for symbol in wanted:
                if symbol not in found and symbol in rows:
                    found[symbol] = day
        if pause and len(found) < len(wanted) and day < last:
            time.sleep(pause)
        day += datetime.timedelta(days=1)
    return found, failed
