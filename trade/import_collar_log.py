"""One-shot copy of The collar / Log into Firestore.

Run from the repo root:

    env/bin/python -m trade.import_collar_log

Writes summary/collar and replaces the log collection. Does not change the sheet.
"""
import os
import sys

from google.cloud import firestore

from trade.logbook import parse_log_sheet
from trade.sheetstofirestore import _open_log_worksheet, _open_the_collar, _sheets_client

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
    "/users/koenkam/code/secrets/collar-c0dc3-firebase-adminsdk-fbsvc-92d702ce65.json"
)


def _load_sheet():
    client = _sheets_client()
    spreadsheet = _open_the_collar(client)
    worksheet = _open_log_worksheet(spreadsheet)
    values = worksheet.get("A1:P", value_render_option="UNFORMATTED_VALUE")
    formulas = worksheet.get("A1:P", value_render_option="FORMULA")
    return spreadsheet.title, worksheet.title, values, formulas


def _commit_batches(db, operations):
    batch = db.batch()
    count = 0
    for operation in operations:
        operation(batch)
        count += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
    if count:
        batch.commit()


def import_collar_log():
    title, worksheet, values, formulas = _load_sheet()
    summary, trades, errors = parse_log_sheet(values, formulas)
    print(f"Read '{title}' / '{worksheet}'")
    if errors:
        print("Import stopped. Sheet profit did not match the stored formula:")
        for error in errors:
            print(f"  {error}")
        return False

    for trade in trades:
        print(
            f"{trade['symbol']:6} close {trade['close_date']} "
            f"sheet {trade['profit']:.2f} stored {trade['profit']:.2f}"
        )

    db = firestore.Client()
    existing = list(db.collection("log").stream())
    operations = []
    for doc in existing:
        ref = doc.reference
        operations.append(lambda batch, ref=ref: batch.delete(ref))
    summary_ref = db.collection("summary").document("collar")
    operations.append(lambda batch, ref=summary_ref: batch.set(ref, summary))
    for trade in trades:
        ref = db.collection("log").document(trade["id"])
        payload = {key: value for key, value in trade.items() if key != "id"}
        operations.append(lambda batch, ref=ref, payload=payload: batch.set(ref, payload))
    _commit_batches(db, operations)

    total = round(sum(trade["profit"] for trade in trades), 2)
    first = trades[0] if trades else None
    last = trades[-1] if trades else None
    print(
        f"Wrote summary/collar start {summary['start_date']} "
        f"value_start {summary['value_start']:.2f}"
    )
    print(f"Wrote {len(trades)} log trades, total usd {total:.2f}")
    if first and last:
        print(
            f"First {first['symbol']} closed {first['close_date']}, "
            f"last {last['symbol']} opened {last['open_date']}"
        )
    return True


if __name__ == "__main__":
    ok = import_collar_log()
    sys.exit(0 if ok else 1)
