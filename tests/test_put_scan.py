"""Checks for trade.put_scan retries. Run: env/bin/python -m tests.test_put_scan"""
import datetime
from types import SimpleNamespace

from trade import put_scan
from trade.put_scan import PutScan


TODAY = datetime.date(2026, 9, 28)
EXPIRY = "20261009"


class FakeController:
    def __init__(self):
        self.commands = []
        self.req_id = 1
        self.option_portfolio = {}
        self.stock_portfolio = {}
        self.account_value = 100000
        self.screener_names = {}

    def sendIbCommand(self, command, extra={}):
        rid = self.req_id
        self.req_id += 1
        stored = dict(command)
        stored["reqId"] = rid
        stored.update(extra)
        self.commands.append(stored)
        return rid

    def set_screener_name(self, symbol, name):
        if name:
            self.screener_names[symbol] = name


def make_scan(symbols=("AMD",)):
    ctrl = FakeController()
    scan = PutScan(ctrl, list(symbols), today=TODAY)
    scan.earnings_done = True
    scan.start_symbols()
    return scan, ctrl


def feed_details(scan, con_id=1, name="Advanced Micro Devices"):
    req = scan.current["details_req"]
    details = SimpleNamespace(contract=SimpleNamespace(conId=con_id), longName=name)
    scan.handle("contractDetails", {"contractDetails": details}, req)
    scan.handle("contractDetailsEnd", {}, req)


def feed_chain(scan, last=100, iv=0.4, hv=0.3, strikes=None):
    cur = scan.current
    scan.handle("securityDefinitionOptionParameter", {
        "exchange": "SMART", "tradingClass": cur["symbol"], "multiplier": "100",
        "expirations": [EXPIRY, "20261016"],
        "strikes": strikes or [80, 85, 90, 92, 94, 95, 96, 98, 100],
    }, cur["chain_req"])
    scan.handle("securityDefinitionOptionParameterEnd", {}, cur["chain_req"])
    scan.handle("tickPrice", {"tickType": 4, "price": last}, cur["stock_req"])
    scan.handle("tickGeneric", {"tickType": 24, "value": iv}, cur["stock_req"])
    scan.handle("tickGeneric", {"tickType": 23, "value": hv}, cur["stock_req"])
    scan.step(now=cur["since"] + 0.01)


def feed_quotes(scan, bid=1.5, ask=1.6, delta=-0.25, oi=500):
    for req_id in list(scan.current["quote_reqs"]):
        if not isinstance(req_id, int):
            continue
        scan.handle("tickPrice", {"tickType": 1, "price": bid}, req_id)
        scan.handle("tickPrice", {"tickType": 2, "price": ask}, req_id)
        scan.handle("tickOptionComputation", {"tickType": 13, "delta": delta}, req_id)
        scan.handle("tickSize", {"tickType": 27, "size": oi}, req_id)
    scan.step(now=scan.current["since"] + 0.01)


def timeout(scan, seconds):
    scan.step(now=scan.current["since"] + seconds)


def wait_retry(scan):
    assert scan.current["phase"] == "retry_wait"
    timeout(scan, scan.current.get("retry_gap", 1) + 0.01)


def advance_done(scan):
    assert scan.current["phase"] == "done"
    timeout(scan, put_scan.NEXT_GAP + 0.01)


def test_details_timeout_retries_then_succeeds():
    scan, ctrl = make_scan()
    assert scan.current["phase"] == "details"
    timeout(scan, put_scan.DETAILS_TIMEOUT + 0.1)
    wait_retry(scan)
    assert scan.current["phase"] == "details"
    assert scan.current["attempts"]["details"] == 2
    assert "retry" in scan.progress()
    feed_details(scan)
    assert scan.current["phase"] == "chain"
    assert ctrl.screener_names["AMD"] == "Advanced Micro Devices"


def test_details_gives_up_after_retries():
    scan, _ = make_scan()
    for _ in range(put_scan.MAX_ATTEMPTS["details"]):
        if scan.current["phase"] == "retry_wait":
            wait_retry(scan)
        timeout(scan, put_scan.DETAILS_TIMEOUT + 0.1)
    assert scan.current["phase"] == "done"
    assert scan.current["status"] == "no contract"


def test_permanent_contract_error_does_not_retry():
    scan, _ = make_scan()
    scan.handle("reqError", {"errorCode": 200, "errorString": "No security definition"},
                scan.current["details_req"])
    assert scan.current["phase"] == "done"
    assert scan.current["status"] == "no contract"


def test_incomplete_quotes_are_retried():
    scan, ctrl = make_scan()
    feed_details(scan)
    feed_chain(scan)
    assert scan.current["phase"] == "quotes"
    first_ids = [rid for rid in scan.current["quote_reqs"] if isinstance(rid, int)]
    assert first_ids
    for req_id in first_ids:
        scan.handle("tickPrice", {"tickType": 1, "price": 1.4}, req_id)
        scan.handle("tickPrice", {"tickType": 2, "price": 1.5}, req_id)
    timeout(scan, put_scan.QUOTES_TIMEOUT + 0.1)
    wait_retry(scan)
    assert scan.current["phase"] == "quotes"
    assert scan.current["attempts"]["quotes"] == 2
    second_ids = [rid for rid in scan.current["quote_reqs"] if isinstance(rid, int)]
    assert second_ids
    assert set(second_ids).isdisjoint(first_ids)
    feed_quotes(scan)
    assert scan.current["phase"] == "done"
    assert scan.current["status"] == ""
    assert scan.current["quotes"]
    assert all(q.get("delta") is not None for q in scan.current["quotes"])


def test_complete_quotes_are_not_retried():
    scan, ctrl = make_scan()
    feed_details(scan)
    feed_chain(scan)
    quote_sends = [c for c in ctrl.commands if c.get("method_name") == "reqMktData"
                   and getattr(c.get("contract"), "secType", None) == "OPT"]
    feed_quotes(scan)
    assert scan.current["phase"] == "done"
    later = [c for c in ctrl.commands if c.get("method_name") == "reqMktData"
             and getattr(c.get("contract"), "secType", None) == "OPT"]
    assert later == quote_sends


def test_missing_weekly_is_not_retried():
    scan, _ = make_scan()
    feed_details(scan)
    scan.handle("securityDefinitionOptionParameter", {
        "exchange": "SMART", "tradingClass": "AMD", "multiplier": "100",
        "expirations": ["20261016"], "strikes": [90, 95, 100],
    }, scan.current["chain_req"])
    scan.handle("tickPrice", {"tickType": 4, "price": 100}, scan.current["stock_req"])
    scan.handle("tickGeneric", {"tickType": 24, "value": 0.4}, scan.current["stock_req"])
    scan.handle("tickGeneric", {"tickType": 23, "value": 0.3}, scan.current["stock_req"])
    scan.step(now=scan.current["since"] + 0.01)
    assert scan.current["phase"] == "done"
    assert scan.current["status"] == "no weekly"
    advance_done(scan)
    assert scan.state == "done"


def test_pacing_error_retries_quotes():
    scan, _ = make_scan()
    feed_details(scan)
    feed_chain(scan)
    for rid in list(scan.current["quote_reqs"]):
        if isinstance(rid, int):
            scan.handle("reqError", {"errorCode": 101, "errorString": "Max tickers"}, rid)
    scan.step(now=scan.current["since"] + 0.01)
    assert scan.current["phase"] == "retry_wait"
    assert scan.current["retry_gap"] == put_scan.PACE_GAP
    wait_retry(scan)
    assert scan.current["phase"] == "quotes"
    feed_quotes(scan)
    assert scan.current["status"] == ""


def test_second_pass_retries_symbols_still_missing_data():
    scan, _ = make_scan(("AMD", "KO"))
    feed_details(scan)
    feed_chain(scan)
    for _ in range(put_scan.MAX_ATTEMPTS["quotes"]):
        if scan.current["phase"] == "retry_wait":
            wait_retry(scan)
        timeout(scan, put_scan.QUOTES_TIMEOUT + 0.1)
    assert scan.current["symbol"] == "AMD"
    assert scan.current["status"] == "no quotes"
    advance_done(scan)
    assert scan.current["symbol"] == "KO"
    feed_details(scan, con_id=2, name="Coca Cola")
    feed_chain(scan, last=87)
    feed_quotes(scan)
    advance_done(scan)
    assert scan.pass_no == 2
    assert scan.current["symbol"] == "AMD"
    assert scan.current["phase"] == "quotes"
    assert "retry" in scan.progress()
    feed_quotes(scan)
    assert scan.current["status"] == ""
    assert scan.scans["AMD"]["quotes"]


def test_stale_ticks_after_retry_are_ignored():
    scan, _ = make_scan()
    old_req = scan.current["details_req"]
    timeout(scan, put_scan.DETAILS_TIMEOUT + 0.1)
    wait_retry(scan)
    details = SimpleNamespace(contract=SimpleNamespace(conId=99), longName="Old")
    scan.handle("contractDetails", {"contractDetails": details}, old_req)
    scan.handle("contractDetailsEnd", {}, old_req)
    assert scan.current.get("conId") is None
    assert scan.current["phase"] == "details"


def test_progress_mentions_retries_when_finished():
    scan, _ = make_scan()
    timeout(scan, put_scan.DETAILS_TIMEOUT + 0.1)
    wait_retry(scan)
    feed_details(scan)
    feed_chain(scan)
    feed_quotes(scan)
    advance_done(scan)
    assert scan.state == "done"
    assert "retried" in scan.progress()


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
