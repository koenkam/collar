import wx
import wx.grid
import threading
import queue
import time
from datetime import datetime
import pytz
from .api import IBApi
from config import create_c
from .controller import Controller
from .display import Displayer
from util import parse_premium, resolve_startdate
from .logbook import compute_collar_totals, format_log_row, format_totals, short_put_notional
from .records_ui import RecordsDialog
from .screener_ui import SellPutsFrame, WatchlistDialog, accelerator as screener_accelerator
c=create_c()

class EditPositionDialog(wx.Dialog):
    def __init__(self, parent, controller, symbol="", instrument_id="", start_value="", premium_value=""):
        super().__init__(parent, title="Edit Position", size=(400, 220))
        
        self.controller = controller  # Add controller reference
        self.symbol = symbol
        self.instrument_id = instrument_id
        self.start_value = start_value
        position = controller.option_portfolio.get(instrument_id)
        self.is_long = bool(position is not None and (position.n or 0) > 0)
        if self.is_long:
            try:
                paid = parse_premium(premium_value)
            except ValueError:
                paid = None
            premium_value = "" if paid is None else f"{abs(paid):.2f}"
        self.premium_value = premium_value
        
        self.init_ui()
        
    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Symbol label
        lbl_symbol = wx.StaticText(panel, label=f"Symbol: {self.symbol}")
        font = lbl_symbol.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        lbl_symbol.SetFont(font)
        
        # Instrument ID as copyable text control
        hbox_id = wx.BoxSizer(wx.HORIZONTAL)
        lbl_id = wx.StaticText(panel, label="Instrument ID:")
        self.txt_instrument_id = wx.TextCtrl(panel, value=str(self.instrument_id), 
                                           style=wx.TE_READONLY)
        self.txt_instrument_id.SetBackgroundColour(wx.Colour(0, 0, 0))      # Black background
        self.txt_instrument_id.SetForegroundColour(wx.Colour(255, 255, 255)) # White text
        hbox_id.Add(lbl_id, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=8)
        hbox_id.Add(self.txt_instrument_id, proportion=1)
        
        # Start value input
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_start = wx.StaticText(panel, label="Start:")
        self.txt_start = wx.TextCtrl(panel, value=resolve_startdate(self.start_value))
        hbox1.Add(lbl_start, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=8)
        hbox1.Add(self.txt_start, proportion=1)
        
        # Premium value input
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_premium = wx.StaticText(panel, label="Paid:" if self.is_long else "Premium:")
        self.txt_premium = wx.TextCtrl(panel, value=str(self.premium_value))
        hbox2.Add(lbl_premium, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=8)
        hbox2.Add(self.txt_premium, proportion=1)
        
        # Buttons
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_save = wx.Button(panel, wx.ID_OK, "Save")
        
        # Bind save button event
        btn_save.Bind(wx.EVT_BUTTON, self.on_save)
        
        hbox3.Add(btn_cancel, flag=wx.RIGHT, border=5)
        hbox3.Add(btn_save)
        
        # Add all to main sizer
        vbox.Add(lbl_symbol, flag=wx.EXPAND | wx.ALL, border=10)
        vbox.Add(hbox_id, flag=wx.EXPAND | wx.ALL, border=10)
        vbox.Add(hbox1, flag=wx.EXPAND | wx.ALL, border=10)
        vbox.Add(hbox2, flag=wx.EXPAND | wx.ALL, border=10)
        vbox.Add(hbox3, flag=wx.ALIGN_RIGHT | wx.ALL, border=10)
        
        panel.SetSizer(vbox)
    
    def on_save(self, event):
        """Handle save button click"""
        start_value = resolve_startdate(self.txt_start.GetValue())
        premium_raw = self.txt_premium.GetValue()
        
        try:
            premium_value = parse_premium(premium_raw)
        except ValueError:
            wx.MessageBox(
                "Premium must be a valid number, for example: $ 1,450.23, $1,203.10, $231.40, 10, $10,500",
                "Invalid Input",
                wx.OK | wx.ICON_ERROR
            )
            return
        if self.is_long and premium_value is not None:
            premium_value = -abs(premium_value)
        
        self._saved_start = start_value
        self._saved_premium = premium_value
        
        fields = {"startdate": start_value}
        if premium_value is not None:
            fields["premium"] = premium_value
        try:
            success = self.controller.update_option_fields(self.instrument_id, fields)
        except Exception as e:
            print(f"Error saving {self.instrument_id}: {e}")
            success = False
        
        if success:
            # Close dialog with OK result
            self.EndModal(wx.ID_OK)
        else:
            wx.MessageBox("Failed to save to database", "Save Error", wx.OK | wx.ICON_ERROR)
        
    def get_values(self):
        """Return the entered values"""
        start = getattr(self, "_saved_start", resolve_startdate(self.txt_start.GetValue()))
        if hasattr(self, "_saved_premium"):
            return start, self._saved_premium
        try:
            premium = parse_premium(self.txt_premium.GetValue())
        except ValueError:
            return None, None
        if self.is_long and premium is not None:
            premium = -abs(premium)
        return start, premium

class EditStockDialog(wx.Dialog):
    def __init__(self, parent, controller, symbol="", instrument_id="", avg_cost=""):
        super().__init__(parent, title="Edit Stock Position", size=(400, 180))
        
        self.controller = controller
        self.symbol = symbol
        self.instrument_id = instrument_id
        self.avg_cost = avg_cost
        
        self.init_ui()
        
    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Symbol label
        lbl_symbol = wx.StaticText(panel, label=f"Symbol: {self.symbol}")
        font = lbl_symbol.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        lbl_symbol.SetFont(font)
        
        # Instrument ID as copyable text control
        hbox_id = wx.BoxSizer(wx.HORIZONTAL)
        lbl_id = wx.StaticText(panel, label="Instrument ID:")
        self.txt_instrument_id = wx.TextCtrl(panel, value=str(self.instrument_id), 
                                           style=wx.TE_READONLY)
        self.txt_instrument_id.SetBackgroundColour(wx.Colour(0, 0, 0))      # Black background
        self.txt_instrument_id.SetForegroundColour(wx.Colour(255, 255, 255)) # White text
        hbox_id.Add(lbl_id, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=8)
        hbox_id.Add(self.txt_instrument_id, proportion=1)
        
        # Avg Cost input
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_cost = wx.StaticText(panel, label="Buy Price:")
        self.txt_cost = wx.TextCtrl(panel, value=str(self.avg_cost))
        hbox2.Add(lbl_cost, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=8)
        hbox2.Add(self.txt_cost, proportion=1)
        
        # Buttons
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_save = wx.Button(panel, wx.ID_OK, "Save")
        
        # Bind save button event
        btn_save.Bind(wx.EVT_BUTTON, self.on_save)
        
        hbox3.Add(btn_cancel, flag=wx.RIGHT, border=5)
        hbox3.Add(btn_save)
        
        # Add all to main sizer
        vbox.Add(lbl_symbol, flag=wx.EXPAND | wx.ALL, border=10)
        vbox.Add(hbox_id, flag=wx.EXPAND | wx.ALL, border=10)
        vbox.Add(hbox2, flag=wx.EXPAND | wx.ALL, border=10)
        vbox.Add(hbox3, flag=wx.ALIGN_RIGHT | wx.ALL, border=10)
        
        panel.SetSizer(vbox)
    
    def on_save(self, event):
        """Handle save button click"""
        avg_cost = self.txt_cost.GetValue().strip()
        
        # Validate avg cost
        try:
            if avg_cost:
                float(avg_cost)  # Test if it's a valid number
        except ValueError:
            wx.MessageBox("Buy Price must be a valid number", "Invalid Input", wx.OK | wx.ICON_ERROR)
            return
        
        try:
            success = self.controller.update_stock_fields(
                self.instrument_id,
                {"avgCost": float(avg_cost) if avg_cost else 0.0},
            )
        except Exception as e:
            print(f"Error saving {self.instrument_id}: {e}")
            success = False
        
        if success:
            # Close dialog with OK result
            self.EndModal(wx.ID_OK)
        else:
            wx.MessageBox("Failed to save to database", "Save Error", wx.OK | wx.ICON_ERROR)
        
    def get_values(self):
        """Return the entered values"""
        try:
            cost = self.txt_cost.GetValue().strip()
            return cost if cost else 0
        except ValueError:
            return 0

class MainFrame(wx.Frame):

    def __init__(self, controller):
        super().__init__(None, title="The Collar", size=(1400, 800))
        self.controller = controller
        self.controller.mainframe = self  # Set the mainframe reference in controller
        self.controller.displayer = Displayer(self.controller)  # Initialize Displayer
        self.screener_frame = None
        self.init_ui()
        
        self.last_save_time = 0
        
        # Timer to check for incoming data
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(50)  # Check every 500ms

    def init_ui(self):
        self.panel = wx.Panel(self)
        self.vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Add time display panel at the top
        self.render_time_display()
        self.render_totals()
        
        self.render_portfolio()
        self.render_stock()
        self.render_log()

        self.panel.SetSizer(self.vbox)
        self.render_menu()
        self.Centre()

    def render_menu(self):
        menubar = wx.MenuBar()
        trade = wx.Menu()
        sell = trade.Append(wx.ID_ANY, f"Sell puts...\t{screener_accelerator()}")
        watchlist = trade.Append(wx.ID_ANY, "Watchlist...")
        records = trade.Append(wx.ID_ANY, "Records...")
        review = trade.Append(wx.ID_ANY, "Review...")
        self.Bind(wx.EVT_MENU, self.open_screener, sell)
        self.Bind(wx.EVT_MENU, self.open_watchlist, watchlist)
        self.Bind(wx.EVT_MENU, lambda event: self.open_records("options"), records)
        self.Bind(wx.EVT_MENU, lambda event: self.open_records("review"), review)
        menubar.Append(trade, "&Trade")
        self.SetMenuBar(menubar)

    def render_time_display(self):
        """Create and add the time display panel"""
        # Create a horizontal box for time display
        time_hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        # Create static text for time display
        self.time_label = wx.StaticText(self.panel, label="US Eastern Time: ")
        self.time_display = wx.StaticText(self.panel, label="Loading...")
        
        # Style the time display
        font = self.time_display.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        font.SetPointSize(12)
        self.time_display.SetFont(font)
        self.time_display.SetForegroundColour(wx.Colour(0, 255, 0))
        
        self.account_label = wx.StaticText(self.panel, label="Account: ")
        self.account_display = wx.StaticText(self.panel, label="Loading...")
        self.account_display.SetFont(font)
        self.account_display.SetForegroundColour(wx.Colour(0, 255, 0))
        
        # Add to horizontal sizer
        time_hbox.Add(self.time_label, flag=wx.ALIGN_CENTER_VERTICAL)
        time_hbox.Add(self.time_display, flag=wx.ALIGN_CENTER_VERTICAL)
        
        # Add spacer to push account value to the right
        time_hbox.AddStretchSpacer()
        
        time_hbox.Add(self.account_label, flag=wx.ALIGN_CENTER_VERTICAL)
        time_hbox.Add(self.account_display, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=10)
        
        # Add to main vertical sizer
        self.vbox.Add(time_hbox, flag=wx.EXPAND|wx.ALL, border=10)
        
        # Update time display immediately
        self.update_time_display()
        self.update_account_display()

    def render_totals(self):
        """Fixed strip for the Log totals. Current value stays in the account label."""
        self.totals_line1 = wx.StaticText(self.panel, label="")
        self.totals_line2 = wx.StaticText(self.panel, label="")
        font = self.totals_line1.GetFont()
        font.SetPointSize(11)
        self.totals_line1.SetFont(font)
        self.totals_line2.SetFont(font)
        self._totals_text = None
        self.vbox.Add(self.totals_line1, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=10)
        self.vbox.Add(self.totals_line2, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)

        status_hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.status_text = wx.StaticText(self.panel, label="", style=wx.ST_ELLIPSIZE_END)
        self.btn_review = wx.Button(self.panel, label="Review")
        self.btn_records = wx.Button(self.panel, label="Records")
        self.btn_screener = wx.Button(self.panel, label="Sell puts")
        self.btn_review.Bind(wx.EVT_BUTTON, lambda event: self.open_records("review"))
        self.btn_records.Bind(wx.EVT_BUTTON, lambda event: self.open_records("options"))
        self.btn_screener.Bind(wx.EVT_BUTTON, self.open_screener)
        status_hbox.Add(self.status_text, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL)
        status_hbox.Add(self.btn_screener, flag=wx.LEFT, border=8)
        status_hbox.Add(self.btn_review, flag=wx.LEFT, border=8)
        status_hbox.Add(self.btn_records, flag=wx.LEFT, border=8)
        self.vbox.Add(status_hbox, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, border=10)
        self._status_text = None
        self.update_totals_display()
        self.update_status()

    def update_status(self):
        text = getattr(self.controller, "status_message", "") or ""
        reviews = len(getattr(self.controller, "review", {}) or {})
        state = (text, reviews)
        if state == self._status_text:
            return
        self._status_text = state
        self.status_text.SetLabel(text)
        self.status_text.SetToolTip(text)
        self.btn_review.SetLabel(f"Review ({reviews})")
        self.btn_review.Show(reviews > 0)
        self.panel.Layout()

    def refresh_book_views(self):
        self.fill_log_grid()
        self.update_totals_display()
        self.update_status()

    def open_screener(self, event=None):
        frame = self.screener_frame
        if frame is not None:
            try:
                frame.Show()
                frame.Raise()
                frame.refresh()
                return
            except RuntimeError:
                self.screener_frame = None
        self.screener_frame = SellPutsFrame(self, self.controller)
        self.screener_frame.Show()
        self.screener_frame.Raise()

    def open_watchlist(self, event=None):
        dialog = WatchlistDialog(self, self.controller)
        dialog.ShowModal()
        dialog.Destroy()
        if self.screener_frame:
            self.screener_frame.refresh()

    def open_records(self, page):
        self.controller.book_paused = True
        try:
            dialog = RecordsDialog(self, self.controller, page)
            dialog.ShowModal()
            dialog.Destroy()
        finally:
            self.controller.book_paused = False
            self.controller.schedule_book()

    def update_totals_display(self):
        totals = compute_collar_totals(
            getattr(self.controller, "summary", None),
            getattr(self.controller, "log_trades", None),
            getattr(self.controller, "account_value", None),
            short_put_notional(
                getattr(self.controller, "option_portfolio", None), c.cash_settled_symbols,
            ),
            max_fraction=c.max_collateral_fraction,
        )
        line1, line2 = format_totals(totals)
        text = (line1, line2)
        if text == self._totals_text:
            return
        self._totals_text = text
        self.totals_line1.SetLabel(line1)
        self.totals_line2.SetLabel(line2)
        self.panel.Layout()

    def _lock_grid_height(self, grid, visible_rows):
        """Keep a grid at a fixed height so extra window space goes to the log."""
        height = grid.GetColLabelSize() + visible_rows * grid.GetDefaultRowSize() + 4
        grid.SetMinSize(wx.Size(200, height))
        grid.SetMaxSize(wx.Size(-1, height))

    def update_time_display(self):
        """Update the time display with current Eastern time"""
        try:
            # Get current time in Eastern timezone
            eastern = pytz.timezone('US/Eastern')
            now = datetime.now(eastern)
            
            # Format as "Monday, October 30, 2025 - 15:45:30 EDT"
            time_str = now.strftime("%A, %B %d, %Y - %H:%M:%S %Z")
            
            # Update the display
            self.time_display.SetLabel(time_str)
        except Exception as e:
            self.time_display.SetLabel("Time Error")

    def update_account_display(self):
        """Update the account value display from the IB account summary"""
        value = getattr(self.controller, "account_value", None)
        if value is None:
            self.account_display.SetLabel("Loading...")
            return
        currency = getattr(self.controller, "account_currency", "USD") or "USD"
        if currency == "USD":
            self.account_display.SetLabel(f"${value:,.2f}")
        else:
            self.account_display.SetLabel(f"{value:,.2f} {currency}")
        self.panel.Layout()

    def render_portfolio(self):
        hbox0 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_portfolio = wx.StaticText(self.panel, label='Options')
        hbox0.Add(lbl_portfolio, flag=wx.RIGHT, border=8)        
        self.grid_portfolio = wx.grid.Grid(self.panel)
        self.grid_portfolio.CreateGrid(c.portfolio_visible_rows, len(c.portfolio_labels))
        for col, label in enumerate(c.portfolio_labels):
            self.grid_portfolio.SetColLabelValue(col, label)
    
        # Make the entire grid read-only
        self.grid_portfolio.EnableEditing(False)
    
        # align all columns to the right
        for col, label in enumerate(c.portfolio_labels):
            if label in c.portfolio_columns_left:
                attr = wx.grid.GridCellAttr()
                attr.SetAlignment(wx.ALIGN_LEFT, wx.ALIGN_CENTER)
                attr.SetReadOnly(True)  # Make cells read-only
                self.grid_portfolio.SetColAttr(col, attr)
            else:
                attr = wx.grid.GridCellAttr()
                attr.SetReadOnly(True)  # Make cells read-only
                self.grid_portfolio.SetColAttr(col, attr)
                self.grid_portfolio.SetColFormatNumber(col)
    
        # Bind grid cell click event
        self.grid_portfolio.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK, self.on_portfolio_cell_click)
    
        self.grid_portfolio.AutoSizeColumns()
        self._lock_grid_height(self.grid_portfolio, c.portfolio_visible_rows)
        self.vbox.Add(hbox0, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        self.vbox.Add(self.grid_portfolio, proportion=0, flag=wx.EXPAND|wx.ALL, border=10)

    def on_portfolio_cell_click(self, event):
        """Handle click on portfolio grid cell"""
        row = event.GetRow()
        
        # Get the instrument_id using the controller method
        instrument_id = self.controller.get_instrument_id_from_grid_row(row)
        if instrument_id is None:
            instrument_id = "Unknown"
        
        # Get current values from the grid
        symbol_col = self.get_column_index("Symbol")
        start_col = self.get_column_index("Start")
        premium_col = self.get_column_index("Premium")
        
        current_symbol = ""
        current_start = ""
        current_premium = ""
        
        if symbol_col is not None:
            current_symbol = self.grid_portfolio.GetCellValue(row, symbol_col)
        if start_col is not None:
            current_start = self.grid_portfolio.GetCellValue(row, start_col)
        if premium_col is not None:
            current_premium = self.grid_portfolio.GetCellValue(row, premium_col)
        
        # Show the edit dialog with controller reference
        dialog = EditPositionDialog(self, self.controller, current_symbol, instrument_id, current_start, current_premium)
        
        if dialog.ShowModal() == wx.ID_OK:
            # User clicked Save - data was already saved to Firestore
            start, premium = dialog.get_values()
            
            if start is not None and start_col is not None:
                self.grid_portfolio.SetCellValue(row, start_col, str(start))
            if premium is not None and premium_col is not None:
                self.grid_portfolio.SetCellValue(row, premium_col, str(premium))
            
            self.update_position_data(row, start, premium)
            self.grid_portfolio.ForceRefresh()
        
        dialog.Destroy()
        event.Skip()  # Allow normal grid processing
    
    def get_column_index(self, label_name):
        """Get the column index for a given label"""
        try:
            return c.portfolio_labels.index(label_name)
        except ValueError:
            return None
    
    def update_position_data(self, row, start, premium):
        """Update the position data in the controller"""
        # Use the controller method to get the instrument_id
        instrument_id = self.controller.get_instrument_id_from_grid_row(row)
        
        if instrument_id and instrument_id in self.controller.option_portfolio:
            position = self.controller.option_portfolio[instrument_id]
            
            # Update the position data
            try:
                if start:
                    position.startdate = start
                if premium is not None:
                    position.premium = float(premium)
                
                position.dirty = True
                
                # Trigger a display update
                if hasattr(self.controller, 'displayer'):
                    self.controller.displayer.updatePortfolioDisplay()
                    
                
            except ValueError as e:
                wx.MessageBox(f"Invalid value entered: {e}", "Error", wx.OK | wx.ICON_ERROR)

    def render_stock(self):
        lbl_stock = wx.StaticText(self.panel, label='Stock')
        self.grid_stock = wx.grid.Grid(self.panel)
        self.grid_stock.CreateGrid(c.stock_visible_rows, len(c.stock_labels))
        for col, label in enumerate(c.stock_labels):
            self.grid_stock.SetColLabelValue(col, label)
            if label in c.stock_columns_left:
                attr = wx.grid.GridCellAttr()
                attr.SetAlignment(wx.ALIGN_LEFT, wx.ALIGN_CENTER)
                self.grid_stock.SetColAttr(col, attr)
            else:
                self.grid_stock.SetColFormatNumber(col)
        self._lock_grid_height(self.grid_stock, c.stock_visible_rows)
        #add all elements to self.vbox
        self.vbox.Add(lbl_stock, flag=wx.LEFT, border=8)
        self.vbox.Add(self.grid_stock, proportion=0, flag=wx.EXPAND|wx.ALL, border=10)
        
        # Bind grid cell click event
        self.grid_stock.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK, self.on_stock_cell_click)

    def on_stock_cell_click(self, event):
        """Handle click on stock grid cell"""
        row = event.GetRow()
        
        # Get the instrument_id using the controller method
        instrument_id = self.controller.get_stock_instrument_id_from_grid_row(row)
        if instrument_id is None:
            instrument_id = "Unknown"
        
        # Get current values from the grid
        symbol_col = -1
        try:
            symbol_col = c.stock_labels.index("Symbol")
        except ValueError:
            pass
            
        # Assuming stock grid has "Buy" for avgCost. "Start" might not be in stock_labels, need to check.
        # c.stock_labels = ["Symbol", "N", "Buy","Last", "Profit"]
        # It doesn't have "Start". But Firestore stores it.
        # If it's not in the grid, we can't get it from the grid.
        # We should try to get it from the controller/portfolio if possible, or just leave it blank.
        
        buy_col = -1
        try:
            buy_col = c.stock_labels.index("Buy")
        except ValueError:
            pass
            
        current_symbol = ""
        current_start = "" # Not in grid
        current_cost = ""
        
        if symbol_col != -1:
            current_symbol = self.grid_stock.GetCellValue(row, symbol_col)
        if buy_col != -1:
            current_cost = self.grid_stock.GetCellValue(row, buy_col)
            
        # Try to get start date and avg cost from controller if available
        if instrument_id in self.controller.stock_portfolio:
            pos = self.controller.stock_portfolio[instrument_id]
            if hasattr(pos, 'startdate'):
                current_start = pos.startdate
            if hasattr(pos, 'avgCost'):
                current_cost = pos.avgCost
        
        # Show the edit dialog with controller reference
        dialog = EditStockDialog(self, self.controller, current_symbol, instrument_id, current_cost)
        
        if dialog.ShowModal() == wx.ID_OK:
            # User clicked Save - data was already saved to Firestore
            cost = dialog.get_values()
            
            if cost is not None:
                # Update the grid display
                if buy_col != -1:
                    self.grid_stock.SetCellValue(row, buy_col, str(cost))
                
                # Update the controller/position data
                self.update_stock_data(row, cost)
                
                # Refresh the grid
                self.grid_stock.ForceRefresh()
        
        dialog.Destroy()
        event.Skip()  # Allow normal grid processing

    def render_log(self):
        lbl_log = wx.StaticText(self.panel, label="Log")
        self.grid_log = wx.grid.Grid(self.panel)
        self.grid_log.CreateGrid(0, len(c.log_labels))
        self.grid_log.EnableEditing(False)
        for col, label in enumerate(c.log_labels):
            self.grid_log.SetColLabelValue(col, label)
            attr = wx.grid.GridCellAttr()
            attr.SetReadOnly(True)
            if label in c.log_columns_left:
                attr.SetAlignment(wx.ALIGN_LEFT, wx.ALIGN_CENTER)
            else:
                attr.SetAlignment(wx.ALIGN_RIGHT, wx.ALIGN_CENTER)
            self.grid_log.SetColAttr(col, attr)
        self.vbox.Add(lbl_log, flag=wx.LEFT | wx.TOP, border=8)
        self.vbox.Add(self.grid_log, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)
        self.fill_log_grid()

    def fill_log_grid(self):
        trades = getattr(self.controller, "log_trades", None) or []
        grid = self.grid_log
        current = grid.GetNumberRows()
        if current:
            grid.DeleteRows(0, current)
        if trades:
            grid.AppendRows(len(trades))
        for row, trade in enumerate(trades):
            for col, value in enumerate(format_log_row(trade)):
                grid.SetCellValue(row, col, value)
        grid.AutoSizeColumns()

    def update_stock_data(self, row, cost):
        """Update the stock position data in the controller"""
        # Use the controller method to get the instrument_id
        instrument_id = self.controller.get_stock_instrument_id_from_grid_row(row)
        
        if instrument_id and instrument_id in self.controller.stock_portfolio:
            position = self.controller.stock_portfolio[instrument_id]
            
            # Update the position data
            try:
                if cost is not None:
                    position.avgCost = float(cost)
                
                position.dirty = True
                
                # Trigger a display update
                if hasattr(self.controller, 'displayer'):
                    self.controller.displayer.updatePortfolioDisplay()
                    
            except ValueError as e:
                wx.MessageBox(f"Invalid value entered: {e}", "Error", wx.OK | wx.ICON_ERROR)

    def on_stock_selected(self, event):
        selected_stock = self.choice.GetStringSelection()
        self.txt_stock.SetValue(selected_stock)

    def on_load(self, event):
        stock = self.txt_stock.GetValue()
        if stock:
            self.controller.getStock(stock)

    def on_timer(self, event):
        self.controller.process_incoming_data()
        self.controller.tick()
        status = self.controller.get_connection_status()        
        self.SetTitle(f"The Collar - {status}")
        
        # Check if it's time to save prices
        current_time = time.time()
        if current_time - self.last_save_time > c.save_interval_minutes * 60:
            self.last_save_time = current_time
            threading.Thread(target=self.controller.firestore.save_current_prices).start()
        
        # Update time and account displays
        self.update_time_display()
        self.update_account_display()
        self.update_totals_display()
