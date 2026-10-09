"""Checks for the edit-dialog open prices. Run: env/bin/python -m tests.test_open_prognosis"""
import json

from trade.open_prognosis import (
    ask_deepseek, deepseek_content, option_open_text, prognosis_prompt, stock_open_text,
)


def test_stock_open_field_is_empty_when_unknown():
    assert stock_open_text(151.2) == "151.20"
    assert stock_open_text(None) == ""
    assert stock_open_text(0) == ""


def test_option_open_field_takes_the_price_from_the_reply():
    assert option_open_text("1.80 after earnings") == "1.80"
    assert option_open_text("DeepSeek connection failed") == ""
    assert option_open_text("") == ""


def test_prompt_carries_the_contract_and_prices():
    text = prognosis_prompt(
        "AMD", "P", "20261009", 600, 151.2, 1.85, vix=16.4,
        stock_prev_close=148, implied_vol=0.55, delta=-0.28,
    )
    assert "AMD put expiring 2026-10-09 strike 600" in text
    assert "Current stock price: 151.20" in text
    assert "Stock previous close: 148.00" in text
    assert "Option previous close: 1.85" in text
    assert "implied volatility: 55.0%" in text
    assert "delta: -0.28" in text
    assert "VIX: 16.40" in text
    assert "Do not use VIX as this option's implied volatility" in text
    assert "Use VIX in the option price calculation" not in text
    assert "within a few points of VIX" in text
    call = prognosis_prompt("AMZN", "C", "20261023", 245.5, 98, None)
    assert "AMZN call expiring 2026-10-23 strike 245.50" in call
    assert "VIX: unknown" in call
    assert "Option previous close: unknown" in call
    assert "Look up the previous regular-session close" in call


def test_deepseek_reply_is_the_message_content():
    payload = {"choices": [{"message": {"content": "1.80 after earnings"}}]}
    assert deepseek_content(payload) == "1.80 after earnings"

    seen = {}

    class Response:
        status = 200

        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(request, timeout=None):
        seen["timeout"] = timeout
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data.decode())
        return Response()

    reply = ask_deepseek("Calculate the open", urlopen=opener, key="secret-key", model="deepseek-v4-flash")
    assert reply == "1.80 after earnings"
    assert seen["timeout"] == 180
    assert seen["auth"] == "Bearer secret-key"
    assert seen["body"]["model"] == "deepseek-v4-flash"
    assert seen["body"]["messages"] == [{"role": "user", "content": "Calculate the open"}]
    assert "thinking" not in seen["body"]
    assert ask_deepseek("Calculate", key="") == "DeepSeek API key is missing."
    assert deepseek_content({}) == "DeepSeek returned an unreadable response."


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
