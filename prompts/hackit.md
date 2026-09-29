1. in the collar code, collect the value of the trading account and display it in the user interface

2. when accepting datetime and premium values in the popup, suggest as default date the current date of today if the date field is not defined.
   Also, and accept input values for the premium in the format: [$]x,xxx.xx, for example: $ 1,450.23, $1,203.10, $231.40, 10, $10,500

3. update the wxPython library to the latest version

4. you collected the value of the trading account, can you update a google sheet with that value? it is the sheet "the collar" and update the value of p5 of the first sheet with the value of the account value. only do this the first time the desktop app retrieves the account value to prevent rate limiting

5. Nope, it does not write account value in the sheet 'The collar', first sheet 'Log', cell P5

6. write a plan to move the google sheet "The collar|Log" completely into firestore and into the wxPython app. call this "sheet_migration.md"

- line 1 to 6, with totals, can go into the current main screen at the top.
- we need an extra table for the realized trades, copy those trades from the google sheet log section (starts at line 17). adjust firestore so it can store the log chronologically.
- adjust the UI so we don't have a lot of unused space. the log file can grow substantially over time, whereas the portfolio lines will stay bound to about max 8 lines
- ask me anything that is unclear

7. implement sheet_migration.md

8. we need to be able to hold stocks as well in the app.
   when a cash covered put is assigned the stock, the stock should be registered, including its original price and the date of assignment.
   write a plan, and ask me any questions

9. Update the plan for automatic open/roll/close/assign registration
   the user can open/roll/close put or call positions in the interactive brokers platform. The wxPython app should automatically update all the relevant records when that happens.

- open: the app detects automatically t a new option position has been opened, including symbol, strike, expiry and number of options. from the trading history, collect the information about the premium and commission; calculate the net premium, and write that into the firestore backend.
- roll: the app detects a position has been rolled. this means the option symbol is still present in the portfolio, but strike and/or expiry could have been changed. calculate the new net premium by combining the information in the trade history and the existing premium information. keep the start date of the position. Also take into account the corner case that the number of option contracts may have been changed.
- close: the app detects a position has been (partially) closed.
- assign: we need to register assignments automatically, including cash covered puts and covered calls.
- are there any atomic operations I forgot that should be addressed?
- if you have questions, ask me
- check the plan for data redundancy and data inconsistency
- finally, give the plan a new name that better covers all the requirements.

10. i don't think the plan sufficiently captures the workflow.
    the high-level workflow is: the app does not make any trades (for now). the user makes the trades, and the app should update the records in firestore and update the grids and dashboards.
    adjust the plan. and remember, ask me anything.

11. implement the plan position_book.md

12. for spx, buyback is not calculated correctly. because it is a long position, not a short position. so the profit now would actually be a loss of <buyback>-<premium>
    also, for spx, there is no assignment.

13. i have a list of option candidates for the 'wheel' trade. when entering into a trade, i want to select the put option that gives me the best premium at a delta of -20 to -30 for the first friday with at least 5 trading days from today. What is a good way to normalize option prices for that delta requirement? I want to select the put setup that will give me the most premium for my capital at risk

14. make a plan for an option screener that advises me which put option to sell. You said this:

Normalize each put to a return on the cash it ties up, then compare every symbol at the same delta, for example −0.25. Within one expiry, a higher delta always pays more, so ranking the raw −0.20 to −0.30 band just picks whichever strike sits closest to −0.30.

## 1. Premium per dollar of capital

For a cash-secured put, the capital at risk is the cash reserved to buy the shares:

\[
\text{yield} = \frac{\text{fill price} \times 100 - \text{commission}}{\text{strike} \times 100}
\]

- **Fill price:** use the midpoint of bid and ask, not the last trade. To be conservative, use something between the bid and the midpoint, because wide spreads make the midpoint misleading.
- **Commission:** subtract it, since a one-week put earns small absolute premiums.
- **Margin account:** if you write against margin instead of cash, use the broker's margin requirement as the denominator. The ranking changes, because margin is roughly a fixed share of the underlying price rather than the full strike.

All candidates share one expiry, so days to expiry are the same and yield compares fairly without annualizing. For display, \( \text{yield} \times 365 / \text{DTE} \) gives an annual rate. DTE is calendar days to expiry, and a Friday exchange holiday moves expiry to Thursday.

## 2. Normalize for delta

Two ways, depending on the question you're asking.

**Which symbol pays best for the same risk?** Interpolate each symbol's yield to exactly −0.25, using the two strikes whose deltas bracket it:

\[
y\_{25} = y_1 + \frac{0.25 - |\Delta_1|}{|\Delta_2| - |\Delta_1|}\,(y_2 - y_1)
\]

Rank symbols by \( y\_{25} \). This compares like with like: roughly the same chance of assignment, the same week, per dollar of cash.

**Which strike within the band?** Premium divided by \( |\Delta| \) is roughly the average loss cushion if the put finishes in the money. Delta approximates the probability of finishing in the money. That ratio rises toward the money, so choosing the strike is really a choice of assignment appetite, not a yield comparison. Pick a fixed target delta and keep it.

## 3. What a high yield at the same delta means

At a fixed delta and expiry, yield is driven almost entirely by implied volatility. The name paying the most is the one the market expects to move the most. That is payment for risk, not a free edge, so add two checks:

- **Earnings before expiry:** skip or flag the name. Implied volatility is high because of a known jump.
- **Implied versus realized volatility:** implied volatility divided by recent realized volatility (for example 20-day) above about 1.2 is where the seller has an edge. A high yield with a ratio near 1 is just a volatile stock, priced fairly.

## 4. Screening rule

For each watchlist symbol, on the first Friday at least 5 trading days out:

1. Keep puts with delta −0.20 to −0.30, a bid-ask spread under about 10% of the midpoint, and reasonable open interest.
2. Compute yield on cash from a conservative fill price, net of commission.
3. Interpolate to \( y\_{25} \) per symbol.
4. Drop symbols with earnings before expiry. Rank the rest by \( y\_{25} \), using implied versus realized volatility as a tie-breaker or minimum.
5. Trade the strike nearest your target delta on the top names, subject to your 30% cash reserve.

Your break-even if assigned is strike minus premium per share, the same Break-even column the stock grid already shows.

The app already streams delta through Interactive Brokers option computations, so it could build this ranked list from the option chains.

as a default, use these stocks
AMZN
GOOGL
AMD
shop
NVDA
anet
rddt

JPM
KO
BAC
pypl
rcl
V
HIMS
PANW
MSFT
AAPL
NFLX
meta
axp
micron
broadcom

15. in the plan, adjust the application.
    make a button and a menu option to bring up a list of options and their ranking for selling puts.

16. implement put_screener.md

17. add a CRUD gui to manage the list of stocks for selling puts

18. in the new put option selection screen, add an explanation to each column when the user clicks on the column title.
    do anything possible to reduce the width of each column, so specifically:

- dates can be printed shorter
- percentages behind numbers stay. Do not put the % sign in the column header because we already print percentages with the % in the column.
- it is assumed that numbers with decimals are normally $; Do not put $ in the column title. round money to 2 decimals.
- remove spread and Oi

19. in the popup window 'sell puts', implement this behavior:

- do an initial scan when the window is first opened by the user
- when the window is then closed and reopened, do not do a rescan. only rescan when the user actively rescans.
- print at the top of the window when the scan was last completed.
