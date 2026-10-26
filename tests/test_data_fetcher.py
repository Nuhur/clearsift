from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd
import pytest

from clearsift.data.fetcher import fetch_financials
from clearsift.data.models import CompanyFinancials

FULL_INFO = {
    "sector": "Technology",
    "industry": "Software—Application",
    "marketCap": 3_000_000_000_000,
    "totalDebt": 50_000_000_000,
    "totalCash": 100_000_000_000,
    "totalRevenue": 200_000_000_000,
}


def _mock_ticker(info: dict) -> MagicMock:
    mock = MagicMock()
    mock.info = info
    return mock


def test_all_fields_present() -> None:
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=_mock_ticker(FULL_INFO)):
        cf = fetch_financials("MSFT")

    assert cf.ticker == "MSFT"
    assert cf.sector == "Technology"
    assert cf.industry == "Software—Application"
    assert cf.market_cap == 3e12
    assert cf.total_debt == 5e10
    assert cf.cash_and_short_term_investments == 1e11
    assert cf.total_revenue == 2e11


def test_missing_fields_become_none() -> None:
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=_mock_ticker({})):
        cf = fetch_financials("UNKNOWN")

    assert cf.ticker == "UNKNOWN"
    assert cf.sector is None
    assert cf.market_cap is None
    assert cf.total_debt is None
    assert cf.cash_and_short_term_investments is None
    assert cf.total_revenue is None


def test_partial_fields() -> None:
    partial = {"sector": "Finance", "marketCap": 1e9}
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=_mock_ticker(partial)):
        cf = fetch_financials("XYZ")

    assert cf.sector == "Finance"
    assert cf.market_cap == 1e9
    assert cf.total_debt is None
    assert cf.total_revenue is None


def test_yfinance_exception_returns_all_none() -> None:
    with patch("clearsift.data.fetcher.yf.Ticker", side_effect=Exception("network error")):
        cf = fetch_financials("FAIL")

    assert cf.ticker == "FAIL"
    assert cf.market_cap is None
    assert cf.sector is None


def test_empty_string_sector_becomes_none() -> None:
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=_mock_ticker({"sector": ""})):
        cf = fetch_financials("ABC")

    assert cf.sector is None


def test_nan_and_infinity_become_none() -> None:
    info = {"marketCap": float("nan"), "totalDebt": float("inf")}
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=_mock_ticker(info)):
        cf = fetch_financials("NAN")

    assert cf.market_cap is None
    assert cf.total_debt is None


def test_booleans_become_none() -> None:
    info = {"marketCap": True, "totalDebt": False}
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=_mock_ticker(info)):
        cf = fetch_financials("BOOL")

    assert cf.market_cap is None
    assert cf.total_debt is None


def test_fetched_at_is_set() -> None:
    from datetime import UTC, datetime

    before = datetime.now(UTC)
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=_mock_ticker(FULL_INFO)):
        cf = fetch_financials("AAPL")
    after = datetime.now(UTC)

    assert before <= cf.fetched_at <= after


NAN = float("nan")


def _statement(rows: dict[str, list[object]], years: list[str]) -> pd.DataFrame:
    # same shape as yfinance's income_stmt: one row per item, one column per year
    return pd.DataFrame(rows, index=pd.to_datetime(years)).T


def _fetch_with_statement(statement: object) -> CompanyFinancials:
    mock = _mock_ticker(FULL_INFO)
    mock.income_stmt = statement
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=mock):
        return fetch_financials("MSFT")


def test_interest_income_from_statement() -> None:
    statement = _statement({"Interest Income": [3e9], "Total Revenue": [2e11]}, ["2025-06-30"])

    cf = _fetch_with_statement(statement)

    assert cf.interest_income == 3e9
    assert cf.interest_income_revenue == 2e11
    assert cf.interest_income_year == 2025
    assert cf.latest_income_statement_year == 2025


def test_interest_income_uses_latest_year_whatever_the_order() -> None:
    statement = _statement(
        {"Interest Income": [1e9, 3e9, 2e9], "Total Revenue": [1e11, 3e11, 2e11]},
        ["2023-06-30", "2025-06-30", "2024-06-30"],
    )

    cf = _fetch_with_statement(statement)

    assert cf.interest_income == 3e9
    assert cf.interest_income_revenue == 3e11
    assert cf.interest_income_year == 2025


def test_interest_income_falls_back_to_non_operating() -> None:
    statement = _statement(
        {"Interest Income": [NAN], "Interest Income Non Operating": [2e9], "Total Revenue": [2e11]},
        ["2025-06-30"],
    )

    assert _fetch_with_statement(statement).interest_income == 2e9


def test_falls_back_to_older_year_with_same_year_revenue() -> None:
    # like Apple: newer years have NaN for interest income
    statement = _statement(
        {
            "Interest Income": [NAN, NAN, 3.75e9, 2.8e9],
            "Total Revenue": [416e9, 391e9, 383e9, 394e9],
        },
        ["2025-09-30", "2024-09-30", "2023-09-30", "2022-09-30"],
    )

    cf = _fetch_with_statement(statement)

    assert cf.interest_income == 3.75e9
    assert cf.interest_income_revenue == 383e9
    assert cf.interest_income_year == 2023
    assert cf.latest_income_statement_year == 2025


def test_year_without_revenue_is_skipped() -> None:
    statement = _statement(
        {"Interest Income": [3e9, 2e9], "Total Revenue": [NAN, 1e11]},
        ["2025-06-30", "2024-06-30"],
    )

    cf = _fetch_with_statement(statement)

    assert cf.interest_income == 2e9
    assert cf.interest_income_year == 2024


def test_negative_interest_income_is_skipped() -> None:
    statement = _statement(
        {"Interest Income": [-5e8, 1e9], "Total Revenue": [2e11, 1e11]},
        ["2025-06-30", "2024-06-30"],
    )

    assert _fetch_with_statement(statement).interest_income_year == 2024


def test_zero_interest_income_is_kept() -> None:
    statement = _statement({"Interest Income": [0.0], "Total Revenue": [2e11]}, ["2025-06-30"])

    assert _fetch_with_statement(statement).interest_income == 0.0


def test_no_interest_income_in_any_year_keeps_latest_year() -> None:
    statement = _statement({"Total Revenue": [2e11, 1e11]}, ["2025-06-30", "2024-06-30"])

    cf = _fetch_with_statement(statement)

    assert cf.interest_income is None
    assert cf.interest_income_revenue is None
    assert cf.interest_income_year is None
    assert cf.latest_income_statement_year == 2025


def test_empty_statement_gives_none() -> None:
    cf = _fetch_with_statement(pd.DataFrame())

    assert cf.interest_income is None
    assert cf.latest_income_statement_year is None


def test_broken_statement_keeps_other_fields() -> None:
    mock = _mock_ticker(FULL_INFO)
    type(mock).income_stmt = PropertyMock(side_effect=Exception("network error"))
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=mock):
        cf = fetch_financials("MSFT")

    assert cf.interest_income is None
    assert cf.latest_income_statement_year is None
    assert cf.market_cap == 3e12
    assert cf.sector == "Technology"


def _fetch_with_balance_sheet(sheet: object) -> CompanyFinancials:
    mock = _mock_ticker(FULL_INFO)
    mock.balance_sheet = sheet
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=mock):
        return fetch_financials("MSFT")


def test_balance_sheet_fields() -> None:
    sheet = _statement(
        {"Total Assets": [3.6e11, 3.5e11], "Accounts Receivable": [3e10, 2e10]},
        ["2024-06-30", "2025-06-30"],
    )

    cf = _fetch_with_balance_sheet(sheet)

    assert cf.total_assets == 3.5e11
    assert cf.accounts_receivable == 2e10


def test_receivables_falls_back_to_receivables_row() -> None:
    sheet = _statement(
        {"Total Assets": [3.5e11], "Accounts Receivable": [NAN], "Receivables": [4e10]},
        ["2025-06-30"],
    )

    assert _fetch_with_balance_sheet(sheet).accounts_receivable == 4e10


def test_balance_sheet_does_not_use_older_years() -> None:
    sheet = _statement(
        {"Total Assets": [3.5e11, NAN], "Accounts Receivable": [3e10, NAN]},
        ["2024-06-30", "2025-06-30"],
    )

    cf = _fetch_with_balance_sheet(sheet)

    assert cf.total_assets is None
    assert cf.accounts_receivable is None


def test_negative_balance_sheet_values_become_none() -> None:
    sheet = _statement({"Total Assets": [-1.0], "Accounts Receivable": [-5.0]}, ["2025-06-30"])

    cf = _fetch_with_balance_sheet(sheet)

    assert cf.total_assets is None
    assert cf.accounts_receivable is None


def test_broken_balance_sheet_keeps_other_fields() -> None:
    mock = _mock_ticker(FULL_INFO)
    type(mock).balance_sheet = PropertyMock(side_effect=Exception("network error"))
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=mock):
        cf = fetch_financials("MSFT")

    assert cf.total_assets is None
    assert cf.market_cap == 3e12


def test_balance_sheet_debt_and_cash_from_same_year_as_total_assets() -> None:
    sheet = _statement(
        {
            "Total Assets": [3.6e11, 3.5e11],
            "Total Debt": [1.1e11, 1.0e11],
            "Cash Cash Equivalents And Short Term Investments": [7e10, 6.5e10],
        },
        ["2024-09-30", "2025-09-30"],
    )

    cf = _fetch_with_balance_sheet(sheet)

    assert cf.total_assets == 3.5e11
    assert cf.balance_sheet_debt == 1.0e11
    assert cf.balance_sheet_cash == 6.5e10
    # info's figures are kept separately for the market-cap standards
    assert cf.total_debt == 5e10
    assert cf.cash_and_short_term_investments == 1e11


def test_balance_sheet_cash_does_not_fall_back_to_cash_only_row() -> None:
    sheet = _statement(
        {"Total Assets": [3.5e11], "Cash And Cash Equivalents": [3e10]}, ["2025-09-30"]
    )

    assert _fetch_with_balance_sheet(sheet).balance_sheet_cash is None


CURRENT_DEBT = "Current Debt And Capital Lease Obligation"
LONG_TERM_DEBT = "Long Term Debt And Capital Lease Obligation"


def test_total_debt_used_when_present() -> None:
    sheet = _statement(
        {"Total Debt": [4.171e10], CURRENT_DEBT: [1.0], LONG_TERM_DEBT: [2.0]}, ["2025-12-31"]
    )

    assert _fetch_with_balance_sheet(sheet).balance_sheet_debt == 4.171e10


def test_missing_total_debt_uses_current_plus_long_term() -> None:
    # XOM's 2025 balance sheet: Total Debt is blank but both parts are there
    sheet = _statement(
        {"Total Debt": [NAN], CURRENT_DEBT: [9.296e9], LONG_TERM_DEBT: [3.4241e10]},
        ["2025-12-31"],
    )

    assert _fetch_with_balance_sheet(sheet).balance_sheet_debt == 9.296e9 + 3.4241e10


@pytest.mark.parametrize("missing", [CURRENT_DEBT, LONG_TERM_DEBT])
def test_missing_debt_part_stays_none(missing: str) -> None:
    rows = {"Total Debt": [NAN], CURRENT_DEBT: [9.296e9], LONG_TERM_DEBT: [3.4241e10]}
    rows[missing] = [NAN]

    assert _fetch_with_balance_sheet(_statement(rows, ["2025-12-31"])).balance_sheet_debt is None


def test_negative_debt_part_stays_none() -> None:
    sheet = _statement({CURRENT_DEBT: [-1.0], LONG_TERM_DEBT: [3.4241e10]}, ["2025-12-31"])

    assert _fetch_with_balance_sheet(sheet).balance_sheet_debt is None


def test_debt_parts_from_older_year_are_not_mixed_in() -> None:
    # 2025 only has the long-term part. 2024 has everything, but it mustn't fill the gap
    sheet = _statement(
        {
            "Total Debt": [NAN, 4.171e10],
            CURRENT_DEBT: [NAN, 4.955e9],
            LONG_TERM_DEBT: [3.4241e10, 3.6755e10],
        },
        ["2025-12-31", "2024-12-31"],
    )

    assert _fetch_with_balance_sheet(sheet).balance_sheet_debt is None
