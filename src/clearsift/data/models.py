from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# yfinance quoteType values that mean a fund rather than a company
FUND_QUOTE_TYPES: frozenset[str] = frozenset({"ETF", "MUTUALFUND"})


@dataclass
class CompanyFinancials:
    ticker: str
    sector: str | None = None
    industry: str | None = None
    # e.g. EQUITY or ETF, uppercase
    quote_type: str | None = None
    market_cap: float | None = None
    total_debt: float | None = None
    cash_and_short_term_investments: float | None = None
    total_revenue: float | None = None
    interest_income: float | None = None
    # revenue from the same year as interest_income, so the ratio compares like with like
    interest_income_revenue: float | None = None
    interest_income_year: int | None = None
    latest_income_statement_year: int | None = None
    # all from the same annual balance sheet, so total-assets ratios compare like with like
    total_assets: float | None = None
    accounts_receivable: float | None = None
    balance_sheet_debt: float | None = None
    balance_sheet_cash: float | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_fund(self) -> bool:
        """Whether yfinance says this is an ETF or mutual fund rather than a company."""
        return self.quote_type in FUND_QUOTE_TYPES
