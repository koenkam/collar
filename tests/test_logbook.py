"""Checks for the dashboard totals. Run: env/bin/python -m tests.test_logbook"""
import datetime

from trade.logbook import compute_collar_totals, format_dashboard


def test_total_profit_is_account_growth_and_sets_per_year():
    today = datetime.date(2026, 10, 6)
    totals = compute_collar_totals(
        {"start_date": "20260805", "value_start": 100000},
        [{"profit": 4000}, {"profit": 1000}, {}],
        110000,
        today=today,
    )
    assert totals["trading_usd"] == 5000
    assert totals["total_profit"] == 10000
    assert totals["days"] == 62
    assert totals["per_year"] == (110000 / 100000) ** (365 / 62)
    fields = format_dashboard(totals)
    assert fields["trading"] == "$5,000.00"
    assert fields["total"] == "$10,000.00"
    assert fields["per_year"] == f"{totals['per_year']:.2f}"


def test_collateral_limit_is_seventy_percent_and_left_is_the_remainder():
    totals = compute_collar_totals(
        {"start_date": "20260805", "value_start": 100000},
        [],
        100000,
        collateral=60000,
        today=datetime.date(2026, 10, 6),
    )
    assert totals["limit"] == 70000
    assert totals["room"] == 10000
    fields = format_dashboard(totals)
    assert fields["limit"] == "$70,000.00"
    assert fields["left"] == "$10,000.00"


def test_collateral_limit_stays_blank_without_an_account_value():
    totals = compute_collar_totals({}, [], None, collateral=1000)
    assert totals["limit"] is None
    assert totals["room"] is None
    fields = format_dashboard(totals)
    assert fields["limit"] == "—"
    assert fields["left"] == "—"


def test_per_year_stays_blank_without_a_start_value():
    totals = compute_collar_totals(
        {"start_date": "20260805"},
        [{"profit": 5000}],
        110000,
        today=datetime.date(2026, 10, 6),
    )
    assert totals["trading_usd"] == 5000
    assert totals["total_profit"] is None
    assert totals["per_year"] is None
    assert format_dashboard(totals)["total"] == "—"


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
