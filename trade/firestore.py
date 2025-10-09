#i have a firestore database with a collection "portfolio"
import os
from google.cloud import firestore
import datetime

from config import create_c
c=create_c()

# i have the credentials in config/collar-c0dc3-firebase-adminsdk-fbsvc-92d702ce65.json
# load them and use them

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/users/koenkam/code/secrets/collar-c0dc3-firebase-adminsdk-fbsvc-92d702ce65.json"
    
class FirestoreDB:

    def __init__(self, controller):
        self.controller = controller
        self.db = firestore.Client()
        self.option_portfolio_ref = self.db.collection('portfolio')

    def get_portfolio(self):
        docs = self.option_portfolio_ref.stream()
        self.option_portfolio = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            self.option_portfolio.append(data)
        return self.option_portfolio

   
    def merge_stock_item(self, instrument_id):
        position_doc = self.option_portfolio_ref.document(instrument_id)
        doc = position_doc.get()
        portfolio = self.controller.stock_portfolio
        if doc.exists:
            position_data = doc.to_dict()
            portfolio[instrument_id].avgCost = position_data.get('avgCost')
            portfolio[instrument_id].lastPrice = position_data.get('lastPrice')
            portfolio[instrument_id].startdate = position_data.get('startdate')
       
        else:
            # Create new document
            position_data = {
                'avgCost': 0,
                'startdate': datetime.datetime.now().strftime("%Y%m%d"),
                'symbol': portfolio[instrument_id].contract.symbol,
                'secType': portfolio[instrument_id].contract.secType,
                'n': portfolio[instrument_id].n,
                'conId': portfolio[instrument_id].contract.conId,
                'lastPrice': 0

            }
            position_doc.set(position_data)

    def merge_portfolio_item(self, instrument_id):
        position_doc = self.option_portfolio_ref.document(instrument_id)
        portfolio = self.controller.option_portfolio
        doc = position_doc.get()
        if doc.exists:
            position_data = doc.to_dict()
            portfolio[instrument_id].premium = position_data.get('premium')
            portfolio[instrument_id].startdate = position_data.get('startdate')
       
        else:
            # Create new document
            position_data = {
                'premium': 0,
                'startdate': datetime.datetime.now().strftime("%Y%m%d"),
                'symbol': portfolio[instrument_id].contract.symbol,
                'secType': portfolio[instrument_id].contract.secType,
                'right': portfolio[instrument_id].contract.right,
                'strike': portfolio[instrument_id].contract.strike,
                'expiry': portfolio[instrument_id].contract.lastTradeDateOrContractMonth,
                'n': portfolio[instrument_id].n,
                'avgCost': portfolio[instrument_id].avgCost,
                'conId': portfolio[instrument_id].contract.conId,
                'lastPrice': 0

            }
            position_doc.set(position_data)