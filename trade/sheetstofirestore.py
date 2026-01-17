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
    print("Connecting to Firestore...")
    db = firestore.Client()
    ref = db.collection('portfolio')
    
    print("Updating STK_US03...")
    doc_ref = ref.document('STK_US03')
    doc = doc_ref.get()
    if doc.exists:
        print("Document STK_US03 exists, updating lastPrice...")
        data = doc.to_dict()
        data['lastPrice'] = US03price
        print(f"New data for STK_US03: {data}")
        doc_ref.set(data)
        print("STK_US03 updated successfully.")
    print("Updated STK_US03")
    doc_ref = ref.document('STK_ERND')
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['lastPrice'] = ERPDprice
        doc_ref.set(data)
