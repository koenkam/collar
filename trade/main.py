import wx
import wx.grid  # Add this import for Grid functionality
import threading
import queue
from .api import IBApi
from config import create_c
from .controller import Controller
c=create_c()


class MainFrame(wx.Frame):
    def __init__(self, parent, title, gui_to_ib, ib_to_gui):
        super().__init__(parent, title=title, size=(900, 800))
        self.controller = Controller(self)
        self.gui_to_ib = gui_to_ib
        self.ib_to_gui = ib_to_gui
        self.init_ui()
        
        # Timer to check for incoming data
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(50)  # Check every 500ms

    def init_ui(self):
        self.panel = wx.Panel(self)
        self.vbox = wx.BoxSizer(wx.VERTICAL)
        
        """
        make a dropdown with the stocks in c.stocks
        the behavior should be: the dropdown shows the stocks in c.stocks
        when a stock is selected, it is shown in the text box next to it
        there is a load button next to the text box
        """
        self.render_picker()
        self.render_dash()
        self.render_grid()
        self.panel.SetSizer(self.vbox)
        self.Centre()
        self.controller.getStock(self.txt_stock.GetValue()  )

    def render_picker(self):
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_stock = wx.TextCtrl(self.panel, value=c.stocks[0] if c.stocks else "", style=wx.TE_RIGHT)
        hbox1.Add(self.txt_stock, flag=wx.RIGHT, border=8)
        self.choice = wx.Choice(self.panel, choices=c.stocks)
        hbox1.Add(self.choice, flag=wx.RIGHT, border=8)
        self.btn_load = wx.Button(self.panel, label='Load')
        hbox1.Add(self.btn_load)
        self.vbox.Add(hbox1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        # Bind the dropdown selection event
        self.choice.Bind(wx.EVT_CHOICE, self.on_stock_selected)
        self.btn_load.Bind(wx.EVT_BUTTON, self.on_load)

        #add a dropdown for the number of weeks to show, default: 2 weeks, options: 1 to 10
        #give it some horizontal space with the previous widget and show a label "weeks"
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
        #i want to make an excel-like grid with 10 rows and 5 columns
        self.grid = wx.grid.Grid(self.panel)  # Use wx.grid.Grid instead of wx.Grid
        labels = ["Expiration", "Strike", "Type", "Delta", "Mid", "IV","PPD", "ROI"]
        self.grid.CreateGrid(10, len(labels))
        self.vbox.Add(self.grid, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        
        for col, label in enumerate(labels):
            self.grid.SetColLabelValue(col, label)
        self.grid.AutoSizeColumns()


    def on_stock_selected(self, event):
        selected_stock = self.choice.GetStringSelection()
        self.txt_stock.SetValue(selected_stock)

    def on_load(self, event):
        stock = self.txt_stock.GetValue()
        print("on load:", stock)
        if stock:
            self.controller.getStock(stock)

    def on_timer(self, event):
        """Check for incoming data from IB API"""
        while not self.ib_to_gui.empty():
            self.controller.process_incoming_data()


