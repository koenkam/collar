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

def path(c):
    c.project_root = find_project_root()
    return c


def make_c():
    c = Stub()
  

    for f in [
            general,
            path,
        ]:
        c = f(c)
    return c



def create_c():
    return make_c()
