from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd

from clearsift.data.fetcher import fetch_financials

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


def _statement(rows: dict[str, list[object]], years: list[str]) -> pd.DataFrame:
    # same shape as yfinance's income_stmt: one row per item, one column per year
    return pd.DataFrame(rows, index=pd.to_datetime(years)).T


def _ticker_with_statement(statement: object) -> MagicMock:
    mock = _mock_ticker(FULL_INFO)
    mock.income_stmt = statement
    return mock


def _fetch_with_statement(statement: object) -> float | None:
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=_ticker_with_statement(statement)):
        return fetch_financials("MSFT").interest_income


def test_interest_income_from_statement() -> None:
    statement = _statement({"Interest Income": [3e9]}, ["2025-06-30"])

    assert _fetch_with_statement(statement) == 3e9


def test_interest_income_uses_latest_year_whatever_the_order() -> None:
    statement = _statement(
        {"Interest Income": [1e9, 3e9, 2e9]}, ["2023-06-30", "2025-06-30", "2024-06-30"]
    )

    assert _fetch_with_statement(statement) == 3e9


def test_interest_income_falls_back_to_non_operating() -> None:
    statement = _statement(
        {"Interest Income": [float("nan")], "Interest Income Non Operating": [2e9]}, ["2025-06-30"]
    )

    assert _fetch_with_statement(statement) == 2e9


def test_interest_income_does_not_use_older_years() -> None:
    statement = _statement({"Interest Income": [1e9, float("nan")]}, ["2024-06-30", "2025-06-30"])

    assert _fetch_with_statement(statement) is None


def test_negative_interest_income_becomes_none() -> None:
    statement = _statement({"Interest Income": [-5e8]}, ["2025-06-30"])

    assert _fetch_with_statement(statement) is None


def test_zero_interest_income_is_kept() -> None:
    statement = _statement({"Interest Income": [0.0]}, ["2025-06-30"])

    assert _fetch_with_statement(statement) == 0.0


def test_interest_income_missing_rows_becomes_none() -> None:
    statement = _statement({"Total Revenue": [2e11]}, ["2025-06-30"])

    assert _fetch_with_statement(statement) is None


def test_empty_statement_gives_none() -> None:
    assert _fetch_with_statement(pd.DataFrame()) is None


def test_broken_statement_keeps_other_fields() -> None:
    mock = _mock_ticker(FULL_INFO)
    type(mock).income_stmt = PropertyMock(side_effect=Exception("network error"))
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=mock):
        cf = fetch_financials("MSFT")

    assert cf.interest_income is None
    assert cf.market_cap == 3e12
    assert cf.sector == "Technology"
