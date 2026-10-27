import math

from clearsift.t212.models import AccountSummary, Dividend, Order, Position


def test_account_summary_with_nothing_is_all_none() -> None:
    assert AccountSummary.from_api({}) == AccountSummary(None, None, None, None)


def test_account_summary_odd_sections_become_none() -> None:
    summary = AccountSummary.from_api({"cash": "lots", "investments": None, "totalValue": "1"})

    assert summary.cash is None
    assert summary.investments_value is None
    assert summary.total_value is None


def test_position_with_nothing_is_all_none() -> None:
    assert Position.from_api({}) == Position(None, None, None, None, None)


def test_position_bad_numbers_become_none() -> None:
    position = Position.from_api(
        {"quantity": True, "averagePricePaid": math.nan, "currentPrice": math.inf}
    )

    assert position.quantity is None
    assert position.average_price is None
    assert position.current_price is None


def test_order_without_fill() -> None:
    order = Order.from_api({"order": {"id": 7, "ticker": "VODl_EQ", "status": "CANCELLED"}})

    assert order.id == 7
    assert order.status == "CANCELLED"
    assert order.fill_price is None
    assert order.filled_at is None


def test_order_bad_id_and_dates_become_none() -> None:
    order = Order.from_api({"order": {"id": "7", "createdAt": "yesterday"}})

    assert order.id is None
    assert order.created_at is None


def test_dividend_empty_ticker_becomes_none() -> None:
    dividend = Dividend.from_api({"ticker": "", "amount": 1.5, "paidOn": 20260814})

    assert dividend.ticker is None
    assert dividend.amount == 1.5
    assert dividend.paid_on is None
