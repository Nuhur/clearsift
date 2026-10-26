from dataclasses import replace
from typing import Any

import pytest

from clearsift.config import RatioLimits, ScreeningConfig
from clearsift.data.models import CompanyFinancials
from clearsift.screening.ratios import screen_ratios

CONFIG = ScreeningConfig(
    mode="strict",
    fail_closed=True,
    max_data_age_days=120,
    market_cap_max_age_days=1,
    max_interest_income_age_years=3,
    ratios=RatioLimits(
        max_debt_to_market_cap=0.30,
        max_cash_to_market_cap=0.30,
        max_impermissible_income=0.05,
    ),
    excluded_sectors=("alcohol",),
    always_exclude_tickers=(),
)


def _company(**overrides: Any) -> CompanyFinancials:
    # every ratio comfortably under its limit unless a test changes it
    values: dict[str, Any] = {
        "market_cap": 1000.0,
        "total_debt": 100.0,
        "cash_and_short_term_investments": 200.0,
        "interest_income": 10.0,
        "interest_income_revenue": 500.0,
        "interest_income_year": 2025,
        "latest_income_statement_year": 2025,
    }
    values.update(overrides)
    return CompanyFinancials(ticker="MSFT", **values)


def _limits(**overrides: float) -> ScreeningConfig:
    return replace(CONFIG, ratios=replace(CONFIG.ratios, **overrides))


def test_all_ratios_pass() -> None:
    result = screen_ratios(_company(), CONFIG)

    assert result.status == "compliant"
    assert result.reasons == [
        "debt is 10.00% of market cap, limit is 30%",
        "cash is 20.00% of market cap, limit is 30%",
        "interest income is 2.00% of revenue, limit is 5%",
    ]


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("total_debt", 342.0, "debt is 34.20% of market cap, limit is 30%"),
        ("cash_and_short_term_investments", 400.0, "cash is 40.00% of market cap, limit is 30%"),
        ("interest_income", 30.0, "interest income is 6.00% of revenue, limit is 5%"),
    ],
)
def test_each_ratio_fails(field: str, value: float, expected: str) -> None:
    result = screen_ratios(_company(**{field: value}), CONFIG)

    assert result.status == "excluded"
    assert result.reasons == [expected]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("total_debt", 300.0),
        ("cash_and_short_term_investments", 300.0),
        ("interest_income", 25.0),
    ],
)
def test_exactly_on_limit_is_excluded(field: str, value: float) -> None:
    result = screen_ratios(_company(**{field: value}), CONFIG)

    assert result.status == "excluded"


def test_just_under_limit_passes() -> None:
    result = screen_ratios(_company(total_debt=299.9), CONFIG)

    assert result.status == "compliant"


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("market_cap", "market cap is missing"),
        ("interest_income_revenue", "total revenue is missing"),
        ("total_debt", "debt is missing"),
        ("cash_and_short_term_investments", "cash is missing"),
        ("interest_income", "interest income is missing"),
    ],
)
def test_each_missing_value_is_excluded(field: str, expected: str) -> None:
    result = screen_ratios(_company(**{field: None}), CONFIG)

    assert result.status == "excluded"
    assert result.reasons == [expected]


def test_nan_counts_as_missing() -> None:
    result = screen_ratios(_company(total_debt=float("nan")), CONFIG)

    assert result.reasons == ["debt is missing"]


@pytest.mark.parametrize("value", [0.0, -1000.0])
def test_zero_or_negative_market_cap_is_excluded(value: float) -> None:
    result = screen_ratios(_company(market_cap=value), CONFIG)

    assert result.status == "excluded"
    assert result.reasons == ["market cap is zero or negative"]


@pytest.mark.parametrize("value", [0.0, -500.0])
def test_zero_or_negative_revenue_is_excluded(value: float) -> None:
    result = screen_ratios(_company(interest_income_revenue=value), CONFIG)

    assert result.status == "excluded"
    assert result.reasons == ["total revenue is zero or negative"]


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("total_debt", "debt is negative"),
        ("cash_and_short_term_investments", "cash is negative"),
    ],
)
def test_negative_debt_or_cash_is_excluded(field: str, expected: str) -> None:
    result = screen_ratios(_company(**{field: -50.0}), CONFIG)

    assert result.status == "excluded"
    assert result.reasons == [expected]


def test_multiple_failures_are_all_reported() -> None:
    company = _company(
        total_debt=342.0, cash_and_short_term_investments=400.0, interest_income=30.0
    )

    result = screen_ratios(company, CONFIG)

    assert result.status == "excluded"
    assert len(result.reasons) == 3


def test_missing_market_cap_still_checks_interest_income() -> None:
    result = screen_ratios(_company(market_cap=None, interest_income=30.0), CONFIG)

    assert result.reasons == [
        "market cap is missing",
        "interest income is 6.00% of revenue, limit is 5%",
    ]


def test_interest_income_just_under_aaoifi_limit_passes() -> None:
    result = screen_ratios(_company(interest_income=24.95), CONFIG)

    assert result.status == "compliant"
    assert "interest income is 4.99% of revenue, limit is 5%" in result.reasons


def test_interest_income_on_aaoifi_limit_fails() -> None:
    result = screen_ratios(_company(interest_income=25.0), CONFIG)

    assert result.reasons == ["interest income is 5.00% of revenue, limit is 5%"]


def test_zero_limit_passes_exactly_zero_interest_income() -> None:
    config = _limits(max_impermissible_income=0.0)

    result = screen_ratios(_company(interest_income=0.0), config)

    assert result.status == "compliant"
    assert "interest income is 0.00% of revenue, limit is 0%" in result.reasons


def test_zero_limit_excludes_any_interest_income() -> None:
    config = _limits(max_impermissible_income=0.0)

    result = screen_ratios(_company(interest_income=0.01), config)

    assert result.status == "excluded"
    assert result.reasons == ["interest income is under 0.01% of revenue, limit is 0%"]


def test_zero_limit_applies_to_debt_too() -> None:
    config = _limits(max_debt_to_market_cap=0.0)

    assert screen_ratios(_company(total_debt=0.0), config).status == "compliant"
    assert screen_ratios(_company(total_debt=1.0), config).status == "excluded"


def test_two_decimals_just_under_limit() -> None:
    result = screen_ratios(_company(total_debt=299.6), CONFIG)

    assert result.status == "compliant"
    assert result.reasons[0] == "debt is 29.96% of market cap, limit is 30%"


def test_pass_that_would_round_up_to_limit_says_just_under() -> None:
    result = screen_ratios(_company(total_debt=299.996), CONFIG)

    assert result.status == "compliant"
    assert result.reasons[0] == "debt is just under 30% of market cap, limit is 30%"


def test_fail_on_limit_shows_the_real_number() -> None:
    result = screen_ratios(_company(total_debt=300.0), CONFIG)

    assert result.reasons == ["debt is 30.00% of market cap, limit is 30%"]


def test_uses_same_year_revenue_not_total_revenue() -> None:
    company = _company(total_revenue=1_000_000.0, interest_income_revenue=500.0)

    result = screen_ratios(company, CONFIG)

    assert "interest income is 2.00% of revenue, limit is 5%" in result.reasons


def test_total_revenue_missing_does_not_matter() -> None:
    assert screen_ratios(_company(total_revenue=None), CONFIG).status == "compliant"


def test_older_year_is_doubtful_with_note() -> None:
    company = _company(interest_income=4.9, interest_income_year=2023)

    result = screen_ratios(company, CONFIG)

    assert result.status == "doubtful"
    assert (
        "interest income is 0.98% of revenue (from 2023, newer years not reported), limit is 5%"
        in result.reasons
    )


def test_older_year_on_the_age_limit_is_still_used() -> None:
    result = screen_ratios(_company(interest_income_year=2022), CONFIG)

    assert result.status == "doubtful"
    assert any("(from 2022, newer years not reported)" in r for r in result.reasons)


def test_older_year_over_limit_is_still_excluded() -> None:
    company = _company(interest_income=30.0, interest_income_year=2023)

    result = screen_ratios(company, CONFIG)

    assert result.status == "excluded"
    assert result.reasons == [
        "interest income is 6.00% of revenue (from 2023, newer years not reported), limit is 5%"
    ]


@pytest.mark.parametrize("year", [None, 2021], ids=["never", "too-old"])
def test_not_disclosed_is_doubtful(year: int | None) -> None:
    company = _company(
        interest_income=None if year is None else 10.0,
        interest_income_revenue=None if year is None else 500.0,
        interest_income_year=year,
    )

    result = screen_ratios(company, CONFIG)

    assert result.status == "doubtful"
    assert "interest income not disclosed in recent reports, check by hand" in result.reasons


def test_not_disclosed_plus_a_failure_is_excluded() -> None:
    company = _company(total_debt=500.0, interest_income_year=None)

    result = screen_ratios(company, CONFIG)

    assert result.status == "excluded"
    assert result.reasons == [
        "debt is 50.00% of market cap, limit is 30%",
        "interest income not disclosed in recent reports, check by hand",
    ]


def test_no_income_statement_is_missing() -> None:
    company = _company(
        interest_income=None,
        interest_income_revenue=None,
        interest_income_year=None,
        latest_income_statement_year=None,
    )

    result = screen_ratios(company, CONFIG)

    assert result.status == "excluded"
    assert result.reasons == ["interest income is missing"]
