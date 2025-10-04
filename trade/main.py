import wx
import wx.grid  # Add this import for Grid functionality
import threading
import queue
from .api import IBApi
from config import create_c
from .controller import Controller
from .display import Displayer
c=create_c()


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
        
        self.render_portfolio()
        #self.render_dash()
        self.panel.SetSizer(self.vbox)
        self.Centre()
        #self.controller.getStock(self.txt_stock.GetValue()  )

  

    def render_portfolio(self):
        #draw a title "Portfolio" at the top of the window
        hbox0 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_portfolio = wx.StaticText(self.panel, label='Portfolio')
        hbox0.Add(lbl_portfolio, flag=wx.RIGHT, border=8)        
        self.grid_portfolio = wx.grid.Grid(self.panel)
        self.grid_portfolio.CreateGrid(5, len(c.portfolio_labels))
        for col, label in enumerate(c.portfolio_labels):
            self.grid_portfolio.SetColLabelValue(col, label)
        # align all columns to the right
        for col, label in enumerate(c.portfolio_labels):
            if label in c.portfolio_columns_left:
                attr = wx.grid.GridCellAttr()
                attr.SetAlignment(wx.ALIGN_LEFT, wx.ALIGN_CENTER)
                self.grid_portfolio.SetColAttr(col, attr)
            else:
                self.grid_portfolio.SetColFormatNumber(col)
        self.grid_portfolio.AutoSizeColumns()
        self.vbox.Add(hbox0, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        self.vbox.Add(self.grid_portfolio, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)



    def on_stock_selected(self, event):
        selected_stock = self.choice.GetStringSelection()
        self.txt_stock.SetValue(selected_stock)

    def on_load(self, event):
        stock = self.txt_stock.GetValue()
        if stock:
            self.controller.getStock(stock)

    def on_timer(self, event):
        self.controller.process_incoming_data()

