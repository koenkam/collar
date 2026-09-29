from collections import OrderedDict
from ibapi.contract import Contract
from ibapi.order import Order
import re
import time
import datetime
from config import create_c
#from experiments import option
c = create_c()
from .book import as_count, describe, option_id, reconcile, stock_id
from .firestore import FirestoreDB, log_sequence, sort_log
from .screener import normalize_watchlist, watchlist_from_store
from .sheetstofirestore import sheets_to_firestore, update_collar_account_value
from util import Stub
import threading

UNSET_COMMISSION = 1e300

class Controller:

    def __init__(self, gui_to_ib, ib_to_gui):
        print('Running sheets_to_firestore()...')
        sheets_to_firestore()
        print('Finished sheets_to_firestore()')
        self.ib_to_gui = ib_to_gui
        self.gui_to_ib = gui_to_ib
        print('Initializing FirestoreDB in Controller...')
        self.firestore = FirestoreDB(self)
        self.summary = self.firestore.get_summary()
        self.log_trades = self.firestore.get_log()
        self.book_options, self.book_stocks = self.firestore.load_book()
        self.processed = self.firestore.load_processed()
        self.review = self.firestore.load_review()
        self.book_initialized = self.firestore.is_initialized()
        symbols, persist = watchlist_from_store(
            self.firestore.load_screener_symbols(), c.screener_symbols
        )
        self.screener_symbols = symbols
        if persist:
            self.firestore.save_screener_symbols(symbols)
        print('Initialized FirestoreDB in Controller')
        self.broker = {}
        self.fills = {}
        self.commissions = {}
        self.fill_symbols = {}
        self.symbol_activity = {}
        self.underlying = {}
        self.subscribed = set()
        self.positions_ready = False
        self.executions_ready = False
        self.reconcile_due = None
        self.book_paused = False
        self.status_message = ""
        self.put_scan = None
        self.display_batching = False
        self.display_pending = False
        self.reqId = 1
        self.orderId = 1  # Separate counter for order IDs
        self.requests = OrderedDict()  # Maintain order of requests
        self.orders = OrderedDict()
        self.conId = None
        self.stats = {}
        self.option_portfolio = {}
        self.option_portfolio_gui_map = {}
        self.stock_portfolio = {}
        self.stock_portfolio_gui_map = {}
        self.mainframe = None  # Will be set by MainFrame
        self.displayer = None
        self.account_value = None
        self.account_currency = "USD"
        self.account_id = ""
        self.account_summary_req_id = None
        self.last_account_summary_request = 0
        self.account_value_synced_to_sheet = False
        self.net_liquidation_by_currency = {}
    
    def get_connection_status(self):
        if not hasattr(self, 'last_successful_connection'):
            self.check_if_connection_alive()
            return "Unknown"
        
        time_since_last = time.time() - self.last_successful_connection        
        if time_since_last > 5:
            self.check_if_connection_alive()
        if time_since_last < 10:
            return "✅ Connected" 
        elif time_since_last < 30:
            return "⚠️ Warning"
        else:
            return "❌ Disconnected"

    def start(self):
        self.reqPositions()
        self.reqOpenOrders()
        self.reqAccountSummary()
        self.reqExecutions()


    def get_instrument_id_from_contract(self, contract):
        
        finstrument_key_list =  [
            contract.lastTradeDateOrContractMonth if contract.secType == 'OPT' else 'STK',
            contract.symbol
        ]
        if contract.secType == 'OPT':
            finstrument_key_list += [
                contract.strike,
                contract.right
            ]
        instrument_key = "_".join(map(str, finstrument_key_list))
        return instrument_key
    
    def get_option_instrument_id_from_grid_row(self, row):
        portfolio_gui_map = getattr(self, 'option_portfolio_gui_map', {})
        for instr_id, grid_row in portfolio_gui_map.items():
            if grid_row == row:
                return instr_id
        return None

    def get_stock_instrument_id_from_grid_row(self, row):
        stock_gui_map = getattr(self, 'stock_portfolio_gui_map', {})
        for instr_id, grid_row in stock_gui_map.items():
            if grid_row == row:
                return instr_id
        return None

    def get_instrument_id_from_grid_row(self, row):
        # Deprecated: Use specific methods instead
        res = self.get_option_instrument_id_from_grid_row(row)
        if res: return res
        return self.get_stock_instrument_id_from_grid_row(row)

    def get_instrument_id_from_request(self, reqId):
        request = self.requests.get(reqId)
        if request is None:
            return ""
        contract = request.get("contract", None)
        if contract is None:
            return ""
        return self.get_instrument_id_from_contract(contract)

    def check_if_connection_alive(self):
        """Check if the IB connection is still alive by requesting current time"""
        try:
            command = {
                "method_name": "reqCurrentTime"
            }
            self.sendIbCommand(command)            
            self.last_connection_check = time.time()
            
            
        except Exception as e:
            print(f"Error checking connection: {e}")
            return False

    def handle_currentTime(self):
        self.last_successful_connection = time.time()
        if self.account_value is None:
            now = time.time()
            if now - self.last_account_summary_request > 15:
                self.reqAccountSummary()

    def handle_managedAccounts(self):
        accounts_list = self.incoming_command["kwargs"].get("accountsList", "")
        accounts = [a.strip() for a in accounts_list.split(",") if a.strip()]
        if accounts and not self.account_id:
            self.account_id = accounts[0]

    def handle_accountSummary(self):
        tag = self.incoming_command["kwargs"].get("tag")
        value = self.incoming_command["kwargs"].get("value")
        currency = (self.incoming_command["kwargs"].get("currency") or "").strip().upper() or "USD"
        account = self.incoming_command["kwargs"].get("account", "")
        if account:
            self.account_id = account
        print(f"Account summary {tag}={value} {currency} {account}")
        if tag != "NetLiquidation" or value in (None, ""):
            return
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return
        self.net_liquidation_by_currency[currency] = amount
        self.account_value, self.account_currency = self._select_net_liquidation()
        if self.mainframe:
            self.mainframe.update_account_display()

    def handle_accountSummaryEnd(self):
        self.account_value, self.account_currency = self._select_net_liquidation()
        if self.mainframe:
            self.mainframe.update_account_display()
        if self.account_value is None or self.account_value_synced_to_sheet:
            return
        self.account_value_synced_to_sheet = True
        print(
            f"Using NetLiquidation {self.account_value} {self.account_currency} "
            f"from {self.net_liquidation_by_currency}"
        )
        threading.Thread(
            target=update_collar_account_value,
            args=(self.account_value,),
            daemon=True
        ).start()

    def _select_net_liquidation(self):
        values = self.net_liquidation_by_currency
        if not values:
            return None, "USD"
        for currency in ("BASE", "USD"):
            if currency in values:
                return values[currency], currency
        currency, amount = max(values.items(), key=lambda item: abs(item[1]))
        return amount, currency

    def reqAccountSummary(self):
        if self.account_summary_req_id is not None:
            self.sendIbCommand({
                "method_name": "cancelAccountSummary",
                "reqId": self.account_summary_req_id
            })
        self.last_account_summary_request = time.time()
        self.account_summary_req_id = self.reqId
        command = {
            "method_name": "reqAccountSummary",
            "groupName": "All",
            "tags": "NetLiquidation"
        }
        self.sendIbCommand(command)
    
    def process_incoming_data(self, limit=2000):
        self.display_batching = True
        try:
            self._process_incoming_data(limit)
        finally:
            self.display_batching = False
        if self.display_pending and self.displayer:
            self.display_pending = False
            self.displayer.updatePortfolioDisplay()

    def _process_incoming_data(self, limit):
        handled = 0
        while not self.ib_to_gui.empty() and handled < limit:
            handled += 1

            self.incoming_command = self.ib_to_gui.get()

            if self.incoming_command["type"] in ['command_result', 'error']:
                continue
            if self.incoming_command["type"] in [
                'position', 'positionEnd', 'openOrder', 'openOrderEnd',
                'currentTime', 'accountSummary', 'accountSummaryEnd', 'managedAccounts',
                'execDetails', 'execDetailsEnd', 'commissionReport'
            ]:
                handler = getattr(self, f"handle_{self.incoming_command['type']}")
                handler()
                continue
            
            # Check for both reqId and orderId
            incoming_request_id = None
            try:
                if "reqId" in self.incoming_command["kwargs"]:
                    incoming_request_id = int(self.incoming_command["kwargs"]["reqId"])
                elif "orderId" in self.incoming_command["kwargs"]:
                    incoming_request_id = int(self.incoming_command["kwargs"]["orderId"])
            except (KeyError, ValueError, TypeError):
                incoming_request_id = None
                
            if incoming_request_id in self.requests:
                command = self.requests[incoming_request_id]
                command_type = self.incoming_command["type"]

                if command.get("owner") == "screener":
                    if self.put_scan is not None:
                        self.put_scan.handle(command_type, self.incoming_command["kwargs"], incoming_request_id)
                    continue
                if command_type == "reqError":
                    continue
                if hasattr(self, f"handle_{command_type}"):
                    handler = getattr(self, f"handle_{command_type}")
                    handler()
                else:
                    ignore_list = [
                        "tickPrice",
                        "tickSize", 
                        "tickGeneric",
                        "tickString",
                        "securityDefinitionOptionParameterEnd"
                    ]
                    if command_type in ignore_list:
                        continue
                    print(f"No handler for method: {command_type}")

    def sendIbCommand(self, command, extra={}):
        newcommand = command.copy()        
        if "reqId" not in newcommand:
            newcommand["reqId"] = self.reqId
        
        self.gui_to_ib.put(newcommand.copy())
        for k, v in extra.items():
            newcommand[k] = v
        self.requests[self.reqId] = newcommand
        self.reqId += 1  
        self.do_stats(command)
        return newcommand["reqId"]


    def sendIbOrder(self, command, extra={}):
        newcommand = command.copy()     
        if "orderId" not in newcommand:
            newcommand["orderId"] = self.orderId
        self.gui_to_ib.put(newcommand.copy())
        for k, v in extra.items():
            newcommand[k] = v
        self.orders[self.orderId] = newcommand
        self.do_stats(command)

    def do_stats(self, command):
        if self.stats.get(command["method_name"]) is None:
            self.stats[command["method_name"]] = 0
        self.stats[command["method_name"]] += 1

    def cancelStreams(self):
        new_requests = OrderedDict()
        cancel_commands = []
        for reqId, command in self.requests.items():
            if command["method_name"] == "reqMktData":
                cancel_command = {
                    "method_name": "cancelMktData",
                    "reqId": reqId
                }
                cancel_commands.append(cancel_command)
            else:
                new_requests[reqId] = command
        self.requests = new_requests
        for cancel_command in cancel_commands:
            self.sendIbCommand(cancel_command)

  

    def reqPositions(self):
        command = {
            "method_name": "reqPositions"
        }
        self.sendIbCommand(command)

    def reqOpenOrders(self):
        command = {
            "method_name": "reqOpenOrders"
        }
        self.sendIbCommand(command)

    def reqExecutions(self):
        self.sendIbCommand({"method_name": "reqExecutions"})

    def find_option_id_for_stocktick(self, symbol):
        for instrument_id, position in self.option_portfolio.items():
            contract = position.contract
            if contract.secType == 'OPT' and contract.symbol == symbol:
                return instrument_id
        return None

    def handle_tickPrice(self):        
        instrument_id = self.get_instrument_id_from_request(self.incoming_command["kwargs"]["reqId"])        
        request = self.requests.get(self.incoming_command["kwargs"]["reqId"])
        if request is None:
            return
        contract = request.get("contract", None)
        if contract is None:
            return
        
        price = self.incoming_command["kwargs"].get("price")
        if price is None or price <= 0:
            return
            
        if contract.secType in ("STK", "IND"):
            self.handle_tickPrice_stock(instrument_id, contract, price)
        elif contract.secType == "OPT":
            self.handle_tickPrice_option(instrument_id, contract, price)

    def handle_tickPrice_stock(self, instrument_id, contract, price):
        self.underlying[contract.symbol] = price
        # Update underlying price for ALL matching options
        updates_made = False
        for opt_id, position in self.option_portfolio.items():
            if position.contract.secType == 'OPT' and position.contract.symbol == contract.symbol:
                if not hasattr(position, 'underlyingPrice'):
                    position.underlyingPrice = None
                position.underlyingPrice = price
                position.dirty = True
                updates_made = True
        
        if updates_made:
            self.displayer.updatePortfolioDisplay()
        
        # Update stock position if it exists
        if instrument_id in self.stock_portfolio:
            if not hasattr(self.stock_portfolio[instrument_id], 'lastPrice'):
                self.stock_portfolio[instrument_id].lastPrice = None
            self.stock_portfolio[instrument_id].lastPrice = price
            self.stock_portfolio[instrument_id].dirty = True
            self.displayer.updatePortfolioDisplay()
            

    def handle_tickPrice_option(self, instrument_id, contract, price):
        if self.incoming_command["kwargs"].get("tickType") in (1, 2, 4): 
            if instrument_id in self.option_portfolio:
                if not hasattr(self.option_portfolio[instrument_id], 'lastPrice'):
                    self.option_portfolio[instrument_id].lastPrice = None
                self.option_portfolio[instrument_id].lastPrice = price
                self.option_portfolio[instrument_id].dirty = True
                self.displayer.updatePortfolioDisplay()

    def handle_tickOptionComputation(self):
        reqId = self.incoming_command["kwargs"]["reqId"]
        instrument_id = self.get_instrument_id_from_request(reqId)
        request = self.requests.get(reqId)
        if request is None:
            return
        contract = request.get("contract", None)
        if contract is None or instrument_id not in self.option_portfolio:
            return
        self.option_portfolio[instrument_id].impliedVol = self.incoming_command["kwargs"].get("impliedVol", None)
        self.option_portfolio[instrument_id].delta = self.incoming_command["kwargs"].get("delta", None)
        self.option_portfolio[instrument_id].gamma = self.incoming_command["kwargs"].get("gamma", None)
        self.option_portfolio[instrument_id].theta = self.incoming_command["kwargs"].get("theta", None)
        self.option_portfolio[instrument_id].vega = self.incoming_command["kwargs"].get("vega", None)
        self.option_portfolio[instrument_id].optPrice = self.incoming_command["kwargs"].get("optPrice", None)
        self.option_portfolio[instrument_id].dirty = True
        self.displayer.updatePortfolioDisplay()

    def handle_position(self):
        """Record the broker position, including a count of zero."""
        kwargs = self.incoming_command["kwargs"]
        account = kwargs.get("account", "")
        contract = kwargs.get("contract")
        if contract is None or contract.secType not in ("OPT", "STK"):
            return
        n = as_count(kwargs.get("position", 0.0))
        avg_cost = kwargs.get("avgCost", 0.0)
        instrument_id = self.get_instrument_id_from_contract(contract)
        if n == 0:
            self.broker.pop(instrument_id, None)
        else:
            self.broker[instrument_id] = self.broker_entry(contract, n, avg_cost)
        if self.positions_ready:
            self.touch(contract.symbol)
        if contract.secType == "OPT":
            self.update_option_stub(instrument_id, contract, n, avg_cost, account)
        else:
            self.update_stock_stub(instrument_id, contract, n, avg_cost, account)
        self.displayer.updatePortfolioDisplay()

    def broker_entry(self, contract, n, avg_cost):
        entry = {
            "sec_type": contract.secType,
            "symbol": contract.symbol,
            "n": n,
            "avg_cost": avg_cost,
            "conId": contract.conId,
            "multiplier": self.contract_multiplier(contract),
        }
        if contract.secType == "OPT":
            entry.update({
                "strike": float(contract.strike),
                "right": contract.right,
                "expiry": contract.lastTradeDateOrContractMonth,
            })
        return entry

    def contract_multiplier(self, contract):
        try:
            value = float(contract.multiplier or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
        return 100.0 if contract.secType == "OPT" else 1.0

    def update_option_stub(self, instrument_id, contract, n, avg_cost, account):
        stub = self.option_portfolio.get(instrument_id)
        if n == 0:
            if stub is not None and not hasattr(stub, "order"):
                self.remove_option_stub(instrument_id)
            elif stub is not None:
                stub.n = 0
                stub.dirty = True
            return
        if stub is None:
            stub = Stub(account=account, n=n, avgCost=avg_cost, contract=contract,
                        premium=None, startdate="", dirty=True)
            doc = self.book_options.get(instrument_id) or {}
            stub.lastPrice = doc.get("lastPrice", 0)
            stub.underlyingPrice = doc.get("underlyingPrice", 0)
            self.option_portfolio[instrument_id] = stub
        stub.account = account
        stub.n = n
        stub.avgCost = avg_cost
        stub.contract = contract
        stub.dirty = True
        self.apply_book_to_option(instrument_id)
        self.subscribe_option(instrument_id, contract)

    def update_stock_stub(self, instrument_id, contract, n, avg_cost, account):
        if n == 0:
            self.remove_stock_stub(instrument_id)
            return
        stub = self.stock_portfolio.get(instrument_id)
        if stub is None:
            doc = self.book_stocks.get(instrument_id) or {}
            stub = Stub(account=account, n=n, avgCost=avg_cost, contract=contract, dirty=True)
            stub.lastPrice = doc.get("lastPrice", 0)
            self.stock_portfolio[instrument_id] = stub
        stub.account = account
        stub.n = n
        stub.brokerAvgCost = avg_cost
        stub.contract = contract
        stub.dirty = True
        self.apply_book_to_stock(instrument_id)
        self.subscribe_stock(contract)

    def remove_option_stub(self, instrument_id):
        self.option_portfolio.pop(instrument_id, None)
        self.option_portfolio_gui_map.clear()

    def remove_stock_stub(self, instrument_id):
        self.stock_portfolio.pop(instrument_id, None)
        self.stock_portfolio_gui_map.clear()

    def apply_book_to_option(self, instrument_id):
        stub = self.option_portfolio.get(instrument_id)
        if stub is None:
            return
        doc = self.book_options.get(instrument_id) or {}
        stub.premium = doc.get("premium")
        stub.startdate = doc.get("startdate") or ""
        stub.dirty = True

    def apply_book_to_stock(self, instrument_id):
        stub = self.stock_portfolio.get(instrument_id)
        if stub is None:
            return
        doc = self.book_stocks.get(instrument_id) or {}
        broker_avg = getattr(stub, "brokerAvgCost", stub.avgCost)
        stub.avgCost = doc.get("avgCost") or broker_avg
        stub.credit = float(doc.get("credit") or 0.0)
        stub.startdate = doc.get("startdate") or ""
        stub.dirty = True

    def refresh_from_book(self):
        for instrument_id in list(self.option_portfolio):
            self.apply_book_to_option(instrument_id)
        for instrument_id in list(self.stock_portfolio):
            self.apply_book_to_stock(instrument_id)
        if self.displayer:
            self.displayer.updatePortfolioDisplay()
        if self.mainframe:
            self.mainframe.refresh_book_views()

    def market_data(self, contract):
        self.sendIbCommand({
            "method_name": "reqMktData",
            "contract": contract,
            "genericTickList": "",
            "snapshot": False,
            "regulatorySnapshot": False,
            "mktDataOptions": []
        })

    def subscribe_option(self, instrument_id, contract):
        if instrument_id not in self.subscribed:
            self.subscribed.add(instrument_id)
            contract.exchange = c.default_exchange
            self.market_data(contract)
        underlying = Contract()
        underlying.symbol = contract.symbol
        underlying.currency = contract.currency or "USD"
        underlying.exchange = c.default_exchange
        if contract.symbol in c.cash_settled_symbols:
            underlying.secType = "IND"
            key = f"IND_{contract.symbol}"
        else:
            underlying.secType = "STK"
            underlying.exchange = "SMART"
            key = f"STK_{contract.symbol}"
        if key not in self.subscribed:
            self.subscribed.add(key)
            self.market_data(underlying)

    def subscribe_stock(self, contract):
        key = f"STK_{contract.symbol}"
        if key in self.subscribed:
            return
        self.subscribed.add(key)
        stock = Contract()
        stock.symbol = contract.symbol
        stock.secType = "STK"
        stock.currency = contract.currency or "USD"
        stock.exchange = "SMART"
        stock.primaryExchange = contract.primaryExchange or ""
        self.market_data(stock)

    def handle_positionEnd(self):
        self.positions_ready = True
        self.schedule_book(0)
        self.finalizePortfolioDisplay()

    # --- fills ---------------------------------------------------------------

    def handle_execDetails(self):
        kwargs = self.incoming_command["kwargs"]
        contract = kwargs.get("contract")
        execution = kwargs.get("execution")
        if contract is None or execution is None or not execution.execId:
            return
        if execution.execId in self.processed:
            return
        date, ts = self.parse_execution_time(execution.time)
        fill = {
            "exec_id": execution.execId,
            "instrument_id": self.get_instrument_id_from_contract(contract),
            "sec_type": contract.secType,
            "symbol": contract.symbol,
            "side": execution.side,
            "qty": float(execution.shares),
            "price": float(execution.price),
            "date": date,
            "ts": ts,
            "perm_id": execution.permId,
            "conId": contract.conId,
            "multiplier": self.contract_multiplier(contract),
        }
        if contract.secType == "OPT":
            fill.update({
                "strike": float(contract.strike),
                "right": contract.right,
                "expiry": contract.lastTradeDateOrContractMonth,
            })
        self.fills[execution.execId] = fill
        self.fill_symbols[execution.execId] = contract.symbol
        if self.executions_ready:
            self.touch(contract.symbol)

    def handle_commissionReport(self):
        report = self.incoming_command["kwargs"].get("commissionReport")
        if report is None or not report.execId:
            return
        commission = float(report.commission)
        if commission >= UNSET_COMMISSION:
            return
        self.commissions[report.execId] = commission
        symbol = self.fill_symbols.get(report.execId)
        if symbol and self.executions_ready:
            self.touch(symbol)
        else:
            self.schedule_book()

    def handle_execDetailsEnd(self):
        self.executions_ready = True
        self.schedule_book(0)

    def parse_execution_time(self, text):
        text = str(text or "")
        digits = re.match(r"\s*(\d{8})", text)
        date = digits.group(1) if digits else datetime.date.today().strftime("%Y%m%d")
        clock = re.search(r"(\d{1,2}):(\d{2}):(\d{2})", text)
        moment = datetime.datetime.strptime(date, "%Y%m%d")
        if clock:
            moment = moment.replace(hour=int(clock.group(1)), minute=int(clock.group(2)),
                                    second=int(clock.group(3)))
        return date, moment.timestamp()

    # --- book --------------------------------------------------------------

    def touch(self, symbol):
        self.symbol_activity[symbol] = time.time()
        self.schedule_book()

    def schedule_book(self, delay=2.0):
        due = time.time() + delay
        if self.reconcile_due is None or due < self.reconcile_due:
            self.reconcile_due = due

    def start_put_scan(self, force=False):
        if self.put_scan is not None and self.put_scan.running:
            if not force:
                return self.put_scan
            self.put_scan.stop()
        self.put_scan = PutScan(self, self.screener_symbols)
        self.put_scan.start()
        return self.put_scan

    def put_scan_running(self):
        return self.put_scan is not None and bool(self.put_scan.running)

    def save_screener_watchlist(self, symbols):
        cleaned = normalize_watchlist(symbols)
        if not cleaned:
            raise ValueError("Add at least one ticker")
        self.screener_symbols = cleaned
        self.firestore.save_screener_symbols(cleaned)
        return cleaned

    def stop_put_scan(self):
        if self.put_scan is not None:
            self.put_scan.stop()

    def tick(self):
        if self.put_scan is not None:
            self.put_scan.step()
        if self.book_paused or not (self.positions_ready and self.executions_ready):
            return
        if self.reconcile_due is None or time.time() < self.reconcile_due:
            return
        self.reconcile_due = None
        try:
            if self.book_initialized:
                self.run_book()
            else:
                self.start_book()
        except Exception as e:
            print(f"Position book error: {e}")
            self.set_status(f"Book not updated: {e}")
            self.schedule_book(30)

    def set_status(self, text):
        self.status_message = text
        print(text)
        if self.mainframe:
            self.mainframe.update_status()

    def pending_fills(self):
        ready, waiting = [], set()
        for exec_id, fill in self.fills.items():
            if exec_id in self.processed:
                continue
            commission = self.commissions.get(exec_id)
            if commission is None:
                waiting.add(fill["symbol"])
                continue
            ready.append(dict(fill, commission=commission))
        return ready, waiting

    def book_config(self):
        return {
            "cash_settled": set(c.cash_settled_symbols),
            "roll_window_seconds": c.roll_window_seconds,
            "underlying": dict(self.underlying),
        }

    def run_book(self):
        now = time.time()
        fills, waiting = self.pending_fills()
        settling = {s for s, t in self.symbol_activity.items() if now - t < c.book_settle_seconds}
        skip = waiting | settling
        outcomes = reconcile(self.book_options, self.book_stocks, self.broker, fills,
                             datetime.date.today(), self.book_config(), skip_symbols=skip)
        messages = []
        touched = set()
        for outcome in outcomes:
            touched.add(outcome.symbol)
            if outcome.ok:
                self.commit_outcome(outcome)
                messages.extend(outcome.messages)
            else:
                self.save_review(outcome)
        for symbol in list(self.review):
            if symbol not in touched and symbol not in skip:
                self.firestore.commit([("delete", "review", symbol)])
                self.review.pop(symbol, None)
        if messages:
            self.set_status("; ".join(messages))
        if skip:
            self.schedule_book(c.book_settle_seconds / 2)
        if outcomes or messages:
            self.refresh_from_book()
        elif self.mainframe:
            self.mainframe.update_status()

    def next_log_seq(self):
        return max((log_sequence(t) for t in self.log_trades), default=0) + 1

    def log_ops(self, rows):
        ops, saved = [], []
        seq = self.next_log_seq()
        for row in rows:
            doc = dict(row, seq=seq)
            log_id = f"{doc['close_date']}_{seq:04d}"
            ops.append(("set", "log", log_id, doc))
            saved.append(dict(doc, id=log_id))
            seq += 1
        return ops, saved

    def commit_outcome(self, outcome):
        ops = []
        for iid, doc in outcome.options.items():
            ops.append(("delete", "portfolio", iid) if doc is None else ("set", "portfolio", iid, doc))
        for iid, doc in outcome.stocks.items():
            ops.append(("delete", "portfolio", iid) if doc is None else ("set", "portfolio", iid, doc))
        log_ops, saved = self.log_ops(outcome.logs)
        ops.extend(log_ops)
        event = "; ".join(outcome.messages)
        for exec_id in outcome.processed:
            ops.append(("set", "processed", exec_id, {"symbol": outcome.symbol, "event": event}))
        if outcome.symbol in self.review:
            ops.append(("delete", "review", outcome.symbol))
        self.firestore.commit(ops)
        for iid, doc in outcome.options.items():
            if doc is None:
                self.book_options.pop(iid, None)
            else:
                self.book_options[iid] = doc
        for iid, doc in outcome.stocks.items():
            if doc is None:
                self.book_stocks.pop(iid, None)
            else:
                self.book_stocks[iid] = doc
        self.log_trades.extend(saved)
        sort_log(self.log_trades)
        self.processed.update(outcome.processed)
        self.review.pop(outcome.symbol, None)

    def save_review(self, outcome):
        item = dict(outcome.review, updated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        previous = self.review.get(outcome.symbol)
        if previous and {k: v for k, v in previous.items() if k != "updated"} == \
                {k: v for k, v in item.items() if k != "updated"}:
            return
        self.firestore.commit([("set", "review", outcome.symbol, item)])
        self.review[outcome.symbol] = item
        self.set_status(f"Review {outcome.symbol}: {outcome.problems[0]}")

    def accept_broker_ops(self, symbols, archive_label):
        """Make the book counts equal the broker for these symbols."""
        ops = []
        today = datetime.date.today().strftime("%Y%m%d")
        options = dict(self.book_options)
        stocks = dict(self.book_stocks)
        for iid, doc in list(options.items()):
            if doc.get("symbol") in symbols and iid not in self.broker:
                ops.append(("set", "portfolio_archive", iid, dict(doc, archived=today, reason=archive_label)))
                ops.append(("delete", "portfolio", iid))
                options.pop(iid)
        for iid, doc in list(stocks.items()):
            if doc.get("symbol") in symbols and iid not in self.broker:
                ops.append(("set", "portfolio_archive", iid, dict(doc, archived=today, reason=archive_label)))
                ops.append(("delete", "portfolio", iid))
                stocks.pop(iid)
        for iid, entry in self.broker.items():
            if entry["symbol"] not in symbols:
                continue
            if entry["sec_type"] == "OPT":
                doc = dict(options.get(iid) or {
                    "secType": "OPT", "symbol": entry["symbol"], "right": entry["right"],
                    "strike": entry["strike"], "expiry": entry["expiry"],
                    "premium": None, "startdate": today,
                })
                doc.update({"n": entry["n"], "multiplier": entry["multiplier"], "conId": entry["conId"]})
                options[iid] = doc
            else:
                doc = dict(stocks.get(iid) or {"secType": "STK", "symbol": entry["symbol"], "startdate": today})
                if not doc.get("avgCost"):
                    doc["avgCost"] = entry["avg_cost"]
                doc.setdefault("credit", 0.0)
                doc.update({"n": entry["n"], "conId": entry["conId"]})
                stocks[iid] = doc
            ops.append(("set", "portfolio", iid, doc))
        return ops, options, stocks

    def start_book(self):
        """First run: adopt broker counts and hand-entered premiums, archive the rest."""
        symbols = {d.get("symbol") for d in self.book_options.values()}
        symbols |= {d.get("symbol") for d in self.book_stocks.values()}
        symbols |= {e["symbol"] for e in self.broker.values()}
        ops, options, stocks = self.accept_broker_ops(symbols, "not held when the book started")
        archived = sum(1 for op in ops if op[1] == "portfolio_archive")
        for exec_id in self.fills:
            ops.append(("set", "processed", exec_id, {"event": "before the book started"}))
        ops.append(("set", "summary", "book", {
            "initialized": datetime.date.today().strftime("%Y%m%d"),
        }))
        self.firestore.commit(ops)
        self.book_options, self.book_stocks = options, stocks
        self.processed.update(self.fills)
        self.book_initialized = True
        held_options = sum(1 for e in self.broker.values() if e["sec_type"] == "OPT")
        held_stocks = sum(1 for e in self.broker.values() if e["sec_type"] == "STK")
        self.set_status(
            f"Book started from the broker: {held_options} options, {held_stocks} stocks; "
            f"{archived} old records archived"
        )
        self.refresh_from_book()

    def resolve_review(self, symbol):
        item = self.review.get(symbol) or {}
        ops, options, stocks = self.accept_broker_ops({symbol}, "resolved from review")
        exec_ids = set(item.get("exec_ids") or [])
        exec_ids |= {i for i, f in self.fills.items() if f["symbol"] == symbol and i not in self.processed}
        for exec_id in exec_ids:
            ops.append(("set", "processed", exec_id, {"symbol": symbol, "event": "resolved by hand"}))
        ops.append(("delete", "review", symbol))
        self.firestore.commit(ops)
        self.book_options, self.book_stocks = options, stocks
        self.processed.update(exec_ids)
        self.review.pop(symbol, None)
        self.set_status(f"Review {symbol} resolved: book counts now match the broker")
        self.refresh_from_book()

    # --- records edited by hand ----------------------------------------------

    def save_option(self, old_id, fields):
        new_id = option_id(fields["expiry"], fields["symbol"], fields["strike"], fields["right"])
        doc = dict(self.book_options.get(old_id) or {}) if old_id else {}
        doc.update(fields)
        doc["secType"] = "OPT"
        doc.setdefault("multiplier", 100.0)
        held = self.broker.get(new_id)
        doc["n"] = held["n"] if held else 0
        ops = [("set", "portfolio", new_id, doc)]
        if old_id and old_id != new_id:
            ops.append(("delete", "portfolio", old_id))
        self.firestore.commit(ops)
        if old_id and old_id != new_id:
            self.book_options.pop(old_id, None)
        self.book_options[new_id] = doc
        self.set_status(f"Saved {describe(doc)}")
        self.refresh_from_book()
        return new_id

    def delete_option(self, iid):
        held = self.broker.get(iid)
        if held:
            doc = dict(self.book_options.get(iid) or {})
            doc.update({"premium": None, "startdate": datetime.date.today().strftime("%Y%m%d"),
                        "n": held["n"]})
            self.firestore.commit([("set", "portfolio", iid, doc)])
            self.book_options[iid] = doc
            self.set_status(f"{describe(doc)} is still held: premium cleared")
        else:
            self.firestore.commit([("delete", "portfolio", iid)])
            self.book_options.pop(iid, None)
            self.set_status(f"Deleted {iid}")
        self.refresh_from_book()

    def save_stock(self, old_id, fields):
        new_id = stock_id(fields["symbol"])
        doc = dict(self.book_stocks.get(old_id) or {}) if old_id else {}
        doc.update(fields)
        doc["secType"] = "STK"
        held = self.broker.get(new_id)
        doc["n"] = held["n"] if held else 0
        ops = [("set", "portfolio", new_id, doc)]
        if old_id and old_id != new_id:
            ops.append(("delete", "portfolio", old_id))
        self.firestore.commit(ops)
        if old_id and old_id != new_id:
            self.book_stocks.pop(old_id, None)
        self.book_stocks[new_id] = doc
        self.set_status(f"Saved {doc['symbol']} stock")
        self.refresh_from_book()
        return new_id

    def delete_stock(self, iid):
        held = self.broker.get(iid)
        if held:
            doc = dict(self.book_stocks.get(iid) or {})
            doc.update({"avgCost": held["avg_cost"], "credit": 0.0, "n": held["n"],
                        "startdate": datetime.date.today().strftime("%Y%m%d")})
            self.firestore.commit([("set", "portfolio", iid, doc)])
            self.book_stocks[iid] = doc
            self.set_status(f"{doc.get('symbol', iid)} is still held: buy price reset, credit cleared")
        else:
            self.firestore.commit([("delete", "portfolio", iid)])
            self.book_stocks.pop(iid, None)
            self.set_status(f"Deleted {iid}")
        self.refresh_from_book()

    def update_option_fields(self, iid, fields):
        doc = dict(self.book_options.get(iid) or {})
        if not doc:
            stub = self.option_portfolio.get(iid)
            if stub is None:
                return False
            contract = stub.contract
            doc = {
                "secType": "OPT", "symbol": contract.symbol, "right": contract.right,
                "strike": float(contract.strike), "expiry": contract.lastTradeDateOrContractMonth,
                "multiplier": self.contract_multiplier(contract), "conId": contract.conId,
            }
        doc.update(fields)
        held = self.broker.get(iid)
        doc["n"] = held["n"] if held else 0
        self.firestore.commit([("set", "portfolio", iid, doc)])
        self.book_options[iid] = doc
        self.refresh_from_book()
        return True

    def update_stock_fields(self, iid, fields):
        doc = dict(self.book_stocks.get(iid) or {})
        if not doc:
            stub = self.stock_portfolio.get(iid)
            if stub is None:
                return False
            doc = {"secType": "STK", "symbol": stub.contract.symbol, "credit": 0.0,
                   "startdate": datetime.date.today().strftime("%Y%m%d")}
        doc.update(fields)
        held = self.broker.get(iid)
        doc["n"] = held["n"] if held else 0
        self.firestore.commit([("set", "portfolio", iid, doc)])
        self.book_stocks[iid] = doc
        self.refresh_from_book()
        return True

    def save_log(self, old_id, fields):
        if old_id:
            existing = next((t for t in self.log_trades if t.get("id") == old_id), {})
            doc = {k: v for k, v in existing.items() if k != "id"}
            doc.update(fields)
            doc = {k: v for k, v in doc.items() if v is not None}
            self.firestore.commit([("set", "log", old_id, doc)])
            self.log_trades = [t for t in self.log_trades if t.get("id") != old_id]
            self.log_trades.append(dict(doc, id=old_id))
            log_id = old_id
        else:
            row = {k: v for k, v in fields.items() if v is not None}
            ops, saved = self.log_ops([row])
            self.firestore.commit(ops)
            self.log_trades.extend(saved)
            log_id = saved[0]["id"]
        sort_log(self.log_trades)
        self.set_status(f"Saved log row {log_id}")
        self.refresh_from_book()
        return log_id

    def delete_log(self, log_id):
        self.firestore.commit([("delete", "log", log_id)])
        self.log_trades = [t for t in self.log_trades if t.get("id") != log_id]
        self.set_status(f"Deleted log row {log_id}")
        self.refresh_from_book()

    def handle_openOrder(self):
        contract = self.incoming_command["kwargs"].get("contract", None)
        order = self.incoming_command["kwargs"].get("order", None)
        orderState = self.incoming_command["kwargs"].get("orderState", None)
        
        if contract is None or order is None or orderState is None:
            return
        instrument_id = self.get_instrument_id_from_contract(contract)
        if instrument_id not in self.option_portfolio:
            # Create a new portfolio entry for this instrument
            self.option_portfolio[instrument_id] = Stub(
                account="",
                n=0,
                avgCost=0.0,
                contract=contract,
                premium=None,
                startdate=None,
                dirty=True
            )
        position = self.option_portfolio[instrument_id]
        position.order = order
        position.orderState = orderState
        position.dirty = True
        self.displayer.updatePortfolioDisplay()
        self.adjust_order(position)

    def handle_orderStatus(self):
        """
        there are actually 2 orderStatus objects:
        position.orderStatus  
        position.order.orderState  
        """
        for position in self.option_portfolio.values():
            if hasattr(position, 'order') \
                    and position.order.permId == self.incoming_command["kwargs"].get("permId", None):
                position.orderState.status = self.incoming_command["kwargs"].get("status", "")
                position.dirty = True
                self.displayer.updatePortfolioDisplay()
                #self.adjust_order(position)
                break
        
    def handle_cancelOrder(self):
        for position in self.option_portfolio.values():
            if hasattr(position, 'order') \
                    and position.order.orderId == self.incoming_command["kwargs"].get("orderId", None):
                position.orderState.status = "Cancelled"
                position.dirty = True
                self.displayer.updatePortfolioDisplay()
                #self.adjust_order(position)
                break

    def can_adjust_order(self, position):
        return False

        if not hasattr(position, 'contract'):
            return False
        if position.contract.secType != "OPT":
            return False
        if not hasattr(position,'order'):
            return False
        if position.n == 0:
            return False
        if not hasattr(position, 'orderState'):
            return False
        if position.orderState.status in ('Cancelled', 'Filled', 'Inactive'):
            return False
        if position.order.action != 'BUY':
            return False


        if position.contract.right != 'P':
            return False
        if position.order.lmtPrice is None or position.order.lmtPrice == 0.0:
            return False
        if position.closeat is None or position.closeat == 0.0:
            return False
        if position.closeat >= position.order.lmtPrice:
            return False
        return True        

    def adjust_order(self, position):
        """Adjust an existing order"""
        if not self.can_adjust_order(position):
            return
        
        print("CAN ADJUST ORDER", position.contract.symbol, position.contract.lastTradeDateOrContractMonth, 
              position.contract.strike, position.contract.right, position.n, position.closeat, position.order.lmtPrice)
        
        new_limit = position.closeat * 0.9
        new_limit = round(new_limit * 100) / 100
        if new_limit < 0.15:
            new_limit = 0.15
        
        # Create a NEW order object with only TWS-compatible properties
        from ibapi.order import Order
        modified_order = Order()
        
        # Copy only essential properties
        modified_order.action = position.order.action
        modified_order.totalQuantity = position.order.totalQuantity
        modified_order.orderType = position.order.orderType
        modified_order.lmtPrice = new_limit
        modified_order.tif = getattr(position.order, 'tif', 'GTC')
        
        # Only copy safe, standard properties if they exist
        if hasattr(position.order, 'auxPrice') and position.order.auxPrice:
            modified_order.auxPrice = position.order.auxPrice
        if hasattr(position.order, 'account') and position.order.account:
            modified_order.account = position.order.account

        command = {
            "method_name": "placeOrder",
            "contract": position.contract,
            "order": modified_order,
            "orderId": position.order.orderId
        }
        
        self.sendIbCommand(command)
        
        # Update the position's order for display AFTER sending the command
        position.order.lmtPrice = new_limit
        
        print(f"Modified order {position.order.orderId} from {position.order.lmtPrice} to {new_limit}")

    def finalizePortfolioDisplay(self):
        """Final portfolio display update"""
        if hasattr(self, 'displayer') and self.displayer:
            self.displayer.updatePortfolioDisplay()

    def handle_openOrderEnd(self):
        """Handle end of open orders from IB"""
        print("Received openOrderEnd - all open orders processed")
        self.finalizePortfolioDisplay()
