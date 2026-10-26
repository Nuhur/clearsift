from __future__ import annotations

import math

from clearsift.config import ScreeningConfig
from clearsift.data.models import CompanyFinancials
from clearsift.screening.business import ScreenResult


def screen_ratios(financials: CompanyFinancials, config: ScreeningConfig) -> ScreenResult:
    """Check a company's debt, cash and interest income against the limits in the config."""
    failures: list[str] = []
    passes: list[str] = []

    # fail closed: a missing or non-positive base means none of its ratios can be trusted
    market_cap = _base(financials.market_cap, "market cap", failures)
    revenue = _base(financials.total_revenue, "total revenue", failures)

    limits = config.ratios
    checks = (
        ("debt", financials.total_debt, market_cap, "market cap", limits.max_debt_to_market_cap),
        (
            "cash",
            financials.cash_and_short_term_investments,
            market_cap,
            "market cap",
            limits.max_cash_to_market_cap,
        ),
        (
            "interest income",
            financials.interest_income,
            revenue,
            "revenue",
            limits.max_impermissible_income,
        ),
    )
    for name, value, base, base_name, limit in checks:
        if value is None or not math.isfinite(value):
            failures.append(f"{name} is missing")
            continue
        # a negative amount would slip under any limit, so it can't be trusted
        if value < 0:
            failures.append(f"{name} is negative")
            continue
        if base is None:
            continue

        ratio = value / base
        reason = f"{name} is {_actual_percent(ratio)} of {base_name}, limit is {limit * 100:g}%"
        (passes if _within_limit(ratio, limit) else failures).append(reason)

    if failures:
        return ScreenResult("excluded", failures)
    return ScreenResult("compliant", passes)


def _base(value: float | None, name: str, failures: list[str]) -> float | None:
    if value is None or not math.isfinite(value):
        failures.append(f"{name} is missing")
        return None
    if value <= 0:
        failures.append(f"{name} is zero or negative")
        return None
    return value


def _within_limit(ratio: float, limit: float) -> bool:
    # a limit of 0 means none at all, otherwise nothing at 0 would ever pass
    if limit == 0:
        return ratio == 0
    return ratio < limit


def _actual_percent(ratio: float) -> str:
    # a tiny amount would round to 0.0% and look like it should have passed a zero limit
    if 0 < ratio < 0.0005:
        return "under 0.1%"
    return f"{ratio:.1%}"
