from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class CompanyFinancials:
    ticker: str
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    total_debt: float | None = None
    cash_and_short_term_investments: float | None = None
    total_revenue: float | None = None
    interest_income: float | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
