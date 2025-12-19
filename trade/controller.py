from collections import OrderedDict
from ibapi.contract import Contract
from ibapi.order import Order
import time
import datetime
from config import create_c
#from experiments import option
c = create_c()
from .firestore import FirestoreDB
from .sheetstofirestore import sheets_to_firestore
from util import Stub

class Controller:

    def __init__(self, gui_to_ib, ib_to_gui):
        sheets_to_firestore()
        self.ib_to_gui = ib_to_gui
        self.gui_to_ib = gui_to_ib
        self.firestore = FirestoreDB(self)
        self.firestore.get_portfolio()
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
    
    
    def process_incoming_data(self):
        while not self.ib_to_gui.empty():

            self.incoming_command = self.ib_to_gui.get()

            if self.incoming_command["type"] in ['command_result', 'error']:
                return
            if self.incoming_command["type"] in ['position', 'positionEnd', 'openOrder', 'openOrderEnd', 'currentTime']:
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
                        return
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
            
        if contract.secType == "STK":
            self.handle_tickPrice_stock(instrument_id, contract, price)
        elif contract.secType == "OPT":
            self.handle_tickPrice_option(instrument_id, contract, price)

    def handle_tickPrice_stock(self, instrument_id, contract, price):
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
            
            # Update Firestore
            self.firestore.update_stock_price(instrument_id, price)

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
        if contract is None:
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
        """Handle individual position updates"""
        self.account = self.incoming_command["kwargs"].get("account", "")
        self.contract = self.incoming_command["kwargs"].get("contract", {})
        self.n = self.incoming_command["kwargs"].get("position", 0.0)
        if self.n == 0:
            return
        if self.contract.symbol == "SPX":
            return
        self.avgCost = self.incoming_command["kwargs"].get("avgCost", 0.0)
        self.instrument_id = self.get_instrument_id_from_contract(self.contract)
        if self.contract.secType == "OPT":
            self.handle_postion_option()
        elif self.contract.secType == "STK":
            self.handle_position_stock()

    def handle_position_stock(self):
        self.stock_portfolio[self.instrument_id] = Stub(
                account=self.account,
                n=self.n,
                avgCost=self.avgCost,
                contract=self.contract,
                dirty=True
            )
        self.displayer.updatePortfolioDisplay()
        self.contract.exchange = c.default_exchange
        self.firestore.merge_stock_item(self.instrument_id)

    def handle_postion_option(self):
        self.option_portfolio[self.instrument_id] = Stub(
                account=self.account,
                n=self.n,
                avgCost=self.avgCost,
                contract=self.contract,
                premium=None,
                startdate=None,
                dirty=True
            )
        self.firestore.merge_portfolio_item(self.instrument_id)
            
        # Update GUI portfolio display
        self.displayer.updatePortfolioDisplay()

        self.contract.exchange = c.default_exchange
        command = {
            "method_name": "reqMktData",
            "contract": self.contract,
            "genericTickList": "",
            "snapshot": False,
            "regulatorySnapshot": False,
            "mktDataOptions": []
        }
        self.sendIbCommand(command)
        stock_contract = Contract()
        stock_contract.symbol = self.contract.symbol
        stock_contract.secType = "STK"
        stock_contract.currency = self.contract.currency
        stock_contract.exchange = c.default_exchange
        stock_command = {
            "method_name": "reqMktData",
            "contract": stock_contract,
            "genericTickList": "",
            "snapshot": False,
            "regulatorySnapshot": False,
            "mktDataOptions": []
        }
        self.sendIbCommand(stock_command)

    def handle_positionEnd(self):
        # Final GUI update or summary calculations
        self.finalizePortfolioDisplay()

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
