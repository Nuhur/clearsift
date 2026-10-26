from __future__ import annotations

import math
import numbers
from typing import Any

import pandas as pd
import yfinance as yf

from clearsift.data.models import CompanyFinancials

# yfinance uses its own key names, so map them to ours
_FIELD_MAP: dict[str, str] = {
    "sector": "sector",
    "industry": "industry",
    "market_cap": "marketCap",
    "total_debt": "totalDebt",
    "cash_and_short_term_investments": "totalCash",
    "total_revenue": "totalRevenue",
}

# companies report these under different rows, so try each list in order
_INTEREST_INCOME_ROWS = ("Interest Income", "Interest Income Non Operating")
_RECEIVABLES_ROWS = ("Accounts Receivable", "Receivables")


def fetch_financials(ticker: str) -> CompanyFinancials:
    """Get a company's financials from yfinance, with anything missing set to None."""
    try:
        yf_ticker = yf.Ticker(ticker)
    except Exception:
        # fail closed: if yfinance falls over, everything counts as missing
        return CompanyFinancials(ticker=ticker)

    info: dict = {}
    try:
        info = yf_ticker.info or {}
    except Exception:
        pass

    kwargs: dict[str, object] = {attr: _number(info.get(key)) for attr, key in _FIELD_MAP.items()}

    # sector and industry are text, so the line above wrongly set them to None
    kwargs["sector"] = info.get("sector") or None
    kwargs["industry"] = info.get("industry") or None

    kwargs.update(_interest_income(yf_ticker))
    kwargs.update(_balance_sheet(yf_ticker))

    return CompanyFinancials(ticker=ticker, **kwargs)  # type: ignore[arg-type]


def _number(raw: Any) -> float | None:
    # yfinance sometimes gives NaN or inf instead of nothing, so treat it as missing.
    # Python counts True and False as numbers, so skip those too
    if isinstance(raw, bool) or not isinstance(raw, numbers.Real):
        return None
    value = float(raw)
    return value if math.isfinite(value) else None


def _interest_income(yf_ticker: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "interest_income": None,
        "interest_income_revenue": None,
        "interest_income_year": None,
        "latest_income_statement_year": None,
    }
    # kept apart from info so a broken income statement doesn't lose the other fields
    try:
        statement = yf_ticker.income_stmt
        if not isinstance(statement, pd.DataFrame) or statement.empty:
            return result
        # columns are year-end dates, so sort them instead of trusting the order
        columns = sorted(statement.columns, reverse=True)
        years = [pd.Timestamp(column).year for column in columns]
    except Exception:
        return result

    result["latest_income_statement_year"] = years[0]
    # some companies (e.g. Apple) stopped reporting interest income, so walk back to the
    # newest year that has it. How old is too old is up to the config, not us
    for column, year in zip(columns, years, strict=True):
        year_data = statement[column]
        income = _first_non_negative(year_data, _INTEREST_INCOME_ROWS)
        revenue = _number(year_data.get("Total Revenue"))
        if income is not None and revenue is not None:
            result.update(
                interest_income=income, interest_income_revenue=revenue, interest_income_year=year
            )
            break
    return result


def _balance_sheet(yf_ticker: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "total_assets": None,
        "accounts_receivable": None,
        "balance_sheet_debt": None,
        "balance_sheet_cash": None,
    }
    # kept apart from info so a broken balance sheet doesn't lose the other fields
    try:
        sheet = yf_ticker.balance_sheet
        if not isinstance(sheet, pd.DataFrame) or sheet.empty:
            return result
        # columns are year-end dates, so pick the latest instead of trusting the order.
        # No falling back to older years, those numbers would be stale
        latest = sheet[max(sheet.columns)]
    except Exception:
        return result

    result["total_assets"] = _first_non_negative(latest, ("Total Assets",))
    result["accounts_receivable"] = _first_non_negative(latest, _RECEIVABLES_ROWS)
    result["balance_sheet_debt"] = _balance_sheet_debt(latest)
    # no falling back to plain "Cash And Cash Equivalents", it leaves out short-term
    # investments and would make the cash ratio look smaller than it is
    result["balance_sheet_cash"] = _first_non_negative(
        latest, ("Cash Cash Equivalents And Short Term Investments",)
    )
    return result


def _balance_sheet_debt(year_data: Any) -> float | None:
    total = _first_non_negative(year_data, ("Total Debt",))
    if total is not None:
        return total
    # yfinance sometimes leaves Total Debt blank (e.g. XOM 2025) even though it's just
    # these two added up. Only use them if both are there, half the debt isn't the debt
    current = _first_non_negative(year_data, ("Current Debt And Capital Lease Obligation",))
    long_term = _first_non_negative(year_data, ("Long Term Debt And Capital Lease Obligation",))
    if current is None or long_term is None:
        return None
    return current + long_term


def _first_non_negative(year_data: Any, rows: tuple[str, ...]) -> float | None:
    for row in rows:
        value = _number(year_data.get(row))
        # none of these can be negative, so a negative number is bad data
        if value is not None and value >= 0:
            return value
    return None
