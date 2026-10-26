from dataclasses import replace
from typing import Any

import pytest

from clearsift.config import Methodology, ScreeningConfig
from clearsift.data.models import CompanyFinancials
from clearsift.screening.screen import compare_stock, screen_stock

AAOIFI = Methodology(
    name="aaoifi",
    denominator="market_cap",
    max_debt=0.30,
    max_cash=0.30,
    max_receivables_and_cash=None,
    max_impermissible_income=0.05,
)

CONFIG = ScreeningConfig(
    mode="strict",
    fail_closed=True,
    max_data_age_days=120,
    market_cap_max_age_days=1,
    max_interest_income_age_years=3,
    methodology=AAOIFI,
    methodologies=(AAOIFI,),
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
        "interest_income_revenue": 500.0,
        "interest_income_year": 2025,
        "latest_income_statement_year": 2025,
        "interest_income": 10.0,
        "total_assets": 2000.0,
        "accounts_receivable": 100.0,
        "balance_sheet_debt": 100.0,
        "balance_sheet_cash": 200.0,
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


STANDARD = replace(CONFIG, mode="standard")


def test_doubtful_does_not_pass_in_strict_mode() -> None:
    company = _company(sector="Consumer Defensive", industry="Grocery Stores")

    verdict = screen_stock("TEST", CONFIG, get=FakeGet(company))

    assert verdict.status == "doubtful"
    assert verdict.needs_review
    assert not verdict.passes


def test_doubtful_passes_in_standard_mode() -> None:
    company = _company(sector="Consumer Defensive", industry="Grocery Stores")

    verdict = screen_stock("TEST", STANDARD, get=FakeGet(company))

    assert verdict.status == "doubtful"
    assert verdict.needs_review
    assert verdict.passes


@pytest.mark.parametrize("config", [CONFIG, STANDARD], ids=["strict", "standard"])
def test_excluded_never_passes(config: ScreeningConfig) -> None:
    company = _company(sector="Consumer Defensive", industry="Grocery Stores", total_debt=500.0)

    verdict = screen_stock("TEST", config, get=FakeGet(company))

    assert verdict.status == "excluded"
    assert not verdict.passes


@pytest.mark.parametrize("config", [CONFIG, STANDARD], ids=["strict", "standard"])
def test_compliant_passes_in_both_modes(config: ScreeningConfig) -> None:
    verdict = screen_stock("TEST", config, get=FakeGet(_company()))

    assert verdict.passes
    assert not verdict.needs_review


def test_excluded_beats_doubtful() -> None:
    company = _company(sector="Consumer Defensive", industry="Grocery Stores", total_debt=500.0)

    verdict = screen_stock("TEST", CONFIG, get=FakeGet(company))

    assert verdict.status == "excluded"


def test_ticker_uppercased_and_day_limits_passed_on() -> None:
    get = FakeGet(_company())

    screen_stock(" msft ", CONFIG, get=get)

    assert get.calls == [("MSFT", {"max_age_days": 120, "market_cap_max_age_days": 1})]


@pytest.mark.parametrize(
    "overrides",
    [{"interest_income_year": 2023}, {"interest_income_year": None}],
    ids=["older-year", "not-disclosed"],
)
def test_unclear_interest_income_fails_in_strict_mode(overrides: dict[str, Any]) -> None:
    verdict = screen_stock("TEST", CONFIG, get=FakeGet(_company(**overrides)))

    assert verdict.status == "doubtful"
    assert not verdict.passes


@pytest.mark.parametrize(
    "overrides",
    [{"interest_income_year": 2023}, {"interest_income_year": None}],
    ids=["older-year", "not-disclosed"],
)
def test_unclear_interest_income_passes_in_standard_mode(overrides: dict[str, Any]) -> None:
    verdict = screen_stock("TEST", STANDARD, get=FakeGet(_company(**overrides)))

    assert verdict.status == "doubtful"
    assert verdict.needs_review
    assert verdict.passes


MSCI = Methodology(
    name="msci",
    denominator="total_assets",
    max_debt=0.3333,
    max_cash=0.3333,
    max_receivables_and_cash=0.3333,
    max_impermissible_income=0.05,
)


def test_verdict_records_methodology() -> None:
    verdict = screen_stock("TEST", CONFIG, get=FakeGet(_company()))

    assert verdict.methodology == "AAOIFI"


def test_compare_runs_every_methodology_from_one_fetch() -> None:
    config = replace(CONFIG, methodologies=(AAOIFI, MSCI))
    # info's debt is 40% of market cap, which fails AAOIFI. MSCI uses the balance
    # sheet debt instead, which is only 5% of total assets
    get = FakeGet(_company(total_debt=400.0))

    verdicts = compare_stock("TEST", config, get=get)

    assert len(get.calls) == 1
    assert [v.methodology for v in verdicts] == ["AAOIFI", "MSCI"]
    assert [v.passes for v in verdicts] == [False, True]
