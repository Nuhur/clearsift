from __future__ import annotations

import math
from typing import Literal

from clearsift.config import Denominator, Methodology, ScreeningConfig
from clearsift.data.models import CompanyFinancials
from clearsift.screening.business import RatioValue, ScreenResult, Status

# what each single check found: fine, needs a manual look, or a hard fail
Outcome = Literal["pass", "doubt", "fail"]
Check = tuple[Outcome, str]

_DENOMINATOR_NAMES: dict[Denominator, str] = {
    "market_cap": "market cap",
    "total_assets": "total assets",
}


def screen_ratios(financials: CompanyFinancials, config: ScreeningConfig) -> ScreenResult:
    """Check a company's ratios against the limits of the methodology in the config."""
    method = config.methodology
    checks: list[Check] = []
    values: list[RatioValue] = []

    base_name = _DENOMINATOR_NAMES[method.denominator]
    # fail closed: a missing or non-positive base means none of its ratios can be trusted
    base = _base(getattr(financials, method.denominator), base_name, checks)
    # total assets come from the annual balance sheet, so take debt and cash from the same
    # sheet. Mixing in info's newer figures would compare numbers from different dates
    if method.denominator == "total_assets":
        debt, cash = financials.balance_sheet_debt, financials.balance_sheet_cash
    else:
        debt, cash = financials.total_debt, financials.cash_and_short_term_investments
    checks += _ratio("debt", debt, base, base_name, method.max_debt, method, values)
    checks += _ratio("cash", cash, base, base_name, method.max_cash, method, values)

    if method.max_receivables_and_cash is not None:
        receivables = financials.accounts_receivable
        if receivables is None:
            checks.append(("fail", "accounts receivable is missing"))
        # the cash check has already said if cash is missing, so only add this if both are there
        elif cash is not None:
            checks += _ratio(
                "receivables plus cash",
                receivables + cash,
                base,
                base_name,
                method.max_receivables_and_cash,
                method,
                values,
            )

    interest_checks, interest_ratio = _interest_income(financials, config, values)
    checks += interest_checks
    interest_year = financials.interest_income_year if interest_ratio is not None else None

    outcomes = {outcome for outcome, _ in checks}
    if "fail" in outcomes:
        return ScreenResult(
            "excluded",
            [reason for outcome, reason in checks if outcome != "pass"],
            ratio_values=tuple(values),
        )
    status: Status = "doubtful" if "doubt" in outcomes else "compliant"
    return ScreenResult(
        status,
        [reason for _, reason in checks],
        interest_ratio,
        interest_year,
        tuple(values),
    )


def _interest_income(
    financials: CompanyFinancials, config: ScreeningConfig, values: list[RatioValue]
) -> tuple[list[Check], float | None]:
    latest = financials.latest_income_statement_year
    year = financials.interest_income_year
    # no income statement at all means yfinance gave us nothing, which is missing data
    if latest is None:
        return [("fail", "interest income is missing")], None
    # the company has reports but stopped showing interest income in them. That's not
    # the same as no data, so it's a manual check rather than a hard fail (like Zoya)
    if year is None or latest - year > config.max_interest_income_age_years:
        return [("doubt", "interest income not disclosed in recent reports, check by hand")], None

    checks: list[Check] = []
    revenue = _base(financials.interest_income_revenue, "total revenue", checks)
    note = "" if year == latest else f" (from {year}, newer years not reported)"
    checks += _ratio(
        "interest income",
        financials.interest_income,
        revenue,
        "revenue" + note,
        config.methodology.max_impermissible_income,
        config.methodology,
        values,
    )
    # a missing or negative number fails above, so only keep the ratio if nothing did
    income = financials.interest_income
    ratio = None
    if (
        income is not None
        and revenue is not None
        and all(outcome != "fail" for outcome, _ in checks)
    ):
        ratio = income / revenue
    # an older year is the best we've got, but it might not reflect the company today
    if note:
        checks = [("doubt" if outcome == "pass" else outcome, reason) for outcome, reason in checks]
    return checks, ratio


def _ratio(
    name: str,
    value: float | None,
    base: float | None,
    base_name: str,
    limit: float,
    method: Methodology,
    values: list[RatioValue],
) -> list[Check]:
    if value is None or not math.isfinite(value):
        return [("fail", f"{name} is missing")]
    # a negative amount would slip under any limit, so it can't be trusted
    if value < 0:
        return [("fail", f"{name} is negative")]
    # the base already failed, and that reason is in the list
    if base is None:
        return []

    ratio = value / base
    passed = _within_limit(ratio, limit)
    values.append(RatioValue(name, ratio, limit, passed))
    shown = _actual_percent(ratio, limit, passed)
    reason = f"{name} is {shown} of {base_name}, {method.label} limit is {_limit_percent(limit)}"
    return [("pass" if passed else "fail", reason)]


def _base(value: float | None, name: str, checks: list[Check]) -> float | None:
    if value is None or not math.isfinite(value):
        checks.append(("fail", f"{name} is missing"))
        return None
    if value <= 0:
        checks.append(("fail", f"{name} is zero or negative"))
        return None
    return value


def _within_limit(ratio: float, limit: float) -> bool:
    # a limit of 0 means none at all, otherwise nothing at 0 would ever pass
    if limit == 0:
        return ratio == 0
    return ratio < limit


def _actual_percent(ratio: float, limit: float, passed: bool) -> str:
    shown = f"{ratio:.2%}"
    # rounding up to the limit would make a pass look like a fail. The limit is rounded
    # too, because 0.3 * 100 comes out as 30.000000000000004
    if passed and limit > 0 and float(shown.rstrip("%")) >= round(limit * 100, 6):
        return f"just under {_limit_percent(limit)}"
    # a tiny amount would round to 0.00% and look like it should have passed a zero limit
    if 0 < ratio < 0.00005:
        return "under 0.01%"
    return shown


def _limit_percent(limit: float) -> str:
    return f"{limit * 100:g}%"
