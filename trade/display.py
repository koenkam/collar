import datetime
from config import create_c
c=create_c()

class Displayer:

    def __init__(self, controller):
        self.controller = controller
        self.mainframe = controller.mainframe

    def updatePortfolioDisplay(self):
        grid = self.mainframe.grid_portfolio
        portfolio = self.controller.portfolio
        portfolio_gui_map = self.controller.portfolio_gui_map
        # Ensure enough rows
        current_rows = grid.GetNumberRows()
        required_rows = len(portfolio.items())
        if required_rows > current_rows:
            grid.AppendRows(required_rows - current_rows)
        elif required_rows < current_rows:
            grid.DeleteRows(0, current_rows - required_rows)
        
        for instrument_id, position in portfolio.items():
            if not position.dirty:
                pass
                #return
            position.dirty = False
            contract = position.contract
            if instrument_id in portfolio_gui_map:
                row = portfolio_gui_map[instrument_id]
            else:
                row = max(portfolio_gui_map.values(), default=-1) + 1
                portfolio_gui_map[instrument_id] = row
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
            strike = contract.strike if hasattr(contract, 'strike') else ""
            

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
            ppd_now = pl /dit
            
            underlying = position.underlyingPrice if hasattr(position, 'underlyingPrice') else ""
            if underlying and strike and lastPrice != 0.0 and contract.secType == 'OPT':
                assignvalue = -lastPrice * position.n * 100
                assignvalue += (strike - underlying) * position.n * 100
                itm_percentage = (underlying - strike) / strike * 100
                
            else:
                assignvalue = ""
                itm_percentage = ""

            closeat = (premium- dit * ppd)/ 100 / abs(position.n) if position.n != 0 else 0.0
            output = [
                contract.symbol,
                strike,
                underlying,
                itm_percentage,
                position.n,
                opttype,
                startdate,
                optexpire,
                premium,
                lastPrice,
                closeat,
                buyback,
                pl,
                days,
                dit,
                dte,
                ppd,
                ppd_now,
                assignvalue
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
                    color = "green"
                elif pl < 0 :
                    color = "red"
                else:
                    color = "white"
                self.mainframe.grid_portfolio.SetCellTextColour(row, pl_col, color)
            except (ValueError, TypeError):
                pass  # Ignore if conversion fails
        assign_col = self.findColumnByLabel("Assign")
        n_col = self.findColumnByLabel("N")
        if assign_col != -1:
            try:
                assign = float(output[assign_col])
                if assign < 0:
                    self.mainframe.grid_portfolio.SetCellTextColour(row, assign_col, "red")
                else:
                    # Reset to default background
                    self.mainframe.grid_portfolio.SetCellTextColour(row, assign_col, "white")
            except (ValueError, TypeError):
                pass  # Ignore if conversion fails
        itm_col = self.findColumnByLabel("ITM%")
        if itm_col != -1:
            try:
                itm = float(output[itm_col])
                if itm != "" and itm < -c.itm_threshold:
                    self.mainframe.grid_portfolio.SetCellTextColour(row, itm_col, "red")
                elif itm != "" and itm >= -c.itm_threshold:
                    self.mainframe.grid_portfolio.SetCellTextColour(row, itm_col, "white")
            except (ValueError, TypeError):
                pass  # Ignore if conversion fails
        closeat_col = self.findColumnByLabel("Close@")
        last_col = self.findColumnByLabel("Last")
        if closeat_col != -1 and last_col != -1:
            try:
                closeat = float(output[closeat_col])
                last = float(output[last_col])
                if last < closeat: # last is less than closeat
                    self.mainframe.grid_portfolio.SetCellTextColour(row, closeat_col, "green")
                else:
                    # Reset to default background
                    self.mainframe.grid_portfolio.SetCellTextColour(row, closeat_col, "white")
            except (ValueError, TypeError):
                pass  # Ignore if conversion fails