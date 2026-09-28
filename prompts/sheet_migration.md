# Sheet migration: The collar / Log

Move the `Log` worksheet of spreadsheet `The collar` into Firestore and the wxPython main window. After the one-time import, the app is the place those figures are read. Open option and stock positions stay on the live Interactive Brokers grids they already use.

Other tabs (`Log-old`, `Calc`, `Watchlist`, `results`, `ABC`, `Doodle`) stay in Google Sheets.

## What is on the sheet today

`Log` has three blocks.

**Rows 1–6, totals.** Labels in columns A, I, and L. Values in C, J, and P.

| Cell | Label | Formula or source |
| --- | --- | --- |
| C1 | start | Constant date, 2026-08-05 |
| C2 | value start | Constant, 462128.52 |
| J1 | assign | `SUM(J10:J16)` — assignment notional of the open block |
| J2 | percentage | `J1/P5` — assign ÷ account value (about 0.66) |
| J3 | max | `P5*0.7` — 70% of account value |
| P1 | total usd | `SUM(P10:P73)` — realized profit, capped at row 73 |
| P2 | total eur | `P1 * googlefinance("currency:usdeur")` |
| P3 | total eur ex otm puts | `SUMIF(P10:P, ">0") * googlefinance("currency:usdeur")` — winning closes only |
| P4 | days in trade | Today minus the earliest date in column A |
| P5 | current value | Number written by the app, once per launch |
| P6 | Per year | `(P5 / (P5 - P1)) ^ (365 / P4)` — growth factor, about 1.22 |

**Rows 9–15, open positions.** Header on row 9, positions on rows 11–15. The app already shows these from Interactive Brokers plus the `portfolio` collection. This block is not copied into the log. Rows 14–15 have quantity 0; the same NVDA and GOOGL trades already sit in the log, so those two rows are skipped.

**Row 17 onward, realized trades.** Label on row 17, trades on rows 18–41 (24 trades). Newest close is at the top. The sheet is not strictly sorted: the closed SPX hedge sits below later AMD trades.

Columns A–J are the open side. Columns L, M, N, and P are the close side.

| Col | Open | Close |
| --- | --- | --- |
| A / L | Date | Date |
| B | PUT or CALL | |
| C | Symbol | |
| D | Signed quantity | |
| E | Strike | |
| F / M | Price per share | Price per share |
| G | Expiry | |
| H / N | Commission | Commission |
| I | Premium | |
| J | Assign | |
| P | | Profit |

Quantity is positive for a short option and negative for a long option. That is the opposite of Interactive Brokers, where a short is a negative `n`. The log stores the sheet's signed quantity so the existing formulas keep the same result.

Premium and profit are formulas, not typed numbers:

- premium = `quantity * open_price * 100 - open_commission`, blank when quantity is 0
- assign = `strike * quantity * 100` for the open block when quantity is not 0; the log uses the same formula; the long SPX row has no assign
- profit = `premium - close_price * quantity * 100 + close_commission`

Open price and open commission are often a sum of rolls (`=2+0.9+0.9`, `=2.07+2.36+2.34`). One AMD row averages two prices (`=(7.37+6.6)/2`). Import stores the evaluated number, which is what those formulas already contribute to premium, and keeps the raw expression beside it.

Close commission is added in the profit formula. Open commission is subtracted inside premium. Imported profits match the sheet by keeping that formula as written.

## Firestore

Keep the existing `portfolio` collection for open positions. Add two new places.

**Document `summary/collar`.** The two constants that are not derived:

- `start_date`: `20260805`
- `value_start`: `462128.52`

**Collection `log`.** One document per realized trade. Document id is `close_date` + a zero-padded sequence, for example `20260925_0001`. Sequence follows the sheet from top to bottom on import, then increments for any trade added later. A query ordered by document id walks the log chronologically by close date, with same-day trades in import order.

Fields:

- `open_date`, `close_date` as `YYYYMMDD` strings
- `right` (`P` or `C`), `symbol`, `signed_quantity`, `strike`, `expiry`
- `open_price`, `open_commission`, `close_price`, `close_commission` as numbers
- `open_price_expr`, `open_commission_expr` when the sheet cell was a formula rather than a plain number
- `premium`, `assign`, `profit` stored as the evaluated numbers so the grid does not re-parse expressions

`assign` is omitted when the sheet left it blank (the long SPX hedge).

The app reads the whole collection ordered by document id, newest close first, which matches the sheet. Twenty-four documents do not need pagination. When the log is large, the same query still returns newest first and the grid scrolls.

## Totals on the main screen

A fixed strip under the clock and account value. Figures are computed in the app, not read back from the sheet, so the row-73 cap in `SUM(P10:P73)` goes away.

- **start** and **value start** come from `summary/collar`
- **current value** is the account value already shown at the top right
- **assign** is the sum of `strike * abs(n) * 100` over open short puts (`right == P` and `n < 0`). Long hedges are left out, matching the blank assign on the SPX row
- **percentage** is assign ÷ account value
- **max** is account value × 0.7
- **total usd** is the sum of `profit` on every log document
- **days in trade** is today minus `start_date`
- **per year** is `(account / (account - total_usd)) ^ (365 / days)`

EUR totals stay off this strip until there is a rate source that replaces `googlefinance("currency:usdeur")`.

## Layout

The window is 1400×800. The options grid and the stock grid each have `proportion=1`, so each empty grid takes half the window. Options stay around 8 rows; the log does not.

- Clock and account row: unchanged
- Totals strip: fixed height, one or two lines of the figures above
- Options grid: height fixed to the column header plus 8 rows. Extra open positions scroll inside the grid
- Stock grid: height fixed to the header plus 4 rows
- Log grid: `proportion=1`, so it takes the rest of the window and scrolls

The log grid has one row per trade, not a preallocated empty block. Columns, left to right: Open, Type, Symbol, #, Strike, Price, Expiry, Com, Premium, Assign, Close, Close px, Close com, Profit. Numeric columns follow the existing float formatting.

This screen is read-only. Editing a realized trade is out of scope. Detecting a new open, roll, or close from Interactive Brokers is the separate registration task; the `log` collection is append-only so that task can add a document later.

## Import

A one-shot script, run by hand, using the existing service account and spreadsheet id.

1. Read `Log!A1:P` twice: unformatted values for numbers, formulas for the raw price and commission expressions.
2. Convert date serials with the Sheets epoch (1899-12-30). Serial 46239 is 2026-08-05.
3. Write `summary/collar` from C1 and C2.
4. Walk from row 18 downward. Skip blank rows. Skip a row whose symbol is empty.
5. Write one `log` document per row, sequence starting at 1.
6. Print sheet profit next to stored profit for every row and stop if any pair differs by more than one cent.

The script does not delete sheet rows and does not write P5. Re-running it overwrites the same document ids, so a second run replaces the import instead of duplicating it.

## Sheet writes after the cutover

`update_collar_account_value` still writes P5 on first account read. That write stays until the totals strip is on screen and checked against the sheet. Removing the write is a separate small change after that check, so a bad import does not strand the sheet.

## Check against the sheet

- 24 log rows, first NVDA closed 2026-09-25, last AMD opened 2026-08-05
- total usd equals the current P1 figure, about $13,844.78, with no row cap
- assign, percentage, and max match J1, J2, and J3 for the same account value
- per year matches P6 for the same account value, total usd, and day count
- options and stock grids no longer grow with the window; the log grid does
