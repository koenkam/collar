import wx
import wx.grid
import threading
import queue
from datetime import datetime
import pytz
from .api import IBApi
from config import create_c
from .controller import Controller
from .display import Displayer
c=create_c()

class EditPositionDialog(wx.Dialog):
    def __init__(self, parent, controller, symbol="", instrument_id="", start_value="", premium_value=""):
        super().__init__(parent, title="Edit Position", size=(400, 220))
        
        self.controller = controller  # Add controller reference
        self.symbol = symbol
        self.instrument_id = instrument_id
        self.start_value = start_value
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
        self.txt_start = wx.TextCtrl(panel, value=str(self.start_value))
        hbox1.Add(lbl_start, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=8)
        hbox1.Add(self.txt_start, proportion=1)
        
        # Premium value input
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_premium = wx.StaticText(panel, label="Premium:")
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
        start_value = self.txt_start.GetValue().strip()
        premium_value = self.txt_premium.GetValue().strip()
        
        # Validate premium value
        try:
            if premium_value:
                float(premium_value)  # Test if it's a valid number
        except ValueError:
            wx.MessageBox("Premium must be a valid number", "Invalid Input", wx.OK | wx.ICON_ERROR)
            return
        
        # Save to Firestore - use 'firestore' instead of 'firestoredb'
        success = self.controller.firestore.update_position(
            self.instrument_id, 
            start_value if start_value else None,
            premium_value if premium_value else None
        )
        
        if success:
            # Close dialog with OK result
            self.EndModal(wx.ID_OK)
        else:
            wx.MessageBox("Failed to save to database", "Save Error", wx.OK | wx.ICON_ERROR)
        
    def get_values(self):
        """Return the entered values"""
        try:
            start = self.txt_start.GetValue()
            premium = self.txt_premium.GetValue()
            return start, premium
        except ValueError:
            return None, None

class MainFrame(wx.Frame):

    def __init__(self, controller):
        super().__init__(None, title="The Collar", size=(1400, 800))
        self.controller = controller
        self.controller.mainframe = self  # Set the mainframe reference in controller
        self.controller.displayer = Displayer(self.controller)  # Initialize Displayer
        self.init_ui()
        
        # Timer to check for incoming data
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(50)  # Check every 500ms

    def init_ui(self):
        self.panel = wx.Panel(self)
        self.vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Add time display panel at the top
        self.render_time_display()
        
        self.render_portfolio()
        self.render_stock()

        self.panel.SetSizer(self.vbox)
        self.Centre()

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
        
        # Add to horizontal sizer
        time_hbox.Add(self.time_label, flag=wx.ALIGN_CENTER_VERTICAL)
        time_hbox.Add(self.time_display, flag=wx.ALIGN_CENTER_VERTICAL)
        
        # Add spacer to push time to the right
        time_hbox.AddStretchSpacer()
        
        # Add to main vertical sizer
        self.vbox.Add(time_hbox, flag=wx.EXPAND|wx.ALL, border=10)
        
        # Update time display immediately
        self.update_time_display()

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

    def render_portfolio(self):
        hbox0 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_portfolio = wx.StaticText(self.panel, label='Options')
        hbox0.Add(lbl_portfolio, flag=wx.RIGHT, border=8)        
        self.grid_portfolio = wx.grid.Grid(self.panel)
        self.grid_portfolio.CreateGrid(5, len(c.portfolio_labels))
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
        self.vbox.Add(hbox0, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        self.vbox.Add(self.grid_portfolio, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)

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
            
            if start is not None and premium is not None:
                # Update the grid display
                if start_col is not None:
                    self.grid_portfolio.SetCellValue(row, start_col, str(start))
                if premium_col is not None:
                    self.grid_portfolio.SetCellValue(row, premium_col, str(premium))
                
                # Update the controller/position data
                self.update_position_data(row, start, premium)
                
                # Refresh the grid
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
                if premium:
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
        self.grid_stock.CreateGrid(5, len(c.stock_labels))
        for col, label in enumerate(c.stock_labels):
            self.grid_stock.SetColLabelValue(col, label)
            if label in c.stock_columns_left:
                attr = wx.grid.GridCellAttr()
                attr.SetAlignment(wx.ALIGN_LEFT, wx.ALIGN_CENTER)
                self.grid_stock.SetColAttr(col, attr)
            else:
                self.grid_stock.SetColFormatNumber(col)
        #add all elements to self.vbox
        self.vbox.Add(lbl_stock, flag=wx.LEFT, border=8)
        self.vbox.Add(self.grid_stock, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)

    def on_stock_selected(self, event):
        selected_stock = self.choice.GetStringSelection()
        self.txt_stock.SetValue(selected_stock)

    def on_load(self, event):
        stock = self.txt_stock.GetValue()
        if stock:
            self.controller.getStock(stock)

    def on_timer(self, event):
        self.controller.process_incoming_data()
        status = self.controller.get_connection_status()        
        self.SetTitle(f"The Collar - {status}")
        
        # Update time display
        self.update_time_display()
