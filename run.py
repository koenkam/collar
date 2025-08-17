import wx
import threading
import queue
from trade.api import IBApi
from trade.main import MainFrame

def main():
    # Create queues for communication
    command_queue = queue.Queue()
    data_queue = queue.Queue()
    
    # Create IBApi instance but don't start yet
    ib_api = IBApi(command_queue, data_queue)
    
    # Start IBApi in completely separate thread
    def run_ib_api():
        try:
            ib_api.start_api()
        except Exception as e:
            print(f"IBApi error: {e}")
    
    ib_thread = threading.Thread(target=run_ib_api, daemon=True)
    ib_thread.start()
    
    print('Starting GUI...')
    # Create wxPython app - this should not be blocked by IBApi
    app = wx.App(False)
    frame = MainFrame(None, "IB TWS Client", command_queue, data_queue)
    frame.Center()
    frame.Show(True)
    frame.Raise()
    
    print('GUI should be visible now')
    app.MainLoop()

if __name__ == "__main__":
    main()
