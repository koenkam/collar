"""Popup chart of realized log profit, grouped by day, month, or year."""
import math

import wx

from .logbook import profit_buckets

GROUPS = (("day", "Day"), ("month", "Month"), ("year", "Year"))
PROFIT_COLOUR = wx.Colour(22, 140, 72)
LOSS_COLOUR = wx.Colour(190, 48, 42)
CUMULATIVE_COLOUR = wx.Colour(28, 78, 150)


class ProfitChart(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = []
        self.SetBackgroundColour(wx.WHITE)
        self.SetMinSize((720, 380))
        self.Bind(wx.EVT_PAINT, self.on_paint)

    def set_rows(self, rows):
        self.rows = rows
        self.Refresh()

    def on_paint(self, event):
        self.draw(wx.PaintDC(self), self.GetClientSize())

    def draw(self, dc, size):
        width, height = size
        dc.SetBackground(wx.Brush(wx.WHITE))
        dc.Clear()
        if width < 40 or height < 40:
            return
        if not self.rows:
            self._empty(dc, width, height)
            return
        left, right, top, bottom = 78, 24, 36, 72
        plot_w = width - left - right
        plot_h = height - top - bottom
        if plot_w < 20 or plot_h < 20:
            return
        low, high, ticks = _scale(self.rows)
        dc.SetPen(wx.Pen(wx.Colour(220, 220, 220)))
        dc.SetTextForeground(wx.Colour(80, 80, 80))
        dc.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        for value in ticks:
            y = _y(value, low, high, top, plot_h)
            dc.DrawLine(left, y, left + plot_w, y)
            label = _axis_money(value)
            text_w, text_h = dc.GetTextExtent(label)
            dc.DrawText(label, left - text_w - 8, y - text_h // 2)
        zero = _y(0, low, high, top, plot_h)
        dc.SetPen(wx.Pen(wx.Colour(90, 90, 90)))
        dc.DrawLine(left, zero, left + plot_w, zero)

        count = len(self.rows)
        slot = plot_w / count
        bar_w = max(2, int(slot * 0.55))
        points = []
        step = max(1, (count + 11) // 12)
        for index, row in enumerate(self.rows):
            x = left + index * slot + (slot - bar_w) / 2
            y = _y(row["profit"], low, high, top, plot_h)
            colour = PROFIT_COLOUR if row["profit"] >= 0 else LOSS_COLOUR
            dc.SetBrush(wx.Brush(colour))
            dc.SetPen(wx.Pen(colour))
            dc.DrawRectangle(int(x), int(min(zero, y)), bar_w, max(1, int(abs(y - zero))))
            center = int(left + index * slot + slot / 2)
            points.append(wx.Point(center, _y(row["cumulative"], low, high, top, plot_h)))
            if index % step == 0 or index == count - 1:
                dc.SetTextForeground(wx.Colour(60, 60, 60))
                dc.DrawRotatedText(row["label"], center - 6, top + plot_h + 6, -50)
        if len(points) > 1:
            dc.SetPen(wx.Pen(CUMULATIVE_COLOUR, 2))
            dc.DrawLines(points)
        dc.SetBrush(wx.Brush(CUMULATIVE_COLOUR))
        dc.SetPen(wx.Pen(CUMULATIVE_COLOUR))
        for point in points:
            dc.DrawCircle(point.x, point.y, 3)
        self._legend(dc, width)

    def _legend(self, dc, width):
        dc.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        dc.SetTextForeground(wx.Colour(40, 40, 40))
        items = ((PROFIT_COLOUR, "Period"), (CUMULATIVE_COLOUR, "Cumulative"))
        x = width - 16
        for colour, label in reversed(items):
            text_w, text_h = dc.GetTextExtent(label)
            x -= text_w
            dc.DrawText(label, x, 8)
            x -= 18
            dc.SetBrush(wx.Brush(colour))
            dc.SetPen(wx.Pen(colour))
            dc.DrawRectangle(x, 10, 12, 12)
            x -= 16

    def _empty(self, dc, width, height):
        dc.SetTextForeground(wx.Colour(80, 80, 80))
        dc.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        text = "No realized trades"
        text_w, text_h = dc.GetTextExtent(text)
        dc.DrawText(text, (width - text_w) // 2, (height - text_h) // 2)


class LogChartDialog(wx.Dialog):
    def __init__(self, parent, trades):
        super().__init__(parent, title="Log results", size=(920, 560))
        self.trades = list(trades or [])
        self.group = "month"
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(panel, label="Group"), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        self.buttons = {}
        for key, label in GROUPS:
            button = wx.ToggleButton(panel, label=label, name=key)
            button.SetValue(key == self.group)
            button.Bind(wx.EVT_TOGGLEBUTTON, self.on_group)
            self.buttons[key] = button
            row.Add(button, flag=wx.RIGHT, border=4)
        self.summary = wx.StaticText(panel, label="")
        row.AddStretchSpacer()
        row.Add(self.summary, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        self.chart = ProfitChart(panel)
        vbox.Add(row, flag=wx.EXPAND | wx.ALL, border=10)
        vbox.Add(self.chart, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)
        panel.SetSizer(vbox)
        self.SetMinSize((640, 420))
        self.apply_group()

    def on_group(self, event):
        button = event.GetEventObject()
        if not button.GetValue():
            button.SetValue(True)
            return
        self.group = button.GetName()
        for key, other in self.buttons.items():
            if key != self.group:
                other.SetValue(False)
        self.apply_group()

    def apply_group(self):
        rows = profit_buckets(self.trades, self.group)
        self.chart.set_rows(rows)
        if not rows:
            self.summary.SetLabel("")
            return
        self.summary.SetLabel(f"{len(rows)} periods · {_axis_money(rows[-1]['cumulative'])} total")


def _scale(rows):
    values = [row["profit"] for row in rows] + [row["cumulative"] for row in rows] + [0]
    low, high = min(values), max(values)
    if low == high:
        high = low + 1
    span = high - low
    raw = span / 4
    magnitude = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    residual = raw / magnitude
    step = 10 * magnitude
    for factor in (1, 2, 2.5, 5, 10):
        if residual <= factor:
            step = factor * magnitude
            break
    start = math.floor(low / step) * step
    end = math.ceil(high / step) * step
    if start == end:
        end = start + step
    ticks = []
    value = start
    while value <= end + step * 0.01:
        ticks.append(0.0 if abs(value) < step * 1e-6 else value)
        value += step
    return start, end, ticks


def _y(value, low, high, top, plot_h):
    return int(top + (high - value) / (high - low) * plot_h)


def _axis_money(value):
    sign = "-" if value < 0 else ""
    amount = abs(value)
    if amount >= 1000:
        return f"{sign}${amount:,.0f}"
    return f"{sign}${amount:,.2f}"
