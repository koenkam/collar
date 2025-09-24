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
        self.portfolio_ref = self.db.collection('portfolio')

    def get_portfolio(self):
        docs = self.portfolio_ref.stream()
        self.portfolio = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            self.portfolio.append(data)
        print("Fetched portfolio from Firestore:", self.portfolio)
        return self.portfolio

   
    
    def merge_portfolio_item(self, positionkey):
        instrument_id = self.controller.get_instrument_id_from_portfolio(positionkey)
        position_doc = self.portfolio_ref.document(instrument_id)
        doc = position_doc.get()
        if doc.exists:
            position_data = doc.to_dict()
            self.controller.portfolio[positionkey]['premium'] = position_data.get('premium')
            self.controller.portfolio[positionkey]['startdate'] = position_data.get('startdate')
        else:
            # Create new document
            position_data = {
                'premium': 0,
                'startdate': datetime.datetime.now().strftime("%Y%m%d"),
                'symbol': self.controller.portfolio[positionkey]['symbol'],
                'secType': self.controller.portfolio[positionkey]['secType'],
                'right': self.controller.portfolio[positionkey]['contract'].right,
                'strike': self.controller.portfolio[positionkey]['contract'].strike,
                'expiry': self.controller.portfolio[positionkey]['contract'].lastTradeDateOrContractMonth,
                'position': self.controller.portfolio[positionkey]['position'],
                'avgCost': self.controller.portfolio[positionkey]['avgCost'],
            }
            position_doc.set(position_data)