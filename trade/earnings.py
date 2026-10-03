"""Earnings dates from Nasdaq's public calendar."""
import json
import time
import urllib.request

URL = "https://api.nasdaq.com/api/calendar/earnings?date={date}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Accept": "application/json",
}


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


def fetch_calendar(days):
    """Return (calendar, failed_days). Calendar maps each day to {symbol: time}."""
    calendar, failed = {}, []
    for day in days:
        try:
            calendar[day] = fetch_day(day)
        except Exception as e:
            print(f"Earnings calendar {day}: {e}")
            failed.append(day)
    return calendar, failed
