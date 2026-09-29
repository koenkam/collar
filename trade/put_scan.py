"""Sell puts scan: read Interactive Brokers data one symbol at a time."""
import datetime
import math
import threading
import time

import pytz
from ibapi.contract import Contract

from config import create_c
from .book import breakeven
from .earnings import fetch_calendar
from .logbook import short_put_notional
from .screener import (
    candidate_strikes, day_text, dte, earnings_flag, evaluate_symbol, held_text,
    is_session, rank, target_expiry, weekdays_through,
)

c = create_c()

DETAILS_TIMEOUT = 10
CHAIN_TIMEOUT = 12
VOL_GRACE = 4
QUOTES_TIMEOUT = 10
OI_GRACE = 2

PRICE_TICKS = {4: "last", 68: "last", 9: "close", 75: "close", 1: "bid", 66: "bid", 2: "ask", 67: "ask"}
MODEL_TICKS = (13, 83)
OI_TICKS = (27, 28)
MISSING = 1e100


def usable(value):
    return value is not None and not (isinstance(value, float) and math.isnan(value)) and abs(value) < MISSING


class PutScan:

    def __init__(self, controller, symbols, today=None):
        self.controller = controller
        self.symbols = list(symbols)
        self.today = today or datetime.date.today()
        self.expiry_day = target_expiry(self.today, c.market_holidays, c.screener_min_sessions)
        self.expiry = day_text(self.expiry_day) if self.expiry_day else None
        self.index = -1
        self.current = None
        self.scans = {}
        self.rows = []
        self.state = "running"
        self.started_at = time.time()
        self.finished_at = None
        self.version = 0
        self.closed_market = False
        self.calendar = None
        self.failed_days = []
        self.earnings_done = False
        self.earnings_applied = False
        self.request_ids = {}
        self.used_frozen = False

    @property
    def cfg(self):
        return {
            "fill_fraction": c.screener_fill_fraction,
            "commission": c.option_commission,
            "max_spread": c.screener_max_spread,
            "min_oi": c.screener_min_open_interest,
            "target_delta": c.screener_target_delta,
            "band": c.screener_delta_band,
        }

    # --- lifecycle -----------------------------------------------------------

    def session_is_open(self):
        eastern = datetime.datetime.now(pytz.timezone("US/Eastern"))
        if not is_session(eastern.date(), c.market_holidays):
            return False
        minutes = eastern.hour * 60 + eastern.minute
        return 9 * 60 + 30 <= minutes < 16 * 60

    def restore_data_type(self):
        if self.used_frozen:
            self.controller.sendIbCommand({"method_name": "reqMarketDataType", "marketDataType": 1})
            self.used_frozen = False

    def start(self):
        if not self.session_is_open():
            self.used_frozen = True
            self.closed_market = True
            self.controller.sendIbCommand({"method_name": "reqMarketDataType", "marketDataType": 2})
        if self.expiry_day:
            days = weekdays_through(self.today, self.expiry_day)
            threading.Thread(target=self.load_earnings, args=(days,), daemon=True).start()
        else:
            self.earnings_done = True
        self.next_symbol()

    def load_earnings(self, days):
        calendar, failed = fetch_calendar(days)
        self.calendar, self.failed_days = calendar, failed
        self.earnings_done = True

    def stop(self):
        if self.state != "running":
            return
        self.cancel_current()
        self.restore_data_type()
        self.state = "stopped"
        self.finished_at = time.time()
        self.refresh_rows()

    @property
    def running(self):
        return self.state == "running"

    def progress(self):
        total = len(self.symbols)
        if self.state == "running":
            symbol = self.current["symbol"] if self.current else ""
            return f"{symbol} {min(self.index + 1, total)} of {total}"
        stamp = time.strftime("%H:%M", time.localtime(self.finished_at or self.started_at))
        expiry = self.expiry_day.strftime("%a %-d %b") if self.expiry_day else "no expiry"
        when = "Stopped" if self.state == "stopped" else "Last completed"
        parts = [f"{when} {stamp}, expiry {expiry}"]
        if self.closed_market:
            parts.append("closed market: quotes are from the last session")
        if not self.earnings_done:
            parts.append("earnings still loading")
        elif self.failed_days:
            parts.append("earnings check incomplete")
        return "; ".join(parts)

    def age_minutes(self):
        return (time.time() - (self.finished_at or self.started_at)) / 60

    # --- requests ------------------------------------------------------------

    def send(self, command, kind, key=None):
        req_id = self.controller.sendIbCommand(command, extra={"owner": "screener"})
        self.request_ids[req_id] = (kind, key)
        return req_id

    def cancel(self, req_id):
        self.controller.sendIbCommand({"method_name": "cancelMktData", "reqId": req_id})

    def cancel_current(self):
        scan = self.current
        if not scan:
            return
        if scan.get("stock_req") and not scan.get("stock_cancelled"):
            self.cancel(scan["stock_req"])
            scan["stock_cancelled"] = True
        for req_id in scan.get("quote_reqs", {}):
            if req_id not in scan.setdefault("cancelled", set()):
                self.cancel(req_id)
                scan["cancelled"].add(req_id)

    def next_symbol(self):
        self.index += 1
        if self.index >= len(self.symbols):
            self.current = None
            self.state = "done"
            self.finished_at = time.time()
            self.restore_data_type()
            self.refresh_rows()
            return
        symbol = self.symbols[self.index]
        scan = {
            "symbol": symbol, "phase": "details", "since": time.time(), "quotes": [],
            "quote_reqs": {}, "expiry": self.expiry, "errors": [],
        }
        self.current = scan
        self.scans[symbol] = scan
        self.version += 1
        if not self.expiry:
            self.finish_symbol("no expiry")
            return
        stock = Contract()
        stock.symbol, stock.secType, stock.exchange, stock.currency = symbol, "STK", "SMART", "USD"
        scan["details_req"] = self.send({"method_name": "reqContractDetails", "contract": stock}, "details")

    def finish_symbol(self, status=""):
        scan = self.current
        self.cancel_current()
        scan["status"] = status
        scan["phase"] = "done"
        self.refresh_rows()
        self.next_symbol()

    # --- messages ------------------------------------------------------------

    def handle(self, msg_type, kwargs, req_id):
        scan = self.current
        if scan is None or self.state != "running":
            return
        kind = self.request_ids.get(req_id, (None, None))[0]
        if msg_type == "marketDataType":
            if kwargs.get("marketDataType") in (2, 4):
                self.closed_market = True
                scan["closed_market"] = True
            return
        if msg_type == "reqError":
            code = kwargs.get("errorCode")
            if code in (10167, 10090):
                return
            scan["errors"].append(f"{code} {kwargs.get('errorString', '')}".strip())
            if kind == "details" and req_id == scan.get("details_req"):
                self.finish_symbol("no contract")
            elif kind == "quote" and req_id in scan["quote_reqs"]:
                scan["quote_reqs"][req_id]["failed"] = True
            return

        if kind == "details" and req_id == scan.get("details_req"):
            if msg_type == "contractDetails" and not scan.get("conId"):
                details = kwargs.get("contractDetails")
                scan["conId"] = details.contract.conId
            elif msg_type == "contractDetailsEnd":
                self.start_chain()
        elif kind == "chain" and req_id == scan.get("chain_req"):
            if msg_type == "securityDefinitionOptionParameter":
                if kwargs.get("exchange") == "SMART":
                    trading_class = kwargs.get("tradingClass") or scan["symbol"]
                    preferred = trading_class == scan["symbol"]
                    if preferred or not scan.get("expirations"):
                        scan["trading_class"] = trading_class
                        scan["multiplier"] = kwargs.get("multiplier") or "100"
                        scan["expirations"] = set(kwargs.get("expirations") or [])
                        scan["strikes"] = set(kwargs.get("strikes") or [])
            elif msg_type == "securityDefinitionOptionParameterEnd":
                scan["chain_done"] = True
        elif kind == "stock" and req_id == scan.get("stock_req"):
            if msg_type == "tickPrice":
                field = PRICE_TICKS.get(kwargs.get("tickType"))
                price = kwargs.get("price")
                if field and usable(price) and price > 0:
                    scan[field] = price
            elif msg_type == "tickGeneric":
                value = kwargs.get("value")
                if usable(value) and value > 0:
                    if kwargs.get("tickType") == 24:
                        scan["iv"] = value
                    elif kwargs.get("tickType") == 23:
                        scan["hv"] = value
        elif kind == "quote" and req_id in scan["quote_reqs"]:
            quote = scan["quote_reqs"][req_id]
            tick = kwargs.get("tickType")
            if msg_type == "tickPrice":
                field = PRICE_TICKS.get(tick)
                price = kwargs.get("price")
                if field in ("bid", "ask") and usable(price):
                    quote[field] = price if price > 0 else 0.0
            elif msg_type == "tickSize" and tick in OI_TICKS:
                size = kwargs.get("size")
                if usable(size):
                    quote["oi"] = max(quote.get("oi") or 0, float(size))
            elif msg_type == "tickOptionComputation" and tick in MODEL_TICKS:
                delta = kwargs.get("delta")
                if usable(delta) and -1 <= delta <= 0:
                    quote["delta"] = delta

    # --- phases --------------------------------------------------------------

    def start_chain(self):
        scan = self.current
        if not scan.get("conId"):
            self.finish_symbol("no contract")
            return
        scan["phase"] = "chain"
        scan["since"] = time.time()
        scan["chain_req"] = self.send({
            "method_name": "reqSecDefOptParams",
            "underlyingSymbol": scan["symbol"],
            "futFopExchange": "",
            "underlyingSecType": "STK",
            "underlyingConId": scan["conId"],
        }, "chain")
        stock = Contract()
        stock.symbol, stock.secType, stock.exchange, stock.currency = scan["symbol"], "STK", "SMART", "USD"
        stock.conId = scan["conId"]
        scan["stock_req"] = self.send({
            "method_name": "reqMktData", "contract": stock, "genericTickList": "104,106",
            "snapshot": False, "regulatorySnapshot": False, "mktDataOptions": [],
        }, "stock")

    def spot(self, scan):
        if scan.get("last"):
            return scan["last"]
        if scan.get("bid") and scan.get("ask"):
            return (scan["bid"] + scan["ask"]) / 2
        return scan.get("close")

    def start_quotes(self):
        scan = self.current
        scan["spot"] = self.spot(scan)
        if not scan.get("stock_cancelled"):
            self.cancel(scan["stock_req"])
            scan["stock_cancelled"] = True
        if not scan.get("expirations"):
            self.finish_symbol("no chain")
            return
        if self.expiry not in scan["expirations"]:
            self.finish_symbol("no weekly")
            return
        if not scan["spot"]:
            self.finish_symbol("no price")
            return
        strikes = candidate_strikes(scan.get("strikes") or [], scan["spot"], scan.get("iv"),
                                    dte(self.expiry, self.today), *c.screener_candidate_band,
                                    target=c.screener_target_delta)
        if not strikes:
            self.finish_symbol("no strikes")
            return
        scan["phase"] = "quotes"
        scan["since"] = time.time()
        for strike in strikes:
            option = Contract()
            option.symbol, option.secType, option.exchange, option.currency = scan["symbol"], "OPT", "SMART", "USD"
            option.lastTradeDateOrContractMonth = self.expiry
            option.strike = strike
            option.right = "P"
            option.multiplier = scan.get("multiplier") or "100"
            option.tradingClass = scan.get("trading_class") or scan["symbol"]
            req_id = self.send({
                "method_name": "reqMktData", "contract": option, "genericTickList": "101",
                "snapshot": False, "regulatorySnapshot": False, "mktDataOptions": [],
            }, "quote")
            scan["quote_reqs"][req_id] = {"strike": strike}

    def quotes_complete(self, scan):
        quotes = [q for q in scan["quote_reqs"].values() if not q.get("failed")]
        if not quotes:
            return True
        return all(q.get("bid") is not None and q.get("ask") is not None and q.get("delta") is not None
                   for q in quotes)

    def step(self, now=None):
        if self.state != "running":
            if not self.earnings_applied and self.earnings_done:
                self.refresh_rows()
            return
        now = now or time.time()
        scan = self.current
        if scan is None:
            return
        elapsed = now - scan["since"]
        if scan["phase"] == "details" and elapsed > DETAILS_TIMEOUT:
            self.finish_symbol("no contract")
        elif scan["phase"] == "chain":
            has_vol = scan.get("iv") and scan.get("hv")
            ready = scan.get("chain_done") and self.spot(scan) and (has_vol or elapsed > VOL_GRACE)
            if ready or elapsed > CHAIN_TIMEOUT:
                self.start_quotes()
        elif scan["phase"] == "quotes":
            if self.quotes_complete(scan):
                scan.setdefault("complete_at", now)
                have_oi = all(q.get("oi") is not None for q in scan["quote_reqs"].values() if not q.get("failed"))
                if have_oi or now - scan["complete_at"] > OI_GRACE:
                    self.collect_quotes()
            elif elapsed > QUOTES_TIMEOUT:
                self.collect_quotes()

    def collect_quotes(self):
        scan = self.current
        scan["quotes"] = [
            {k: q.get(k) for k in ("strike", "bid", "ask", "delta", "oi")}
            for q in scan["quote_reqs"].values() if not q.get("failed")
        ]
        self.finish_symbol("")

    # --- results -------------------------------------------------------------

    def refresh_rows(self):
        ctrl = self.controller
        account = getattr(ctrl, "account_value", None)
        assign = short_put_notional(ctrl.option_portfolio)
        available = 0.7 * account - assign if account is not None else None
        options = list(ctrl.option_portfolio.values())
        stocks = list(ctrl.stock_portfolio.values())
        rows = []
        for symbol in self.symbols:
            scan = self.scans.get(symbol)
            if scan is None or scan["phase"] != "done":
                continue
            row = evaluate_symbol(scan, self.cfg)
            row["dte"] = dte(self.expiry, self.today) if self.expiry else None
            row["held"] = held_text(symbol, options, stocks, lambda p: breakeven({
                "n": p.n, "avgCost": p.avgCost, "credit": getattr(p, "credit", 0.0)}))
            row["earnings"] = None
            if self.earnings_done and self.expiry_day:
                row["earnings"] = earnings_flag(symbol, self.expiry_day, self.calendar or {}, self.failed_days)
            pick = row["pick"]
            if pick and available is not None:
                row["fits"] = max(0, int(available // (pick["strike"] * 100)))
            else:
                row["fits"] = None
            row["errors"] = scan.get("errors", [])
            rows.append(row)
        self.rows = rank(rows)
        if self.earnings_done:
            self.earnings_applied = True
        self.version += 1
