"""Sell puts window: ranked cash-secured puts from the latest scan."""
import wx

from config import create_c
from .screener import format_candidate_row, format_screener_row, normalize_symbol

c = create_c()

COLUMNS = [
    ("Symbol", 58, "Ticker on the watchlist."),
    ("Price", 54, "Last stock price."),
    ("Expiry", 48, "Option expiry, month-day."),
    ("DTE", 36, "Calendar days from today to expiry."),
    ("Strike", 54, "Recommended put strike: closest to delta −0.25 in the 0.20–0.30 band."),
    ("Delta", 44, "Model delta of the recommended put. Target is −0.25."),
    ("Bid", 48, "Bid of the recommended put."),
    ("Ask", 48, "Ask of the recommended put."),
    ("Fill", 48, "Assumed sale price: bid plus a quarter of the way to the ask."),
    ("Prem", 56, "Dollar premium per contract at the fill, after commission."),
    ("Yield", 52, "Premium as a percent of cash posted (strike × 100) on the recommended put."),
    ("Ann", 56, "Yield scaled to a year: yield × 365 / DTE. Display only."),
    ("Y25", 52, "Yield interpolated to delta −0.25, so names can be ranked at the same risk. Pick the name with this; trade the recommended strike."),
    ("IV", 50, "30-day implied volatility of the stock, from Interactive Brokers."),
    ("HV", 50, "30-day historical volatility: how much the stock has actually moved."),
    ("IV/HV", 50, "Implied divided by historical. Above 1, options look rich vs recent moves; below 1 the row is dimmed."),
    ("Earn", 48, "Earnings before this expiry (or unknown if the calendar could not be read). Ranked below names with a clear calendar."),
    ("Fits", 40, "How many contracts fit in the 70% cash reserve after current short puts. over = cannot fit one."),
    ("BE", 56, "Break-even if assigned: strike minus fill, per share."),
    ("Held", 140, "What you already hold on this symbol: short puts and/or shares."),
]

CANDIDATE_COLUMNS = [
    ("Strike", 54, "Put strike for this symbol and expiry."),
    ("Delta", 48, "Model delta of this put."),
    ("Bid", 48, "Bid of this put."),
    ("Ask", 48, "Ask of this put."),
    ("Fill", 48, "Assumed sale price: bid plus a quarter of the way to the ask."),
    ("Yield", 50, "Premium as a percent of cash posted (strike × 100)."),
    ("Notes", 180, "Why this put is not used for ranking, if it fails a filter."),
]


def bind_column_help(listctrl, columns):
    def on_click(event, cols=columns):
        index = event.GetColumn()
        if 0 <= index < len(cols):
            label, _, text = cols[index]
            wx.MessageBox(text, label, wx.OK | wx.ICON_INFORMATION)
    listctrl.Bind(wx.EVT_LIST_COL_CLICK, on_click)


class WatchlistDialog(wx.Dialog):
    """Add, change, reorder, and remove tickers used by the put scan."""

    def __init__(self, parent, controller):
        super().__init__(parent, title="Put watchlist", size=(640, 540),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self.symbols = list(controller.screener_symbols)
        self._warned_scan = False
        self._names_key = None
        self.init_ui()
        self.fill()
        if hasattr(controller, "lookup_watchlist_names"):
            controller.lookup_watchlist_names(self.symbols)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.timer.Start(250)

    def init_ui(self):
        panel = wx.Panel(self)
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(wx.StaticText(panel, label="Symbols scanned when selling puts"),
                flag=wx.LEFT | wx.RIGHT | wx.TOP, border=10)

        self.list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list.InsertColumn(0, "Symbol", width=90)
        self.list.InsertColumn(1, "Company", width=480)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_edit)
        box.Add(self.list, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)

        row = wx.BoxSizer(wx.HORIZONTAL)
        for name, handler in (
            ("Add", self.on_add), ("Edit", self.on_edit), ("Delete", self.on_delete),
            ("Up", self.on_up), ("Down", self.on_down),
        ):
            button = wx.Button(panel, label=name)
            button.Bind(wx.EVT_BUTTON, handler)
            row.Add(button, flag=wx.RIGHT, border=6)
        box.Add(row, flag=wx.LEFT | wx.RIGHT, border=10)

        extras = wx.BoxSizer(wx.HORIZONTAL)
        restore = wx.Button(panel, label="Restore defaults")
        restore.Bind(wx.EVT_BUTTON, self.on_restore)
        close = wx.Button(panel, wx.ID_CLOSE, "Close")
        close.Bind(wx.EVT_BUTTON, self.on_close)
        extras.Add(restore)
        extras.AddStretchSpacer()
        extras.Add(close)
        box.Add(extras, flag=wx.EXPAND | wx.ALL, border=10)
        panel.SetSizer(box)
        wrap = wx.BoxSizer(wx.VERTICAL)
        wrap.Add(panel, proportion=1, flag=wx.EXPAND)
        self.SetSizer(wrap)

    def selected_index(self):
        return self.list.GetFirstSelected()

    def names(self):
        return getattr(self.controller, "screener_names", None) or {}

    def fill(self, select=None):
        names = self.names()
        self.list.DeleteAllItems()
        for symbol in self.symbols:
            index = self.list.InsertItem(self.list.GetItemCount(), symbol)
            self.list.SetItem(index, 1, names.get(symbol) or "")
        self._names_key = tuple(names.get(symbol) or "" for symbol in self.symbols)
        if select is not None and 0 <= select < len(self.symbols):
            self.list.Select(select)
            self.list.EnsureVisible(select)

    def on_timer(self, event):
        names = self.names()
        key = tuple(names.get(symbol) or "" for symbol in self.symbols)
        if key == self._names_key:
            return
        for index, symbol in enumerate(self.symbols):
            if index < self.list.GetItemCount():
                self.list.SetItem(index, 1, names.get(symbol) or "")
        self._names_key = key

    def on_close(self, event):
        if getattr(self, "timer", None):
            self.timer.Stop()
        if self.IsModal():
            self.EndModal(wx.ID_CLOSE)
        else:
            self.Hide()

    def ask_symbol(self, title, value=""):
        dialog = wx.TextEntryDialog(self, "Ticker", title, value)
        if dialog.ShowModal() != wx.ID_OK:
            dialog.Destroy()
            return None
        text = dialog.GetValue()
        dialog.Destroy()
        try:
            return normalize_symbol(text)
        except ValueError as e:
            wx.MessageBox(str(e), "Invalid ticker", wx.OK | wx.ICON_ERROR)
            return None

    def persist(self, select=None):
        try:
            self.symbols = list(self.controller.save_screener_watchlist(self.symbols))
        except Exception as e:
            wx.MessageBox(f"Not saved: {e}", "Save error", wx.OK | wx.ICON_ERROR)
            self.symbols = list(self.controller.screener_symbols)
            self.fill(select)
            return
        self.fill(select)
        if not self._warned_scan and self.controller.put_scan_running():
            self._warned_scan = True
            wx.MessageBox(
                "The scan already in progress still uses the previous list. "
                "Stop it and Scan again to use the new list.",
                "Watchlist saved", wx.OK | wx.ICON_INFORMATION,
            )

    def on_add(self, event):
        symbol = self.ask_symbol("Add ticker")
        if symbol is None:
            return
        if symbol in self.symbols:
            wx.MessageBox(f"{symbol} is already on the list", "Duplicate",
                          wx.OK | wx.ICON_INFORMATION)
            return
        self.symbols.append(symbol)
        self.persist(len(self.symbols) - 1)

    def on_edit(self, event):
        index = self.selected_index()
        if index < 0:
            return
        symbol = self.ask_symbol("Edit ticker", self.symbols[index])
        if symbol is None:
            return
        if symbol in self.symbols and self.symbols[index] != symbol:
            wx.MessageBox(f"{symbol} is already on the list", "Duplicate",
                          wx.OK | wx.ICON_INFORMATION)
            return
        self.symbols[index] = symbol
        self.persist(index)

    def on_delete(self, event):
        index = self.selected_index()
        if index < 0:
            return
        if len(self.symbols) == 1:
            wx.MessageBox("The watchlist needs at least one ticker", "Cannot delete",
                          wx.OK | wx.ICON_INFORMATION)
            return
        symbol = self.symbols[index]
        if wx.MessageBox(f"Remove {symbol} from the watchlist?", "Delete ticker",
                         wx.YES_NO | wx.ICON_WARNING) != wx.YES:
            return
        del self.symbols[index]
        self.persist(min(index, len(self.symbols) - 1))

    def on_up(self, event):
        index = self.selected_index()
        if index <= 0:
            return
        self.symbols[index - 1], self.symbols[index] = self.symbols[index], self.symbols[index - 1]
        self.persist(index - 1)

    def on_down(self, event):
        index = self.selected_index()
        if index < 0 or index >= len(self.symbols) - 1:
            return
        self.symbols[index + 1], self.symbols[index] = self.symbols[index], self.symbols[index + 1]
        self.persist(index + 1)

    def on_restore(self, event):
        if wx.MessageBox(
            "Replace the watchlist with the default symbols from config?",
            "Restore defaults", wx.YES_NO | wx.ICON_QUESTION,
        ) != wx.YES:
            return
        self.symbols = list(c.screener_symbols)
        self.persist(0 if self.symbols else None)


class SellPutsFrame(wx.Frame):

    def __init__(self, parent, controller):
        super().__init__(parent, title="Sell puts", size=(1240, 620),
                         style=wx.DEFAULT_FRAME_STYLE)
        self.controller = controller
        self._version = None
        self._symbol = None
        self.init_ui()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(200)
        try:
            self.maybe_autoscans()
        except Exception as e:
            print(f"Put scan failed to start: {e}")
        self.refresh()

    def init_ui(self):
        panel = wx.Panel(self)
        box = wx.BoxSizer(wx.VERTICAL)
        bar = wx.BoxSizer(wx.HORIZONTAL)
        self.progress = wx.StaticText(panel, label="", style=wx.ST_ELLIPSIZE_END)
        self.btn_watchlist = wx.Button(panel, label="Watchlist")
        self.btn_watchlist.Bind(wx.EVT_BUTTON, self.on_watchlist)
        self.btn_scan = wx.Button(panel, label="Scan")
        self.btn_scan.Bind(wx.EVT_BUTTON, self.on_scan)
        bar.Add(self.progress, proportion=1, flag=wx.EXPAND)
        bar.Add(self.btn_watchlist, flag=wx.LEFT | wx.ALIGN_CENTER_VERTICAL, border=8)
        bar.Add(self.btn_scan, flag=wx.LEFT | wx.ALIGN_CENTER_VERTICAL, border=8)
        box.Add(bar, flag=wx.EXPAND | wx.ALL, border=10)

        self.list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for index, (label, width, _) in enumerate(COLUMNS):
            self.list.InsertColumn(index, label, width=width)
        bind_column_help(self.list, COLUMNS)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_select)
        box.Add(self.list, proportion=2, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)

        box.Add(wx.StaticText(panel, label="Strikes for the selected symbol"),
                flag=wx.LEFT | wx.TOP, border=10)
        self.detail = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for index, (label, width, _) in enumerate(CANDIDATE_COLUMNS):
            self.detail.InsertColumn(index, label, width=width)
        bind_column_help(self.detail, CANDIDATE_COLUMNS)
        box.Add(self.detail, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)
        panel.SetSizer(box)

    def scan(self):
        return getattr(self.controller, "put_scan", None)

    def maybe_autoscans(self):
        if self.scan() is None:
            self.controller.start_put_scan()

    def on_watchlist(self, event):
        dialog = WatchlistDialog(self, self.controller)
        dialog.ShowModal()
        dialog.Destroy()
        self.refresh()

    def on_scan(self, event):
        scan = self.scan()
        try:
            if scan is not None and scan.running:
                self.controller.stop_put_scan()
            else:
                self._version = None
                self.controller.start_put_scan(force=True)
        except Exception as e:
            wx.MessageBox(f"Scan did not start: {e}", "Sell puts", wx.OK | wx.ICON_ERROR)
        self.refresh()

    def on_timer(self, event):
        scan = self.scan()
        if scan is not None:
            scan.step()
        self.refresh()

    def refresh(self):
        scan = self.scan()
        running = bool(scan and scan.running)
        self.btn_scan.SetLabel("Stop" if running else "Scan")
        self.progress.SetLabel(scan.progress() if scan else "No scan yet")
        version = getattr(scan, "version", None)
        if version == self._version:
            return
        self._version = version
        rows = list(scan.rows) if scan else []
        self.list.DeleteAllItems()
        highlight = wx.Colour(30, 80, 30)
        dim = wx.Colour(120, 120, 120)
        top = True
        for row in rows:
            values = format_screener_row(row)
            index = self.list.InsertItem(self.list.GetItemCount(), values[0])
            for col, value in enumerate(values[1:], start=1):
                self.list.SetItem(index, col, value)
            if row.get("rank") == 1 and top:
                self.list.SetItemBackgroundColour(index, highlight)
                top = False
            elif row.get("ivhv") is not None and row["ivhv"] < 1.0:
                self.list.SetItemTextColour(index, dim)
        if self._symbol:
            self.show_candidates(self._symbol)

    def on_select(self, event):
        index = event.GetIndex()
        self._symbol = self.list.GetItemText(index, 0)
        self.show_candidates(self._symbol)

    def show_candidates(self, symbol):
        self.detail.DeleteAllItems()
        scan = self.scan()
        if scan is None:
            return
        row = next((r for r in scan.rows if r.get("symbol") == symbol), None)
        if row is None:
            return
        pick_strike = row["pick"]["strike"] if row.get("pick") else None
        for quote in row.get("candidates") or []:
            values = format_candidate_row(quote)
            index = self.detail.InsertItem(self.detail.GetItemCount(), values[0])
            for col, value in enumerate(values[1:], start=1):
                self.detail.SetItem(index, col, value)
            if pick_strike is not None and quote.get("strike") == pick_strike:
                self.detail.SetItemBackgroundColour(index, wx.Colour(30, 80, 30))

    def on_close(self, event):
        self.Hide()
        if event.CanVeto():
            event.Veto()


def accelerator():
    return "Ctrl+Shift+P"
