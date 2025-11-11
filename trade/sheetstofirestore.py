#in my google account, i have a sheet called "The collar", i wish to retrieve some values from that sheet
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import create_c
from google.cloud import firestore
c=create_c()

def sheets_to_firestore():
    excel_creds = ServiceAccountCredentials.from_json_keyfile_name(c.credentials_path, c.scope)
    client = gspread.authorize(excel_creds)
    sheet = client.open("FXA").worksheet('lazy')
    try:
        US03price = float(sheet.get('A1')[0][0].replace(',','.'))
        ERPDprice = float(sheet.get('A2')[0][0].replace(',','.'))
        print(f"US03price: {US03price}, ERPDprice: {ERPDprice}")
    except Exception as e:
        print(f"Error retrieving prices from sheet: {e}")
        return
    db = firestore.Client()
    ref = db.collection('portfolio')
    #get the doc with pk 'STK_US03' and put all values in a dict
    doc_ref = ref.document('STK_US03')
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['lastPrice'] = US03price
        doc_ref.set(data)
    doc_ref = ref.document('STK_ERND')
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['lastPrice'] = ERPDprice
        doc_ref.set(data)
