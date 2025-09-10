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
                method_name = command["method_name"]
                #print(f"trying to handle method: {method_name}")
                if hasattr(self, f"handle_{method_name}"):
                    handler = getattr(self, f"handle_{method_name}")
                    handler(incoming_command)
            

    def sendIbCommand(self, command):
        newcommand = command.copy()
        if "reqId" not in newcommand:
            newcommand["reqId"] = self.reqId
        self.mainframe.gui_to_ib.put(newcommand)
        self.requests[self.reqId] = newcommand
        self.reqId += 1

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
    

    def handle_reqContractDetails(self, incoming_command):
        if incoming_command["kwargs"]["secType"] == "STK":

            self.conId = incoming_command["kwargs"]["conId"]
            self.requests[incoming_command["reqId"]]["conId"] = self.conId
            self.getStockPrice()
            self.reqSecDefOptParams()
        elif incoming_command["kwargs"]["secType"] == "OPT":
            self.options[incoming_command["kwargs"]["conId"]] = {
                "symbol": self.stock,
                "lastTradeDateOrContractMonth": incoming_command["kwargs"].get("lastTradeDateOrContractMonth", ""),
                "strike": incoming_command["kwargs"].get("strike", 0.0),
                "right": incoming_command["kwargs"].get("right", ""),
            }
            command = {
                "method_name": "reqMktData",
                "conId": incoming_command["kwargs"]["conId"],
                "secType": "OPT",
            }

            self.sendIbCommand(command)


    def handle_reqMktData(self, incoming_command):
        request = self.requests[incoming_command["kwargs"]["reqId"]]
        if "contract"  in request and request["contract"].secType == "STK":
            if "price" in incoming_command["kwargs"]:
                self.stockprice = incoming_command["kwargs"]["price"]
                self.mainframe.txt_price.SetValue(f"{self.stockprice:.2f}")
            return

        #elif incoming_command["secType"] == "OPT":
        #    conId = incoming_command["kwargs"]["conId"]
        #    print(f"Option market data for conId {conId}: {incoming_command['kwargs']}")
        #else:
        #    print(f"Unknown secType in reqMktData: {incoming_command['kwargs']}") do i know if it is stock or option market data?
        


    def handle_reqSecDefOptParams(self, incoming_command):
        if self.strikes or self.expirations:
            return
        #print(f"Handling reqSecDefOptParams: {incoming_command}")
        today = datetime.date.today()
        for expiration in incoming_command["kwargs"].get("expirations", []):
            max_weeks = int(self.mainframe.choice_weeks.GetStringSelection())
            expiration_date = datetime.datetime.strptime(expiration, "%Y%m%d").date()
            #calculate the difference in weeks between today and expiration_date
            delta_weeks = (expiration_date - today).days // 7
            if 0 < delta_weeks <= max_weeks:
                self.expirations.append(expiration)
        self.expirations = sorted(self.expirations)
        self.strikes = sorted(incoming_command["kwargs"].get("strikes", []))

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