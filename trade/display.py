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
        """Highlight cells based on certain conditions using configurable rules"""
        highlighting_rules = [
            self._create_strike_underlying_rule(),
            self._create_ppd_comparison_rule(),
            self._create_pl_rule(),
            self._create_assign_rule(),
            self._create_itm_rule(),
            self._create_closeat_rule()
        ]
        
        for rule in highlighting_rules:
            self._apply_highlighting_rule(rule, output, row)
    
    def _create_strike_underlying_rule(self):
        """Rule for highlighting underlying price based on strike comparison"""
        return {
            'columns': ['Strike', 'Underlying'],
            'target_column': 'Underlying',
            'condition': lambda strike, underlying: underlying < strike,
            'colors': {'true': 'red', 'false': 'green'}
        }
    
    def _create_ppd_comparison_rule(self):
        """Rule for highlighting PPD_NOW based on PPD comparison"""
        return {
            'columns': ['PPD_NOW', 'PPD'],
            'target_column': 'PPD_NOW',
            'condition': lambda ppd_now, ppd: ppd_now > ppd,
            'colors': {'true': 'green', 'false': 'white'}
        }
    
    def _create_pl_rule(self):
        """Rule for highlighting P&L with three-way color coding"""
        def pl_condition(pl):
            if pl > 0:
                return 'positive'
            elif pl < 0:
                return 'negative'
            else:
                return 'neutral'
        
        return {
            'columns': ['PL'],
            'target_column': 'PL',
            'condition': pl_condition,
            'colors': {'positive': 'green', 'negative': 'red', 'neutral': 'white'},
            'multi_condition': True
        }
    
    def _create_assign_rule(self):
        """Rule for highlighting assignment value"""
        return {
            'columns': ['Assign'],
            'target_column': 'Assign',
            'condition': lambda assign: assign < 0,
            'colors': {'true': 'red', 'false': 'white'}
        }
    
    def _create_itm_rule(self):
        """Rule for highlighting ITM percentage based on threshold"""
        return {
            'columns': ['ITM%'],
            'target_column': 'ITM%',
            'condition': lambda itm: itm != "" and itm < -c.itm_threshold,
            'colors': {'true': 'red', 'false': 'white'},
            'allow_empty': True
        }
    
    def _create_closeat_rule(self):
        """Rule for highlighting close-at price based on last price comparison"""
        return {
            'columns': ['Close@', 'Last'],
            'target_column': 'Close@',
            'condition': lambda closeat, last: last < closeat,
            'colors': {'true': 'green', 'false': 'white'}
        }
    
    def _apply_highlighting_rule(self, rule, output, row):
        """Apply a single highlighting rule to the grid"""
        try:
            # Get column indices
            column_indices = {}
            for col_name in rule['columns']:
                col_index = self.findColumnByLabel(col_name)
                if col_index == -1:
                    return  # Skip rule if any required column is missing
                column_indices[col_name] = col_index
            
            # Extract values and convert to float
            values = []
            for col_name in rule['columns']:
                value = output[column_indices[col_name]]
                if value == "":
                    if rule.get('allow_empty', False):
                        values.append(value)
                    else:
                        return  # Skip if empty value not allowed
                else:
                    try:
                        values.append(float(value))
                    except (ValueError, TypeError):
                        if rule.get('allow_empty', False):
                            values.append(value)
                        else:
                            return
            
            # Apply condition
            if rule.get('multi_condition', False):
                # For rules with multiple return values (like PL rule)
                condition_result = rule['condition'](values[0])
                color = rule['colors'].get(condition_result, 'white')
            else:
                # For binary conditions
                condition_result = rule['condition'](*values)
                color = rule['colors']['true' if condition_result else 'false']
            
            # Apply color
            target_col = column_indices[rule['target_column']]
            self.mainframe.grid_portfolio.SetCellTextColour(row, target_col, color)
            
        except (ValueError, TypeError, KeyError):
            pass  # Ignore if conversion fails or rule is malformed