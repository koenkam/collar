from collections import OrderedDict
from ibapi.contract import Contract
import time
import datetime
from config import create_c
#from experiments import option
c = create_c()
from .firestore import FirestoreDB

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
        self.lastprice = {}
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
    
    def get_instrument_id_from_portfolio(self, positionkey):
        self.position = self.portfolio[positionkey]
        contract = self.position["contract"]
        return self.get_instrument_id_from_contract(contract)

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


    def tickPriceIsOptionPrice(self):
        reqId = self.incoming_command["kwargs"]["reqId"]
        if "strike" in self.requests[reqId]:
            return True
        return False

    def handle_tickPrice(self):
        instrument_id = self.get_instrument_id_from_request(self.incoming_command["kwargs"]["reqId"])
        request = self.requests[self.incoming_command["kwargs"]["reqId"]]
        price = None
        if "contract"  in request and request["contract"].secType == "STK":
            if "price" in self.incoming_command["kwargs"]:
                price = self.incoming_command["kwargs"]["price"]
                if self.mainframe.txt_stock.GetValue() == request["contract"].symbol:
                    self.stockprice = price
                    self.mainframe.txt_price.SetValue(f"{self.stockprice:.2f}")
                self.lastprice[instrument_id] = price
            return
        if self.incoming_command["kwargs"].get("tickType") == 4:  # LAST price
            price = self.incoming_command["kwargs"]["price"]
            if self.tickPriceIsOptionPrice():
                reqId = self.incoming_command["kwargs"]["reqId"]
                request = self.requests[reqId]
                optionKey = request["optionKey"]
                self.options[optionKey]["lastPrice"] = price
                self.renderGrid()
            else:
                self.stockprice = price
                self.mainframe.txt_price.SetValue(f"{self.stockprice:.2f}")
            self.lastprice[instrument_id] = price            
        
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
        if self.iter_option["delta"] is not None \
            and (self.iter_option["delta"] < c.delta_min \
                or self.iter_option["delta"] > c.delta_max):
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
        
        
        # Store in portfolio data structure
        if not hasattr(self, 'portfolio'):
            self.portfolio = {}
        
        position_key = self.get_instrument_id_from_contract(contract)
        self.portfolio[position_key] = {
            "account": account,
            "symbol": symbol,
            "secType": secType,
            "position": position,
            "avgCost": avgCost,
            "contract": contract,
            "premium": None,
            "startdate": None
        }

        self.firestore.merge_portfolio_item(position_key)
        
        # Update GUI portfolio display
        self.updatePortfolioDisplay()

        #now request the price of this instrument
        command = {
            "method_name": "reqMktData",
            "contract": contract,
        }
        self.sendIbCommand(command)


    def handle_positionEnd(self):
        # Final GUI update or summary calculations
        self.finalizePortfolioDisplay()

    def updatePortfolioDisplay(self):
        if not hasattr(self, 'portfolio'):
            return
        portfolio_items = list(self.portfolio.values())
        grid = self.mainframe.grid_portfolio
        
        # Ensure enough rows
        current_rows = grid.GetNumberRows()
        required_rows = len(portfolio_items)
        if required_rows > current_rows:
            grid.AppendRows(required_rows - current_rows)
        elif required_rows < current_rows:
            grid.DeleteRows(0, current_rows - required_rows)
        
        for instrument_id, position in self.portfolio.items():
            print("INSTRUMENT ID", instrument_id, self.portfolio_gui_map)
            if instrument_id in self.portfolio_gui_map:
                row = self.portfolio_gui_map[instrument_id]
            else:
                row = max(self.portfolio_gui_map.values(), default=-1) + 1
                self.portfolio_gui_map[instrument_id] = row
            if position.get('secType') == 'OPT':
                opttype = 'PUT' if position['contract'].right == 'P' else 'CALL'
                optexpire = position['contract'].lastTradeDateOrContractMonth
            else:
                opttype = position['secType']
                optexpire = ""
            col = 0
            print("ROW", row, position)
            grid.SetCellValue(row, col, position.get("symbol", ""))
            col += 1
            grid.SetCellValue(row, col, f"{int(position.get('position', 0.0))}")
            col += 1
            grid.SetCellValue(row, col, opttype)
            col += 1
            grid.SetCellValue(row, col, position.get('startdate', ''))
            col += 1
            grid.SetCellValue(row, col , optexpire)
            col += 1
            grid.SetCellValue(row, col, f"{position.get('premium', 0.0):.2f}")
        grid.AutoSizeColumns()

    def finalizePortfolioDisplay(self):
        """Final portfolio display update"""
        pass

