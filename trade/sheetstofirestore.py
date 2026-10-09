#in my google account, i have a sheet called "The collar", i wish to retrieve some values from that sheet
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import create_c
c=create_c()

def _sheets_client():
    excel_creds = ServiceAccountCredentials.from_json_keyfile_name(c.credentials_path, c.scope)
    return gspread.authorize(excel_creds)

def _open_the_collar(client):
    if getattr(c, "collar_spreadsheet_id", None):
        return client.open_by_key(c.collar_spreadsheet_id)
    last_error = None
    for title in ("The collar", "the collar", "The Collar"):
        try:
            return client.open(title)
        except gspread.exceptions.SpreadsheetNotFound as e:
            last_error = e
    if last_error:
        raise last_error
    raise gspread.exceptions.SpreadsheetNotFound("The collar")

def _open_log_worksheet(spreadsheet):
    name = getattr(c, "collar_worksheet_name", "Log")
    try:
        return spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.get_worksheet(0)
        if worksheet and worksheet.title.strip().lower() == name.lower():
            return worksheet
        raise

def update_collar_account_value(account_value):
    """Write the trading account value to The collar / Log / P5, once per launch."""
    cell = getattr(c, "collar_account_cell", "P5")
    try:
        client = _sheets_client()
        spreadsheet = _open_the_collar(client)
        worksheet = _open_log_worksheet(spreadsheet)
        worksheet.update_acell(cell, account_value)
        print(
            f"Updated '{spreadsheet.title}' / '{worksheet.title}'!{cell} "
            f"with account value {account_value}"
        )
        return True
    except Exception as e:
        sa_email = json.load(open(c.credentials_path)).get("client_email", "")
        detail = str(e).strip() or type(e).__name__
        print(
            f"Error updating The collar / Log / {cell}: {detail}. "
            f"Do not use a Google sign-in popup. In the spreadsheet Share dialog, add "
            f"{sa_email} as Editor "
            f"(https://docs.google.com/spreadsheets/d/{c.collar_spreadsheet_id}/edit)"
        )
        return False
