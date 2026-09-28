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
