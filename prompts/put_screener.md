# Put screener

The screener ranks cash-secured puts on the watchlist and advises which one to sell. It reads option chains from Interactive Brokers and places no orders. You trade the suggestion yourself, and the position book records it.

## Question it answers

For the first Friday expiry at least 5 trading days out: which symbol pays the most premium per dollar of cash tied up, at the same delta, and which strike on that symbol?

## Watchlist

Default symbols, as Interactive Brokers tickers:

AMZN, GOOGL, AMD, SHOP, NVDA, ANET, RDDT, JPM, KO, BAC, PYPL, RCL, V, HIMS, PANW, MSFT, AAPL, NFLX, META, AXP, MU (Micron), AVGO (Broadcom).

Stored as `c.screener_symbols` in config. The list can be edited without code changes later.

## Expiry

Interactive Brokers lists each symbol's actual expiry dates. The screener takes the earliest listed expiry that:

- falls on a Friday, or on the Thursday before a Friday market holiday, and
- has at least 5 full trading sessions after today, counting the expiry day itself.

Today never counts. A scan on Monday 28 September 2026 counts Tuesday to Friday as 4 sessions, so Friday 2 October is too close and the target is Friday 9 October.

Trading days skip weekends and NYSE holidays. The holiday list lives in config for the current and next year.

A symbol without that weekly expiry is shown as "no weekly" and not ranked.

## Data per symbol

1. **Stock price, implied volatility, historical volatility.** One stock market-data request with Interactive Brokers generic ticks 104 and 106. That gives the last price, 30-day implied volatility, and 30-day historical volatility. No price history download is needed.
2. **Chain.** A contract-details request gets the stock's contract id. An option-parameters request then lists expiries and strikes.
3. **Candidate strikes.** Black-Scholes on the stock's implied volatility estimates which strikes fall between delta −0.12 and −0.40. Only those puts are requested, usually 5 to 10 per symbol.
4. **Put quotes.** Each candidate is requested for bid, ask, open interest, and model delta. The model delta is the Interactive Brokers option computation the app already receives.

**Market data line limit.** Interactive Brokers allows about 100 live market-data lines at once by default. The full watchlist needs roughly 200 put quotes, so the scan runs one symbol at a time: request, wait until every put has a bid, ask, and delta (about 3 seconds, with a timeout), cancel, and move on. A full scan takes about 1 to 2 minutes and shows its progress.

**Outside market hours** bids and asks are stale or missing. The scan asks for frozen data then, and every row is marked "closed market".

## Filters

A put is dropped when:

- the delta is outside −0.20 to −0.30 for the recommended strike (interpolation may use a strike just outside the band),
- the bid is zero,
- the spread is over 10% of the midpoint,
- open interest is under 100.

A symbol is flagged, and ranked below the others, when it reports earnings before the option expires.

## Earnings dates

At the start of a scan, the screener reads Nasdaq's public earnings calendar (`api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD`) once for each weekday from today through the target expiry. That is at most 10 requests, and each one lists every company reporting that day and whether it reports before the open or after the close.

A symbol is flagged when it reports:

- on a day before expiry, or
- on expiry day before the open, or with no time given.

A report after the close on expiry day comes after the option has expired, so it is not flagged.

The calendar is unofficial and can change or fail. When a day cannot be read, symbols show "earnings unknown" and are ranked normally, and the progress line says the check was incomplete.

## Numbers

**Fill price.** Halfway from the bid to the midpoint:

\[
\text{fill} = \text{bid} + 0.25\,(\text{ask} - \text{bid})
\]

**Yield on cash.**

\[
\text{yield} = \frac{\text{fill} \times 100 - \text{commission}}{\text{strike} \times 100}
\]

Commission per contract is `c.option_commission`, $0.50 by default. The log averages about $0.45.

**Annualized yield**, for display only: \( \text{yield} \times 365 / \text{DTE} \), where DTE is calendar days to expiry.

**Yield at delta −0.25.** Interpolated from the two strikes whose deltas bracket −0.25:

\[
y_{25} = y_1 + \frac{0.25 - |\Delta_1|}{|\Delta_2| - |\Delta_1|}\,(y_2 - y_1)
\]

A symbol without strikes on both sides of −0.25 shows "no 25Δ" and is ranked below the others.

**Implied versus historical volatility**: 30-day implied divided by 30-day historical. At 1.2 or above the premium is rich relative to recent moves.

**Break-even** if assigned: strike minus fill price, per share.

## Ranking

1. Symbols with earnings before expiry and symbols without a 25Δ yield go below the rest.
2. The rest sort by \( y_{25} \), highest first.
3. Implied versus historical volatility is shown beside it. It is used only to break ties within 0.02 percentage points of yield. Rows under 1.0 are dimmed.

## Recommended strike

The strike whose delta is closest to the target, `c.screener_target_delta`, default −0.25, within the band. The row shows that strike's own fill, yield, and break-even. \( y_{25} \) is only for ranking.

## Capital

Capital at risk is cash-secured: strike × 100 per contract. Margin requirements are not used.

Available cash for new puts is the 70% maximum from the totals strip minus the current short-put notional:

\[
\text{available} = 0.7 \times \text{account value} - \text{assign}
\]

The row shows how many contracts fit: \( \lfloor \text{available} / (\text{strike} \times 100) \rfloor \). A put that does not fit one contract is marked "over reserve" but still ranked.

## What you already hold

Symbols you already hold are ranked like the rest. A **Held** column shows what is on the book for that symbol, from the options grid and stock grid: for example `2 × 580P 10-16` for open short puts, or `400 sh, BE 195.95` for shares with their break-even. It is blank when you hold nothing on that symbol.

## Screen

### Opening it

Two ways, both opening the same **Sell puts** window:

- A **Sell puts** button on the status row, next to **Review** and **Records**.
- A **Trade** menu in a new menu bar, with **Sell puts…** (Cmd+Shift+P). The menu also lists **Records…** and **Review…**, which open the record editor on the matching tab, so the menu reaches every window the buttons do.

The app has no menu bar today. On macOS the Trade menu appears in the system menu bar at the top of the screen, beside the app's name.

The window is modeless: the options, stock, and log grids keep updating behind it, and you can place the trade in TWS while it stays open. Opening it again brings the existing window to the front instead of creating a second one.

When opened, the window shows the last result from this session with its scan time, for example `Scanned 16:42, expiry Fri 9 Oct`. It starts a new scan by itself only when there is no result yet, or the last one is more than 15 minutes old. **Scan** always starts a fresh one. During a scan the button reads **Stop**, and the progress line shows the symbol being read, for example `AMD 3 of 22`.

### The list

The window shows one row per symbol:

Symbol, Price, Expiry, DTE, Strike, Delta, Bid, Ask, Fill, Premium ($), Yield, Annual, Y25, IV, HV, IV/HV, Spread %, OI, Earnings, Fits, Break-even, Held.

Rows sort by rank. The top row is highlighted. Clicking a row lists every candidate strike for that symbol with its delta and yield, so you can pick a different strike yourself.

The scan result is kept in memory for the session. It is not written to Firestore.

## Code

- `trade/screener.py`: expiry choice, trading-day count, Black-Scholes delta estimate for strike selection, fill, yield, interpolation, filters, earnings flag, ranking. Pure functions, tested like `tests/test_book.py`.
- `trade/earnings.py`: the Nasdaq calendar read, with a timeout and a browser user agent, run off the UI thread.
- API and controller additions: contract details, option parameters, stock generic ticks 104 and 106, option open interest, one symbol at a time with cancellation.
- `trade/screener_ui.py`: the Sell puts window and the per-symbol detail.
- `trade/main.py`: the menu bar with the Trade menu and its shortcut, and the Sell puts button.
- Config: symbols, target delta, band, spread limit, minimum open interest, commission, fill fraction, holidays.

## Outside this plan

Placing orders, calls on assigned shares, and saving scan history.
