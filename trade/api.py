from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract, ContractDetails
from ibapi.order import Order
from ibapi.common import *
import threading
import time
import inspect

class IBApi(EWrapper, EClient):
    def __init__(self, gui_to_ib=None, ib_to_gui=None):
        EClient.__init__(self, self)
        self.orders = []
        self.positions = []
        self.accounts = []
        self.account_summary = {}
        self.gui_to_ib = gui_to_ib
        self.ib_to_gui = ib_to_gui
        # Don't call start_api() in constructor

    def start_api(self):
        """Start the API connection and run the event loop"""
        try:
            # Start command processing thread if queue exists
            if self.gui_to_ib:
                self.command_thread = threading.Thread(target=self._process_commands, daemon=True)
                self.command_thread.start()
            
            self.connect("127.0.0.1", 7496, 0)
            self.run()
        except Exception as e:
            print(f"Error connecting to TWS: {e}")

    def nextValidId(self, orderId: int):
        pass

    def _process_commands(self):
        """Process commands from the queue"""
        print("Command processing thread started")
        while True:
            try:
                if not self.gui_to_ib.empty():
                    self.command = self.gui_to_ib.get(timeout=1)
                    self._prepare_reqMktData()
                    self._prepare_contractDetailsStock()
                    self._prepare_contractDetailsOption()
                    self._execute_command()
                time.sleep(0.1)  # Small delay to prevent busy waiting
            except Exception as e:
                print(f"Command processing error: {e}")
                continue

    def _prepare_contractDetailsOption(self):
        if self.command["method_name"] != "reqContractDetails":
            return
        if not "option" in self.command:
            return
        option = self.command["option"]
        #self.command is defined as: {"method_name": "reqContractDetails", "option": {"symbol": "AAPL", "expiry": "20240920", "strike": 175, "right": "C"}, "reqId": 1}
        #turn this into the signature for the reqContractDetails method
        # reqContractDetails(self, reqId: int, contract: Contract)
        contract = Contract()
        contract.symbol = option.get("symbol", "")
        contract.secType = "OPT"
        contract.exchange = "SMART"
        contract.currency = "USD"
        contract.lastTradeDateOrContractMonth = option.get("lastTradeDateOrContractMonth", "")
        contract.strike = option.get("strike", 0.0)
        contract.right = option.get("right", "")
        self.command["contract"] = contract
        del self.command["option"]


    def _prepare_contractDetailsStock(self):
        if self.command["method_name"] != "reqContractDetails":
            return
        if not "stock" in self.command:
            return
        #self.command is defined as: {"method_name": "reqContractDetails", "stock": "AAPL", "reqId": 1}
        #turn this into the signature for the reqContractDetails method
        # reqContractDetails(self, reqId: int, contract: Contract)
        contract = Contract()
        contract.symbol = self.command["stock"]
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        self.command["contract"] = contract
        del self.command["stock"]

    def _prepare_reqMktData(self):

        if self.command["method_name"] != "reqMktData":
            return
        #self.command is defined as: {"method_name": "reqMktData", "conId": 123123123123, "reqId": 1}
        #turn this into the signature for the reqMktData method
        # reqMktData(self, reqId: TickerId, contract: Contract, genericTickList: str, snapshot: bool, regulatorySnapshot: bool, mktDataOptions: ListOfTagValue)
        if self.command["secType"] == "STK":
            contract = Contract()
            contract.conId = self.command["conId"]
            contract.exchange = "SMART"
            contract.secType = "STK"
            contract.currency = "USD"
            self.command["contract"] = contract

            #add default values for the other parameters
            self.command["genericTickList"] = "221"
            self.command["snapshot"] = False
            self.command["regulatorySnapshot"] = False
            self.command["mktDataOptions"] = []
        elif self.command["secType"] == "OPT":
            contract = Contract()
            contract.conId = self.command["conId"]
            contract.exchange = "SMART"
            contract.secType = "OPT"
            contract.currency = "USD"
            self.command["contract"] = contract
            # Request Greeks and implied volatility data
            self.command["genericTickList"] = "106"  # Model option, Impl Vol, Gamma, Theta, Delta
        self.command["snapshot"] = False
        self.command["regulatorySnapshot"] = False
        self.command["mktDataOptions"] = []
        del self.command["secType"]
        del self.command["conId"]

    def _execute_command(self):
        """Execute IB API commands - pure generic dispatcher"""
        try:
            method_name = self.command["method_name"]
            # Remove method_name, pass the rest as kwargs
            kwargs = {k: v for k, v in self.command.items() if k != "method_name"}
            
            if hasattr(self, method_name):
                method = getattr(self, method_name)
                #print(f"Executing: {method_name} {kwargs}")
                result = method(**kwargs)
                self.ib_to_gui.put({
                    "type": "command_result", 
                    "method": method_name,
                    "result": result
                })
                
        except Exception as e:
            print(f"Error executing command {self.command}: {e}")
            if self.ib_to_gui:
                self.ib_to_gui.put({"type": "error", "data": str(e)})
    
    def auto_queue(func):
        """Decorator to automatically send callback data to GUI queue"""
        def wrapper(self, *args, **kwargs):
            # Call the original function first (for any custom logic)
            result = func(self, *args, **kwargs)
            func_name = func.__name__
            if func_name == "error":
                return
            sig = inspect.signature(func)
            bound = sig.bind(self, *args, **kwargs)
            bound.apply_defaults()
            # Remove 'self' from the arguments
            arg_dict = {k: v for k, v in bound.arguments.items() if k != 'self'}
            self.ib_to_gui.put({
                "type": func_name,
                "args": args,
                "kwargs": arg_dict
            })
            
            return result
        return wrapper

    @auto_queue
    def tickPrice(self, reqId: int, tickType: int, price: float, attrib):
        #if reqId != 2 and tickType == 4:  # LAST
        #    print(f"Tick Price. ReqId: {reqId}, TickType: {tickType}, Price: {price}")
        return

    @auto_queue
    def tickSize(self, reqId: int, tickType: int, size: int):
        return
    
    @auto_queue
    def tickString(self, reqId: int, tickType: int, value: str):
        return

    @auto_queue
    def tickGeneric(self, reqId: int, tickType: int, value: float):
        return
    
    @auto_queue
    def tickOptionComputation(self, reqId: int, tickType: int, tickAttrib: int,
                            impliedVol: float, delta: float, optPrice: float, 
                            pvDividend: float, gamma: float, vega: float, 
                            theta: float, undPrice: float):
        """Handle option Greeks and computed values"""
        print(f"Option Computation. ReqId: {reqId}, TickType: {tickType}")
        print(f"  Delta: {delta}, Gamma: {gamma}, Theta: {theta}, Vega: {vega}")
        print(f"  ImpliedVol: {impliedVol}, OptPrice: {optPrice}, UndPrice: {undPrice}")
        return
    
    def contractDetails(self, reqId: int, contract: ContractDetails):
        if contract.contract.secType == "STK":
            kwargs = {
                "reqId": reqId,
                "secType": contract.contract.secType,
                "conId": contract.contract.conId,
            }
        else:
            kwargs = {
                "reqId": reqId,
                "secType": contract.contract.secType,
                "conId": contract.contract.conId,
                "strike": contract.contract.strike,
                "right": contract.contract.right,
                "lastTradeDateOrContractMonth": contract.contract.lastTradeDateOrContractMonth,
            }
        args = kwargs.values()


        self.ib_to_gui.put({
            "type": "contractDetails",
            "reqId": reqId,
            "args": args,
            "kwargs": kwargs
        })

    @auto_queue
    def securityDefinitionOptionParameter(self, reqId: int, exchange: str, 
                                    underlyingConId: int, tradingClass: str,
                                    multiplier: str, expirations: set,
                                    strikes: set):
        """Handle option security definition parameters"""
        """
        print(f"Option params for reqId {reqId} on {exchange}:")
        print(f"  Underlying conId: {underlyingConId}")
        print(f"  Trading class: {tradingClass}")
        print(f"  Multiplier: {multiplier}")
        print(f"  Expirations: {sorted(list(expirations))}")
        print(f"  Strikes count: {len(strikes)}")
        """
        # The auto_queue decorator will automatically send this data to GUI
        return

    @auto_queue 
    def securityDefinitionOptionParameterEnd(self, reqId: int):
        """Called when all option parameter data has been received"""
        return

    @auto_queue
    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson = ""):
        if reqId == -1:
            return
        if errorCode in [200, 201, 202]:  # Generic IB errors
            return
        print(f"ERROR {reqId} {errorCode} {errorString}")
        if errorCode == 321 and reqId in [9001, 9002]:
            print("Account validation error - this might be due to incorrect account name")
            print(f"Available accounts: {self.accounts}")
            # Send error to data queue so UI can display it
            if self.data_queue:
                self.data_queue.put({"type": "error", "data": f"Error {errorCode}: {errorString}"})


