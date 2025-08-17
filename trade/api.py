from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.common import *
import threading
import time

class IBApi(EWrapper, EClient):
    def __init__(self, command_queue=None, data_queue=None):
        EClient.__init__(self, self)
        self.orders = []
        self.positions = []
        self.accounts = []
        self.account_summary = {}
        self.command_queue = command_queue
        self.data_queue = data_queue
        # Don't call start_api() in constructor

    def start_api(self):
        """Start the API connection and run the event loop"""
        try:
            # Start command processing thread if queue exists
            if self.command_queue:
                print("Starting command processing thread...")
                self.command_thread = threading.Thread(target=self._process_commands, daemon=True)
                self.command_thread.start()
            
            print("Connecting to TWS...")
            self.connect("127.0.0.1", 7496, 0)
            print("Starting run loop...")
            self.run()
        except Exception as e:
            print(f"Error connecting to TWS: {e}")

    def nextValidId(self, orderId: int):
        self.orders.clear()
        self.positions.clear()
        self.account_summary.clear()
        self.reqAllOpenOrders()
        self.reqPositions()
        # Don't automatically request managed accounts - wait for manual request

    def _process_commands(self):
        """Process commands from the queue"""
        print("Command processing thread started")
        while True:
            try:
                if not self.command_queue.empty():
                    command = self.command_queue.get(timeout=1)
                    print(f"Processing command: {command}")
                    self._execute_command(command)
                time.sleep(0.1)  # Small delay to prevent busy waiting
            except Exception as e:
                print(f"Command processing error: {e}")
                continue

    def _execute_command(self, command):
        """Execute a command received from the queue"""
        if command == "get_orders":
            self.reqAllOpenOrders()
        elif command == "get_positions":
            self.reqPositions()
        elif command == "get_cash":
            self.get_cash()
        elif command == "get_account_summary":
            self.get_account_summary()
        elif command == "get_accounts":
            self.reqManagedAccts()
        # Add more commands as needed

    def openOrder(self, orderId, contract, order, orderState):
        self.orders.append((orderId, contract, order, orderState))

    def position(self, account, contract, position, avgCost):
        self.positions.append((account, contract, position, avgCost))

    def positionEnd(self):
        if self.data_queue:
            self.data_queue.put({"type": "positions", "data": self.positions.copy()})
        else:
            print("Current Positions:")
            for pos in self.positions:
                print(pos)

    def openOrderEnd(self):
        if self.data_queue:
            self.data_queue.put({"type": "orders", "data": self.orders.copy()})
        else:
            print("Current Orders:")
            for ord in self.orders:
                print(ord)

    def managedAccounts(self, accountsList: str):
        """Callback for managed accounts"""
        self.accounts = [acc.strip() for acc in accountsList.split(",") if acc.strip()]
        print(f"Managed accounts: {self.accounts}")
        # Don't automatically request account summary - wait for manual request
        if "U7255176" in self.accounts:
            print("Found target account U7255176")
        else:
            print("Target account U7255176 not found in managed accounts")

    def get_cash(self):
        """Request cash balance for account U7255176"""
        group = "All"  # Use "All" instead of specific account
        print(f"Requesting cash for group: '{group}'")
        # Cancel any existing account summary requests first
        self.cancelAccountSummary(9001)
        self.reqAccountSummary(9001, group, "TotalCashValue,AvailableFunds,BuyingPower")

    def get_account_summary(self):
        """Request account summary for account U7255176"""
        group = "All"  # Use "All" instead of specific account
        print(f"Requesting account summary for group: '{group}'")
        # Cancel any existing account summary requests first
        self.cancelAccountSummary(9002)
        self.reqAccountSummary(9002, group, "NetLiquidation,TotalCashValue,AvailableFunds,BuyingPower,GrossPositionValue")

    def accountSummary(self, reqId: int, account: str, tag: str, value: str, currency: str):
        """Callback for account summary data"""
        key = f"{account}_{tag}"
        self.account_summary[key] = {"value": value, "currency": currency}
        print(f"Account {account}: {tag} = {value} {currency}")

    def accountSummaryEnd(self, reqId: int):
        """Called when account summary is complete"""
        print(f"Account summary end for reqId: {reqId}")
        if self.data_queue:
            if reqId == 9001:  # Cash request
                cash_data = {k: v for k, v in self.account_summary.items() if "Cash" in k or "Funds" in k or "Power" in k}
                self.data_queue.put({"type": "cash", "data": cash_data})
            elif reqId == 9002:  # Full account summary
                self.data_queue.put({"type": "account_summary", "data": self.account_summary.copy()})
        else:
            print("Account Summary Complete")
            for key, data in self.account_summary.items():
                print(f"{key}: {data['value']} {data['currency']}")

    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson = ""):
        """Handle errors from TWS"""
        print(f"ERROR {reqId} {errorCode} {errorString}")
        if errorCode == 321 and reqId in [9001, 9002]:
            print("Account validation error - this might be due to incorrect account name")
            print(f"Available accounts: {self.accounts}")
            # Send error to data queue so UI can display it
            if self.data_queue:
                self.data_queue.put({"type": "error", "data": f"Error {errorCode}: {errorString}"})


