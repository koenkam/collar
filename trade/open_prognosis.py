"""Expected stock open shown in the edit dialog, and the DeepSeek prompt."""
import json
import re
import urllib.error
import urllib.request

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_KEY_PATH = "/Users/koenkam/code/autobalance/keys/llm.json"
DEEPSEEK_TIMEOUT = 180


def stock_open_text(price):
    """Two-decimal price, or an empty string when it is not known."""
    number = _price(price)
    if number is None:
        return ""
    return f"{number:.2f}"


def option_open_text(reply):
    """The first price in a DeepSeek reply, or an empty string when none is given."""
    match = re.search(r"\d+\.\d+", reply or "")
    if match is None:
        return ""
    return f"{float(match.group()):.2f}"


def prognosis_prompt(symbol, right, expiry, strike, stock_open, prev_close, vix=None,
                     stock_prev_close=None, implied_vol=None, delta=None):
    """Prompt for an option open. Yesterday's option price is the anchor, not VIX."""
    side = {"P": "put", "C": "call"}.get(right, "")
    contract = " ".join(
        part for part in (
            symbol,
            side,
            f"expiring {_expiry_text(expiry)}" if expiry else "",
            f"strike {_strike_text(strike)}" if strike not in ("", None) else "",
        ) if part
    )
    if _price(stock_prev_close) is None:
        previous_stock = (
            "Stock previous close: unknown. Look up the previous regular-session close. "
            "Do not treat the current stock price as the previous close."
        )
    else:
        previous_stock = f"Stock previous close: {_money(stock_prev_close)}."
    return "\n".join([
        f"Estimate the opening price per share of the {contract}.",
        f"Current stock price: {_money(stock_open)}. Use this as the stock price at the open.",
        previous_stock,
        (
            f"Option previous close: {_close_text(prev_close)}. "
            "Start from this price. It is the market's price for this contract."
        ),
        (
            f"This option's implied volatility: {_vol_text(implied_vol)}. "
            "This is the volatility of this contract. Interactive Brokers sends it as a decimal, "
            "and the figure above is already in percent."
        ),
        f"This option's delta: {_delta_text(delta)}.",
        (
            f"VIX: {_money(vix)}. VIX is the S&P 500 volatility index, not the implied volatility of {symbol}. "
            "Do not use VIX as this option's implied volatility, and do not build a Black-Scholes price from VIX. "
            "If the volatility you are about to use is within a few points of VIX, you have used VIX by mistake. "
            "A single stock is usually much more volatile than VIX. Imply the volatility from this option's previous close instead."
        ),
        "",
        "Calculate it this way:",
        (
            "1. Keep this option's own implied volatility. If it is unknown, imply it from the option's previous close, "
            "the stock's previous close, the strike, and the time to expiry. If you cannot imply it, do not invent one."
        ),
        (
            "2. Reprice the option at the current stock price with that same implied volatility. "
            "Time is calendar days from today to expiry, divided by 365. One day of time decay is small next to the stock move."
        ),
        f"3. The price cannot be below intrinsic value. {_intrinsic_rule(right)}",
        (
            "4. Change the price for news only when you know a specific item since the previous close, "
            "such as earnings, a profit warning, or a management change. If you know of none, do not change the price for news."
        ),
        (
            "5. Check the reprice against the previous option close plus delta times the change in the stock. "
            "If those two differ by a lot, trust the reprice from this option's own implied volatility."
        ),
        (
            "If both the option previous close and the implied volatility are unknown, do not invent a price. "
            "The first line must then be the single word unknown, with no digits."
        ),
        (
            "Otherwise the first line must be only the option price, with two decimals and no other numbers. "
            "Then at most two sentences: the implied volatility you used, and any news that changed the price."
        ),
    ])


def load_deepseek_credentials(path=DEEPSEEK_KEY_PATH):
    """Return (key, model). An empty key means the file is missing or has no key."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return "", ""
    key = data.get("DEEPSEEK_API_KEY") or ""
    if not isinstance(key, str) or not key.strip() or key.strip() == "CHANGE_ME":
        return "", ""
    model = data.get("DEEPSEEK_MODEL") or "deepseek-v4-flash"
    return key.strip(), model


def deepseek_content(payload):
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return "DeepSeek returned an unreadable response."
    if not isinstance(content, str) or not content.strip():
        return "DeepSeek returned an empty response."
    return content


def ask_deepseek(prompt, urlopen=None, key=None, model=None):
    """Send the prompt as the only user message. Return the reply text or an error string."""
    if key is None:
        key, file_model = load_deepseek_credentials()
        if model is None:
            model = file_model
    if not key:
        return "DeepSeek API key is missing."
    model = model or "deepseek-v4-flash"
    opener = urlopen or urllib.request.urlopen
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    request = urllib.request.Request(
        DEEPSEEK_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
    )
    try:
        with opener(request, timeout=DEEPSEEK_TIMEOUT) as response:
            status = getattr(response, "status", 200)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        return f"DeepSeek error {exc.code}: {detail}".rstrip()
    except Exception as exc:
        return f"DeepSeek connection failed: {exc}"
    if status != 200:
        return f"DeepSeek error {status}"
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "DeepSeek returned an unreadable response."
    return deepseek_content(payload)


def _price(value):
    number = _number(value)
    if number is None or number <= 0 or number > 1e6:
        return None
    return number


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _money(value):
    number = _price(value)
    if number is None:
        return "unknown"
    return f"{number:.2f}"


def _vol_text(value):
    """Implied vol as a percent. Interactive Brokers sends 0.45 for 45%."""
    number = _number(value)
    if number is None or number <= 0 or number > 5:
        return "unknown"
    return f"{number * 100:.1f}%"


def _delta_text(value):
    number = _number(value)
    if number is None or abs(number) > 1:
        return "unknown"
    return f"{number:.2f}"


def _intrinsic_rule(right):
    if right == "P":
        return "For this put that is the strike minus the stock price, or zero when the stock is above the strike."
    if right == "C":
        return "For this call that is the stock price minus the strike, or zero when the stock is below the strike."
    return "For a put that is the strike minus the stock, and for a call the stock minus the strike, or zero when that is negative."


def _close_text(value):
    if value is None or value == "":
        return "unknown"
    return _money(value)


def _expiry_text(expiry):
    text = str(expiry or "")
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _strike_text(strike):
    number = _number(strike)
    if number is None:
        return str(strike or "")
    if number == int(number):
        return str(int(number))
    return f"{number:.2f}"
