"""Record editor: create, view, change, and delete book records by hand."""
import wx

from util import parse_premium
from .book import as_count, breakeven
from .logbook import format_price, format_yyyymmdd, to_yyyymmdd

OPTION_FIELDS = [
    ("symbol", "Symbol", "symbol", True),
    ("right", "Right (P or C)", "right", True),
    ("strike", "Strike", "number", True),
    ("expiry", "Expiry", "date", True),
    ("premium", "Premium", "number", False),
    ("startdate", "Start", "date", False),
    ("n", "Contracts (broker)", "readonly", False),
]

STOCK_FIELDS = [
    ("symbol", "Symbol", "symbol", True),
    ("avgCost", "Buy", "number", False),
    ("credit", "Credit", "number", False),
    ("startdate", "Date", "date", False),
    ("n", "Shares (broker)", "readonly", False),
]

LOG_FIELDS = [
    ("open_date", "Open", "date", False),
    ("close_date", "Close", "date", True),
    ("right", "Type (P, C, or STK)", "right", False),
    ("symbol", "Symbol", "symbol", True),
    ("signed_quantity", "#", "int", False),
    ("strike", "Strike", "number", False),
    ("expiry", "Expiry", "date", False),
    ("open_price", "Price", "number", False),
    ("open_commission", "Com", "number", False),
    ("premium", "Premium", "number", False),
    ("assign", "Assign", "number", False),
    ("close_price", "Close px", "number", False),
    ("close_commission", "Close com", "number", False),
    ("profit", "Profit", "number", True),
]


def show_value(kind, value):
    if value is None or value == "":
        return ""
    if kind == "date":
        return format_yyyymmdd(value)
    if kind == "number":
        return format_price(round(float(value), 4))
    if kind == "readonly":
        return str(as_count(value))
    return str(value)


def parse_value(kind, text):
    text = text.strip()
    if text == "":
        return None
    if kind == "symbol":
        return text.upper()
    if kind == "right":
        label = text.upper()
        return {"PUT": "P", "CALL": "C"}.get(label, label)
    if kind == "date":
        return to_yyyymmdd(text)
    if kind == "int":
        return int(float(text))
    if kind == "number":
        return parse_premium(text)
    return text


class RecordFormDialog(wx.Dialog):
    def __init__(self, parent, title, fields, values):
        super().__init__(parent, title=title)
        self.fields = fields
        self.result = None
        panel = wx.Panel(self)
        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=10)
        grid.AddGrowableCol(1)
        self.controls = {}
        for key, label, kind, required in fields:
            grid.Add(wx.StaticText(panel, label=label + (" *" if required else "")),
                     flag=wx.ALIGN_CENTER_VERTICAL)
            ctrl = wx.TextCtrl(panel, value=show_value(kind, values.get(key)), size=(240, -1))
            if kind == "readonly":
                ctrl.SetEditable(False)
                ctrl.Enable(False)
            grid.Add(ctrl, flag=wx.EXPAND)
            self.controls[key] = ctrl
        buttons = wx.StdDialogButtonSizer()
        ok = wx.Button(panel, wx.ID_OK, "Save")
        ok.Bind(wx.EVT_BUTTON, self.on_save)
        buttons.AddButton(ok)
        buttons.AddButton(wx.Button(panel, wx.ID_CANCEL, "Cancel"))
        buttons.Realize()
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(grid, flag=wx.EXPAND | wx.ALL, border=12)
        box.Add(buttons, flag=wx.ALIGN_RIGHT | wx.ALL, border=10)
        panel.SetSizer(box)
        box.Fit(self)

    def on_save(self, event):
        result = {}
        for key, label, kind, required in self.fields:
            if kind == "readonly":
                continue
            try:
                value = parse_value(kind, self.controls[key].GetValue())
            except ValueError:
                wx.MessageBox(f"{label} is not valid", "Invalid input", wx.OK | wx.ICON_ERROR)
                return
            if required and value is None:
                wx.MessageBox(f"{label} is required", "Invalid input", wx.OK | wx.ICON_ERROR)
                return
            result[key] = value
        self.result = result
        self.EndModal(wx.ID_OK)


class RecordPage(wx.Panel):
    def __init__(self, parent, columns, buttons):
        super().__init__(parent)
        self.ids = []
        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for index, (label, width) in enumerate(columns):
            self.list.InsertColumn(index, label, width=width)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.buttons = {}
        for name in buttons:
            button = wx.Button(self, label=name)
            row.Add(button, flag=wx.RIGHT, border=8)
            self.buttons[name] = button
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self.list, proportion=1, flag=wx.EXPAND | wx.ALL, border=6)
        self.detail = None
        box.Add(row, flag=wx.ALL, border=6)
        self.box = box
        self.SetSizer(box)

    def add_detail(self):
        self.detail = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 140))
        self.box.Insert(1, self.detail, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)

    def fill(self, rows):
        self.list.DeleteAllItems()
        self.ids = []
        for record_id, values in rows:
            index = self.list.InsertItem(self.list.GetItemCount(), str(values[0]))
            for col, value in enumerate(values[1:], start=1):
                self.list.SetItem(index, col, str(value))
            self.ids.append(record_id)

    def selected(self):
        index = self.list.GetFirstSelected()
        if index < 0 or index >= len(self.ids):
            return None
        return self.ids[index]


class RecordsDialog(wx.Dialog):
    def __init__(self, parent, controller, page="options"):
        super().__init__(parent, title="Records", size=(1100, 620),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self.notebook = wx.Notebook(self)

        self.options_page = RecordPage(self.notebook, [
            ("Id", 200), ("Symbol", 70), ("Right", 50), ("Strike", 70), ("Expiry", 90),
            ("Book n", 60), ("Broker n", 70), ("Premium", 90), ("Start", 90),
        ], ["New", "Edit", "Delete"])
        self.stocks_page = RecordPage(self.notebook, [
            ("Id", 120), ("Symbol", 70), ("Book n", 70), ("Broker n", 70), ("Buy", 80),
            ("Credit", 90), ("Break-even", 90), ("Date", 90),
        ], ["New", "Edit", "Delete"])
        self.log_page = RecordPage(self.notebook, [
            ("Id", 130), ("Open", 90), ("Type", 50), ("Symbol", 70), ("#", 50),
            ("Strike", 70), ("Close", 90), ("Premium", 90), ("Profit", 90),
        ], ["New", "Edit", "Delete"])
        self.review_page = RecordPage(self.notebook, [
            ("Symbol", 80), ("Problem", 560), ("Updated", 130),
        ], ["Resolve"])
        self.review_page.add_detail()

        self.pages = {
            "options": self.options_page,
            "stocks": self.stocks_page,
            "log": self.log_page,
            "review": self.review_page,
        }
        for name, label in (("options", "Options"), ("stocks", "Stocks"),
                            ("log", "Log"), ("review", "Review")):
            self.notebook.AddPage(self.pages[name], label)

        for name in ("options", "stocks", "log"):
            record_page = self.pages[name]
            record_page.buttons["New"].Bind(wx.EVT_BUTTON, lambda e, n=name: self.on_new(n))
            record_page.buttons["Edit"].Bind(wx.EVT_BUTTON, lambda e, n=name: self.on_edit(n))
            record_page.buttons["Delete"].Bind(wx.EVT_BUTTON, lambda e, n=name: self.on_delete(n))
            record_page.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda e, n=name: self.on_edit(n))
        self.review_page.buttons["Resolve"].Bind(wx.EVT_BUTTON, self.on_resolve)
        self.review_page.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_review_selected)

        close = wx.Button(self, wx.ID_CLOSE, "Close")
        close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self.notebook, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)
        box.Add(close, flag=wx.ALIGN_RIGHT | wx.ALL, border=8)
        self.SetSizer(box)

        self.refresh()
        self.start_page = list(self.pages).index(page) if page in self.pages else 0
        self.notebook.SetSelection(self.start_page)

    # --- lists ---------------------------------------------------------------

    def broker_n(self, iid):
        entry = self.controller.broker.get(iid)
        return as_count(entry["n"]) if entry else 0

    def refresh(self):
        ctrl = self.controller
        rows = []
        for iid in sorted(ctrl.book_options):
            doc = ctrl.book_options[iid]
            rows.append((iid, [
                iid, doc.get("symbol", ""), doc.get("right", ""), format_price(doc.get("strike")),
                format_yyyymmdd(doc.get("expiry")), as_count(doc.get("n")), self.broker_n(iid),
                show_value("number", doc.get("premium")), format_yyyymmdd(doc.get("startdate")),
            ]))
        self.options_page.fill(rows)

        rows = []
        for iid in sorted(ctrl.book_stocks):
            doc = ctrl.book_stocks[iid]
            rows.append((iid, [
                iid, doc.get("symbol", ""), as_count(doc.get("n")), self.broker_n(iid),
                show_value("number", doc.get("avgCost")), show_value("number", doc.get("credit")),
                f"{breakeven(doc):.2f}", format_yyyymmdd(doc.get("startdate")),
            ]))
        self.stocks_page.fill(rows)

        rows = []
        for trade in ctrl.log_trades:
            rows.append((trade.get("id"), [
                trade.get("id", ""), format_yyyymmdd(trade.get("open_date")), trade.get("right", ""),
                trade.get("symbol", ""), trade.get("signed_quantity", ""),
                format_price(trade.get("strike")), format_yyyymmdd(trade.get("close_date")),
                show_value("number", trade.get("premium")), show_value("number", trade.get("profit")),
            ]))
        self.log_page.fill(rows)

        rows = []
        for symbol in sorted(ctrl.review):
            item = ctrl.review[symbol]
            problems = item.get("problems") or []
            rows.append((symbol, [symbol, problems[0] if problems else "", item.get("updated", "")]))
        self.review_page.fill(rows)
        if self.review_page.detail is not None:
            self.review_page.detail.SetValue("")

    # --- actions -------------------------------------------------------------

    def spec(self, name):
        if name == "options":
            return OPTION_FIELDS, self.controller.book_options
        if name == "stocks":
            return STOCK_FIELDS, self.controller.book_stocks
        return LOG_FIELDS, {t.get("id"): t for t in self.controller.log_trades}

    def edit(self, name, record_id):
        fields, records = self.spec(name)
        values = dict(records.get(record_id) or {}) if record_id else {}
        if name in ("options", "stocks") and record_id:
            values["n"] = self.broker_n(record_id)
        title = f"Edit {record_id}" if record_id else f"New {name[:-1] if name != 'log' else 'log row'}"
        dialog = RecordFormDialog(self, title, fields, values)
        if dialog.ShowModal() == wx.ID_OK and dialog.result is not None:
            try:
                if name == "options":
                    self.controller.save_option(record_id, dialog.result)
                elif name == "stocks":
                    self.controller.save_stock(record_id, dialog.result)
                else:
                    self.controller.save_log(record_id, dialog.result)
            except Exception as e:
                wx.MessageBox(f"Not saved: {e}", "Save error", wx.OK | wx.ICON_ERROR)
        dialog.Destroy()
        self.refresh()

    def on_new(self, name):
        self.edit(name, None)

    def on_edit(self, name):
        record_id = self.pages[name].selected()
        if record_id is None:
            return
        self.edit(name, record_id)

    def on_delete(self, name):
        record_id = self.pages[name].selected()
        if record_id is None:
            return
        message = f"Delete {record_id}?"
        if name in ("options", "stocks") and record_id in self.controller.broker:
            message += (
                "\n\nThe broker still reports this position. It stays in the book with its "
                "premium or credit cleared."
            )
        if wx.MessageBox(message, "Delete record", wx.YES_NO | wx.ICON_WARNING) != wx.YES:
            return
        try:
            if name == "options":
                self.controller.delete_option(record_id)
            elif name == "stocks":
                self.controller.delete_stock(record_id)
            else:
                self.controller.delete_log(record_id)
        except Exception as e:
            wx.MessageBox(f"Not deleted: {e}", "Delete error", wx.OK | wx.ICON_ERROR)
        self.refresh()

    def on_review_selected(self, event):
        symbol = self.review_page.selected()
        item = self.controller.review.get(symbol) or {}
        lines = list(item.get("problems") or [])
        lines.append("")
        lines.append("Book and broker counts:")
        for row in item.get("instruments") or []:
            lines.append(f"  {row['id']}: book {row['book']}, broker {row['broker']}")
        fills = item.get("fills") or []
        if fills:
            lines.append("")
            lines.append("Fills not yet applied:")
            lines.extend(f"  {f['text']}" for f in fills)
        self.review_page.detail.SetValue("\n".join(lines))

    def on_resolve(self, event):
        symbol = self.review_page.selected()
        if symbol is None:
            return
        message = (
            f"Resolve {symbol}?\n\n"
            "The book takes the broker's contract and share counts for this symbol. "
            "The listed fills are marked as handled and are not applied. Records the broker "
            "no longer holds are archived.\n\n"
            "Afterwards, correct the premium, credit, or log rows in the other tabs."
        )
        if wx.MessageBox(message, "Resolve review", wx.YES_NO | wx.ICON_QUESTION) != wx.YES:
            return
        try:
            self.controller.resolve_review(symbol)
        except Exception as e:
            wx.MessageBox(f"Not resolved: {e}", "Resolve error", wx.OK | wx.ICON_ERROR)
        self.refresh()
