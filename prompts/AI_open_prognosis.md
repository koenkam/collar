# AI open prognosis

The edit-position dialog always shows the stock open, the DeepSeek prompt, and the option open. Asking DeepSeek fills in the option open. A price that is not known yet is an empty field. The options grid has no Open column.

## The two prices

**Stock open** is the opening-auction price TWS publishes as tick type 35. The field is empty until that price arrives. The premarket last trade on the chart is a different price and stays in UndLng.

Tick 9 on the same stream is the previous session's close of the stock. The option stream already delivers tick 9 (previous option close), which the prompt uses when the button is clicked. No new market-data line is added. `225` is added to the underlying request that `subscribe_option` already sends.

Store these on their own fields. Do not write them into `underlyingPrice` or `lastPrice`.

- `expected_open` — underlying tick 35, the stock open shown in the edit dialog
- `underlying_prev_close` — underlying tick 9
- `option_prev_close` — option tick 9

`handle_tickPrice_stock` currently treats every positive tick as the underlying price. Once `225` is requested, tick 35 would overwrite UndLng. Keep UndLng on the ticks that feed it today. Record tick 9 and tick 35 beside that path. On the option, keep Last on ticks 1, 2, and 4, and record tick 9 separately.

The dialog reads `expected_open` when it opens. There is no grid column for it.

## The edit dialog

Clicking an option row opens the editor for the start date and the premium. The same dialog always also shows:

- **Stock open** and **Option open**, two separate single-line fields. Stock open is the auction price, or empty when it is not known. Option open stays empty until DeepSeek answers, then shows the price from that answer.
- The prompt, in an editable multiline field. It is filled from the latest prices when the dialog opens. A missing price is written as "unknown" so the sentence can be edited.
- A button labeled `Ask DeepSeek`.
- The full reply, in its own box under the button.

**Previous close.** The prompt uses the option's stored tick 9. If it has not arrived, send one `reqHistoricalData` for that option: two days, one-day bars, trades, regular trading hours, and take the close of the last completed session. The dialog is already open. When the bar arrives, refill the prompt unless the user has edited it. If TWS returns nothing, the previous-close words stay "unknown" so the user can type it.

> Calculate the open price for the option [symbol] [put or call] [expiry] [strike] based on the expected opening price for [symbol] of [expected open]. The option closed on the previous trading day at [prev close]. VIX is [vix]. Use VIX in the option price calculation. Do not guess - make a calculated estimate. Take into account if there is any recent news for the stock, including earnings, profit warnings, director changes, or any other news that will significantly impact the price of the underlying and thus the price of the option. Create the shortest possible answer for your price estimate. Include any news that impacted the price of the option.

Fill the brackets and remove them. `[put or call]` is the word `put` or `call`. Expiry is `YYYY-MM-DD`. Expected open and previous close are decimal prices. Expected open is the stock auction price shown as Stock open.

`Ask DeepSeek` sends the field's current text. The full reply is shown under the button, and the price in that reply is shown in Option open. Stock open stays the auction price.

## DeepSeek

Read the key from `/Users/koenkam/code/autobalance/keys/llm.json`, field `DEEPSEEK_API_KEY`. Use `DEEPSEEK_MODEL` from that file (`deepseek-v4-flash` today). The key is already there. Do not read the encrypted `.env` entry, and do not write the key into the repo, the log, or the popup.

Send one request on a background thread so the window stays live:

`POST https://api.deepseek.com/chat/completions`

```json
{
  "model": "<DEEPSEEK_MODEL>",
  "messages": [{ "role": "user", "content": "<the text in the field>" }]
}
```

Header `Authorization: Bearer <key>`. The user message is the edited field and nothing else, so the model sees the prompt the user sees. Show `choices[0].message.content` in the reply box. On a missing key, a connection failure, or a non-200 response, show the error in that same box and leave the prompt in place so the user can send it again. Do not retry on its own. Timeout 60 seconds.

This is the same chat call autobalance uses in `webserver/reverse_llm.py` (`chat_openai` against `https://api.deepseek.com/chat/completions`). It does not browse. The prompt still asks for news; the popup shows whatever DeepSeek returns.

## Tests

Pure tests, no TWS and no network:

- A known auction price is shown as 151.20. An unknown auction price leaves the stock-open field empty.
- The prompt text contains the symbol, put or call, expiry, strike, expected stock open, and previous option close.

Mock the HTTP response in one test and check that the reply box would receive `choices[0].message.content`.
