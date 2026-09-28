"""Position book: turn broker positions and fills into book changes.

The engine is pure. It receives the stored book, the broker positions, and
the fills not yet applied, and returns one outcome per symbol. An outcome is
either a set of changes to write, or a review item when the change cannot be
explained.
"""
import datetime
import itertools

from .logbook import format_price, money

EPS = 1e-6


def option_id(expiry, symbol, strike, right):
    return f"{expiry}_{symbol}_{float(strike)}_{right}"


def stock_id(symbol):
    return f"STK_{symbol}"


def as_count(value):
    value = float(value or 0)
    rounded = round(value)
    return int(rounded) if abs(value - rounded) < EPS else value


def sgn(value):
    return (value > EPS) - (value < -EPS)


def describe(doc):
    symbol = doc.get("symbol", "")
    if doc.get("secType") == "STK":
        return symbol
    expiry = str(doc.get("expiry") or "")
    date = f"{expiry[0:4]}-{expiry[4:6]}-{expiry[6:8]}" if len(expiry) == 8 else expiry
    return f"{symbol} {format_price(doc.get('strike'))}{doc.get('right', '')} {date}"


def multiplier(doc):
    try:
        value = float(doc.get("multiplier") or 0)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value
    return 1.0 if doc.get("secType") == "STK" else 100.0


def fill_delta(fill):
    qty = float(fill["qty"])
    return qty if fill["side"] == "BOT" else -qty


def fill_cash(fill):
    """Cash in (positive) or out (negative) for one fill, net of commission."""
    return -fill_delta(fill) * float(fill["price"]) * multiplier(fill) - float(fill["commission"])


class Outcome:
    def __init__(self, symbol):
        self.symbol = symbol
        self.options = {}          # id -> final doc, or None to delete
        self.stocks = {}           # id -> final doc, or None to delete
        self.logs = []
        self.processed = []
        self.messages = []
        self.problems = []
        self.review = None

    @property
    def ok(self):
        return not self.problems

    def has_changes(self):
        return bool(self.options or self.stocks or self.logs or self.processed)


class SymbolBook:
    """Working copy of one symbol while its events are applied."""

    def __init__(self, symbol, options, stocks, broker, fills, today, cfg):
        self.symbol = symbol
        self.today = today
        self.cfg = cfg
        self.cash_settled = symbol in cfg.get("cash_settled", set())
        self.outcome = Outcome(symbol)
        self.original_options = {i: dict(d) for i, d in options.items()}
        self.options = {i: dict(d) for i, d in options.items()}
        for doc in self.options.values():
            doc["n"] = as_count(doc.get("n"))
        sid = stock_id(symbol)
        self.stock_key = sid
        self.original_stock = dict(stocks[sid]) if sid in stocks else None
        self.stock = dict(stocks[sid]) if sid in stocks else None
        if self.stock is not None:
            self.stock["n"] = as_count(self.stock.get("n"))
        self.broker = broker
        self.fills = sorted(fills, key=lambda f: (f.get("ts") or 0, f["exec_id"]))

    # --- helpers -----------------------------------------------------------

    def problem(self, text):
        self.outcome.problems.append(text)

    def n_of(self, iid):
        doc = self.options.get(iid)
        return as_count(doc.get("n")) if doc else 0

    def broker_n(self, iid):
        entry = self.broker.get(iid)
        return as_count(entry.get("n")) if entry else 0

    def ensure_option(self, iid, source, startdate):
        doc = self.options.get(iid)
        if doc is None or as_count(doc.get("n")) == 0:
            base = dict(doc or {})
            base.update({
                "secType": "OPT",
                "symbol": source.get("symbol", self.symbol),
                "right": source.get("right"),
                "strike": float(source.get("strike")),
                "expiry": str(source.get("expiry")),
                "multiplier": multiplier(source),
                "n": 0,
                "premium": 0.0,
                "startdate": startdate,
            })
            if source.get("conId"):
                base["conId"] = source["conId"]
            self.options[iid] = base
            return base, True
        return doc, False

    def ensure_stock(self, startdate, source=None):
        if self.stock is None or as_count(self.stock.get("n")) == 0:
            base = dict(self.stock or {})
            base.update({
                "secType": "STK",
                "symbol": self.symbol,
                "n": 0,
                "avgCost": 0.0,
                "credit": 0.0,
                "startdate": startdate,
            })
            if source and source.get("conId"):
                base["conId"] = source["conId"]
            self.stock = base
        return self.stock

    def premium_slice(self, doc, contracts):
        n = abs(as_count(doc.get("n")))
        premium = float(doc.get("premium") or 0.0)
        if n == 0:
            return 0.0
        return premium * contracts / n

    def option_log(self, doc, contracts, slice_, cash_close, close_price, close_commission, close_date, kind):
        mult = multiplier(doc)
        short = as_count(doc.get("n")) < 0
        signed_quantity = as_count(contracts if short else -contracts)
        profit = slice_ + cash_close
        row = {
            "kind": kind,
            "open_date": doc.get("startdate") or close_date,
            "close_date": close_date,
            "right": doc.get("right"),
            "symbol": doc.get("symbol", self.symbol),
            "signed_quantity": signed_quantity,
            "strike": float(doc.get("strike")),
            "expiry": str(doc.get("expiry")),
            "premium": money(slice_),
            "close_price": round(float(close_price), 6),
            "close_commission": round(float(close_commission), 6),
            "profit": money(profit),
        }
        if short and doc.get("right") == "P":
            row["assign"] = money(float(doc.get("strike")) * signed_quantity * mult)
        return row

    # --- option fills ------------------------------------------------------

    def clusters(self):
        window = float(self.cfg.get("roll_window_seconds", 900))
        by_right = {}
        for fill in self.fills:
            if fill["sec_type"] == "OPT":
                by_right.setdefault(fill["right"], []).append(fill)
        clusters = []
        for right, fills in by_right.items():
            current = []
            last_ts = None
            for fill in fills:
                ts = fill.get("ts") or 0
                if current and last_ts is not None and ts - last_ts > window:
                    clusters.append(current)
                    current = []
                current.append(fill)
                last_ts = ts
            if current:
                clusters.append(current)
        clusters.sort(key=lambda group: (group[0].get("ts") or 0, group[0]["exec_id"]))
        return clusters

    def apply_cluster(self, fills):
        legs = {}
        for fill in fills:
            leg = legs.setdefault(fill["instrument_id"], {
                "fill": fill, "delta": 0.0, "cash": 0.0, "qty": 0.0,
                "gross": 0.0, "commission": 0.0, "date": fill["date"],
            })
            leg["delta"] += fill_delta(fill)
            leg["cash"] += fill_cash(fill)
            leg["qty"] += float(fill["qty"])
            leg["gross"] += float(fill["qty"]) * float(fill["price"])
            leg["commission"] += float(fill["commission"])
            leg["date"] = fill["date"]

        openings, closings = [], []
        for iid, leg in legs.items():
            n0 = self.n_of(iid)
            delta = as_count(leg["delta"])
            n1 = as_count(n0 + delta)
            leg["n0"], leg["n1"] = n0, n1
            if delta == 0:
                self.problem(f"{iid}: bought and sold the same contract in one batch")
                return
            if n0 != 0 and n1 != 0 and sgn(n0) != sgn(n1):
                self.problem(f"{iid}: position crossed from {n0} to {n1}")
                return
            if n0 == 0 or abs(n1) > abs(n0):
                openings.append(iid)
            else:
                closings.append(iid)

        if openings and closings:
            if len(openings) != 1:
                self.problem("roll into more than one contract")
                return
            self.apply_roll(legs, closings, openings[0])
            return
        for iid in closings:
            self.apply_close(iid, legs[iid])
        for iid in openings:
            self.apply_open(iid, legs[iid])

    def apply_open(self, iid, leg):
        doc, created = self.ensure_option(iid, leg["fill"], leg["date"])
        doc["premium"] = float(doc.get("premium") or 0.0) + leg["cash"]
        doc["n"] = leg["n1"]
        added = abs(leg["n1"] - leg["n0"])
        if created:
            self.outcome.messages.append(
                f"Opened {describe(doc)} x{abs(leg['n1'])}, premium ${doc['premium']:,.2f}"
            )
        else:
            self.outcome.messages.append(
                f"Added {added} × {describe(doc)}, premium ${doc['premium']:,.2f}"
            )

    def apply_close(self, iid, leg):
        doc = self.options[iid]
        contracts = abs(leg["n0"]) - abs(leg["n1"])
        slice_ = self.premium_slice(doc, contracts)
        close_price = leg["gross"] / leg["qty"] if leg["qty"] else 0.0
        row = self.option_log(doc, contracts, slice_, leg["cash"], close_price,
                              leg["commission"], leg["date"], "close")
        self.outcome.logs.append(row)
        doc["premium"] = float(doc.get("premium") or 0.0) - slice_
        doc["n"] = leg["n1"]
        self.outcome.messages.append(
            f"Closed {as_count(contracts)} × {describe(doc)}, profit ${row['profit']:,.2f}"
        )

    def apply_roll(self, legs, closings, target_id):
        transferred = sum(leg["cash"] for leg in legs.values())
        startdates = []
        described = []
        for iid in closings:
            leg = legs[iid]
            doc = self.options[iid]
            contracts = abs(leg["n0"]) - abs(leg["n1"])
            slice_ = self.premium_slice(doc, contracts)
            transferred += slice_
            doc["premium"] = float(doc.get("premium") or 0.0) - slice_
            doc["n"] = leg["n1"]
            if doc.get("startdate"):
                startdates.append(doc["startdate"])
            described.append(describe(doc))
        leg = legs[target_id]
        doc, created = self.ensure_option(target_id, leg["fill"], leg["date"])
        if not created and doc.get("startdate"):
            startdates.append(doc["startdate"])
        doc["premium"] = float(doc.get("premium") or 0.0) + transferred
        doc["n"] = leg["n1"]
        if startdates:
            doc["startdate"] = min(startdates)
        self.outcome.messages.append(
            f"Rolled {', '.join(described)} → {describe(doc)}, premium ${doc['premium']:,.2f}"
        )

    # --- stock fills -------------------------------------------------------

    def apply_stock_fill(self, fill):
        qty = float(fill["qty"])
        price = float(fill["price"])
        commission = float(fill["commission"])
        if fill["side"] == "BOT":
            stock = self.ensure_stock(fill["date"], fill)
            n0 = float(stock["n"])
            if n0 < 0:
                self.problem(f"{self.symbol}: buy while short stock")
                return
            cost = float(stock.get("avgCost") or 0.0) * n0 + qty * price + commission
            stock["n"] = as_count(n0 + qty)
            stock["avgCost"] = cost / float(stock["n"])
            self.outcome.messages.append(
                f"Bought {as_count(qty)} {self.symbol} at {price:,.2f}, buy {stock['avgCost']:,.2f}"
            )
            return
        stock = self.stock
        n0 = float(stock["n"]) if stock else 0.0
        if stock is None or qty - n0 > EPS:
            self.problem(f"{self.symbol}: sold {as_count(qty)} shares, only {as_count(n0)} recorded")
            return
        avg = float(stock.get("avgCost") or 0.0)
        credit = float(stock.get("credit") or 0.0)
        credit_slice = credit * qty / n0
        profit = (price - avg) * qty + credit_slice - commission
        self.outcome.logs.append({
            "kind": "stock_sale",
            "open_date": stock.get("startdate") or fill["date"],
            "close_date": fill["date"],
            "right": "STK",
            "symbol": self.symbol,
            "signed_quantity": as_count(qty),
            "open_price": round(avg, 6),
            "premium": money(credit_slice),
            "close_price": round(price, 6),
            "close_commission": round(commission, 6),
            "profit": money(profit),
        })
        stock["credit"] = credit - credit_slice
        stock["n"] = as_count(n0 - qty)
        self.outcome.messages.append(
            f"Sold {as_count(qty)} {self.symbol} at {price:,.2f}, profit ${money(profit):,.2f}"
        )

    # --- positions the fills do not explain ---------------------------------

    def residuals(self, stock_fill_delta):
        """Split unexplained option changes into assignment candidates and the rest."""
        candidates = []   # (iid, contracts, share_change)
        disappeared = []  # (iid, contracts)
        ids = set(self.options) | {
            iid for iid, entry in self.broker.items() if entry.get("sec_type") == "OPT"
        }
        for iid in sorted(ids):
            stored = self.n_of(iid)
            held = self.broker_n(iid)
            if stored == held:
                continue
            if stored == 0 or (held != 0 and sgn(stored) != sgn(held)) or abs(held) > abs(stored):
                self.problem(f"{iid}: broker shows {held}, the book {stored}, no fill explains it")
                continue
            contracts = abs(stored) - abs(held)
            doc = self.options[iid]
            disappeared.append((iid, contracts))
            if self.cash_settled or stored > 0:
                continue
            shares = contracts * multiplier(doc)
            if doc.get("right") == "P":
                candidates.append((iid, contracts, shares))
            elif doc.get("right") == "C":
                candidates.append((iid, contracts, -shares))

        stored_stock = float(self.stock["n"]) if self.stock else 0.0
        held_stock = self.broker_n(self.stock_key)
        stock_residual = held_stock - stored_stock - stock_fill_delta
        return candidates, disappeared, stock_residual

    def choose_assignments(self, candidates, stock_residual):
        if len(candidates) > 12:
            self.problem("too many open options to match an assignment")
            return None
        matches = []
        for size in range(len(candidates) + 1):
            for combo in itertools.combinations(candidates, size):
                if abs(sum(c[2] for c in combo) - stock_residual) < EPS:
                    matches.append(combo)
        if not matches:
            if abs(stock_residual) > EPS:
                self.problem(
                    f"{self.symbol}: shares changed by {as_count(stock_residual)} with no matching fill or assignment"
                )
            else:
                self.problem(f"{self.symbol}: options changed with no matching fill or assignment")
            return None
        if len(matches) > 1:
            self.problem(f"{self.symbol}: more than one way to explain the share change")
            return None
        return {c[0] for c in matches[0]}

    def assignment_date(self, doc):
        expiry = str(doc.get("expiry") or "")
        today = self.today.strftime("%Y%m%d")
        return min(expiry, today) if len(expiry) == 8 else today

    def apply_put_assignment(self, iid, contracts):
        doc = self.options[iid]
        mult = multiplier(doc)
        shares = contracts * mult
        slice_ = self.premium_slice(doc, contracts)
        date = self.assignment_date(doc)
        stock = self.ensure_stock(date)
        n0 = float(stock["n"])
        strike = float(doc["strike"])
        stock["avgCost"] = (float(stock.get("avgCost") or 0.0) * n0 + strike * shares) / (n0 + shares)
        stock["credit"] = float(stock.get("credit") or 0.0) + slice_
        stock["n"] = as_count(n0 + shares)
        doc["premium"] = float(doc.get("premium") or 0.0) - slice_
        doc["n"] = as_count(as_count(doc["n"]) + contracts)
        self.outcome.messages.append(
            f"Assigned {as_count(shares)} {self.symbol} from {describe(doc)}, "
            f"buy {stock['avgCost']:,.2f}, break-even {breakeven(stock):,.2f}"
        )

    def apply_call_assignment(self, iid, contracts):
        doc = self.options[iid]
        mult = multiplier(doc)
        shares = contracts * mult
        stock = self.stock
        n0 = float(stock["n"]) if stock else 0.0
        if stock is None or shares - n0 > EPS:
            self.problem(f"{iid}: call assigned for {as_count(shares)} shares, only {as_count(n0)} recorded")
            return
        strike = float(doc["strike"])
        avg = float(stock.get("avgCost") or 0.0)
        credit = float(stock.get("credit") or 0.0)
        credit_slice = credit * shares / n0
        call_slice = self.premium_slice(doc, contracts)
        profit = (strike - avg) * shares + credit_slice + call_slice
        date = self.assignment_date(doc)
        self.outcome.logs.append({
            "kind": "call_assignment",
            "open_date": stock.get("startdate") or date,
            "close_date": date,
            "right": "C",
            "symbol": self.symbol,
            "signed_quantity": as_count(contracts),
            "strike": strike,
            "expiry": str(doc.get("expiry")),
            "open_price": round(avg, 6),
            "premium": money(credit_slice + call_slice),
            "close_price": strike,
            "close_commission": 0.0,
            "profit": money(profit),
        })
        stock["credit"] = credit - credit_slice
        stock["n"] = as_count(n0 - shares)
        doc["premium"] = float(doc.get("premium") or 0.0) - call_slice
        doc["n"] = as_count(as_count(doc["n"]) + contracts)
        self.outcome.messages.append(
            f"Called away {as_count(shares)} {self.symbol} at {format_price(strike)}, profit ${money(profit):,.2f}"
        )

    def apply_expiration(self, iid, contracts):
        doc = self.options[iid]
        expiry = str(doc.get("expiry") or "")
        if expiry > self.today.strftime("%Y%m%d"):
            self.problem(f"{iid}: gone before expiry and no fill explains it")
            return
        close_price = 0.0
        if self.cash_settled:
            price = self.cfg.get("underlying", {}).get(self.symbol)
            if not price:
                self.problem(f"{iid}: expired, settlement price unknown")
                return
            strike = float(doc["strike"])
            intrinsic = max(0.0, strike - price) if doc.get("right") == "P" else max(0.0, price - strike)
            if intrinsic > EPS:
                self.problem(f"{iid}: expired in the money, settlement not reported")
                return
        slice_ = self.premium_slice(doc, contracts)
        mult = multiplier(doc)
        short = as_count(doc["n"]) < 0
        signed_quantity = contracts if short else -contracts
        cash_close = -close_price * signed_quantity * mult
        row = self.option_log(doc, contracts, slice_, cash_close, close_price, 0.0, expiry, "expiration")
        self.outcome.logs.append(row)
        doc["premium"] = float(doc.get("premium") or 0.0) - slice_
        doc["n"] = as_count(as_count(doc["n"]) + (contracts if short else -contracts))
        self.outcome.messages.append(
            f"Expired {as_count(contracts)} × {describe(doc)}, profit ${row['profit']:,.2f}"
        )

    # --- run ---------------------------------------------------------------

    def run(self):
        for fill in self.fills:
            if fill["sec_type"] not in ("OPT", "STK"):
                self.outcome.processed.append(fill["exec_id"])

        for cluster in self.clusters():
            self.apply_cluster(cluster)
            if self.problems_found():
                return self.finish()

        stock_fills = [f for f in self.fills if f["sec_type"] == "STK"]
        if stock_fills and self.cash_settled:
            self.problem(f"{self.symbol}: stock fill on a cash-settled symbol")
            return self.finish()
        stock_fill_delta = sum(fill_delta(f) for f in stock_fills)

        candidates, disappeared, stock_residual = self.residuals(stock_fill_delta)
        if self.problems_found():
            return self.finish()

        if self.cash_settled:
            assigned = set()
            if abs(stock_residual) > EPS:
                self.problem(f"{self.symbol}: shares changed on a cash-settled symbol")
                return self.finish()
        else:
            assigned = self.choose_assignments(candidates, stock_residual)
            if assigned is None:
                return self.finish()

        by_id = {c[0]: c for c in candidates}
        for iid in sorted(assigned):
            _, contracts, change = by_id[iid]
            if change > 0:
                self.apply_put_assignment(iid, contracts)
        for fill in stock_fills:
            self.apply_stock_fill(fill)
            if self.problems_found():
                return self.finish()
        for iid in sorted(assigned):
            _, contracts, change = by_id[iid]
            if change < 0:
                self.apply_call_assignment(iid, contracts)
        for iid, contracts in disappeared:
            if iid not in assigned:
                self.apply_expiration(iid, contracts)
        if self.problems_found():
            return self.finish()

        for iid in set(self.options) | {
            i for i, e in self.broker.items() if e.get("sec_type") == "OPT"
        }:
            if self.n_of(iid) != self.broker_n(iid):
                self.problem(f"{iid}: book {self.n_of(iid)} does not match broker {self.broker_n(iid)}")
        stored_stock = as_count(self.stock["n"]) if self.stock else 0
        if stored_stock != self.broker_n(self.stock_key):
            self.problem(
                f"{self.symbol}: book shares {stored_stock} do not match broker {self.broker_n(self.stock_key)}"
            )
        return self.finish()

    def problems_found(self):
        return bool(self.outcome.problems)

    def finish(self):
        out = self.outcome
        if out.problems:
            out.options, out.stocks, out.logs, out.messages = {}, {}, [], []
            out.processed = []
            out.review = {
                "symbol": self.symbol,
                "problems": list(out.problems),
                "instruments": self.review_instruments(),
                "fills": [review_fill(f) for f in self.fills],
                "exec_ids": [f["exec_id"] for f in self.fills],
            }
            return out
        out.processed.extend(f["exec_id"] for f in self.fills if f["sec_type"] in ("OPT", "STK"))
        for iid, doc in self.options.items():
            original = self.original_options.get(iid)
            if as_count(doc.get("n")) == 0:
                if original is not None:
                    out.options[iid] = None
                continue
            doc["n"] = self.broker_n(iid)
            if doc.get("premium") is not None:
                doc["premium"] = money(doc["premium"])
            if original != doc:
                out.options[iid] = doc
        if self.stock is not None:
            if as_count(self.stock.get("n")) == 0:
                if self.original_stock is not None:
                    out.stocks[self.stock_key] = None
            else:
                self.stock["n"] = self.broker_n(self.stock_key)
                self.stock["avgCost"] = round(float(self.stock.get("avgCost") or 0.0), 6)
                self.stock["credit"] = money(self.stock.get("credit") or 0.0)
                if self.original_stock != self.stock:
                    out.stocks[self.stock_key] = self.stock
        return out

    def review_instruments(self):
        ids = set(self.original_options) | {
            iid for iid, e in self.broker.items() if e.get("sec_type") == "OPT"
        } | {f["instrument_id"] for f in self.fills if f["sec_type"] == "OPT"}
        rows = []
        for iid in sorted(ids):
            original = self.original_options.get(iid)
            stored = as_count(original.get("n")) if original else 0
            held = self.broker_n(iid)
            if stored or held or any(f["instrument_id"] == iid for f in self.fills):
                rows.append({"id": iid, "book": stored, "broker": held})
        stored_stock = as_count(self.original_stock.get("n")) if self.original_stock else 0
        held = self.broker_n(self.stock_key)
        if stored_stock or held:
            rows.append({"id": self.stock_key, "book": stored_stock, "broker": held})
        return rows


def review_fill(fill):
    text = f"{fill['date']} {fill['side']} {as_count(fill['qty'])} {fill['instrument_id']} @ {fill['price']}"
    return {"exec_id": fill["exec_id"], "text": text}


def breakeven(stock):
    n = float(stock.get("n") or 0)
    avg = float(stock.get("avgCost") or 0.0)
    if n <= 0:
        return avg
    return avg - float(stock.get("credit") or 0.0) / n


def reconcile(options, stocks, broker, fills, today=None, cfg=None, skip_symbols=()):
    """Return one Outcome per symbol that changed or could not be explained."""
    today = today or datetime.date.today()
    cfg = cfg or {}
    symbols = set()
    for doc in options.values():
        if as_count(doc.get("n")) != 0:
            symbols.add(doc.get("symbol"))
    for doc in stocks.values():
        if as_count(doc.get("n")) != 0:
            symbols.add(doc.get("symbol"))
    for entry in broker.values():
        symbols.add(entry.get("symbol"))
    for fill in fills:
        symbols.add(fill.get("symbol"))
    symbols.discard(None)

    outcomes = []
    for symbol in sorted(symbols):
        if symbol in skip_symbols:
            continue
        sym_options = {i: d for i, d in options.items() if d.get("symbol") == symbol}
        sym_stocks = {i: d for i, d in stocks.items() if d.get("symbol") == symbol}
        sym_broker = {i: e for i, e in broker.items() if e.get("symbol") == symbol}
        sym_fills = [f for f in fills if f.get("symbol") == symbol]
        book = SymbolBook(symbol, sym_options, sym_stocks, sym_broker, sym_fills, today, cfg)
        outcome = book.run()
        if outcome.problems or outcome.has_changes():
            outcomes.append(outcome)
    return outcomes
