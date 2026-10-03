import os
import queue
import sys
import threading
import time

import wx

from trade.api import IBApi
from trade.controller import Controller
from trade.main import MainFrame

ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "collar.png")


def apply_app_icon(frame):
    if not os.path.isfile(ICON_PATH):
        return
    icon = wx.Icon(ICON_PATH, wx.BITMAP_TYPE_PNG)
    if icon.IsOk():
        frame.SetIcon(icon)
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSImage
        image = NSImage.alloc().initWithContentsOfFile_(ICON_PATH)
        if image is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception as e:
        print(f"Dock icon not set: {e}")


def main():
    # Create queues for communication
    gui_to_ib = queue.Queue()
    ib_to_gui = queue.Queue()
    controller = Controller(gui_to_ib, ib_to_gui)
    ib_api = IBApi(gui_to_ib, ib_to_gui)

    

    # Start IBApi in completely separate thread
    def run_ib_api():
        try:
            ib_api.start_api()
        except Exception as e:
            print(f"IBApi error: {e}")
    
    ib_thread = threading.Thread(target=run_ib_api, daemon=True)
    ib_thread.start()
    
    app = wx.App(False)
    
    frame = MainFrame(controller)
    apply_app_icon(frame)
    
    frame.Center()
    
    result = frame.Show(True)
    
    # Force the window to come to front on macOS
    frame.Raise()
    if sys.platform == 'darwin':  # macOS
        frame.RequestUserAttention(wx.USER_ATTENTION_ERROR)
    
    app.SetTopWindow(frame)
    controller.start()  # Start processing in controller
    app.MainLoop()

if __name__ == "__main__":
    main()
