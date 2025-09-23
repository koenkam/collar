import wx
import wx.grid  # Add this import for Grid functionality
import threading
import queue
from .api import IBApi
from config import create_c
from .controller import Controller
c=create_c()


class MainFrame(wx.Frame):

    def __init__(self, controller):
        super().__init__(None, title="The Collar", size=(900, 800))
        self.controller = controller
        self.controller.mainframe = self  # Set the mainframe reference in controller
        self.init_ui()
        
        # Timer to check for incoming data
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(50)  # Check every 500ms

    def init_ui(self):
        self.panel = wx.Panel(self)
        self.vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.render_portfolio()
        self.render_picker()
        self.render_dash()
        self.render_grid()
        self.panel.SetSizer(self.vbox)
        self.Centre()
        self.controller.getStock(self.txt_stock.GetValue()  )

    def render_portfolio(self):
        #draw a title "Portfolio" at the top of the window
        hbox0 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_portfolio = wx.StaticText(self.panel, label='Portfolio')
        hbox0.Add(lbl_portfolio, flag=wx.RIGHT, border=8)        
        self.grid_portfolio = wx.grid.Grid(self.panel)
        self.grid_portfolio.CreateGrid(5, len(c.portfolio_labels))
        for col, label in enumerate(c.portfolio_labels):
            self.grid_portfolio.SetColLabelValue(col, label)
        self.grid_portfolio.AutoSizeColumns()
        self.vbox.Add(hbox0, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        self.vbox.Add(self.grid_portfolio, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)



    def render_picker(self):
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_stock = wx.TextCtrl(self.panel, value=c.stocks[0] if c.stocks else "")
        print(self.txt_stock.GetValue())
        hbox1.Add(self.txt_stock, flag=wx.RIGHT, border=8)
        self.choice = wx.Choice(self.panel, choices=c.stocks)
        hbox1.Add(self.choice, flag=wx.RIGHT, border=8)
        self.btn_load = wx.Button(self.panel, label='Load')
        hbox1.Add(self.btn_load)
        self.vbox.Add(hbox1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        self.choice.Bind(wx.EVT_CHOICE, self.on_stock_selected)
        self.btn_load.Bind(wx.EVT_BUTTON, self.on_load)
        hbox1.Add((20, 0))
        lbl_weeks = wx.StaticText(self.panel, label='Weeks:')
        hbox1.Add(lbl_weeks, flag=wx.RIGHT, border=8)
        self.choice_weeks = wx.Choice(self.panel, choices=[str(i) for i in range(1, 11)])
        self.choice_weeks.SetStringSelection("2")  # Set default to 2 weeks
        hbox1.Add(self.choice_weeks, flag=wx.RIGHT, border=8)

    def render_dash(self):
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_price = wx.StaticText(self.panel, label='Price:')
        hbox2.Add(lbl_price, flag=wx.RIGHT, border=8)
        self.txt_price = wx.TextCtrl(self.panel)
        hbox2.Add(self.txt_price, flag=wx.RIGHT, border=8)
        self.vbox.Add(hbox2, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10)

    def render_grid(self):
        self.grid = wx.grid.Grid(self.panel)  
        labels = c.options_labels
        self.grid.CreateGrid(10, len(labels))
        self.vbox.Add(self.grid, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        
        for col, label in enumerate(labels):
            self.grid.SetColLabelValue(col, label)
        self.grid.AutoSizeColumns()

    def resetGrid(self):
        """Reset grid to empty state"""
        self.grid.ClearGrid()
        
        # Only delete rows if there are rows to delete
        num_rows = self.grid.GetNumberRows()
        if num_rows > 0:
            self.grid.DeleteRows(0, num_rows)
        
        self.grid.ForceRefresh()

    def on_stock_selected(self, event):
        selected_stock = self.choice.GetStringSelection()
        self.txt_stock.SetValue(selected_stock)

    def on_load(self, event):
        stock = self.txt_stock.GetValue()
        if stock:
            self.controller.getStock(stock)

    def on_timer(self, event):
        self.controller.process_incoming_data()