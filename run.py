import wx
import threading
import sys
import time
from trade.api import IBApi
from trade.main import MainFrame
from trade.controller import Controller
import queue


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
