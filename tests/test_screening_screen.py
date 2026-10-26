from typing import Any

from clearsift.config import RatioLimits, ScreeningConfig
from clearsift.data.models import CompanyFinancials
from clearsift.screening.screen import screen_stock

CONFIG = ScreeningConfig(
    mode="strict",
    fail_closed=True,
    max_data_age_days=120,
    market_cap_max_age_days=1,
    ratios=RatioLimits(
        max_debt_to_market_cap=0.30,
        max_cash_to_market_cap=0.30,
        max_impermissible_income=0.05,
    ),
    excluded_sectors=("alcohol", "tobacco"),
    always_exclude_tickers=(),
)


def _company(**overrides: Any) -> CompanyFinancials:
    # a software company with every ratio well under its limit
    values: dict[str, Any] = {
        "sector": "Technology",
        "industry": "Software - Infrastructure",
        "market_cap": 1000.0,
        "total_debt": 100.0,
        "cash_and_short_term_investments": 200.0,
        "total_revenue": 500.0,
        "interest_income": 10.0,
    }
    values.update(overrides)
    return CompanyFinancials(ticker="TEST", **values)


class FakeGet:
    """Stands in for get_financials and remembers how it was called."""

    def __init__(self, financials: CompanyFinancials) -> None:
        self.financials = financials
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, ticker: str, **kwargs: Any) -> CompanyFinancials:
        self.calls.append((ticker, kwargs))
        return self.financials


def test_compliant_stock_passes() -> None:
    verdict = screen_stock("TEST", CONFIG, get=FakeGet(_company()))

    assert verdict.status == "compliant"
    assert verdict.passes
    assert verdict.business.status == "compliant"
    assert verdict.ratios.status == "compliant"


def test_business_excluded() -> None:
    company = _company(sector="Consumer Defensive", industry="Tobacco")

    verdict = screen_stock("TEST", CONFIG, get=FakeGet(company))

    assert verdict.status == "excluded"
    assert not verdict.passes
    assert verdict.business.status == "excluded"
    assert verdict.ratios.status == "compliant"


def test_ratios_excluded() -> None:
    verdict = screen_stock("TEST", CONFIG, get=FakeGet(_company(total_debt=500.0)))

    assert verdict.status == "excluded"
    assert not verdict.passes
    assert verdict.business.status == "compliant"
    assert verdict.ratios.status == "excluded"


def test_both_excluded_keeps_every_reason() -> None:
    company = _company(
        sector="Consumer Defensive", industry="Tobacco", total_debt=500.0, interest_income=50.0
    )

    verdict = screen_stock("TEST", CONFIG, get=FakeGet(company))

    assert verdict.status == "excluded"
    assert verdict.business.status == "excluded"
    assert "tobacco" in verdict.business.reasons[0]
    assert verdict.ratios.status == "excluded"
    assert len(verdict.ratios.reasons) == 2


def test_doubtful_does_not_pass() -> None:
    company = _company(sector="Consumer Defensive", industry="Grocery Stores")

    verdict = screen_stock("TEST", CONFIG, get=FakeGet(company))

    assert verdict.status == "doubtful"
    assert not verdict.passes


def test_excluded_beats_doubtful() -> None:
    company = _company(sector="Consumer Defensive", industry="Grocery Stores", total_debt=500.0)

    verdict = screen_stock("TEST", CONFIG, get=FakeGet(company))

    assert verdict.status == "excluded"


def test_ticker_uppercased_and_day_limits_passed_on() -> None:
    get = FakeGet(_company())

    verdict = screen_stock(" msft ", CONFIG, get=get)

    assert verdict.ticker == "MSFT"
    assert get.calls == [("MSFT", {"max_age_days": 120, "market_cap_max_age_days": 1})]
