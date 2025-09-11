from collections import OrderedDict
from ibapi.contract import Contract
import time
import datetime

class Controller:
    def __init__(self, mainframe):
        self.mainframe = mainframe
        self.reqId = 1
        self.requests = OrderedDict()  # Maintain order of requests
        self.conId = None
        self.stats = {}

    def process_incoming_data(self):
        while not self.mainframe.ib_to_gui.empty():
            
            incoming_command = self.mainframe.ib_to_gui.get()

            if incoming_command["type"] in ['command_result']:
                return
            try:
                incoming_request_id = int(incoming_command["kwargs"]["reqId"])
            except (KeyError, ValueError, TypeError):
                print(f"Invalid or missing reqId in incoming command: {incoming_command}")
            #print(f"looking for request id: {incoming_request_id} {self.requests}")
            if incoming_request_id in self.requests:
                command = self.requests[incoming_request_id]
                command_type = incoming_command["type"]

                if hasattr(self, f"handle_{command_type}"):
                    handler = getattr(self, f"handle_{command_type}")
                    handler(incoming_command)
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
            

    def sendIbCommand(self, command):
        newcommand = command.copy()
        if "reqId" not in newcommand:
            newcommand["reqId"] = self.reqId
        self.mainframe.gui_to_ib.put(newcommand)
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

    def getStock(self, stock=""):
        #first cancel all other stock price streams
        #send command to ibapi to cancel all other streams
        self.cancelStreams()
        
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
    

    def handle_contractDetails(self, incoming_command):
        if incoming_command["kwargs"]["secType"] == "STK":

            self.conId = incoming_command["kwargs"]["conId"]
            self.requests[incoming_command["reqId"]]["conId"] = self.conId
            self.getStockPrice()
            self.reqSecDefOptParams()
        elif incoming_command["kwargs"]["secType"] == "OPT":
            reqId = incoming_command["kwargs"]["reqId"]
            self.options[reqId] = {
                "symbol": self.stock,
                "lastTradeDateOrContractMonth": incoming_command["kwargs"].get("lastTradeDateOrContractMonth", ""),
                "strike": int(incoming_command["kwargs"].get("strike", 0)),
                "right": incoming_command["kwargs"].get("right", ""),
            }
            self.renderGrid()
            command = {
                "method_name": "reqMktData",
                "conId": incoming_command["kwargs"]["conId"],
                "secType": "OPT",
            }

            self.sendIbCommand(command)


    def handle_tickPrice(self, incoming_command):
        request = self.requests[incoming_command["kwargs"]["reqId"]]
        if "contract"  in request and request["contract"].secType == "STK":
            if "price" in incoming_command["kwargs"]:
                self.stockprice = incoming_command["kwargs"]["price"]
                self.mainframe.txt_price.SetValue(f"{self.stockprice:.2f}")
            return
        if incoming_command["kwargs"].get("tickType") == 4:  # LAST price
            reqId = incoming_command["kwargs"]["reqId"]
            if reqId not in self.options:
                self.options[reqId] = {}
            self.options[reqId]["lastPrice"] = incoming_command["kwargs"]["price"]
            self.renderGrid()
        
    def handle_tickOptionComputation(self, incoming_command):
        reqId = incoming_command["kwargs"]["reqId"]
        if reqId not in self.options:
            self.options[reqId] = {}
        self.options[reqId]["impliedVol"] = incoming_command["kwargs"].get("impliedVol", None)
        self.options[reqId]["delta"] = incoming_command["kwargs"].get("delta", None)
        self.options[reqId]["gamma"] = incoming_command["kwargs"].get("gamma", None)
        self.options[reqId]["theta"] = incoming_command["kwargs"].get("theta", None)
        self.options[reqId]["vega"] = incoming_command["kwargs"].get("vega", None)
        self.options[reqId]["optPrice"] = incoming_command["kwargs"].get("optPrice", None)
        self.mainframe.txt_price.SetValue(f"{self.stockprice:.2f} | Options: {len(self.options)}")
        self.renderGrid()

    def handle_securityDefinitionOptionParameter(self, incoming_command):
        today = datetime.date.today()
        for expiration in incoming_command["kwargs"].get("expirations", []):
            max_weeks = int(self.mainframe.choice_weeks.GetStringSelection())
            expiration_date = datetime.datetime.strptime(expiration, "%Y%m%d").date()
            delta_weeks = (expiration_date - today).days // 7
            if 0 < delta_weeks <= max_weeks:
                self.expirations.append(expiration)
        self.expirations = sorted(self.expirations)
        self.strikes = sorted(incoming_command["kwargs"].get("strikes", []))
        print(len(self.expirations) * len(self.strikes), "options found")

        for expiration in self.expirations:
            for strike in self.strikes:
                option_type = "P"
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

    def renderGrid(self):
        grid = self.mainframe.grid
        grid.ClearGrid()
        row = 0
        for reqId, option in self.options.items():
            if row >= grid.GetNumberRows():
                grid.AppendRows(1)
            grid.SetCellValue(row, 0, option.get("lastTradeDateOrContractMonth", ""))
            grid.SetCellValue(row, 1, f"{option.get('strike', 0.0):.2f}")
            grid.SetCellValue(row, 2, option.get("right", ""))
            grid.SetCellValue(row, 3, f"{option.get('delta', 0.0):.4f}" if option.get('delta') is not None else "")
            grid.SetCellValue(row, 4, f"{option.get('optPrice', 0.0):.2f}" if option.get('optPrice') is not None else "")
            grid.SetCellValue(row, 5, f"{option.get('impliedVol', 0.0):.2%}" if option.get('impliedVol') is not None else "")
            if self.stockprice and option.get('optPrice') is not None:
                ppd = self.stockprice - option['strike'] + option['optPrice'] if option['right'] == 'P' else option['strike'] - self.stockprice + option['optPrice']
                grid.SetCellValue(row, 6, f"{ppd:.2f}")
                roi = (ppd / (option['strike'] * 100)) * 52 if option['strike'] > 0 else 0
                grid.SetCellValue(row, 7, f"{roi:.2%}")
            row += 1
        grid.AutoSizeColumns()