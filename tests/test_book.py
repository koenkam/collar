"""Scenario checks for trade.book. Run: env/bin/python -m tests.test_book"""
import datetime

from trade.book import breakeven, option_id, reconcile, stock_id

TODAY = datetime.date(2026, 9, 28)
CFG = {"cash_settled": {"SPX"}, "roll_window_seconds": 900, "underlying": {}}


def opt(symbol, strike, right, expiry, n, premium, startdate="20260901", open_commission=None):
    doc = {
        "secType": "OPT", "symbol": symbol, "right": right, "strike": float(strike),
        "expiry": expiry, "multiplier": 100.0, "n": n, "premium": premium,
        "startdate": startdate,
    }
    if open_commission is not None:
        doc["open_commission"] = open_commission
    return doc


def held(symbol, n, strike=None, right=None, expiry=None):
    if strike is None:
        return stock_id(symbol), {"sec_type": "STK", "symbol": symbol, "n": n}
    return option_id(expiry, symbol, strike, right), {
        "sec_type": "OPT", "symbol": symbol, "n": n, "strike": float(strike),
        "right": right, "expiry": expiry, "multiplier": 100.0,
    }


def fill(exec_id, symbol, side, qty, price, commission, strike=None, right=None,
         expiry=None, ts=0, date="20260928"):
    base = {
        "exec_id": exec_id, "symbol": symbol, "side": side, "qty": qty, "price": price,
        "commission": commission, "date": date, "ts": ts,
    }
    if strike is None:
        base.update({"sec_type": "STK", "instrument_id": stock_id(symbol), "multiplier": 1.0})
    else:
        base.update({
            "sec_type": "OPT", "instrument_id": option_id(expiry, symbol, strike, right),
            "strike": float(strike), "right": right, "expiry": expiry, "multiplier": 100.0,
        })
    return base


def only(outcomes):
    assert len(outcomes) == 1, [o.problems for o in outcomes]
    return outcomes[0]


def test_open():
    iid, entry = held("AMD", -4, 600, "P", "20261009")
    out = only(reconcile({}, {}, {iid: entry}, [
        fill("e1", "AMD", "SLD", 4, 11.6, 1.85, 600, "P", "20261009"),
    ], TODAY, CFG))
    assert out.ok
    doc = out.options[iid]
    assert doc["n"] == -4 and doc["startdate"] == "20260928"
    assert round(doc["premium"], 2) == 4638.15
    assert doc["open_commission"] == 1.85
    assert out.processed == ["e1"] and not out.logs


def test_scale_in():
    iid, entry = held("AMD", -6, 600, "P", "20261009")
    book = {iid: opt("AMD", 600, "P", "20261009", -4, 4638.15, "20260925")}
    out = only(reconcile(book, {}, {iid: entry}, [
        fill("e1", "AMD", "SLD", 2, 10.0, 1.0, 600, "P", "20261009"),
    ], TODAY, CFG))
    doc = out.options[iid]
    assert doc["n"] == -6 and doc["startdate"] == "20260925"
    assert round(doc["premium"], 2) == round(4638.15 + 1999.0, 2)


def test_partial_close_logs_both_commissions():
    iid, entry = held("NVDA", -1, 220, "P", "20260930")
    book = {iid: opt("NVDA", 220, "P", "20260930", -2, 346.74, "20260923")}
    out = only(reconcile(book, {}, {iid: entry}, [
        fill("e1", "NVDA", "BOT", 1, 1.0, 0.62, 220, "P", "20260930"),
    ], TODAY, CFG))
    row = out.logs[0]
    # premium slice 173.37 already net of the opening commission; closing commission subtracted
    assert row["premium"] == 173.37 and row["signed_quantity"] == 1
    assert row["profit"] == round(173.37 - 100 - 0.62, 2)
    assert row["assign"] == 22000.0
    doc = out.options[iid]
    assert doc["n"] == -1 and round(doc["premium"], 2) == 173.37


def test_full_close_removes_document():
    iid, _ = held("GOOGL", 0, 332.5, "P", "20260930")
    book = {iid: opt("GOOGL", 332.5, "P", "20260930", -3, 748.67)}
    out = only(reconcile(book, {}, {}, [
        fill("e1", "GOOGL", "BOT", 3, 0.82, 1.3, 332.5, "P", "20260930"),
    ], TODAY, CFG))
    assert out.options == {iid: None}
    assert out.logs[0]["profit"] == round(748.67 - 246 - 1.3, 2)


def test_close_log_keeps_sell_price_and_opening_commission():
    iid, _ = held("AMD", 0, 600, "P", "20261009")
    book = {iid: opt("AMD", 600, "P", "20261009", -4, 4638.15, "20260925", open_commission=1.85)}
    out = only(reconcile(book, {}, {}, [
        fill("e1", "AMD", "BOT", 4, 4.7, 1.6692, 600, "P", "20261009", date="20261002"),
    ], datetime.date(2026, 10, 2), CFG))
    row = out.logs[0]
    assert row["open_price"] == 11.6
    assert row["open_commission"] == 1.85
    assert row["close_price"] == 4.7
    assert row["close_commission"] == 1.6692
    assert row["premium"] == 4638.15
    assert row["profit"] == round(4638.15 - 4 * 4.7 * 100 - 1.6692, 2)


def test_partial_close_slices_opening_commission():
    iid, entry = held("NVDA", -1, 220, "P", "20260930")
    book = {iid: opt("NVDA", 220, "P", "20260930", -2, 346.74, "20260923", open_commission=1.26)}
    out = only(reconcile(book, {}, {iid: entry}, [
        fill("e1", "NVDA", "BOT", 1, 1.0, 0.62, 220, "P", "20260930"),
    ], TODAY, CFG))
    row = out.logs[0]
    assert row["open_price"] == 1.74
    assert row["open_commission"] == 0.63
    assert out.options[iid]["open_commission"] == 0.63


def test_roll_carries_opening_commission():
    old, _ = held("AMD", 0, 600, "P", "20261009")
    new, entry = held("AMD", -3, 580, "P", "20261016")
    book = {old: opt("AMD", 600, "P", "20261009", -4, 4638.15, "20260925", open_commission=1.85)}
    out = only(reconcile(book, {}, {new: entry}, [
        fill("e1", "AMD", "BOT", 4, 9.0, 2.0, 600, "P", "20261009", ts=100),
        fill("e2", "AMD", "SLD", 3, 14.0, 1.5, 580, "P", "20261016", ts=160),
    ], TODAY, CFG))
    doc = out.options[new]
    assert doc["open_commission"] == round(1.85 + 2.0 + 1.5, 6)
    price = (doc["premium"] + doc["open_commission"]) / (3 * 100)
    assert round(price, 6) == round(5240 / 300, 6)


def test_roll_keeps_start_and_carries_premium_with_count_change():
    old, _ = held("AMD", 0, 592.5, "P", "20260930")
    new, entry = held("AMD", -3, 580, "P", "20261016")
    book = {old: opt("AMD", 592.5, "P", "20260930", -4, 4638.15, "20260925")}
    out = only(reconcile(book, {}, {new: entry}, [
        fill("e1", "AMD", "BOT", 4, 9.0, 2.0, 592.5, "P", "20260930", ts=100),
        fill("e2", "AMD", "SLD", 3, 14.0, 1.5, 580, "P", "20261016", ts=160),
    ], TODAY, CFG))
    assert out.ok and not out.logs
    assert out.options[old] is None
    doc = out.options[new]
    assert doc["startdate"] == "20260925" and doc["n"] == -3
    assert round(doc["premium"], 2) == round(4638.15 - 3602 + 4198.5, 2)


def test_put_close_and_call_open_are_not_a_roll():
    put, _ = held("SHOP", 0, 150, "P", "20261009")
    call, entry = held("SHOP", -2, 160, "C", "20261016")
    book = {put: opt("SHOP", 150, "P", "20261009", -2, 500.0)}
    out = only(reconcile(book, {}, {call: entry}, [
        fill("e1", "SHOP", "BOT", 2, 1.0, 1.0, 150, "P", "20261009", ts=100),
        fill("e2", "SHOP", "SLD", 2, 2.0, 1.0, 160, "C", "20261016", ts=110),
    ], TODAY, CFG))
    assert len(out.logs) == 1 and out.logs[0]["profit"] == round(500 - 200 - 1, 2)
    assert out.options[put] is None
    assert out.options[call]["startdate"] == "20260928"
    assert round(out.options[call]["premium"], 2) == 399.0
    assert out.options[call]["open_commission"] == 1.0
    assert "open_price" not in out.logs[0]


def test_expiration_worthless():
    iid, _ = held("NVDA", 0, 210, "P", "20260925")
    book = {iid: opt("NVDA", 210, "P", "20260925", -2, 500.0)}
    out = only(reconcile(book, {}, {}, [], TODAY, CFG))
    assert out.options == {iid: None}
    assert out.logs[0]["kind"] == "expiration" and out.logs[0]["profit"] == 500.0
    assert out.logs[0]["close_date"] == "20260925"


def test_disappearing_before_expiry_goes_to_review():
    iid, _ = held("NVDA", 0, 210, "P", "20261030")
    book = {iid: opt("NVDA", 210, "P", "20261030", -2, 500.0)}
    out = only(reconcile(book, {}, {}, [], TODAY, CFG))
    assert not out.ok and out.review and not out.logs and not out.options


def test_put_assignment_example_from_plan():
    first, _ = held("AMD", 0, 200, "P", "20260925")
    second, _ = held("AMD", 0, 180, "P", "20260925")
    sid, stock_entry = held("AMD", 100)
    out = only(reconcile({first: opt("AMD", 200, "P", "20260925", -1, 200.0)}, {},
                         {sid: stock_entry}, [], TODAY, CFG))
    stock = out.stocks[sid]
    assert stock["n"] == 100 and stock["avgCost"] == 200 and stock["credit"] == 200
    assert stock["startdate"] == "20260925" and not out.logs

    sid, stock_entry = held("AMD", 200)
    out = only(reconcile({second: opt("AMD", 180, "P", "20260925", -1, 100.0)}, {sid: stock},
                         {sid: stock_entry}, [], TODAY, CFG))
    stock = out.stocks[sid]
    assert stock["avgCost"] == 190 and stock["credit"] == 300
    assert round(breakeven(stock), 2) == 188.50
    assert stock["startdate"] == "20260925"


def test_put_assigned_and_call_expired_same_day():
    put, _ = held("AMD", 0, 200, "P", "20260925")
    call, _ = held("AMD", 0, 250, "C", "20260925")
    sid, entry = held("AMD", 100)
    book = {
        put: opt("AMD", 200, "P", "20260925", -1, 200.0),
        call: opt("AMD", 250, "C", "20260925", -1, 80.0),
    }
    out = only(reconcile(book, {}, {sid: entry}, [], TODAY, CFG))
    assert out.ok
    assert out.stocks[sid]["n"] == 100 and out.stocks[sid]["credit"] == 200
    assert [row["kind"] for row in out.logs] == ["expiration"]
    assert out.logs[0]["profit"] == 80.0
    assert out.options == {put: None, call: None}


def test_call_assignment_logs_cycle():
    call, _ = held("SHOP", 0, 160, "C", "20260918")
    sid, entry = held("SHOP", 200)
    stocks = {sid: {"secType": "STK", "symbol": "SHOP", "n": 400, "avgCost": 150.0,
                    "credit": 800.0, "startdate": "20260212"}}
    book = {call: opt("SHOP", 160, "C", "20260918", -2, 300.0)}
    out = only(reconcile(book, stocks, {sid: entry}, [], TODAY, CFG))
    row = out.logs[0]
    assert row["kind"] == "call_assignment"
    assert row["profit"] == round((160 - 150) * 200 + 400 + 300, 2)
    stock = out.stocks[sid]
    assert stock["n"] == 200 and stock["credit"] == 400 and stock["avgCost"] == 150
    assert out.options[call] is None


def test_stock_purchase_and_sale():
    sid, entry = held("KO", 100)
    out = only(reconcile({}, {}, {sid: entry}, [
        fill("e1", "KO", "BOT", 100, 60.0, 1.0),
    ], TODAY, CFG))
    stock = out.stocks[sid]
    assert stock["avgCost"] == 60.01 and stock["credit"] == 0

    sid, entry = held("AMD", 300)
    stocks = {sid: {"secType": "STK", "symbol": "AMD", "n": 400, "avgCost": 200.0,
                    "credit": 400.0, "startdate": "20251218"}}
    out = only(reconcile({}, stocks, {sid: entry}, [
        fill("e2", "AMD", "SLD", 100, 210.0, 1.0),
    ], TODAY, CFG))
    assert out.logs[0]["profit"] == round(10 * 100 + 100 - 1, 2)
    assert out.stocks[sid]["n"] == 300 and out.stocks[sid]["credit"] == 300


def test_spx_expiration_is_cash_and_never_touches_stock():
    iid, _ = held("SPX", 0, 4400, "P", "20260925")
    book = {iid: opt("SPX", 4400, "P", "20260925", 10, -4914.5)}
    cfg = dict(CFG, underlying={"SPX": 6500.0})
    out = only(reconcile(book, {}, {}, [], TODAY, cfg))
    assert out.ok and not out.stocks
    row = out.logs[0]
    assert row["signed_quantity"] == -10 and row["profit"] == -4914.5


def test_spx_in_the_money_goes_to_review():
    iid, _ = held("SPX", 0, 4400, "P", "20260925")
    book = {iid: opt("SPX", 4400, "P", "20260925", 10, -4914.5)}
    cfg = dict(CFG, underlying={"SPX": 4300.0})
    out = only(reconcile(book, {}, {}, [], TODAY, cfg))
    assert not out.ok


def test_new_position_without_fill_goes_to_review():
    iid, entry = held("AMD", -2, 600, "P", "20261009")
    out = only(reconcile({}, {}, {iid: entry}, [], TODAY, CFG))
    assert not out.ok and out.review["instruments"][0]["broker"] == -2


def test_nothing_changed():
    iid, entry = held("AMD", -4, 600, "P", "20261009")
    book = {iid: opt("AMD", 600, "P", "20261009", -4.0, 4638.15)}
    assert reconcile(book, {}, {iid: entry}, [], TODAY, CFG) == []


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
