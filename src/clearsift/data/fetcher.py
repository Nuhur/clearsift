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

# companies report interest income under different rows, so try these in order
_INTEREST_INCOME_ROWS = ("Interest Income", "Interest Income Non Operating")


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

    kwargs["interest_income"] = _latest_interest_income(yf_ticker)

    return CompanyFinancials(ticker=ticker, **kwargs)  # type: ignore[arg-type]


def _number(raw: Any) -> float | None:
    # yfinance sometimes gives NaN or inf instead of nothing, so treat it as missing.
    # Python counts True and False as numbers, so skip those too
    if isinstance(raw, bool) or not isinstance(raw, numbers.Real):
        return None
    value = float(raw)
    return value if math.isfinite(value) else None


def _latest_interest_income(yf_ticker: Any) -> float | None:
    # kept apart from info so a broken income statement doesn't lose the other fields
    try:
        statement = yf_ticker.income_stmt
        if not isinstance(statement, pd.DataFrame) or statement.empty:
            return None
        # columns are year-end dates, so pick the latest instead of trusting the order
        latest = statement[max(statement.columns)]
    except Exception:
        return None

    for row in _INTEREST_INCOME_ROWS:
        value = _number(latest.get(row))
        # negative interest income doesn't make sense, so treat it as bad data
        if value is not None and value >= 0:
            return value
    return None
