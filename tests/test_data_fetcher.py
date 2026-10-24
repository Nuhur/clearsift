from unittest.mock import MagicMock, patch

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


def test_fetched_at_is_set() -> None:
    from datetime import UTC, datetime

    before = datetime.now(UTC)
    with patch("clearsift.data.fetcher.yf.Ticker", return_value=_mock_ticker(FULL_INFO)):
        cf = fetch_financials("AAPL")
    after = datetime.now(UTC)

    assert before <= cf.fetched_at <= after
