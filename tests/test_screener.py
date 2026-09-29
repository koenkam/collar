"""Checks for trade.screener. Run: env/bin/python -m tests.test_screener"""
import datetime

from config import create_c
from trade.screener import (
    candidate_strikes, earnings_flag, evaluate_symbol, format_candidate_row,
    format_screener_row, held_text, normalize_symbol, normalize_watchlist,
    put_delta, rank, sessions_after, target_expiry, watchlist_from_store,
    yield_at_delta,
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


def test_earnings_flag():
    expiry = d("20261009")
    calendar = {d("20261006"): {"AMD": "time-after-hours"}, d("20261009"): {"KO": "time-after-hours",
                                                                          "V": "time-pre-market",
                                                                          "JPM": "time-not-supplied"}}
    assert earnings_flag("AMD", expiry, calendar, []) is True
    assert earnings_flag("KO", expiry, calendar, []) is False
    assert earnings_flag("V", expiry, calendar, []) is True
    assert earnings_flag("JPM", expiry, calendar, []) is True
    assert earnings_flag("MSFT", expiry, calendar, [d("20261007")]) is None
    assert earnings_flag("MSFT", expiry, calendar, []) is False


def row(symbol, y25, ivhv=1.0, earnings=False, pick=True):
    return {"symbol": symbol, "y25": y25, "ivhv": ivhv, "earnings": earnings, "status": "",
            "pick": {"yield": y25 or 0.001} if pick else None}


def test_rank():
    ranked = rank([
        row("A", 0.0100), row("B", 0.0120, earnings=True), row("C", 0.0101, ivhv=1.5),
        row("D", None), row("E", 0.02, pick=False), row("F", 0.0090),
    ])
    assert [r["symbol"] for r in ranked] == ["C", "A", "F", "B", "D", "E"]
    assert [r["rank"] for r in ranked] == [1, 2, 3, None, None, None]


def test_held_text_and_row_format():
    from types import SimpleNamespace
    options = [SimpleNamespace(n=-2, contract=SimpleNamespace(symbol="AMD", strike=580.0,
                                                              right="P", lastTradeDateOrContractMonth="20261016"))]
    stocks = [SimpleNamespace(n=400, contract=SimpleNamespace(symbol="SHOP"))]
    assert held_text("AMD", options, stocks, lambda p: 0) == "2 × 580.00P 10-16"
    assert held_text("SHOP", options, stocks, lambda p: 195.95) == "400 sh, BE 195.95"
    row = evaluate_symbol({"symbol": "AMD", "spot": 600, "iv": 0.5, "hv": 0.4,
                           "expiry": "20261009", "quotes": [quote(570, 4.0, 4.3, -0.22)]}, CFG)
    row.update({"dte": 11, "earnings": False, "fits": 3, "held": "2 × 580.00P 10-16", "rank": 1})
    cells = format_screener_row(row)
    assert len(cells) == 20
    assert cells[0] == "AMD" and cells[2] == "10-09" and cells[4] == "570.00"
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


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
