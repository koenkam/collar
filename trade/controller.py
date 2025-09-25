from collections import OrderedDict
from ibapi.contract import Contract
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
        self.requests = OrderedDict()  # Maintain order of requests
        self.conId = None
        self.stats = {}
        self.portfolio = {}
        self.portfolio_gui_map = {}

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
        request = self.requests[reqId]
        contract = request.get("contract", None)
        if contract is None:
            return ""
        return self.get_instrument_id_from_contract(contract)



    def process_incoming_data(self):
        while not self.ib_to_gui.empty():

            self.incoming_command = self.ib_to_gui.get()

            if self.incoming_command["type"] in ['command_result', 'error']:
                return
            if self.incoming_command["type"] in ['position', 'positionEnd']:
                handler = getattr(self, f"handle_{self.incoming_command['type']}")
                handler()
                continue
            try:
                incoming_request_id = int(self.incoming_command["kwargs"]["reqId"])
            except (KeyError, ValueError, TypeError):
                print(f"Invalid or missing reqId in incoming command: {self.incoming_command}")
            #print(f"looking for request id: {incoming_request_id} {self.requests}")
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

    def find_underlying_for_stocktick(self, symbol):
        for instrument_id, position in self.portfolio.items():
            contract = position.contract
            if contract.secType == 'OPT' and contract.symbol == symbol:
                return instrument_id
        return None

    def handle_tickPrice(self):        
        instrument_id = self.get_instrument_id_from_request(self.incoming_command["kwargs"]["reqId"])
        request = self.requests[self.incoming_command["kwargs"]["reqId"]]
        contract = request.get("contract", None)
        if contract.secType == "STK":
            if instrument_id not in self.portfolio:
                underlying_instrument_id = self.find_underlying_for_stocktick(contract.symbol)
                if underlying_instrument_id is not None \
                        and "price" in self.incoming_command["kwargs"]:
                    self.portfolio[underlying_instrument_id].underlyingPrice = self.incoming_command["kwargs"]["price"]
                    self.portfolio[underlying_instrument_id].dirty = True
                    self.updatePortfolioDisplay()
                    return
                
            if "price" in self.incoming_command["kwargs"]:
                price = self.incoming_command["kwargs"]["price"]
                self.portfolio[instrument_id].lastPrice = price
                self.portfolio[instrument_id].dirty = True
                self.updatePortfolioDisplay()
            return
        #if contract.conId == 808931954:  # AMD
        #    print("AMD tickPrice", self.incoming_command)
        if self.incoming_command["kwargs"].get("tickType") in (1,2,4): 
            price = self.incoming_command["kwargs"]["price"]
            self.portfolio[instrument_id].lastPrice = price
            self.portfolio[instrument_id].dirty = True
            self.updatePortfolioDisplay()

    def handle_tickOptionComputation(self):
        reqId = self.incoming_command["kwargs"]["reqId"]
        instrument_id = self.get_instrument_id_from_request(reqId)
        contract = self.requests[reqId].get("contract", None)
        self.portfolio[instrument_id].impliedVol = self.incoming_command["kwargs"].get("impliedVol", None)
        self.portfolio[instrument_id].delta = self.incoming_command["kwargs"].get("delta", None)
        self.portfolio[instrument_id].gamma = self.incoming_command["kwargs"].get("gamma", None)
        self.portfolio[instrument_id].theta = self.incoming_command["kwargs"].get("theta", None)
        self.portfolio[instrument_id].vega = self.incoming_command["kwargs"].get("vega", None)
        self.portfolio[instrument_id].optPrice = self.incoming_command["kwargs"].get("optPrice", None)
        self.portfolio[instrument_id].dirty = True
        self.updatePortfolioDisplay()

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
        self.portfolio[instrument_id] = Stub(
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
        self.updatePortfolioDisplay()

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

    def updatePortfolioDisplay(self):
        grid = self.mainframe.grid_portfolio
        
        # Ensure enough rows
        current_rows = grid.GetNumberRows()
        required_rows = len(self.portfolio.items())
        if required_rows > current_rows:
            grid.AppendRows(required_rows - current_rows)
        elif required_rows < current_rows:
            grid.DeleteRows(0, current_rows - required_rows)
        
        for instrument_id, position in self.portfolio.items():
            if not position.dirty:
                pass
                #return
            position.dirty = False
            contract = position.contract
            if instrument_id in self.portfolio_gui_map:
                row = self.portfolio_gui_map[instrument_id]
            else:
                row = max(self.portfolio_gui_map.values(), default=-1) + 1
                self.portfolio_gui_map[instrument_id] = row
            if contract.secType == 'OPT':
                opttype = 'PUT' if contract.right == 'P' else 'CALL'
                optexpire = contract.lastTradeDateOrContractMonth
            else:
                opttype = contract.secType
                optexpire = ""
            
            startdate = position.startdate if hasattr(position, 'startdate') else ""
            lastPrice = position.lastPrice if hasattr(position, 'lastPrice') and position.lastPrice is not None and position.lastPrice >= 0 else 0.0
            buyback = lastPrice * position.n * 100
            premium = position.premium if hasattr(position, 'premium') \
                and position.premium is not None else 0.0
            pl = premium + buyback if buyback != 0 else 0.0
            if contract.secType == 'OPT' and startdate:
                expiry_date = datetime.datetime.strptime(contract.lastTradeDateOrContractMonth, "%Y%m%d").date()
                start_date = datetime.datetime.strptime(position.startdate, "%Y%m%d").date()
                days = (expiry_date - start_date).days + 1
                dte = (expiry_date - datetime.date.today()).days + 1
                dit = (datetime.date.today() - start_date).days + 1
            else:
                days = 1
                dte = 1
                dit = 1
            ppd = (premium / days)
            ppd_now = pl /days
            strike = contract.strike if hasattr(contract, 'strike') else ""
            underlying = position.underlyingPrice if hasattr(position, 'underlyingPrice') else ""
            output = [
                contract.symbol,
                strike,
                underlying,
                position.n,
                opttype,
                startdate,
                optexpire,
                premium,
                lastPrice,
                buyback,
                pl,
                days,
                dit,
                dte,
                ppd,
                ppd_now,
            ]
            display_list = []
            for i, value in enumerate(output):
                if type(value) in [float, int]:
                    if int(value) == value:
                        display_list.append(f"{int(value)}")
                    else:
                        display_list.append(f"{value:.2f}")
                elif value is None:
                    display_list.append("")
                else:
                    display_list.append(str(value))

            for col, value in enumerate(display_list):
                grid.SetCellValue(row, col, value)

            self.highlightcells(output, row)
                
        grid.AutoSizeColumns()

    def findColumnByLabel(self, label):
        grid = self.mainframe.grid_portfolio
        for col in range(grid.GetNumberCols()):
            if grid.GetColLabelValue(col) == label:
                return col
        return -1

    def highlightcells(self, output, row):
        """Highlight cells based on certain conditions"""
        strike_col = self.findColumnByLabel("Strike")
        underlying_col = self.findColumnByLabel("Underlying")
        if strike_col != -1 and underlying_col != -1:
            try:
                strike = float(output[strike_col])
                underlying = float(output[underlying_col])
                if underlying < strike :
                    self.mainframe.grid_portfolio.SetCellTextColour(row, underlying_col, "red")
                else:
                    # Reset to default background
                    self.mainframe.grid_portfolio.SetCellTextColour(row, underlying_col, "green")
            except (ValueError, TypeError):
                pass  # Ignore if conversion fails
        ppd_now_col = self.findColumnByLabel("PPD_NOW")
        ppd_col = self.findColumnByLabel("PPD")
        if ppd_now_col != -1 and ppd_col != -1:
            try:
                ppd_now = float(output[ppd_now_col])
                ppd = float(output[ppd_col])
                if ppd_now > ppd:
                    self.mainframe.grid_portfolio.SetCellTextColour(row, ppd_now_col, "green")
                else:
                    # Reset to default background
                    self.mainframe.grid_portfolio.SetCellTextColour(row, ppd_now_col, "white")
            except (ValueError, TypeError):
                pass  # Ignore if conversion fails
        pl_col = self.findColumnByLabel("PL")
        if pl_col != -1:
            try:
                pl = float(output[pl_col])
                if pl > 0:
                    self.mainframe.grid_portfolio.SetCellTextColour(row, pl_col, "green")
                else:
                    # Reset to default background
                    self.mainframe.grid_portfolio.SetCellTextColour(row, pl_col, "red")
            except (ValueError, TypeError):
                pass  # Ignore if conversion fails


    def finalizePortfolioDisplay(self):
        """Final portfolio display update"""
        pass

