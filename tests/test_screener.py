"""Checks for trade.screener. Run: env/bin/python -m tests.test_screener"""
import datetime

from config import create_c
from trade.screener import (
    candidate_strikes, company_display_name, earnings_due_soon, earnings_text, evaluate_symbol,
    format_candidate_row, format_screener_row, held_text, normalize_symbol,
    normalize_watchlist, put_delta, rank, sessions_after, target_expiry,
    watchlist_from_store, watchlist_names, yield_at_delta,
)

c = create_c()
H = c.market_holidays
CFG = {"fill_fraction": 0.25, "commission": 0.5, "max_spread": 0.10, "min_oi": 100,
       "target_delta": 0.25, "band": (0.20, 0.30)}


def d(text):
    return datetime.datetime.strptime(text, "%Y%m%d").date()


def test_holidays_are_weekdays():
    for day in H:
        assert d(day).weekday() < 5, day


def test_target_expiry_skips_today():
    today = d("20260928")
    assert sessions_after(today, d("20261002"), H) == 4
    assert target_expiry(today, H) == d("20261009")
    assert target_expiry(d("20260925"), H) == d("20261002")


def test_good_friday_moves_expiry_to_thursday():
    assert target_expiry(d("20260326"), H) == d("20260402")


def test_put_delta_and_candidates():
    delta = put_delta(100, 95, 0.30, 11 / 365)
    assert -0.30 < delta < -0.10
    strikes = candidate_strikes(range(80, 105), 100, 0.30, 11)
    assert strikes and max(strikes) < 100 and min(strikes) >= 90


def quote(strike, bid, ask, delta, oi=500):
    return {"strike": strike, "bid": bid, "ask": ask, "delta": delta, "oi": oi}


def test_yield_and_interpolation():
    scan = {"symbol": "AMD", "spot": 600, "iv": 0.5, "hv": 0.4, "expiry": "20261009", "quotes": [
        quote(580, 6.0, 6.4, -0.30),
        quote(570, 4.0, 4.3, -0.22),
        quote(560, 2.6, 2.8, -0.16),
    ]}
    row = evaluate_symbol(scan, CFG)
    y30 = (6.1 * 100 - 0.5) / 58000
    y22 = (4.075 * 100 - 0.5) / 57000
    assert abs(row["y25"] - (y22 + (0.25 - 0.22) / (0.30 - 0.22) * (y30 - y22))) < 1e-12
    assert row["pick"]["strike"] == 570
    assert abs(row["pick"]["breakeven"] - (570 - 4.075)) < 1e-9
    assert abs(row["ivhv"] - 1.25) < 1e-9


def test_filters():
    rows = evaluate_symbol({"symbol": "X", "expiry": "20261009", "quotes": [
        quote(100, 1.0, 1.5, -0.25),
        quote(99, 0.95, 1.0, -0.24, oi=10),
        quote(98, 0, 0.2, -0.2),
    ]}, CFG)["candidates"]
    problems = {r["strike"]: r["problems"] for r in rows}
    assert problems[100] == ["wide spread"]
    assert problems[99] == ["low open interest"]
    assert problems[98] == ["no bid"]
    assert yield_at_delta(rows) is None


def test_missing_quote_status():
    empty = evaluate_symbol({"symbol": "KO", "spot": 87, "quotes": []}, CFG)
    assert empty["status"] == "no quotes"
    no_delta = evaluate_symbol({"symbol": "KO", "spot": 87, "quotes": [
        {"strike": 80, "bid": 1.0, "ask": 1.1, "delta": None, "oi": 500},
    ]}, CFG)
    assert no_delta["status"] == "no delta"


def test_earnings_date_and_soon_window():
    today = d("20261003")
    assert earnings_text(d("20261103")) == "11-03"
    assert earnings_text(None) == ""
    assert earnings_text(None, unknown=True) == "unk"
    assert earnings_due_soon(d("20261003"), today) is True
    assert earnings_due_soon(d("20261031"), today) is True
    assert earnings_due_soon(d("20261101"), today) is False
    assert earnings_due_soon(d("20261002"), today) is False
    assert earnings_due_soon(None, today) is False


def test_next_earnings_keeps_earliest_date_and_retries():
    import trade.earnings as earnings
    calls = []

    def fake(day, timeout=10, attempts=3):
        calls.append((day, attempts))
        if day == d("20261005"):
            raise OSError("calendar down")
        if day == d("20261006"):
            return {"AMD": "time-after-hours"}
        if day == d("20261007"):
            return {"KO": "time-pre-market", "AMD": "time-after-hours"}
        return {}

    original = earnings.fetch_day
    earnings.fetch_day = fake
    try:
        dates, failed = earnings.fetch_next_earnings(
            ["amd", "KO"], d("20261003"), horizon_days=10, pause=0,
        )
    finally:
        earnings.fetch_day = original
    assert calls and all(attempts == 3 for _, attempts in calls)
    assert dates["AMD"] == d("20261006")
    assert dates["KO"] == d("20261007")
    assert failed is True
    assert d("20261003") not in [day for day, _ in calls]
    assert d("20261004") not in [day for day, _ in calls]


def test_fetch_day_retries_three_times():
    import trade.earnings as earnings
    tries = {"n": 0}

    def boom(request, timeout=10):
        tries["n"] += 1
        raise OSError("calendar down")

    original = earnings.urllib.request.urlopen
    earnings.urllib.request.urlopen = boom
    try:
        try:
            earnings.fetch_day(d("20261006"), attempts=3)
            assert False, "expected the calendar read to fail"
        except OSError:
            pass
    finally:
        earnings.urllib.request.urlopen = original
    assert tries["n"] == 3


def row(symbol, y25, ivhv=1.0, earnings=False, pick=True):
    return {"symbol": symbol, "y25": y25, "ivhv": ivhv, "earnings": earnings, "status": "",
            "pick": {"yield": y25 or 0.001} if pick else None}


def test_rank():
    ranked = rank([
        row("A", 0.0100), row("B", 0.0120, earnings=True), row("C", 0.0101, ivhv=1.5),
        row("D", None), row("E", 0.02, pick=False), row("F", 0.0090),
    ])
    assert [r["symbol"] for r in ranked] == ["B", "C", "A", "F", "D", "E"]
    assert [r["rank"] for r in ranked] == [1, 2, 3, 4, 5, None]


def test_held_text_and_row_format():
    from types import SimpleNamespace
    options = [SimpleNamespace(n=-2, contract=SimpleNamespace(symbol="AMD", strike=580.0,
                                                              right="P", lastTradeDateOrContractMonth="20261016"))]
    stocks = [SimpleNamespace(n=400, contract=SimpleNamespace(symbol="SHOP"))]
    assert held_text("AMD", options, stocks, lambda p: 0) == "2 × 580.00P 10-16"
    assert held_text("SHOP", options, stocks, lambda p: 195.95) == "400 sh, BE 195.95"
    row = evaluate_symbol({"symbol": "AMD", "spot": 600, "iv": 0.5, "hv": 0.4,
                           "expiry": "20261009", "quotes": [quote(570, 4.0, 4.3, -0.22)]}, CFG)
    row.update({"dte": 11, "earnings_date": d("20261103"), "fits": 3, "held": "2 × 580.00P 10-16", "rank": 1})
    cells = format_screener_row(row)
    assert len(cells) == 20
    assert cells[0] == "AMD" and cells[2] == "10-09" and cells[4] == "570.00"
    assert cells[16] == "11-03"
    assert cells[17] == "3"
    assert cells[19] == "2 × 580.00P 10-16"
    detail = format_candidate_row(row["candidates"][0])
    assert len(detail) == 7


def test_watchlist_normalize_and_store():
    assert normalize_symbol(" amd ") == "AMD"
    assert normalize_symbol("brk.b") == "BRK.B"
    try:
        normalize_symbol("bad ticker!")
        assert False
    except ValueError:
        pass
    assert normalize_watchlist(["amd", "AMD", " brk.b ", "", "??"]) == ["AMD", "BRK.B"]
    defaults = ["AMZN", "GOOGL"]
    assert watchlist_from_store(None, defaults) == (["AMZN", "GOOGL"], True)
    assert watchlist_from_store(["shop", "NVDA"], defaults) == (["SHOP", "NVDA"], False)
    assert watchlist_from_store(["???"], defaults) == (["AMZN", "GOOGL"], True)
    assert watchlist_from_store([], defaults) == (["AMZN", "GOOGL"], True)
    assert company_display_name("ADVANCED MICRO DEVICES INC") == "Advanced Micro Devices Inc"
    assert company_display_name("Berkshire Hathaway") == "Berkshire Hathaway"
    assert watchlist_names(["AMD", "KO"], {"AMD": "Advanced Micro Devices Inc", "SHOP": "Shopify"}) == {
        "AMD": "Advanced Micro Devices Inc",
    }


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
