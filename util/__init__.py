import pickle
import functools
from colorama import Fore, Back, Style
import sys, io
import time
from tabulate import tabulate
import datetime
import pytz
from termcolor import colored
import queue


class Stub:
    
    def __init__(self, *args, **kwargs):
        if args and args[0] is not None and type(args[0]) == dict:
            for key, value in args[0].items():
                setattr(self, key, value)
            return
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self):
        r = []
        for p in vars(self):
            if type(getattr(self,p)) == float:
                r.append( f'{p}={getattr(self,p):.2f}')
            else:
                r.append( f'{p}={getattr(self,p)}')
        return '[' + self.__class__.__name__+ ': ' + ', '.join(r) +']'

    def deepcopy(self):
        return pickle.loads(pickle.dumps(self))
    
    def get_columns(self):
        return [attr for attr in dir(self) if not callable(getattr(self, attr)) and not attr.startswith("__")]

    def get_n_columns(self):
        return len(self.get_columns())
    
    def get(self, prop):
        return getattr(self, prop)
    
    def is_empty(self):
        return len(self.__dict__) == 0

    @classmethod
    def getname(cls):
        return cls.__name__

"""
list of strings, concatenate into 1 string
"""
def make_feedback(*args):
    feedback_str = ' '.join([x.strip() for x in args])
    return feedback_str

def clear_queue(q):
    while not q.empty():
        try:
            q.get_nowait()  # Unblocks the get() method if the queue is empty.
        except queue.Empty:
            break

def countdown(t, message):
    for i in range(t,0,-1):
        sys.stdout.write(f'\r{message} in {i} seconds')
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write('\r' + ' ' * 100 + '\r')
    sys.stdout.flush()
    
def print_stub_table(stublist):
    all_attrs = stublist[0].__dict__
    header = [attr for attr in all_attrs if not (attr.startswith("__") and attr.endswith("__"))]
    stubtable = [[getattr(s, prop) for prop in header] for s in stublist]
    print(tabulate(stubtable, headers=header))

def print_list_of_list_table(listoflist):
    print(tabulate(listoflist))

def print_banner(line):
    

    edges = [[
        '┌', '─', '┐',
        '│', ' ', '│',
        '└', '─', '┘'   
    ],
    [
        '╔', '═', '╗',
        '║', ' ', '║',
        '╚', '═', '╝'
    ],
    ]
    chars = edges[0]

    lineout = colorize(line.strip().upper())
    linelength = len(line.strip())
    print(colorize(chars[0] + linelength * chars[1] + chars[2]))
    print(colorize(chars[3]) + lineout + colorize(chars[5]))
    print(colorize(chars[6] + linelength * chars[7] + chars[8]))

def colorize(text):
    return colored(text.strip().upper(), 'blue', 'on_white', attrs=['bold'])

def print_title_banner(line):
    for i in range(10):
        print()
    print_banner(line)
    for i in range(2):
        print()
        
def is_int(number):
    if type(number) == int:
        return True
    if type(number) != str:
        return False
    try:
        int(number)
    except:
        return False
    return True

def is_float(number):
    if type(number) == float:
        return True
    if type(number) != str:
        return False
    try:
        float(number)
    except:
        return False
    return True
    
def is_float_and_not_is_int(number):
    if is_int(number):
        return False
    if is_float(number):
        return True
    return False

def is_str(thestring):
    if type(thestring) == str:
        return True
    return False

def sign(number):
    return 0 if number == 0 else 1 if number > 0 else -1

def mround(number, factor):
    return round(round(number/factor) * factor,2)

def equal_parts(num, div):
    #print(type(num), num)
    #print(type(div), div)
    if type(num) != int or type(div) != int:
        return None
    #r = [num // div + (1 if x < num % div else 0)  for x in range (div)].reverse()
    r = [num // div + (1 if x < num % div else 0)  for x in range (div)]
    #print(r)
    return r


"""
setters + getters for nested objects
rgetattr(object, 'dotted.path.property')
"""
def rgetattr(obj, attr, *args):
    def _getattr(obj, attr):
        return getattr(obj, attr, *args)
    return functools.reduce(_getattr, [obj] + attr.split('.'))

def rsetattr(obj, attr, val):
    pre, _, post = attr.rpartition('.')
    return setattr(rgetattr(obj, pre) if pre else obj, post, val)

def rhasattr(obj, attr):
    _nested_attrs = attr.split(".")
    _curr_obj = obj
    for _a in _nested_attrs[:-1]:
        if hasattr(_curr_obj, _a):
            _curr_obj = getattr(_curr_obj, _a)
        else:
            return False
    return hasattr(_curr_obj, _nested_attrs[-1])


def multiply_scalar_list(s,l):
    return [x * s for x in l]

def vectoradd(a,b):
    r = []
    for i in range(len(a)):
        r.append(a[i] + b[i])
    return r

def wxdebug(func):
    def inner(*args, **kwargs):
        debug = False
        if debug:
            output = f'{Fore.BLUE}{Back.YELLOW}WX {func.__name__}{Style.RESET_ALL}         '
            print(output, end='', flush = True)
        r = func(*args, **kwargs)
        if debug:
            print('\b' * len(output), end='', flush = True)
        return r
    return inner
    
def ibdebug(func):
    
    def inner(*args, **kwargs):
        debug = False
        if debug:
            output = f'{Fore.BLUE}{Back.YELLOW}IBApi {func.__name__}{Style.RESET_ALL}      '
            print(output, end='', flush = True)
        r = func(*args, **kwargs)
        if debug:
            print('\b' * len(output), end='', flush = True)
        return r
    return inner


def get_git_branch():
    return pygit2.Repository('.').head.shorthand


def to_list(v):
    if type(v) == list:
        return v
    else:
        return [v]

"""
creates a new unique number every 10s
"""
def file_ord():
    now=datetime.datetime.now()
    return int((now.second + now.minute * 60 + now.hour * 3600 )/10)

"""
Usage:
with Stopwatch() as timer:
        # Your code block to measure
        for i in range(1000000):
            pass
"""
class Stopwatch:
    """
    Simple stopwatch class to measure execution time of code blocks.
    """

    def __init__(self, name=''):
        self.name = name
        self._start_time = None
        self._end_time = None
        print(f'Stopwatch started: {self.name}')

    def start(self):
        """
        Starts the stopwatch.
        """
        if self._start_time is not None:
            raise RuntimeError("Stopwatch already started")
        self._start_time = time.perf_counter()

    def stop(self):
        """
        Stops the stopwatch.
        """
        if self._start_time is None:
            raise RuntimeError("Stopwatch not started")
        self._end_time = time.perf_counter()

    def elapsed(self):
        """
        Returns the elapsed time in seconds.
        """
        if self._start_time is None or self._end_time is None:
            raise RuntimeError("Stopwatch not started or stopped")
        return self._end_time - self._start_time

    def __enter__(self):
        """
        Context manager to start the stopwatch automatically.
        """
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Context manager to stop the stopwatch automatically and print the elapsed time.
        """
        self.stop()
        elapsed = self.elapsed()
        print(f"{self.name} elapsed time: {elapsed:.6f} seconds".strip())