import math
from dataclasses import replace
from typing import Any

import pytest

from clearsift.config import Methodology, ScreeningConfig
from clearsift.data.models import CompanyFinancials
from clearsift.screening.purification import purification_amount, purification_ratio
from clearsift.screening.ratios import screen_ratios
from clearsift.screening.screen import StockVerdict, screen_financials

AAOIFI = Methodology(
    name="aaoifi",
    denominator="market_cap",
    max_debt=0.30,
    max_cash=0.30,
    max_receivables_and_cash=None,
    max_impermissible_income=0.05,
)

STRICT = ScreeningConfig(
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
STANDARD = replace(STRICT, mode="standard")


def _company(**overrides: Any) -> CompanyFinancials:
    # a software company with every ratio well under its limit, interest is 0.98% of revenue
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
        "interest_income": 4.9,
    }
    values.update(overrides)
    return CompanyFinancials(ticker="TEST", **values)


def _verdict(config: ScreeningConfig = STRICT, **overrides: Any) -> StockVerdict:
    return screen_financials(_company(**overrides), config)


def test_ratio_for_passing_stock() -> None:
    assert purification_ratio(_verdict()) == pytest.approx(0.0098)


def test_ratio_from_older_year() -> None:
    verdict = _verdict(
        STANDARD, interest_income_year=2023, interest_income=10.0, interest_income_revenue=400.0
    )

    assert verdict.passes
    assert purification_ratio(verdict) == pytest.approx(0.025)
    assert verdict.ratios.interest_year == 2023


def test_ratio_none_when_not_disclosed() -> None:
    verdict = _verdict(STANDARD, interest_income_year=None, interest_income=None)

    assert verdict.passes
    assert purification_ratio(verdict) is None


def test_ratio_none_for_failed_stock() -> None:
    verdict = _verdict(total_debt=900.0)

    assert not verdict.passes
    assert purification_ratio(verdict) is None


def test_ratio_none_for_doubtful_stock_in_strict_mode() -> None:
    verdict = _verdict(interest_income_year=2023)

    assert verdict.status == "doubtful"
    assert purification_ratio(verdict) is None


def test_ratio_zero_when_no_interest_income() -> None:
    assert purification_ratio(_verdict(interest_income=0.0)) == 0.0


def test_screen_keeps_interest_ratio_and_year() -> None:
    result = screen_ratios(_company(interest_income=10.0), STRICT)

    assert result.interest_ratio == pytest.approx(0.02)
    assert result.interest_year == 2025


def test_screen_leaves_ratio_out_when_revenue_missing() -> None:
    result = screen_ratios(_company(interest_income_revenue=None), STRICT)

    assert result.interest_ratio is None
    assert result.interest_year is None


def test_screen_leaves_ratio_out_when_interest_negative() -> None:
    result = screen_ratios(_company(interest_income=-5.0), STRICT)

    assert result.interest_ratio is None


def test_amount() -> None:
    assert purification_amount(250.0, 0.02) == 5.0


def test_amount_does_not_round_up_float_noise() -> None:
    # 100 * 0.0098 is 0.9800000000000001 as a float, which mustn't become 0.99
    assert purification_amount(100.0, 0.0098) == 0.98


def test_amount_rounds_up() -> None:
    # 10 * 0.0123 is 0.123, rounding to nearest would give 0.12
    assert purification_amount(10.0, 0.0123) == 0.13


def test_amount_rounds_tiny_amount_up_to_a_penny() -> None:
    assert purification_amount(1.0, 0.0001) == 0.01


def test_amount_of_zero_dividend() -> None:
    assert purification_amount(0.0, 0.02) == 0.0


@pytest.mark.parametrize("dividend", [-1.0, -0.01, math.nan, math.inf])
def test_amount_rejects_bad_dividend(dividend: float) -> None:
    with pytest.raises(ValueError):
        purification_amount(dividend, 0.02)
