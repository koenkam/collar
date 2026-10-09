"""Realized-trade math shared by the Log import and the main window."""
import datetime

from util import expand_yymmdd

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


def format_yymmdd(value, missing="—"):
    """Six-digit date for grid cells. Other screens keep the full date."""
    text = str(value or "")
    if len(text) == 6 and text.isdigit():
        return text
    if len(text) != 8 or not text.isdigit():
        return missing
    return text[2:8]


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


def short_put_collateral(contract, quantity, multiplier=100.0, cash_settled=()):
    """Cash converted to shares if this short put is assigned.

    Undefined for calls, long options, and cash-settled underlyings.
    """
    if getattr(contract, "secType", "") != "OPT" or getattr(contract, "right", "") != "P":
        return None
    if getattr(contract, "symbol", "") in set(cash_settled or ()):
        return None
    if not quantity or quantity >= 0:
        return None
    return float(contract.strike) * abs(quantity) * float(multiplier)


def short_put_notional(option_portfolio, cash_settled=()):
    """Collateral of open short puts. Long hedges and cash-settled contracts are excluded."""
    total = 0.0
    for position in (option_portfolio or {}).values():
        contract = getattr(position, "contract", None)
        if contract is None:
            continue
        try:
            multiplier = float(getattr(contract, "multiplier", 0) or 0)
        except (TypeError, ValueError):
            multiplier = 0.0
        if multiplier <= 0:
            multiplier = 100.0
        value = short_put_collateral(contract, getattr(position, "n", 0), multiplier, cash_settled)
        if value:
            total += value
    return total


def compute_collar_totals(summary, trades, account_value, collateral=None, today=None,
                          max_fraction=0.7):
    """Totals for the dashboard strip.

    `trading_usd` is realized profit from the log. `total_profit` is the account
    value minus the value at start. Per year annualizes that total profit.
    `limit` is the collateral cap, `max_fraction` of the account. `room` is
    that cap minus current collateral.
    """
    today = today or datetime.date.today()
    summary = summary or {}
    start_date = summary.get("start_date") or ""
    value_start = summary.get("value_start")
    trading_usd = 0.0
    for trade in trades or []:
        profit = trade.get("profit")
        if profit is not None:
            trading_usd += float(profit)
    trading_usd = money(trading_usd)
    days = None
    if start_date:
        days = (today - yyyymmdd_to_date(start_date)).days
    percentage = None
    per_year = None
    total_profit = None
    limit = None
    room = None
    account = None
    if account_value is not None:
        account = float(account_value)
        limit = money(account * float(max_fraction))
        if collateral is not None:
            room = money(limit - float(collateral))
            if account != 0:
                percentage = float(collateral) / account
    if account is not None and value_start is not None:
        start_value = float(value_start)
        total_profit = money(account - start_value)
        if days and days > 0 and start_value > 0 and account > 0:
            per_year = (account / start_value) ** (365 / days)
    return {
        "start_date": start_date,
        "value_start": value_start,
        "days": days,
        "per_year": per_year,
        "collateral": None if collateral is None else float(collateral),
        "percentage": percentage,
        "max_fraction": float(max_fraction),
        "limit": limit,
        "room": room,
        "trading_usd": trading_usd,
        "total_profit": total_profit,
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


def format_percent(value, digits=0):
    if value is None:
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def format_dashboard(totals):
    """Display strings for the totals strip, keyed for the grouped layout."""
    days = totals.get("days")
    per_year = totals.get("per_year")
    return {
        "start": format_yyyymmdd(totals.get("start_date")),
        "value_start": format_money(totals.get("value_start")),
        "days": "—" if days is None else str(days),
        "per_year": "—" if per_year is None else f"{per_year:.2f}",
        "trading": format_money(totals.get("trading_usd")),
        "total": format_money(totals.get("total_profit")),
        "collateral": format_money(totals.get("collateral")),
        "percentage": format_percent(totals.get("percentage"), 1),
        "max": format_percent(totals.get("max_fraction"), 0),
        "limit": format_money(totals.get("limit")),
        "left": format_money(totals.get("room")),
    }


def profit_buckets(trades, group="month"):
    """Sum realized profit by close date. `group` is day, month, or year.

    Each row is the period profit and the running total, in date order.
    A trade with no close date or no profit is left out.
    """
    if group not in ("day", "month", "year"):
        group = "month"
    totals = {}
    for trade in trades or []:
        key = _bucket_key(trade.get("close_date"), group)
        profit = as_float(trade.get("profit"))
        if key is None or profit is None:
            continue
        totals[key] = totals.get(key, 0.0) + profit
    rows = []
    running = 0.0
    for key in sorted(totals):
        profit = money(totals[key])
        running = money(running + profit)
        rows.append({
            "key": key,
            "label": _bucket_label(key, group),
            "profit": profit,
            "cumulative": running,
        })
    return rows


def _bucket_key(value, group):
    text = expand_yymmdd(value)
    if not text:
        return None
    if group == "year":
        return text[:4]
    if group == "month":
        return text[:6]
    return text


def _bucket_label(key, group):
    if group == "year":
        return key
    if group == "month":
        return f"{key[:4]}-{key[4:6]}"
    return f"{key[2:4]}-{key[4:6]}-{key[6:8]}"


def format_log_row(trade):
    assign = trade.get("assign")
    return [
        format_yymmdd(trade.get("open_date")),
        right_label(trade.get("right")),
        trade.get("symbol") or "",
        str(trade.get("signed_quantity", "")),
        format_price(trade.get("strike")),
        format_price(trade.get("open_price")),
        format_yymmdd(trade.get("expiry")),
        format_number(trade.get("open_commission")),
        format_number(trade.get("premium")),
        "" if assign is None else format_number(assign),
        format_yymmdd(trade.get("close_date")),
        format_price(trade.get("close_price")),
        format_number(trade.get("close_commission")),
        format_number(trade.get("profit")),
    ]
