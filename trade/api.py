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
                    self._execute_command()
                time.sleep(0.1)  # Small delay to prevent busy waiting
            except Exception as e:
                contract = self.command.get("contract", None) if hasattr(self, 'command') and self.command else None
                sec_type = contract.secType if contract and hasattr(contract, 'secType') else None
                print(f"Command processing error: {e} {getattr(self, 'command', None)} {sec_type}")
                continue

    def reqPositions(self, *args, **kwargs):
        super().reqPositions()

    def reqCurrentTime(self, *args, **kwargs ):
        return super().reqCurrentTime()

    
    def reqOpenOrders(self, *args, **kwargs ):
        return super().reqOpenOrders()
    
        
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
        return
    
    
    @auto_queue
    def position(self, account: str, contract: Contract, position: float, avgCost: float):
        super().position(account, contract, position, avgCost)
        return  

    @auto_queue
    def currentTime(self, time):
        return super().currentTime(time)

    
    @auto_queue
    def positionEnd(self):
        return

    @auto_queue
    def openOrder(self, orderId, contract, order, orderState):
        super().openOrder(orderId, contract, order, orderState)

    @auto_queue
    def openOrderEnd(self):
        super().openOrderEnd()

    @auto_queue
    def orderStatus(self, orderId: OrderId, status: str, filled: float,
                    remaining: float, avgFillPrice: float, permId: int,
                    parentId: int, lastFillPrice: float, clientId: int,
                    whyHeld: str, mktCapPrice: float):
        super().orderStatus(orderId, status, filled, remaining, avgFillPrice,
                           permId, parentId, lastFillPrice, clientId,
                           whyHeld, mktCapPrice)

    @auto_queue
    def cancelOrder(self, orderId: OrderId):
        super().cancelOrder(orderId)

    def reqMktDataDelayed(self, reqId: TickerId, contract: Contract,
                          genericTickList: str, snapshot: bool,
                          regulatorySnapshot: bool, mktDataOptions: list):
        self.reqMarketDataType(4)  # 1 = real-time, 2 = frozen, 3 = delayed, 4 = delayed-frozen
        super().reqMktData(reqId, contract, genericTickList, snapshot,
                           regulatorySnapshot, mktDataOptions)
        self.reqMarketDataType(1)

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=''):
        if reqId == -1:
            return
        if errorCode in [-1, 200, 201, 202]:  # Generic IB errors
            return
        print(f"ERROR {reqId} {errorCode} {errorString}")
        if errorCode == 321 and reqId in [9001, 9002]:
            print("Account validation error - this might be due to incorrect account name")
            print(f"Available accounts: {self.accounts}")
            # Send error to data queue so UI can display it
            if hasattr(self, "data_queue") and self.data_queue:
                self.data_queue.put({"type": "error", "data": f"Error {errorCode}: {errorString}"})

   
