from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from clearsift.config import Mode, ScreeningConfig
from clearsift.data.cache import get_financials
from clearsift.data.models import CompanyFinancials
from clearsift.screening.business import ScreenResult, Status, screen_business
from clearsift.screening.ratios import screen_ratios


@dataclass(frozen=True)
class StockVerdict:
    ticker: str
    financials: CompanyFinancials
    business: ScreenResult
    ratios: ScreenResult
    status: Status
    mode: Mode
    methodology: str

    @property
    def passes(self) -> bool:
        """Whether the stock gets in."""
        if self.status == "compliant":
            return True
        # standard mode lets doubtful through, it just gets flagged for a manual check
        return self.status == "doubtful" and self.mode == "standard"

    @property
    def needs_review(self) -> bool:
        """Whether someone should check this business by hand."""
        return self.status == "doubtful"


def screen_stock(
    ticker: str,
    config: ScreeningConfig,
    get: Callable[..., CompanyFinancials] = get_financials,
) -> StockVerdict:
    """Fetch a stock's financials and run every screen on it."""
    return screen_financials(_fetch(ticker, config, get), config)


def compare_stock(
    ticker: str,
    config: ScreeningConfig,
    get: Callable[..., CompanyFinancials] = get_financials,
) -> list[StockVerdict]:
    """Screen a stock under every methodology in the config, one verdict each."""
    # fetch once, the data is the same whichever standard is judging it
    financials = _fetch(ticker, config, get)
    return [
        screen_financials(financials, replace(config, methodology=method))
        for method in config.methodologies
    ]


def screen_financials(financials: CompanyFinancials, config: ScreeningConfig) -> StockVerdict:
    """Run every screen on financials that have already been fetched."""
    ticker = financials.ticker
    # run both even if the first fails, so every problem shows at once
    business = screen_business(financials, config)
    ratios = screen_ratios(financials, config)

    statuses = {business.status, ratios.status}
    status: Status
    if "excluded" in statuses:
        status = "excluded"
    elif "doubtful" in statuses:
        status = "doubtful"
    else:
        status = "compliant"

    return StockVerdict(
        ticker, financials, business, ratios, status, config.mode, config.methodology.label
    )


def _fetch(
    ticker: str, config: ScreeningConfig, get: Callable[..., CompanyFinancials]
) -> CompanyFinancials:
    # the cache and the always-exclude list both use uppercase tickers
    return get(
        ticker.strip().upper(),
        max_age_days=config.max_data_age_days,
        market_cap_max_age_days=config.market_cap_max_age_days,
    )
