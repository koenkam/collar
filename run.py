import wx
import threading
import queue
import sys
from trade.api import IBApi
from trade.main import MainFrame

def main():
    # Create queues for communication
    gui_to_ib = queue.Queue()
    ib_to_gui = queue.Queue()
    
    # Create IBApi instance but don't start yet
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
    
    frame = MainFrame(None, "IB TWS Client", gui_to_ib, ib_to_gui)
    
    frame.Center()
    
    result = frame.Show(True)
    
    # Force the window to come to front on macOS
    frame.Raise()
    if sys.platform == 'darwin':  # macOS
        frame.RequestUserAttention(wx.USER_ATTENTION_ERROR)
    
    app.SetTopWindow(frame)
    
    app.MainLoop()

if __name__ == "__main__":
    main()
