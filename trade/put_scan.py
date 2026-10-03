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
RETRY_GAP = 0.4
PACE_GAP = 2.0
NEXT_GAP = 0.35
MAX_PASSES = 2
MAX_ATTEMPTS = {"details": 3, "chain": 3, "vol": 2, "quotes": 3}

PRICE_TICKS = {4: "last", 68: "last", 9: "close", 75: "close", 1: "bid", 66: "bid", 2: "ask", 67: "ask"}
MODEL_TICKS = (10, 11, 12, 13, 80, 81, 82, 83)
OI_TICKS = (27, 28)
MISSING = 1e100
IGNORE_CODES = {10167, 10090}
PACE_CODES = {100, 101}
TRANSIENT_CODES = {100, 101, 162, 366, 1100, 2103, 2105, 2107, 2110, 10189, 10197}
PERMANENT_CODES = {200, 321, 322}
RETRYABLE_STATUS = {"no contract", "no chain", "no price", "no strikes", "no quotes", "no delta"}


def usable(value):
    return value is not None and not (isinstance(value, float) and math.isnan(value)) and abs(value) < MISSING


def quote_ready(quote):
    return quote.get("bid") is not None and quote.get("ask") is not None and quote.get("delta") is not None


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
        self.pending = []
        self.pass_no = 1
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
        self.retried_symbols = set()

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
        self.start_symbols()

    def start_symbols(self):
        self.pending = list(self.symbols)
        self.pass_no = 1
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
            scan = self.current
            symbol = scan["symbol"] if scan else ""
            pos = self.symbols.index(symbol) + 1 if symbol in self.symbols else min(self.index + 1, total)
            suffix = " retry" if self._retrying(scan) else ""
            return f"{symbol} {pos} of {total}{suffix}"
        stamp = time.strftime("%H:%M", time.localtime(self.finished_at or self.started_at))
        expiry = self.expiry_day.strftime("%a %-d %b") if self.expiry_day else "no expiry"
        when = "Stopped" if self.state == "stopped" else "Last completed"
        parts = [f"{when} {stamp}, expiry {expiry}"]
        if self.closed_market:
            parts.append("closed market: quotes are from the last session")
        if self.retried_symbols:
            parts.append(f"retried {len(self.retried_symbols)} with missing data")
        if not self.earnings_done:
            parts.append("earnings still loading")
        elif self.failed_days:
            parts.append("earnings check incomplete")
        return "; ".join(parts)

    def _retrying(self, scan):
        if self.pass_no > 1:
            return True
        if not scan:
            return False
        attempts = scan.get("attempts") or {}
        return any(n > 1 for n in attempts.values()) or scan.get("phase") == "retry_wait"

    def age_minutes(self):
        return (time.time() - (self.finished_at or self.started_at)) / 60

    # --- requests ------------------------------------------------------------

    def send(self, command, kind, key=None):
        req_id = self.controller.sendIbCommand(command, extra={"owner": "screener"})
        gen = self.current.get("gen", 1) if self.current else 0
        self.request_ids[req_id] = (kind, gen)
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
        for req_id in list(scan.get("quote_reqs", {})):
            if not isinstance(req_id, int):
                continue
            if req_id not in scan.setdefault("cancelled", set()):
                self.cancel(req_id)
                scan["cancelled"].add(req_id)

    def begin_phase(self, phase):
        scan = self.current
        scan["phase"] = phase
        scan["since"] = time.time()
        scan.setdefault("attempts", {})
        scan["attempts"][phase] = scan["attempts"].get(phase, 0) + 1
        scan.pop("complete_at", None)

    def can_retry(self, phase):
        scan = self.current
        if not scan or self.state != "running":
            return False
        used = (scan.get("attempts") or {}).get(phase, 0)
        return used < MAX_ATTEMPTS.get(phase, 1)

    def retry_current(self, phase, gap=None):
        scan = self.current
        if not scan or self.state != "running":
            return
        self.cancel_current()
        scan["gen"] = scan.get("gen", 1) + 1
        scan["resume"] = phase
        scan["phase"] = "retry_wait"
        scan["since"] = time.time()
        scan["retry_gap"] = RETRY_GAP if gap is None else gap
        scan.pop("complete_at", None)
        self.retried_symbols.add(scan["symbol"])
        self.version += 1

    def resume(self):
        scan = self.current
        phase = scan.get("resume") or "details"
        if phase == "details":
            self.request_details()
        elif phase == "chain":
            self.start_chain()
        elif phase == "vol":
            self.request_stock(reset=False)
            scan["phase"] = "chain"
            scan["since"] = time.time()
            scan.setdefault("attempts", {})
            scan["attempts"]["vol"] = scan["attempts"].get("vol", 0) + 1
        else:
            self.start_quotes()

    def next_symbol(self):
        if not self.pending:
            retry = [symbol for symbol in self.symbols if self.needs_another_pass(symbol)]
            if retry and self.pass_no < MAX_PASSES:
                self.pass_no += 1
                self.pending = retry
                for symbol in retry:
                    self.retried_symbols.add(symbol)
            else:
                self.current = None
                self.state = "done"
                self.finished_at = time.time()
                self.restore_data_type()
                self.refresh_rows()
                return
        symbol = self.pending.pop(0)
        self.index = self.symbols.index(symbol) if symbol in self.symbols else self.index + 1
        reuse = symbol in self.scans and self.scans[symbol].get("phase") == "done"
        if reuse:
            self.reopen_symbol(symbol)
        else:
            self.open_symbol(symbol)

    def open_symbol(self, symbol):
        scan = {
            "symbol": symbol, "phase": "details", "since": time.time(), "quotes": [],
            "quote_reqs": {}, "expiry": self.expiry, "errors": [], "attempts": {}, "gen": 1,
        }
        self.current = scan
        self.scans[symbol] = scan
        self.version += 1
        if not self.expiry:
            self.finish_symbol("no expiry")
            return
        self.request_details()

    def reopen_symbol(self, symbol):
        scan = self.scans[symbol]
        scan["status"] = ""
        scan["attempts"] = {}
        scan["gen"] = scan.get("gen", 1) + 1
        scan["errors"] = list(scan.get("errors") or [])
        scan["quote_reqs"] = {q["strike"]: dict(q) for q in (scan.get("quotes") or []) if q.get("strike") is not None}
        scan["cancelled"] = set()
        scan["stock_cancelled"] = True
        self.current = scan
        self.version += 1
        if not scan.get("conId"):
            self.request_details()
        elif not scan.get("expirations"):
            self.start_chain()
        elif self.expiry not in scan["expirations"]:
            self.finish_symbol("no weekly")
        elif not self.spot(scan):
            self.start_chain()
        else:
            self.start_quotes()

    def request_details(self):
        scan = self.current
        self.begin_phase("details")
        stock = Contract()
        stock.symbol, stock.secType, stock.exchange, stock.currency = scan["symbol"], "STK", "SMART", "USD"
        scan["details_req"] = self.send({"method_name": "reqContractDetails", "contract": stock}, "details")

    def finish_symbol(self, status=""):
        scan = self.current
        self.cancel_current()
        scan["status"] = status
        scan["phase"] = "done"
        scan["since"] = time.time()
        self.refresh_rows()

    def needs_another_pass(self, symbol):
        scan = self.scans.get(symbol)
        if not scan or scan.get("phase") != "done":
            return False
        if scan.get("status") in RETRYABLE_STATUS:
            return True
        quotes = scan.get("quotes") or []
        return bool(quotes) and not any(quote_ready(q) for q in quotes)

    # --- messages ------------------------------------------------------------

    def handle(self, msg_type, kwargs, req_id):
        scan = self.current
        if scan is None or self.state != "running":
            return
        kind, gen = self.request_ids.get(req_id, (None, None))
        if gen not in (None, scan.get("gen")):
            return
        if msg_type == "marketDataType":
            if kwargs.get("marketDataType") in (2, 4):
                self.closed_market = True
                scan["closed_market"] = True
            return
        if msg_type == "reqError":
            self.handle_error(scan, kind, req_id, kwargs)
            return
        if scan.get("phase") == "retry_wait":
            self.handle_data(scan, kind, req_id, msg_type, kwargs)
            return
        if kind == "details" and req_id == scan.get("details_req"):
            if msg_type == "contractDetails" and not scan.get("conId"):
                details = kwargs.get("contractDetails")
                scan["conId"] = details.contract.conId
                self.controller.set_screener_name(
                    scan["symbol"], getattr(details, "longName", None)
                )
            elif msg_type == "contractDetailsEnd":
                if scan.get("conId"):
                    self.start_chain()
                elif self.can_retry("details"):
                    self.retry_current("details")
                else:
                    self.finish_symbol("no contract")
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
            self.handle_stock(scan, msg_type, kwargs)
        elif kind == "quote" and req_id in scan.get("quote_reqs", {}):
            self.handle_quote(scan["quote_reqs"][req_id], msg_type, kwargs)

    def handle_data(self, scan, kind, req_id, msg_type, kwargs):
        """Keep ticks that arrive while a retry is waiting, but do not change phase."""
        if kind == "details" and req_id == scan.get("details_req") and msg_type == "contractDetails":
            if not scan.get("conId"):
                details = kwargs.get("contractDetails")
                scan["conId"] = details.contract.conId
                self.controller.set_screener_name(
                    scan["symbol"], getattr(details, "longName", None)
                )
        elif kind == "stock" and req_id == scan.get("stock_req"):
            self.handle_stock(scan, msg_type, kwargs)
        elif kind == "quote" and req_id in scan.get("quote_reqs", {}):
            self.handle_quote(scan["quote_reqs"][req_id], msg_type, kwargs)

    def handle_stock(self, scan, msg_type, kwargs):
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

    def handle_quote(self, quote, msg_type, kwargs):
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

    def handle_error(self, scan, kind, req_id, kwargs):
        code = kwargs.get("errorCode")
        if code in IGNORE_CODES:
            return
        scan.setdefault("errors", []).append(f"{code} {kwargs.get('errorString', '')}".strip())
        gap = PACE_GAP if code in PACE_CODES else RETRY_GAP
        if kind == "details" and req_id == scan.get("details_req"):
            if code in PERMANENT_CODES or not self.can_retry("details"):
                self.finish_symbol("no contract")
            else:
                self.retry_current("details", gap=gap)
        elif kind == "chain" and req_id == scan.get("chain_req"):
            if code not in PERMANENT_CODES and self.can_retry("chain"):
                self.retry_current("chain", gap=gap)
        elif kind == "stock" and req_id == scan.get("stock_req"):
            if code in TRANSIENT_CODES and self.can_retry("chain"):
                self.retry_current("chain", gap=gap)
        elif kind == "quote" and req_id in scan.get("quote_reqs", {}):
            scan["quote_reqs"][req_id]["failed"] = True
            if code in TRANSIENT_CODES:
                scan["quote_reqs"][req_id]["pace"] = True

    # --- phases --------------------------------------------------------------

    def start_chain(self):
        scan = self.current
        if not scan.get("conId"):
            if self.can_retry("details"):
                self.retry_current("details")
            else:
                self.finish_symbol("no contract")
            return
        self.begin_phase("chain")
        scan["chain_done"] = False
        scan["stock_cancelled"] = False
        scan["chain_req"] = self.send({
            "method_name": "reqSecDefOptParams",
            "underlyingSymbol": scan["symbol"],
            "futFopExchange": "",
            "underlyingSecType": "STK",
            "underlyingConId": scan["conId"],
        }, "chain")
        self.request_stock(reset=False)

    def request_stock(self, reset=True):
        scan = self.current
        if scan.get("stock_req") and not scan.get("stock_cancelled"):
            self.cancel(scan["stock_req"])
            scan["stock_cancelled"] = True
        stock = Contract()
        stock.symbol, stock.secType, stock.exchange, stock.currency = scan["symbol"], "STK", "SMART", "USD"
        stock.conId = scan["conId"]
        scan["stock_cancelled"] = False
        if reset:
            scan["gen"] = scan.get("gen", 1) + 1
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
        if scan.get("stock_req") and not scan.get("stock_cancelled"):
            self.cancel(scan["stock_req"])
            scan["stock_cancelled"] = True
        if not scan.get("expirations"):
            if self.can_retry("chain"):
                self.retry_current("chain")
            else:
                self.finish_symbol("no chain")
            return
        if self.expiry not in scan["expirations"]:
            self.finish_symbol("no weekly")
            return
        if not scan["spot"]:
            if self.can_retry("chain"):
                self.retry_current("chain")
            else:
                self.finish_symbol("no price")
            return
        strikes = candidate_strikes(scan.get("strikes") or [], scan["spot"], scan.get("iv"),
                                    dte(self.expiry, self.today), *c.screener_candidate_band,
                                    target=c.screener_target_delta)
        if not strikes:
            if not scan.get("iv") and self.can_retry("vol"):
                self.retry_current("vol")
                return
            self.finish_symbol("no strikes")
            return
        prior = {}
        for quote in (scan.get("quote_reqs") or {}).values():
            prior[quote["strike"]] = quote
        for quote in scan.get("quotes") or []:
            prior.setdefault(quote["strike"], quote)
        for req_id in list(scan.get("quote_reqs") or {}):
            if isinstance(req_id, int) and req_id not in scan.setdefault("cancelled", set()):
                self.cancel(req_id)
                scan["cancelled"].add(req_id)
        scan["quote_reqs"] = {}
        scan["cancelled"] = set()
        self.begin_phase("quotes")
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
            old = prior.get(strike) or {}
            scan["quote_reqs"][req_id] = {
                "strike": strike,
                "bid": old.get("bid"),
                "ask": old.get("ask"),
                "delta": old.get("delta"),
                "oi": old.get("oi"),
            }

    def live_quotes(self, scan):
        return [q for q in scan.get("quote_reqs", {}).values() if not q.get("failed")]

    def quotes_complete(self, scan):
        quotes = self.live_quotes(scan)
        return bool(quotes) and all(quote_ready(q) for q in quotes)

    def quotes_missing(self, scan):
        quotes = self.live_quotes(scan)
        if not quotes:
            return True
        return any(not quote_ready(q) for q in quotes)

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
        if scan["phase"] == "done":
            if elapsed >= NEXT_GAP:
                self.next_symbol()
            return
        if scan["phase"] == "retry_wait":
            if elapsed >= scan.get("retry_gap", RETRY_GAP):
                self.resume()
            return
        if scan["phase"] == "details" and elapsed > DETAILS_TIMEOUT:
            if self.can_retry("details"):
                self.retry_current("details")
            else:
                self.finish_symbol("no contract")
        elif scan["phase"] == "chain":
            has_vol = scan.get("iv") and scan.get("hv")
            has_spot = bool(self.spot(scan))
            has_chain = bool(scan.get("expirations"))
            ready = has_chain and has_spot and (has_vol or elapsed > VOL_GRACE)
            if ready:
                if not has_vol and elapsed > VOL_GRACE and self.can_retry("vol"):
                    self.retry_current("vol")
                    return
                self.start_quotes()
            elif elapsed > CHAIN_TIMEOUT:
                if (not has_chain or not has_spot) and self.can_retry("chain"):
                    self.retry_current("chain")
                else:
                    self.start_quotes()
        elif scan["phase"] == "quotes":
            live = self.live_quotes(scan)
            paced = any(q.get("pace") for q in scan.get("quote_reqs", {}).values())
            if not live:
                if self.can_retry("quotes"):
                    self.retry_current("quotes", gap=PACE_GAP if paced else RETRY_GAP)
                else:
                    self.finish_symbol("no quotes")
            elif self.quotes_complete(scan):
                scan.setdefault("complete_at", now)
                have_oi = all(q.get("oi") is not None for q in live)
                if have_oi or now - scan["complete_at"] > OI_GRACE:
                    self.collect_quotes()
            elif elapsed > QUOTES_TIMEOUT:
                if self.can_retry("quotes"):
                    self.retry_current("quotes", gap=PACE_GAP if paced else RETRY_GAP)
                else:
                    self.collect_quotes()

    def collect_quotes(self):
        scan = self.current
        quotes = [
            {k: q.get(k) for k in ("strike", "bid", "ask", "delta", "oi")}
            for q in self.live_quotes(scan)
        ]
        scan["quotes"] = quotes
        if not quotes:
            self.finish_symbol("no quotes")
            return
        if not any(quote_ready(q) for q in quotes):
            self.finish_symbol("no delta" if any(q.get("bid") is not None for q in quotes) else "no quotes")
            return
        self.finish_symbol("")

    # --- results -------------------------------------------------------------

    def refresh_rows(self):
        ctrl = self.controller
        account = getattr(ctrl, "account_value", None)
        collateral = short_put_notional(ctrl.option_portfolio, c.cash_settled_symbols)
        available = c.max_collateral_fraction * account - collateral if account is not None else None
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
