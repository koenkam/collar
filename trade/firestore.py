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

   
    
    def merge_portfolio_item(self, instrument_id):
        position_doc = self.option_portfolio_ref.document(instrument_id)
        doc = position_doc.get()
        if doc.exists:
            position_data = doc.to_dict()
            self.controller.option_portfolio[instrument_id].premium = position_data.get('premium')
            self.controller.option_portfolio[instrument_id].startdate = position_data.get('startdate')
        else:
            # Create new document
            position_data = {
                'premium': 0,
                'startdate': datetime.datetime.now().strftime("%Y%m%d"),
                'symbol': self.controller.option_portfolio[instrument_id].contract.symbol,
                'secType': self.controller.option_portfolio[instrument_id].contract.secType,
                'right': self.controller.option_portfolio[instrument_id].contract.right,
                'strike': self.controller.option_portfolio[instrument_id].contract.strike,
                'expiry': self.controller.option_portfolio[instrument_id].contract.lastTradeDateOrContractMonth,
                'n': self.controller.option_portfolio[instrument_id].n,
                'avgCost': self.controller.option_portfolio[instrument_id].avgCost,
                'conId': self.controller.option_portfolio[instrument_id].contract.conId,
                
            }
            position_doc.set(position_data)