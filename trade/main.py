import wx
import threading
import queue
from .api import IBApi

class MainFrame(wx.Frame):
    def __init__(self, parent, title, command_queue, data_queue):
        super().__init__(parent, title=title, size=(900, 800))
        self.command_queue = command_queue
        self.data_queue = data_queue
        self.init_ui()
        
        # Timer to check for incoming data
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(500)  # Check every 500ms

    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Cash/Account section
        cash_label = wx.StaticText(panel, label="Account Summary:")
        self.cash_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(880, 120))
        
        # Orders section
        orders_label = wx.StaticText(panel, label="Orders:")
        self.orders_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(880, 180))
        
        # Positions section
        positions_label = wx.StaticText(panel, label="Positions:")
        self.positions_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(880, 180))
        
        # Command section
        command_label = wx.StaticText(panel, label="Send Command:")
        self.command_input = wx.TextCtrl(panel, size=(400, 25))
        send_button = wx.Button(panel, label="Send")
        
        # Buttons for common commands
        get_orders_btn = wx.Button(panel, label="Get Orders")
        get_positions_btn = wx.Button(panel, label="Get Positions")
        get_cash_btn = wx.Button(panel, label="Get Cash")
        get_account_btn = wx.Button(panel, label="Get Account Summary")
        
        # Layout
        vbox.Add(cash_label, 0, wx.ALL, 5)
        vbox.Add(self.cash_text, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(orders_label, 0, wx.ALL, 5)
        vbox.Add(self.orders_text, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(positions_label, 0, wx.ALL, 5)
        vbox.Add(self.positions_text, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(command_label, 0, wx.ALL, 5)
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(self.command_input, 1, wx.ALL, 5)
        hbox.Add(send_button, 0, wx.ALL, 5)
        vbox.Add(hbox, 0, wx.EXPAND)
        
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        hbox2.Add(get_orders_btn, 0, wx.ALL, 5)
        hbox2.Add(get_positions_btn, 0, wx.ALL, 5)
        hbox2.Add(get_cash_btn, 0, wx.ALL, 5)
        hbox2.Add(get_account_btn, 0, wx.ALL, 5)
        vbox.Add(hbox2, 0, wx.ALL, 5)
        
        panel.SetSizer(vbox)
        
        # Bind events
        send_button.Bind(wx.EVT_BUTTON, self.on_send_command)
        get_orders_btn.Bind(wx.EVT_BUTTON, self.on_get_orders)
        get_positions_btn.Bind(wx.EVT_BUTTON, self.on_get_positions)
        get_cash_btn.Bind(wx.EVT_BUTTON, self.on_get_cash)
        get_account_btn.Bind(wx.EVT_BUTTON, self.on_get_account_summary)
        get_positions_btn.Bind(wx.EVT_BUTTON, self.on_get_positions)

    def on_send_command(self, event):
        command = self.command_input.GetValue()
        if command:
            self.command_queue.put(command)
            self.command_input.SetValue("")

    def on_get_orders(self, event):
        self.command_queue.put("get_orders")

    def on_get_positions(self, event):
        self.command_queue.put("get_positions")

    def on_get_cash(self, event):
        self.command_queue.put("get_cash")

    def on_get_account_summary(self, event):
        self.command_queue.put("get_account_summary")

    def on_timer(self, event):
        """Check for incoming data from IBApi"""
        while not self.data_queue.empty():
            try:
                data = self.data_queue.get_nowait()
                if data["type"] == "orders":
                    orders_text = "\n".join([str(order) for order in data["data"]])
                    self.orders_text.SetValue(orders_text)
                elif data["type"] == "positions":
                    positions_text = "\n".join([str(pos) for pos in data["data"]])
                    self.positions_text.SetValue(positions_text)
                elif data["type"] == "cash":
                    cash_text = "\n".join([f"{key}: {value['value']} {value['currency']}" for key, value in data["data"].items()])
                    self.cash_text.SetValue(cash_text)
                elif data["type"] == "account_summary":
                    account_text = "\n".join([f"{key}: {value['value']} {value['currency']}" for key, value in data["data"].items()])
                    self.cash_text.SetValue(account_text)
            except queue.Empty:
                break




