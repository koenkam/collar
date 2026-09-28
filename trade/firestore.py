#i have a firestore database with a collection "portfolio"
import os
from google.cloud import firestore
import datetime

from config import create_c
c=create_c()

# i have the credentials in config/collar-c0dc3-firebase-adminsdk-fbsvc-92d702ce65.json
# load them and use them

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/users/koenkam/code/secrets/collar-c0dc3-firebase-adminsdk-fbsvc-92d702ce65.json"

BATCH_LIMIT = 450


def log_sequence(trade):
    if trade.get("seq") is not None:
        return int(trade["seq"])
    try:
        return int(str(trade.get("id", "")).split("_")[-1])
    except ValueError:
        return 0


def sort_log(trades):
    """Newest close first, same-day rows in sequence order."""
    trades.sort(
        key=lambda trade: (trade.get("close_date") or "", -log_sequence(trade)),
        reverse=True,
    )
    return trades


class FirestoreDB:

    def __init__(self, controller):
        self.controller = controller
        self.db = firestore.Client()
        self.option_portfolio_ref = self.db.collection('portfolio')

    def get_summary(self):
        doc = self.db.collection("summary").document("collar").get()
        if not doc.exists:
            return {"start_date": "", "value_start": None}
        data = doc.to_dict() or {}
        return {
            "start_date": data.get("start_date") or "",
            "value_start": data.get("value_start"),
        }

    def get_log(self):
        trades = []
        for doc in self.db.collection("log").stream():
            data = doc.to_dict() or {}
            data["id"] = doc.id
            trades.append(data)
        return sort_log(trades)

    def load_book(self):
        """Option and stock documents, keyed by instrument id."""
        options, stocks = {}, {}
        for doc in self.option_portfolio_ref.stream():
            data = doc.to_dict() or {}
            if data.get("secType") == "STK" or doc.id.startswith("STK_"):
                stocks[doc.id] = data
            else:
                options[doc.id] = data
        return options, stocks

    def load_processed(self):
        return {doc.id for doc in self.db.collection("processed").stream()}

    def load_review(self):
        return {doc.id: doc.to_dict() or {} for doc in self.db.collection("review").stream()}

    def is_initialized(self):
        doc = self.db.collection("summary").document("book").get()
        return doc.exists and bool((doc.to_dict() or {}).get("initialized"))

    def commit(self, ops):
        """Write ("set", collection, id, data) and ("delete", collection, id) together.

        Up to BATCH_LIMIT operations are one atomic batch. Longer lists are
        only written by the one-time start of the book.
        """
        for start in range(0, len(ops), BATCH_LIMIT):
            batch = self.db.batch()
            for op in ops[start:start + BATCH_LIMIT]:
                ref = self.db.collection(op[1]).document(op[2])
                if op[0] == "set":
                    batch.set(ref, op[3])
                else:
                    batch.delete(ref)
            batch.commit()

    def save_current_prices(self):
        """Save current prices for all positions to Firestore"""
        try:
            batch = self.db.batch()
            count = 0
            known = set(self.controller.book_options) | set(self.controller.book_stocks)

            # Update options
            for instrument_id, position in list(self.controller.option_portfolio.items()):
                if instrument_id not in known:
                    continue
                ref = self.option_portfolio_ref.document(instrument_id)
                updates = {}
                if hasattr(position, 'lastPrice') and position.lastPrice is not None and position.lastPrice != 0:
                    updates['lastPrice'] = float(position.lastPrice)
                if hasattr(position, 'underlyingPrice') and position.underlyingPrice is not None and position.underlyingPrice != 0:
                    updates['underlyingPrice'] = float(position.underlyingPrice)
                
                if updates:
                    batch.update(ref, updates)
                    count += 1
                    if count >= 400: # Firestore batch limit is 500
                        batch.commit()
                        batch = self.db.batch()
                        count = 0

            # Update stocks
            for instrument_id, position in list(self.controller.stock_portfolio.items()):
                if instrument_id not in known:
                    continue
                ref = self.option_portfolio_ref.document(instrument_id)
                updates = {}
                if hasattr(position, 'lastPrice') and position.lastPrice is not None and position.lastPrice != 0:
                    updates['lastPrice'] = float(position.lastPrice)
                
                if updates:
                    batch.update(ref, updates)
                    count += 1
                    if count >= 400:
                        batch.commit()
                        batch = self.db.batch()
                        count = 0
                        
            if count > 0:
                batch.commit()
                
            print(f"Saved prices to Firestore at {datetime.datetime.now()}")
            return True
        except Exception as e:
            print(f"Error saving prices to Firestore: {e}")
            return False
