from util import Stub, print_banner
import datetime
import os


def general(c):
    c.scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
        "https://spreadsheets.google.com/feeds",
    ]
    c.save_interval_minutes = 15
    c.collar_spreadsheet_id = "1nkMsXbtqrWiFzX5-gkzOT1UtFsFCmJpHeOl-MtjXGNo"
    c.collar_spreadsheet_title = "The collar"
    c.collar_worksheet_name = "Log"
    c.collar_account_cell = "P5"
    return c

def find_project_root(start_path=None):
    if start_path is None:
        start_path = os.path.dirname(os.path.abspath(__file__))
    current = start_path
    while True:
        if os.path.isdir(os.path.join(current, '.git')):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise FileNotFoundError("No .git directory found in any parent folder.")
        current = parent

def gui(c):
    c.portfolio_labels =  \
        ["Symbol", "Strike", "Underlying", "ITM%", "N", "Type", "Start"]
    c.portfolio_labels += ["Expire", "Premium", "Last", "Buyback", "PL"]
    c.portfolio_labels += [ "Days",
                "DIT",
                "DTE",
                "PPD",
                "PPD_NOW"]
    c.portfolio_labels += ["Assign", "Close@", "Order", "Order_n", "Order_lim"]
    c.portfolio_float_columns = ["Strike", "Underlying", "ITM%", "Premium", 
                                 "Last", "Buyback", "PL", "PPD", "PPD_NOW", "Assign",
                                  "Close@", "Order_lim"]
    c.portfolio_int_columns = ["N", "Days", "DIT", "DTE", "Order_n"]
    c.portfolio_columns_left = ["Symbol", "Type"]
    c.itm_threshold = 2.0  # ITM% threshold to consider option ITM
    c.stock_labels = ["Symbol", "N", "Buy", "Break-even", "Date", "Last", "Profit"]
    c.stock_columns_left = ["Symbol"]
    c.portfolio_visible_rows = 8
    c.stock_visible_rows = 4
    c.log_labels = [
        "Open", "Type", "Symbol", "#", "Strike", "Price", "Expiry",
        "Com", "Premium", "Assign", "Close", "Close px", "Close com", "Profit",
    ]
    c.log_columns_left = ["Open", "Type", "Symbol", "Expiry", "Close"]
    return c

def path(c):
    c.project_root = find_project_root()
    c.credentials_path = os.path.join('/Users/koenkam/code/secrets', 'autobalance-40f29-599eaad48e9f.json')
    return c

def wheel(c):
    c.stocks=[
        'GOOGL',
        'AMZN',
        'NVDA',
        'SHOP',
        'AMD'
    ]
    c.default_exchange = 'CBOE'
    c.cash_settled_symbols = {'SPX', 'XSP', 'NDX', 'RUT', 'VIX'}
    c.book_settle_seconds = 60
    c.roll_window_seconds = 15 * 60
    return c

def screener(c):
    c.screener_symbols = [
        'AMZN', 'GOOGL', 'AMD', 'SHOP', 'NVDA', 'ANET', 'RDDT',
        'JPM', 'KO', 'BAC', 'PYPL', 'RCL', 'V', 'HIMS', 'PANW',
        'MSFT', 'AAPL', 'NFLX', 'META', 'AXP', 'MU', 'AVGO',
    ]
    c.screener_target_delta = 0.25
    c.screener_delta_band = (0.20, 0.30)
    c.screener_candidate_band = (0.12, 0.40)
    c.screener_min_sessions = 5
    c.screener_max_spread = 0.10
    c.screener_min_open_interest = 100
    c.screener_fill_fraction = 0.25
    c.screener_rescan_minutes = 15
    c.option_commission = 0.50
    c.market_holidays = {
        '20260101', '20260119', '20260216', '20260403', '20260525', '20260619',
        '20260703', '20260907', '20261126', '20261225',
        '20270101', '20270118', '20270215', '20270326', '20270531', '20270618',
        '20270705', '20270906', '20271125', '20271224',
    }
    return c

def make_c():
    c = Stub()
  

    for f in [
            general,
            path,
            wheel,
            screener,
            gui
        ]:
        c = f(c)
    return c



def create_c():
    return make_c()
