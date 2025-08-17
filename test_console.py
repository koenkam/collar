import queue
import threading
import time
from trade.api import IBApi

def main():
    command_queue = queue.Queue()
    data_queue = queue.Queue()
    
    # Create and start IBApi
    ib_api = IBApi(command_queue, data_queue)
    
    def run_ib_api():
        try:
            ib_api.start_api()
        except Exception as e:
            print(f"IBApi error: {e}")
    
    ib_thread = threading.Thread(target=run_ib_api, daemon=True)
    ib_thread.start()
    
    print("Waiting for connection...")
    time.sleep(3)
    
    print("Requesting managed accounts...")
    command_queue.put("get_accounts")
    time.sleep(2)
    
    print("Requesting orders...")
    command_queue.put("get_orders")
    
    print("Requesting positions...")
    command_queue.put("get_positions")
    
    print("Requesting cash...")
    command_queue.put("get_cash")
    
    print("Requesting account summary...")
    command_queue.put("get_account_summary")
    
    # Check for data
    timeout = 10
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if not data_queue.empty():
            data = data_queue.get()
            print(f"Received: {data}")
        time.sleep(0.5)
    
    print("Done")

if __name__ == "__main__":
    main()
