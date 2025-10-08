from collections import OrderedDict
from ibapi.contract import Contract
from ibapi.order import Order
import time
import datetime
from config import create_c
#from experiments import option
c = create_c()
from .firestore import FirestoreDB
from util import Stub

class Controller:

    def __init__(self, gui_to_ib, ib_to_gui):
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
        self.mainframe = None  # Will be set by MainFrame
        self.displayer = None
    
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
    

    def get_instrument_id_from_request(self, reqId):
        request = self.requests.get(reqId)
        if request is None:
            return ""
        contract = request.get("contract", None)
        if contract is None:
            return ""
        return self.get_instrument_id_from_contract(contract)



    def process_incoming_data(self):
        while not self.ib_to_gui.empty():

            self.incoming_command = self.ib_to_gui.get()

            if self.incoming_command["type"] in ['command_result', 'error']:
                return
            if self.incoming_command["type"] in ['position', 'positionEnd', 'openOrder', 'openOrderEnd']:
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
        if self.reqId % 100 == 0:
            print(self.stats)

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

    def find_underlying_for_stocktick(self, symbol):
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
        if contract.secType == "STK":
            if instrument_id not in self.option_portfolio:
                underlying_instrument_id = self.find_underlying_for_stocktick(contract.symbol)
                if underlying_instrument_id is not None \
                        and "price" in self.incoming_command["kwargs"]:
                    self.option_portfolio[underlying_instrument_id].underlyingPrice = self.incoming_command["kwargs"]["price"]
                    self.option_portfolio[underlying_instrument_id].dirty = True
                    self.displayer.updatePortfolioDisplay()
                    return
                
            if "price" in self.incoming_command["kwargs"]:
                price = self.incoming_command["kwargs"]["price"]
                self.option_portfolio[instrument_id].lastPrice = price
                self.option_portfolio[instrument_id].dirty = True
                self.displayer.updatePortfolioDisplay()
            return
        #if contract.conId == 808931954:  # AMD
        #    print("AMD tickPrice", self.incoming_command)
        if self.incoming_command["kwargs"].get("tickType") in (1,2,4): 
            price = self.incoming_command["kwargs"]["price"]
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
        account = self.incoming_command["kwargs"].get("account", "")
        contract = self.incoming_command["kwargs"].get("contract", {})
        n = self.incoming_command["kwargs"].get("position", 0.0)
        if n == 0:
            return
        if contract.symbol == "SPX":
            return
        avgCost = self.incoming_command["kwargs"].get("avgCost", 0.0)
        
        instrument_id = self.get_instrument_id_from_contract(contract)
        self.option_portfolio[instrument_id] = Stub(
            account=account,
            n=n,
            avgCost=avgCost,
            contract=contract,
            premium=None,
            startdate=None,
            dirty=True
        )
        self.firestore.merge_portfolio_item(instrument_id)
        
        # Update GUI portfolio display
        self.displayer.updatePortfolioDisplay()

        contract.exchange = c.default_exchange
        command = {
            "method_name": "reqMktData",
            "contract": contract,
            "genericTickList": "",
            "snapshot": False,
            "regulatorySnapshot": False,
            "mktDataOptions": []
        }
        self.sendIbCommand(command)
        if contract.secType == "OPT":
            stock_contract = Contract()
            stock_contract.symbol = contract.symbol
            stock_contract.secType = "STK"
            stock_contract.currency = contract.currency
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
        return # don't use for now
        if not self.can_adjust_order(position):
            return
        print("CAN ADJUST ORDER", position.order.clientId, position.contract.symbol, position.contract.lastTradeDateOrContractMonth, 
              position.contract.strike, position.contract.right, position.n, position.closeat, position.order.lmtPrice)
        
        new_limit = position.closeat * 0.9
        new_limit = round(new_limit * 100) / 100
        if new_limit < 0.15:
            new_limit = 0.15
        
        #delete the existing order and place a new one
        command = {
            "method_name": "cancelOrder",
            "orderId": position.order.orderId
        }
        self.sendIbOrder(command)


        # Create a NEW order object instead of modifying the existing one
        modified_order = Order()
        
        
        # Copy all properties from the original order
        modified_order.orderId = 0  # Will be assigned by sendIbOrder
        modified_order.clientId = 0
        modified_order.permId = 0
        modified_order.action = position.order.action
        modified_order.totalQuantity = position.order.totalQuantity
        modified_order.orderType = position.order.orderType
        modified_order.lmtPrice = new_limit  # ✅ Only change what you need
        modified_order.tif = getattr(position.order, 'tif', 'GTC')
        modified_order.eTradeOnly = getattr(position.order, 'eTradeOnly', False)
        modified_order.firmQuoteOnly = getattr(position.order, 'firmQuoteOnly', False)

        

        command = {
            "method_name": "placeOrder",
            "contract": position.contract,
            "order": modified_order,  # ✅ Use the new order object
        }
        self.sendIbOrder(command)
        
        print(f"Modified order {modified_order.orderId} from {position.order.lmtPrice} to {new_limit}")

    def handle_openOrderEnd(self):
        self.finalizePortfolioDisplay()

    def finalizePortfolioDisplay(self):
        """Final portfolio display update"""
        pass
