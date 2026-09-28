"""Realized-trade math shared by the Log import and the main window."""
import datetime

SHEETS_EPOCH = datetime.date(1899, 12, 30)


def sheets_serial_to_date(serial):
    return SHEETS_EPOCH + datetime.timedelta(days=int(serial))


def to_yyyymmdd(value):
    """Accept a Sheets serial, YYYYMMDD, or YYYY-MM-DD."""
    if value is None or value == "":
        raise ValueError("missing date")
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, datetime.date):
        return value.strftime("%Y%m%d")
    if isinstance(value, (int, float)):
        return sheets_serial_to_date(value).strftime("%Y%m%d")
    text = str(value).strip()
    if text.isdigit() and len(text) == 8:
        return text
    if text.isdigit():
        return sheets_serial_to_date(int(text)).strftime("%Y%m%d")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(text[:10], fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise ValueError(f"unrecognized date {value!r}")


def yyyymmdd_to_date(value):
    return datetime.datetime.strptime(value, "%Y%m%d").date()


def format_yyyymmdd(value):
    if not value or len(str(value)) != 8:
        return "—"
    text = str(value)
    return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"


def as_float(value):
    if value is None or value == "":
        return None
    return float(value)


def money(value):
    return round(float(value), 2)


def clean_price(value):
    return round(float(value), 6)


def trade_premium(signed_quantity, open_price, open_commission):
    if signed_quantity == 0:
        return None
    return signed_quantity * open_price * 100 - open_commission


def trade_profit(premium, close_price, signed_quantity, close_commission):
    return premium - close_price * signed_quantity * 100 + close_commission


def formula_expr(value):
    text = "" if value is None else str(value).strip()
    if text.startswith("="):
        return text
    return None


def pad_row(row, width=16):
    row = list(row or [])
    if len(row) < width:
        row.extend([""] * (width - len(row)))
    return row


def right_code(instr):
    label = str(instr or "").strip().upper()
    if label == "PUT":
        return "P"
    if label == "CALL":
        return "C"
    return label


def right_label(right):
    if right == "P":
        return "PUT"
    if right == "C":
        return "CALL"
    return str(right or "")


def parse_log_sheet(values, formulas):
    """Build summary and realized trades from Log!A1:P.

    `values` are unformatted sheet values. `formulas` are the formula strings.
    Trades start at row 18. Premium and profit are recomputed from the sheet
    formulas and checked against the evaluated profit cell.
    """
    if len(values) < 2:
        raise ValueError("Log sheet is missing the totals block")
    start_row = pad_row(values[0])
    value_row = pad_row(values[1])
    summary = {
        "start_date": to_yyyymmdd(start_row[2]),
        "value_start": money(value_row[2]),
    }

    trades = []
    errors = []
    seq = 0
    for offset in range(17, max(len(values), len(formulas))):
        row = pad_row(values[offset] if offset < len(values) else [])
        formula_row = pad_row(formulas[offset] if offset < len(formulas) else [])
        symbol = str(row[2] or "").strip()
        if not symbol:
            continue
        seq += 1
        sheet_row = offset + 1
        try:
            signed_quantity = int(float(row[3]))
            open_price = as_float(row[5])
            open_commission = as_float(row[7]) or 0.0
            close_price = as_float(row[12])
            close_commission = as_float(row[13]) or 0.0
            if open_price is None or close_price is None:
                raise ValueError("open price and close price are required")
            premium = trade_premium(signed_quantity, open_price, open_commission)
            profit = trade_profit(premium, close_price, signed_quantity, close_commission)
            sheet_profit = as_float(row[15])
            if sheet_profit is None or abs(money(profit) - money(sheet_profit)) > 0.01:
                raise ValueError(
                    f"profit {profit} does not match sheet {sheet_profit}"
                )
            close_date = to_yyyymmdd(row[11])
            trade = {
                "seq": seq,
                "open_date": to_yyyymmdd(row[0]),
                "close_date": close_date,
                "right": right_code(row[1]),
                "symbol": symbol,
                "signed_quantity": signed_quantity,
                "strike": clean_price(row[4]),
                "expiry": to_yyyymmdd(row[6]),
                "open_price": clean_price(open_price),
                "open_commission": clean_price(open_commission),
                "close_price": clean_price(close_price),
                "close_commission": clean_price(close_commission),
                "premium": money(premium),
                "profit": money(profit),
                "id": f"{close_date}_{seq:04d}",
            }
            price_expr = formula_expr(formula_row[5])
            commission_expr = formula_expr(formula_row[7])
            if price_expr:
                trade["open_price_expr"] = price_expr
            if commission_expr:
                trade["open_commission_expr"] = commission_expr
            assign = as_float(row[9])
            if assign is not None:
                trade["assign"] = money(assign)
        except Exception as e:
            errors.append(f"row {sheet_row} {symbol}: {e}")
            continue
        trades.append(trade)
    return summary, trades, errors


def short_put_notional(option_portfolio):
    """Assignment cash of open short puts. Long hedges are excluded."""
    total = 0.0
    for position in (option_portfolio or {}).values():
        contract = getattr(position, "contract", None)
        if contract is None or getattr(contract, "secType", "") != "OPT":
            continue
        if getattr(contract, "right", "") != "P":
            continue
        quantity = getattr(position, "n", 0) or 0
        if quantity >= 0:
            continue
        strike = getattr(contract, "strike", 0) or 0
        total += strike * abs(quantity) * 100
    return total


def compute_collar_totals(summary, trades, account_value, assign_notional, today=None):
    today = today or datetime.date.today()
    summary = summary or {}
    start_date = summary.get("start_date") or ""
    value_start = summary.get("value_start")
    total_usd = 0.0
    for trade in trades or []:
        profit = trade.get("profit")
        if profit is not None:
            total_usd += float(profit)
    total_usd = money(total_usd)
    days = None
    if start_date:
        days = (today - yyyymmdd_to_date(start_date)).days
    percentage = None
    max_assign = None
    per_year = None
    account = None
    if account_value is not None:
        account = float(account_value)
        if account != 0 and assign_notional is not None:
            percentage = float(assign_notional) / account
        max_assign = account * 0.7
        base = account - total_usd
        if days and days > 0 and base > 0:
            per_year = (account / base) ** (365 / days)
    return {
        "start_date": start_date,
        "value_start": value_start,
        "days": days,
        "per_year": per_year,
        "assign": None if assign_notional is None else float(assign_notional),
        "percentage": percentage,
        "max": max_assign,
        "total_usd": total_usd,
        "account_value": account,
    }


def format_money(value):
    if value is None:
        return "—"
    return f"${float(value):,.2f}"


def format_number(value, digits=2):
    if value is None or value == "":
        return ""
    return f"{float(value):.{digits}f}"


def format_price(value):
    if value is None or value == "":
        return ""
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return text or "0"


def format_totals(totals):
    start = format_yyyymmdd(totals.get("start_date"))
    days = "—" if totals.get("days") is None else str(totals["days"])
    per_year = "—" if totals.get("per_year") is None else f"{totals['per_year']:.2f}"
    percentage = "—" if totals.get("percentage") is None else f"{totals['percentage']:.2f}"
    line1 = (
        f"start {start}    "
        f"value start {format_money(totals.get('value_start'))}    "
        f"days {days}    "
        f"per year {per_year}"
    )
    line2 = (
        f"assign {format_money(totals.get('assign'))}    "
        f"percentage {percentage}    "
        f"max {format_money(totals.get('max'))}    "
        f"total {format_money(totals.get('total_usd'))}"
    )
    return line1, line2


def format_log_row(trade):
    assign = trade.get("assign")
    return [
        format_yyyymmdd(trade.get("open_date")),
        right_label(trade.get("right")),
        trade.get("symbol") or "",
        str(trade.get("signed_quantity", "")),
        format_price(trade.get("strike")),
        format_price(trade.get("open_price")),
        format_yyyymmdd(trade.get("expiry")),
        format_number(trade.get("open_commission")),
        format_number(trade.get("premium")),
        "" if assign is None else format_number(assign),
        format_yyyymmdd(trade.get("close_date")),
        format_price(trade.get("close_price")),
        format_number(trade.get("close_commission")),
        format_number(trade.get("profit")),
    ]
