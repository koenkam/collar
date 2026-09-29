"""Put screener math: expiry, strike candidates, yield, delta interpolation, ranking."""
import datetime
import math
import re

AFTER_CLOSE = "time-after-hours"
SYMBOL_RE = re.compile(r"[A-Z][A-Z0-9.]{0,9}$")


def normalize_symbol(text):
    symbol = str(text or "").strip().upper().replace(" ", "")
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError(
            "Symbol must be a ticker, for example AMD, BRK.B, or AVGO"
        )
    return symbol


def normalize_watchlist(symbols):
    """Uppercase tickers, drop blanks, keep first occurrence of each."""
    seen, result = set(), []
    for raw in symbols or []:
        try:
            symbol = normalize_symbol(raw)
        except ValueError:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
    return result


def watchlist_from_store(stored, defaults):
    """Return (symbols, persist). persist is True when Firestore should be seeded."""
    defaults = list(defaults)
    if stored is None:
        return defaults, True
    cleaned = normalize_watchlist(stored)
    if cleaned:
        return cleaned, False
    return defaults, True


def parse_day(value):
    if isinstance(value, datetime.date):
        return value
    return datetime.datetime.strptime(str(value)[:8], "%Y%m%d").date()


def day_text(day):
    return day.strftime("%Y%m%d")


def is_session(day, holidays):
    return day.weekday() < 5 and day_text(day) not in holidays


def sessions_after(today, day, holidays):
    """Trading sessions after today, up to and including day."""
    count = 0
    current = today + datetime.timedelta(days=1)
    while current <= day:
        if is_session(current, holidays):
            count += 1
        current += datetime.timedelta(days=1)
    return count


def is_friday_expiry(day, holidays):
    """A Friday session, or the Thursday before a Friday market holiday."""
    if day.weekday() == 4:
        return is_session(day, holidays)
    if day.weekday() == 3:
        friday = day + datetime.timedelta(days=1)
        return is_session(day, holidays) and day_text(friday) in holidays
    return False


def target_expiry(today, holidays, min_sessions=5):
    day = today + datetime.timedelta(days=1)
    for _ in range(60):
        if is_friday_expiry(day, holidays) and sessions_after(today, day, holidays) >= min_sessions:
            return day
        day += datetime.timedelta(days=1)
    return None


def weekdays_through(today, last_day):
    days = []
    current = today
    while current <= last_day:
        if current.weekday() < 5:
            days.append(current)
        current += datetime.timedelta(days=1)
    return days


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def put_delta(spot, strike, iv, years, rate=0.04):
    if spot <= 0 or strike <= 0 or iv <= 0 or years <= 0:
        return None
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * years) / (iv * math.sqrt(years))
    return norm_cdf(d1) - 1.0


def candidate_strikes(strikes, spot, iv, dte, low=0.12, high=0.40, target=0.25, limit=10):
    """Strikes whose estimated put delta lies in the band, closest to the target first."""
    strikes = sorted({float(s) for s in strikes if s and float(s) > 0})
    years = max(dte, 1) / 365.0
    picked = []
    if iv and iv > 0 and spot:
        for strike in strikes:
            delta = put_delta(spot, strike, iv, years)
            if delta is not None and low <= abs(delta) <= high:
                picked.append((abs(abs(delta) - target), strike))
    elif spot:
        for strike in strikes:
            if spot * 0.85 <= strike <= spot:
                picked.append((abs(strike - spot * 0.95), strike))
    picked.sort()
    return sorted(strike for _, strike in picked[:limit])


def fill_price(bid, ask, fraction=0.25):
    return bid + fraction * (ask - bid)


def cash_yield(fill, strike, commission):
    return (fill * 100 - commission) / (strike * 100)


def evaluate_quote(quote, cfg):
    bid, ask, delta = quote.get("bid"), quote.get("ask"), quote.get("delta")
    row = dict(quote)
    row["problems"] = []
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        row["problems"].append("no bid")
        return row
    mid = (bid + ask) / 2
    row["mid"] = mid
    row["spread_pct"] = (ask - bid) / mid if mid else None
    row["fill"] = fill_price(bid, ask, cfg.get("fill_fraction", 0.25))
    row["premium"] = row["fill"] * 100 - cfg.get("commission", 0.5)
    row["yield"] = cash_yield(row["fill"], quote["strike"], cfg.get("commission", 0.5))
    row["breakeven"] = quote["strike"] - row["fill"]
    if delta is None:
        row["problems"].append("no delta")
    if row["spread_pct"] is not None and row["spread_pct"] > cfg.get("max_spread", 0.10):
        row["problems"].append("wide spread")
    oi = quote.get("oi")
    if oi is not None and oi < cfg.get("min_oi", 100):
        row["problems"].append("low open interest")
    return row


def yield_at_delta(rows, target=0.25):
    """Linear interpolation of yield at |delta| = target from the bracketing strikes."""
    points = sorted(
        (abs(r["delta"]), r["yield"]) for r in rows
        if not r["problems"] and r.get("delta") is not None
    )
    for d, y in points:
        if abs(d - target) < 1e-9:
            return y
    below = [p for p in points if p[0] < target]
    above = [p for p in points if p[0] > target]
    if not below or not above:
        return None
    d1, y1 = below[-1]
    d2, y2 = above[0]
    return y1 + (target - d1) / (d2 - d1) * (y2 - y1)


def recommend(rows, target=0.25, band=(0.20, 0.30)):
    usable = [
        r for r in rows
        if not r["problems"] and r.get("delta") is not None and band[0] <= abs(r["delta"]) <= band[1]
    ]
    if not usable:
        return None
    return min(usable, key=lambda r: (abs(abs(r["delta"]) - target), -r["strike"]))


def earnings_flag(symbol, expiry, calendar, failed_days):
    """True, False, or None when a day that matters could not be read."""
    symbol = symbol.upper()
    for day, rows in calendar.items():
        entry = rows.get(symbol)
        if entry is None:
            continue
        if day < expiry:
            return True
        if day == expiry and entry != AFTER_CLOSE:
            return True
    if any(day <= expiry for day in failed_days):
        return None
    return False


def evaluate_symbol(scan, cfg):
    """Turn the collected data for one symbol into a screener row."""
    row = {
        "symbol": scan["symbol"],
        "status": scan.get("status") or "",
        "spot": scan.get("spot"),
        "iv": scan.get("iv"),
        "hv": scan.get("hv"),
        "expiry": scan.get("expiry"),
        "closed_market": scan.get("closed_market", False),
        "candidates": [],
        "pick": None,
        "y25": None,
        "ivhv": None,
    }
    if row["iv"] and row["hv"]:
        row["ivhv"] = row["iv"] / row["hv"]
    if row["status"]:
        return row
    rows = [evaluate_quote(q, cfg) for q in scan.get("quotes", [])]
    rows.sort(key=lambda r: -r["strike"])
    row["candidates"] = rows
    target = cfg.get("target_delta", 0.25)
    row["y25"] = yield_at_delta(rows, target)
    row["pick"] = recommend(rows, target, cfg.get("band", (0.20, 0.30)))
    if row["pick"] is None:
        row["status"] = "none in band"
    elif row["y25"] is None:
        row["status"] = "no 25Δ"
    return row


def dte(expiry, today):
    return (parse_day(expiry) - today).days


def rank(rows, tie=0.0002):
    """Ranked rows first, then flagged or incomplete rows, then rows that could not be read."""
    def group(r):
        if r["pick"] is None:
            return 2
        if r.get("earnings") is True or r["y25"] is None:
            return 1
        return 0

    def score(r):
        if r["y25"] is not None:
            return r["y25"]
        return r["pick"]["yield"] if r["pick"] else 0

    ordered = sorted(rows, key=lambda r: (group(r), -score(r), r["symbol"]))
    changed = True
    while changed:
        changed = False
        for i in range(len(ordered) - 1):
            a, b = ordered[i], ordered[i + 1]
            if group(a) or group(b) or a["y25"] is None or b["y25"] is None:
                continue
            if abs(a["y25"] - b["y25"]) < tie and (b.get("ivhv") or 0) > (a.get("ivhv") or 0):
                ordered[i], ordered[i + 1] = b, a
                changed = True
    for position, r in enumerate(ordered, start=1):
        r["rank"] = position if group(r) == 0 else None
    return ordered


def vol_text(value):
    if value is None:
        return ""
    return f"{(value if value > 3 else value * 100):.1f}%"


def pct_text(value, digits=2):
    if value is None:
        return ""
    return f"{value * 100:.{digits}f}%"


def money_text(value):
    if value is None or value == "":
        return ""
    return f"{float(value):.2f}"


def expiry_short(expiry):
    text = str(expiry or "")
    if len(text) >= 8:
        return f"{text[4:6]}-{text[6:8]}"
    return text


def earnings_text(flag):
    if flag is True:
        return "before"
    if flag is None:
        return "unk"
    return ""


def fits_text(fits):
    if fits is None:
        return ""
    if fits <= 0:
        return "over"
    return str(fits)


def format_screener_row(row):
    pick = row.get("pick")
    expiry_text = expiry_short(row.get("expiry"))
    if pick is None:
        return [
            row.get("symbol", ""),
            money_text(row.get("spot")),
            expiry_text,
            str(row["dte"]) if row.get("dte") is not None else "",
            row.get("status") or "",
            "", "", "", "", "", "", "",
            pct_text(row.get("y25")),
            vol_text(row.get("iv")),
            vol_text(row.get("hv")),
            f"{row['ivhv']:.2f}" if row.get("ivhv") else "",
            earnings_text(row.get("earnings")),
            "",
            "",
            row.get("held") or "",
        ]
    annual = pick["yield"] * 365 / row["dte"] if row.get("dte") else None
    return [
        row.get("symbol", ""),
        money_text(row.get("spot")),
        expiry_text,
        str(row["dte"]) if row.get("dte") is not None else "",
        money_text(pick.get("strike")),
        f"{pick['delta']:.2f}" if pick.get("delta") is not None else "",
        money_text(pick.get("bid")),
        money_text(pick.get("ask")),
        money_text(pick.get("fill")),
        money_text(pick.get("premium")),
        pct_text(pick.get("yield")),
        pct_text(annual),
        pct_text(row.get("y25")),
        vol_text(row.get("iv")),
        vol_text(row.get("hv")),
        f"{row['ivhv']:.2f}" if row.get("ivhv") else "",
        earnings_text(row.get("earnings")),
        fits_text(row.get("fits")),
        money_text(pick.get("breakeven")),
        row.get("held") or "",
    ]


def format_candidate_row(quote):
    return [
        money_text(quote.get("strike")),
        f"{quote['delta']:.2f}" if quote.get("delta") is not None else "",
        money_text(quote.get("bid")),
        money_text(quote.get("ask")),
        money_text(quote.get("fill")),
        pct_text(quote.get("yield")),
        ", ".join(quote.get("problems") or []),
    ]


def held_text(symbol, options, stocks, stock_breakeven):
    parts = []
    for position in options:
        contract = position.contract
        if contract.symbol != symbol or position.n >= 0:
            continue
        expiry = str(contract.lastTradeDateOrContractMonth)
        parts.append(
            f"{abs(int(position.n))} × {money_text(contract.strike)}{contract.right} {expiry_short(expiry)}"
        )
    for position in stocks:
        if position.contract.symbol == symbol and position.n > 0:
            parts.append(f"{int(position.n)} sh, BE {stock_breakeven(position):.2f}")
    return ", ".join(parts)
