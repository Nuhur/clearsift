from datetime import UTC, datetime

import pytest

from clearsift.data.models import CompanyFinancials


def test_ticker_required() -> None:
    cf = CompanyFinancials(ticker="AAPL")
    assert cf.ticker == "AAPL"


def test_optional_fields_default_none() -> None:
    cf = CompanyFinancials(ticker="AAPL")
    assert cf.sector is None
    assert cf.industry is None
    assert cf.market_cap is None
    assert cf.total_debt is None
    assert cf.cash_and_short_term_investments is None
    assert cf.total_revenue is None
    assert cf.interest_income is None


@pytest.mark.parametrize(
    ("quote_type", "is_fund"),
    [("ETF", True), ("MUTUALFUND", True), ("EQUITY", False), (None, False)],
)
def test_is_fund(quote_type: str | None, is_fund: bool) -> None:
    assert CompanyFinancials(ticker="X", quote_type=quote_type).is_fund is is_fund


def test_fetched_at_defaults_to_utc_now() -> None:
    before = datetime.now(UTC)
    cf = CompanyFinancials(ticker="AAPL")
    after = datetime.now(UTC)
    assert before <= cf.fetched_at <= after


def test_all_fields_set() -> None:
    ts = datetime(2025, 1, 1, tzinfo=UTC)
    cf = CompanyFinancials(
        ticker="MSFT",
        sector="Technology",
        industry="Software",
        market_cap=3e12,
        total_debt=5e10,
        cash_and_short_term_investments=1e11,
        total_revenue=2e11,
        fetched_at=ts,
    )
    assert cf.ticker == "MSFT"
    assert cf.sector == "Technology"
    assert cf.market_cap == 3e12
    assert cf.fetched_at == ts
