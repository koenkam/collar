# Position book

You trade in Interactive Brokers. The app watches, records what happened in Firestore, and updates the grids and the totals strip. The app places, changes, and cancels no orders.

The Google sheet is not updated, apart from the existing account-value write to cell P5. Profits already imported from the sheet stay at the stored amounts. Profits this book calculates subtract both the opening commission and the closing commission.

## Workflow

### 1. You trade

You open, roll, close, or buy back options, or buy or sell shares, in TWS or the IBKR app. Assignments and expirations happen at the broker without a trade from you.

The app only reads. `placeOrder` is not sent. The order-adjust code in the controller is already switched off, and it stays off. Working orders appear in the Order, Order_n, and Order_lim columns as a view only.

### 2. The app sees it

Two moments trigger a check:

- **While running.** The broker pushes new fills, their commissions, and position changes. Each fill is handled once its commission report has arrived.
- **At startup.** The app loads Firestore, then asks the broker for positions and recent fills, and applies only what is not yet recorded. This covers trades made while the app was closed, from any device.

The broker connection only returns recent fills: by default today, and at most about a week when TWS is set to keep more. Set TWS to keep the longest history it allows, and start the app at least that often. When the positions changed but the fills are no longer available, the change goes on the Review list and you enter it by hand.

### 3. The app works out the event

Positions and fills are compared against the stored book. The change becomes one of the events described below: open, scale-in, roll, close, expiration, put assignment, call assignment, stock purchase, or stock sale.

A change the rules cannot explain is not guessed. It goes on a **Review** list with the symbol, the stored count, the broker count, and the fills involved. The affected row stays on its last recorded values. You repair it in the record editor and then mark the item resolved.

### 4. The app writes Firestore

Each event is one Firestore transaction. For a roll, removing the old option and creating the new one happen together. For an assignment, the option, the stock row, and the processed fill ids are written together. A failed write leaves the event unapplied, and it is retried on the next check.

Fill ids already applied are stored, so a restart or a repeated broker message cannot count them twice.

### 5. The screen updates

After the write succeeds, the in-memory rows are refreshed from what was written. The options grid, stock grid, log grid, and totals strip redraw from those rows.

The status line in the window says what changed, for example `Rolled AMD 592.5P → 580P, premium $5,102.30`. The Review count is shown when it is not zero. There are no push notifications.

### 6. You correct it

A record editor in the app lets you create, view, change, and delete the stored records by hand:

- **Option documents**: premium, start date, and the contract fields.
- **Stock documents**: buy price, credit, and start date.
- **Log rows**: every field, including profit. A new row can be added for an event the app missed.
- **Review items**: mark resolved, which removes the item.

Broker share and contract counts are shown but not edited; the next position update overwrites them. Deleting an option or stock row the broker still reports brings it back on the next update with blank premium or blank credit, so an edit is usually the right repair.

A save or delete is written to Firestore right away, and the grids and totals strip redraw from the saved values. Later events build on what you entered. Deleting asks for confirmation.

Clicking an option or stock row still opens the quick edit dialog for premium, start date, and buy price.

Positions that are already open when this goes live keep the premium and start date you entered by hand. Their first recorded event starts from those values.

## Records

Three places, each with one job.

**Option document** in `portfolio`, id `expiry_symbol_strike_right`. Live contracts only, including SPX. The position handler no longer drops symbol `SPX`.

- `n` is the contract count from the broker position. A short is negative, which is the broker's sign.
- `premium` is our net cash for the contracts still open, in dollars. A credit is positive. The opening commission is already subtracted.
- `startdate` is the day the position was first opened. Rolls and added contracts keep it.
- `conId`, `symbol`, `right`, `strike`, `expiry`, `lastPrice`, `underlyingPrice`

The broker average cost is not copied into `premium`.

**Stock document** in `portfolio`, id `STK_{symbol}`. One row per symbol. SPX never has one: settlement is cash.

- `n` is the share count from the broker.
- `avgCost` is the average price per share, weighted by shares. A put assignment contributes its strike. A plain stock purchase contributes its fill price plus commission.
- `credit` is the put premium, in dollars, embedded in the shares still held. A plain purchase adds no credit.
- `startdate` is the first date shares were registered, `YYYYMMDD`.
- Break-even is computed for the grid as `avgCost - credit / n`. It is not stored.

**Log document** in `log`. Realized results only. The id is `close_date` plus the next sequence, as in the import. The totals strip sums `profit`.

**Processed ids** in `processed`. One document per applied fill id, with the event it belonged to.

**Review items** in `review`. One document per change the rules could not explain, removed when you mark it resolved.

`n` on option and stock documents is replaced by the broker position. It is never rebuilt by adding up fills.

## Profit

Opening commission reduces `premium` when the fill is recorded. Closing commission is subtracted in the log profit of the event that realizes the contracts or the shares. Neither commission is added back.

For an option close or expiration:

`profit = premium_slice - close_price * signed_quantity * 100 - close_commission`

`signed_quantity` uses the sheet sign: positive for a short, negative for a long.

## Events

### Open

A sell, or a buy for a long option, on a contract that has no document. SPX included.

The option document is created with `n` from the broker, `startdate` from the fill date, and `premium` from the fills: sale proceeds minus commission, or the debit paid plus commission for a buy.

### Scale-in

More contracts at the same strike and expiry. Not a roll.

`premium` grows by the new fills' net, including commission. `startdate` stays. No log row.

### Roll

A buy of one contract and a sell of another, same symbol and right, different strike or expiry, filled together or as a combo. The contract count may change. SPX rolls the same way.

The old document is removed and the new one written in one transaction. `startdate` is copied. New `premium` is the old premium plus the net of both fills, each net of its commission. No log row, including when the roll reduces the contract count.

A close and an open on different symbols, or a put closed and a call opened, are a close plus an open.

### Close

A buyback, or a sale for a long, with no paired new contract.

The closed contracts take a pro-rata slice of `premium`. That slice and the closing fill go to the log. The rest keeps its premium and `startdate`. A full close removes the document.

### Expiration

An option disappears with no fill explaining it, and the share count does not change by 100 per contract.

Equity options are logged at a close price of zero. SPX is cash-settled: the close price is the settlement intrinsic value when the broker reports one, and zero when the contract finishes out of the money. The document is removed. No stock row changes.

### Put assignment

A short put disappears or shrinks with no fill explaining it, and shares rise by those contracts times 100. Not used for SPX.

The assigned contracts' pro-rata `premium` moves into stock `credit`. `avgCost` blends in the put strike for the new shares. The first assignment sets `startdate`. Any remaining put keeps the rest of its premium. No log row: the premium is counted when the shares leave.

Second assignment example: 100 shares at 200 with $200 of premium, then 100 at 180 with $100 of premium. Buy is 190, credit $300, break-even 188.50.

### Call assignment

A short call disappears or shrinks with no fill explaining it, and shares fall by those contracts times 100. Not used for SPX.

For `s` shares out of `n`:

`profit = (call_strike - avgCost) * s + credit * (s / n) + call_premium_slice - assignment_commission`

`avgCost` stays. `credit` and `n` shrink by the slice. The log row has `right` `C`, the call strike, the stock `startdate` as open date, and the assignment date as close date. Empty stock and call documents are removed.

### Stock purchase

Shares rise with a stock buy fill, not a put assignment.

The fill price plus commission blends into `avgCost`. `credit` is unchanged. No log row.

### Stock sale

Shares fall with a stock sell fill, not a call assignment.

For `s` shares out of `n`:

`profit = (sale_price - avgCost) * s + credit * (s / n) - sale_commission`

`avgCost` stays. `credit` and `n` shrink by the slice. An empty stock document is removed.

## One writer for each figure

| Figure | Written by | Not also stored as |
| --- | --- | --- |
| Contract count, share count | Broker position | A sum of fills |
| Open option premium | Fills and opening commission | Broker average cost |
| Put premium after assignment | Stock `credit` | A log profit at assignment |
| Closing commission | Log profit of the realizing event | An addition to profit |
| Break-even | `avgCost - credit / n` on display | Its own field |
| Realized profit | Log only | A roll, scale-in, purchase, or put assignment |
| Start date | First open, or first share registration | A roll date |

A hand edit in the record editor replaces the stored value for that field. It does not create a second copy.

## Screen

The options grid keeps its columns and includes SPX. Premium and Start come from the option document.

Stock columns are Symbol, N, Buy, Break-even, Date, Last, Profit. Profit is `(Last - break-even) * N`. The grid stays four rows high.

The log grid takes the new rows as they are written, newest first. Stock-sale rows leave the option columns blank.

The totals strip recomputes from the log after every write. Assignment notional, percentage, and max recompute when positions or the account value change.

A Review button, shown when items exist, lists what needs a decision. A Records button opens the record editor.

## Outside this book

Dividends, splits and other corporate actions, a long equity option exercised into shares, and any order placed by the app. A dividend can be added by hand as a log row in the record editor.
