from __future__ import annotations

import math

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


def fetch_financials(ticker: str) -> CompanyFinancials:
    """Get a company's financials from yfinance, with anything missing set to None."""
    info: dict = {}
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        # fail closed: if yfinance falls over, everything counts as missing
        pass

    kwargs: dict[str, object] = {}
    for attr, key in _FIELD_MAP.items():
        raw = info.get(key)
        # yfinance sometimes gives NaN or inf instead of nothing, so treat it as missing.
        # Python counts True and False as numbers, so skip those too
        is_number = isinstance(raw, (int, float)) and not isinstance(raw, bool)
        kwargs[attr] = float(raw) if is_number and math.isfinite(raw) else None

    # sector and industry are text, so the loop above wrongly set them to None
    kwargs["sector"] = info.get("sector") or None
    kwargs["industry"] = info.get("industry") or None

    return CompanyFinancials(ticker=ticker, **kwargs)  # type: ignore[arg-type]
