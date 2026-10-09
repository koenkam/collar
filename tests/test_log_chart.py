"""Checks for log profit grouping. Run: env/bin/python -m tests.test_log_chart"""
from trade.logbook import profit_buckets


def trade(close_date, profit):
    return {"close_date": close_date, "profit": profit}


def test_month_groups_sum_profit_and_keep_a_running_total():
    rows = profit_buckets([
        trade("20261002", 100),
        trade("20261005", -40),
        trade("20260928", 25),
        trade("20261101", 10),
        {"close_date": "20261002"},
        {"profit": 5},
    ], "month")
    assert [row["label"] for row in rows] == ["2026-09", "2026-10", "2026-11"]
    assert [row["profit"] for row in rows] == [25, 60, 10]
    assert [row["cumulative"] for row in rows] == [25, 85, 95]


def test_day_and_year_buckets():
    trades = [trade("20261002", 10), trade("261002", 5), trade("20250115", -3)]
    days = profit_buckets(trades, "day")
    assert [row["label"] for row in days] == ["25-01-15", "26-10-02"]
    assert days[1]["profit"] == 15
    years = profit_buckets(trades, "year")
    assert [row["label"] for row in years] == ["2025", "2026"]
    assert years[1]["cumulative"] == 12


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
