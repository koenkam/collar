from util import Stub, print_banner
import datetime
import os


def general(c):
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
    c.portfolio_columns_left = ["Symbol", "Type"]
    c.itm_threshold = 2.0  # ITM% threshold to consider option ITM
    return c

def path(c):
    c.project_root = find_project_root()
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
    return c

def make_c():
    c = Stub()
  

    for f in [
            general,
            path,
            wheel,
            gui
        ]:
        c = f(c)
    return c



def create_c():
    return make_c()
