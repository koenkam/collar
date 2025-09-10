from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import threading
import time

class App(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        
    def nextValidId(self, orderId):
        print("Connected")
        
    def tickPrice(self, reqId, tickType, price, attrib):
        if tickType == 4:  # LAST
            print(f"Price: ${price}")
    
    def tickGeneric(self, reqId, tickType, value):
        if tickType == 106:  # Implied Vol
            print(f"IV: {value:.1%}")
            
    def tickOptionComputation(self, reqId, tickType, tickAttrib, impliedVol, 
                            delta, optPrice, pvDividend, gamma, vega, theta, undPrice):
        if undPrice is not None and undPrice < 1e100:
            print(f"Underlying: ${undPrice}")
        if impliedVol is not None and impliedVol < 1e100:
            print(f"IV: {impliedVol:.1%}")
        if delta is not None and delta < 1e100:
            print(f"Delta: {delta:.4f}")
        if gamma is not None and gamma < 1e100:
            print(f"Gamma: {gamma:.4f}")
        if theta is not None and theta < 1e100:
            print(f"Theta: {theta:.4f}")
        if vega is not None and vega < 1e100:
            print(f"Vega: {vega:.4f}")

app = App()
app.connect("127.0.0.1", 7496, 0)

# Start API
t = threading.Thread(target=app.run, daemon=True)
t.start()
time.sleep(1)

# Option contract
contract = Contract()
contract.conId = 807816517
contract.secType = "OPT"
contract.exchange = "SMART"
contract.currency = "USD"

# Get data
app.reqMktData(1, contract, "106", False, False, [])
time.sleep(5)

app.disconnect()