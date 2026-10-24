from __future__ import annotations

import yfinance as yf

from clearsift.data.models import CompanyFinancials

# Maps CompanyFinancials field names to yfinance .info keys
_FIELD_MAP: dict[str, str] = {
    "sector": "sector",
    "industry": "industry",
    "market_cap": "marketCap",
    "total_debt": "totalDebt",
    "cash_and_short_term_investments": "totalCash",
    "total_revenue": "totalRevenue",
}


def fetch_financials(ticker: str) -> CompanyFinancials:
    """Fetch financial fields from yfinance. Any missing field is None, never raises."""
    info: dict = {}
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        pass

    kwargs: dict[str, object] = {}
    for attr, key in _FIELD_MAP.items():
        raw = info.get(key)
        kwargs[attr] = float(raw) if isinstance(raw, (int, float)) else None

    # sector and industry are strings, not floats — fix those two
    kwargs["sector"] = info.get("sector") or None
    kwargs["industry"] = info.get("industry") or None

    return CompanyFinancials(ticker=ticker, **kwargs)  # type: ignore[arg-type]
