from collections import OrderedDict
from ibapi.contract import Contract
import time
import datetime
from config import create_c
#from experiments import option
c = create_c()

class Controller:
    def __init__(self, gui_to_ib, ib_to_gui):
        self.ib_to_gui = ib_to_gui
        self.gui_to_ib = gui_to_ib
        self.reqId = 1
        self.requests = OrderedDict()  # Maintain order of requests
        self.conId = None
        self.stats = {}

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
        print("Requesting positions")
        command = {
            "method_name": "reqPositions"
        }
        self.sendIbCommand(command)

    def getStock(self, stock=""):
        #first cancel all other stock price streams
        #send command to ibapi to cancel all other streams
        self.cancelStreams()
        self.mainframe.resetGrid()
        self.optionKeyToRow = {}
        
        if stock != "":
            self.stock = stock
        else:
            self.stock = self.mainframe.txt_stock.GetValue()
        if stock == "":
            return
        self.getContractDetails()

    def getStockContractDict(self):
        contractDict = {
            "symbol": self.stock,
            "secType": "STK",
            "exchange": "SMART",
            "currency": "USD"
        }
        return contractDict


    #for the stock, get the list of expiration dates for the options
    def reqSecDefOptParams(self):
        command = {
            "method_name": "reqSecDefOptParams",
            "underlyingSymbol": self.stock,
            "futFopExchange": "",
            "underlyingSecType": "STK",
            "underlyingConId": self.conId if self.conId is not None else 0
        }
        self.sendIbCommand(command)
        self.strikes = []
        self.expirations = []
        self.options = {}



    def getContractDetails(self):
        command = {
            "method_name": "reqContractDetails",
            "stock": self.stock
        }
        self.sendIbCommand(command)


    def getStockPrice(self):
        if self.conId is None:
            return
        command = {
            "method_name": "reqMktData",
            "secType": "STK",
            "conId": self.conId,
        }
        self.sendIbCommand(command)

    def cancelMktData(self, reqId):
        command = self._serialize_command("cancelMktData", reqId=reqId)
        self.sendIbCommand(command)
    

    def handle_contractDetails(self):
        print(self.incoming_command)
        getattr(self, f"handle_contractDetails_{self.incoming_command['kwargs']['secType']}")()
           
           
    def handle_contractDetails_STK(self):
        self.conId = self.incoming_command["kwargs"]["conId"]
        self.requests[self.incoming_command["reqId"]]["conId"] = self.conId
        self.getStockPrice()
        self.reqSecDefOptParams()

    def handle_contractDetails_OPT(self):
        conId = self.incoming_command["kwargs"]["conId"]
        optionKey = self.incoming_command["kwargs"].get("lastTradeDateOrContractMonth")
        optionKey += "_" + str(self.incoming_command["kwargs"].get("strike"))
        optionKey += "_" + self.incoming_command["kwargs"].get("right")
        optionData = {
            "symbol": self.stock,
            "lastTradeDateOrContractMonth": self.incoming_command["kwargs"].get("lastTradeDateOrContractMonth", ""),
            "strike": self.incoming_command["kwargs"].get("strike", 0),
            "right": self.incoming_command["kwargs"].get("right", ""),
            "conId": conId,
            "optionKey": optionKey
        }
        self.options[optionKey] = optionData
        self.renderGrid()
        command = {
            "method_name": "reqMktData",
            "conId": conId,
            "secType": "OPT",
        }
        self.sendIbCommand(command, extra=optionData)



    def tickPriceIsOptionPrice(self):
        reqId = self.incoming_command["kwargs"]["reqId"]
        if "strike" in self.requests[reqId]:
            return True
        return False

    def handle_tickPrice(self):
        request = self.requests[self.incoming_command["kwargs"]["reqId"]]
        if "contract"  in request and request["contract"].secType == "STK":
            if "price" in self.incoming_command["kwargs"]:
                self.stockprice = self.incoming_command["kwargs"]["price"]
                self.mainframe.txt_price.SetValue(f"{self.stockprice:.2f}")
            return
        if self.incoming_command["kwargs"].get("tickType") == 4:  # LAST price
            if self.tickPriceIsOptionPrice():
                reqId = self.incoming_command["kwargs"]["reqId"]
                request = self.requests[reqId]
                optionKey = request["optionKey"]
                self.options[optionKey]["lastPrice"] = self.incoming_command["kwargs"]["price"]
                self.renderGrid()
            else:
                self.stockprice = self.incoming_command["kwargs"]["price"]
                self.mainframe.txt_price.SetValue(f"{self.stockprice:.2f}")
            
        
    def handle_tickOptionComputation(self):
        reqId = self.incoming_command["kwargs"]["reqId"]
        optionKey = self.requests[reqId].get("optionKey", None)
        
        if optionKey not in self.options:
            self.options[optionKey] = {}
        self.options[optionKey]["impliedVol"] = self.incoming_command["kwargs"].get("impliedVol", None)
        self.options[optionKey]["delta"] = self.incoming_command["kwargs"].get("delta", None)
        self.options[optionKey]["gamma"] = self.incoming_command["kwargs"].get("gamma", None)
        self.options[optionKey]["theta"] = self.incoming_command["kwargs"].get("theta", None)
        self.options[optionKey]["vega"] = self.incoming_command["kwargs"].get("vega", None)
        self.options[optionKey]["optPrice"] = self.incoming_command["kwargs"].get("optPrice", None)
        self.renderGrid()

    def handle_securityDefinitionOptionParameter(self):
        if self.incoming_command["kwargs"].get("exchange", "") != c.default_exchange:
            return
        print(self.incoming_command["kwargs"].get("strikes", []))
        option_type = "P"
        today = datetime.date.today()
        for expiration in self.incoming_command["kwargs"].get("expirations", []):
            max_weeks = int(self.mainframe.choice_weeks.GetStringSelection())
            expiration_date = datetime.datetime.strptime(expiration, "%Y%m%d").date()
            delta_weeks = (expiration_date - today).days // 7
            if 0 < delta_weeks <= max_weeks:
                self.expirations.append(expiration)
        self.expirations = sorted(self.expirations, reverse=False)
        self.strikes = sorted(self.incoming_command["kwargs"].get("strikes", []), reverse=True)
        print(len(self.expirations) * len(self.strikes), "options found")

        for expiration in self.expirations:
            for strike in self.strikes:
                
                command = {
                    "method_name": "reqContractDetails",
                    "option": {
                        "symbol": self.stock,
                        "lastTradeDateOrContractMonth": expiration,
                        "strike": strike,
                        "right": option_type,

                    }
                }
                self.sendIbCommand(command)

    def cleanGridRow(self, optionKey):
        if optionKey in self.optionKeyToRow:
            #remove the row from the grid
            oldrow = self.optionKeyToRow[optionKey]
            del self.optionKeyToRow[optionKey]
            for row_optionKey, row in list(self.optionKeyToRow.items()):
                if row > oldrow:
                    self.optionKeyToRow[row_optionKey] = row - 1
            #delete the row from the grid
            if self.mainframe.grid.GetNumberRows() > 0:
                self.mainframe.grid.DeleteRows(oldrow, 1)

    def filterOption(self):
        if self.iter_option["strike"] > self.stockprice and self.iter_option["right"] == "P":
            return True
        for property in ["impliedVol", "delta", "lastPrice"]:
            if property not in self.iter_option:
                return True
            if self.iter_option[property] is None:
                return True
        if self.iter_option("delta") is not None and (self.iter_option["delta"] < c.delta_min or self.iter_option["delta"] > c.delta_max):
            return True
        return False

    def calculateNew(self):
        expiration_date = datetime.datetime.strptime(self.iter_option["lastTradeDateOrContractMonth"], "%Y%m%d").date()
        days_to_expiration = (expiration_date - datetime.date.today()).days + 1
        self.iter_option["PPD"] = (self.iter_option["lastPrice"])/days_to_expiration
        self.iter_option["ROI"] = (self.iter_option["PPD"]*365)/(self.iter_option["strike"]) * 100

    def renderGrid(self):
        grid = self.mainframe.grid
        for optionKey, self.iter_option in self.options.items():
            if self.filterOption():
                self.cleanGridRow(optionKey)
                continue
            if optionKey not in self.optionKeyToRow:
                grid.AppendRows(1)
                row = grid.GetNumberRows() - 1
                self.optionKeyToRow[optionKey] = row
                grid.SetCellValue(row, 0, self.iter_option.get("lastTradeDateOrContractMonth", ""))
                grid.SetCellValue(row, 1, f"{self.iter_option.get('strike', 0.0):.2f}")
                grid.SetCellValue(row, 2, self.iter_option.get("right", ""))
            else:
                row = self.optionKeyToRow[optionKey]
            #labels = ["Expiration", "Strike", "Type", "Last", "Δ", "IV","PPD", "ROI"]
            last_price = self.iter_option.get('lastPrice')
            grid.SetCellValue(row, 3, f"{last_price:.4f}" if last_price is not None else "")
            grid.SetCellValue(row, 4, f"{self.iter_option.get('delta'):.2f}" if self.iter_option.get('delta') is not None else "")
            grid.SetCellValue(row, 5, f"{self.iter_option.get('impliedVol'):.2%}" if self.iter_option.get('impliedVol') is not None else "")
            grid.SetCellValue(row, 6, f"{self.iter_option.get('PPD'):.2f}" if self.iter_option.get('PPD') is not None else "")
            grid.SetCellValue(row, 7, f"{self.iter_option.get('ROI'):.2%}" if self.iter_option.get('ROI') is not None else "")
            row += 1
        grid.AutoSizeColumns()

    def handle_position(self):
        """Handle individual position updates"""
        account = self.incoming_command["kwargs"].get("account", "")
        contract = self.incoming_command["kwargs"].get("contract", {})
        position = self.incoming_command["kwargs"].get("position", 0.0)
        avgCost = self.incoming_command["kwargs"].get("avgCost", 0.0)
        
        symbol = contract.symbol
        secType = contract.secType
        
        print(f"Position: {symbol} ({secType}) - {position} shares @ {avgCost:.2f}")
        
        # Store in portfolio data structure
        if not hasattr(self, 'portfolio'):
            self.portfolio = {}
        
        position_key = f"{account}_{symbol}_{secType}"
        self.portfolio[position_key] = {
            "account": account,
            "symbol": symbol,
            "secType": secType,
            "position": position,
            "avgCost": avgCost,
            "contract": contract
        }
        
        # Update GUI portfolio display
        self.updatePortfolioDisplay()

    def handle_positionEnd(self):
        """Handle end of position updates"""
        print("Position updates complete")
        # Final GUI update or summary calculations
        self.finalizePortfolioDisplay()

    def updatePortfolioDisplay(self):
        """Update the portfolio display in the GUI"""
        if not hasattr(self, 'portfolio'):
            return
        portfolio_items = list(self.portfolio.values())
        grid = self.mainframe.grid_portfolio
        grid.ClearGrid()
        
        # Ensure enough rows
        current_rows = grid.GetNumberRows()
        required_rows = len(portfolio_items)
        if required_rows > current_rows:
            grid.AppendRows(required_rows - current_rows)
        elif required_rows < current_rows:
            grid.DeleteRows(0, current_rows - required_rows)
        
        for row, item in enumerate(portfolio_items):
            grid.SetCellValue(row, 0, item.get("symbol", ""))
            grid.SetCellValue(row, 1, f"{int(item.get('position', 0.0))}")            
            grid.SetCellValue(row, 2, item.get("secType", ""))
            grid.SetCellValue(row, 3, f"{item.get('avgCost', 0.0):.2f}")
            
        
        grid.AutoSizeColumns()

    def finalizePortfolioDisplay(self):
        """Final portfolio display update"""
        pass