from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from clearsift.config import ScreeningConfig
from clearsift.data.cache import get_financials
from clearsift.data.models import CompanyFinancials
from clearsift.screening.screen import StockVerdict, compare_stock, screen_stock
from clearsift.t212.models import Position
from clearsift.t212.tickers import t212_to_yahoo

NOT_CONVERTED = "couldn't convert ticker, check by hand"


class PositionSource(Protocol):
    """Anything that can list open positions, e.g. T212Client."""

    def positions(self) -> list[Position]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class Holding:
    position: Position
    yahoo: str | None
    # one per standard with compare on, otherwise just one. Empty if it wasn't checked
    verdicts: list[StockVerdict]
    # the one for the standard picked in config.yaml, which decides pass or fail
    verdict: StockVerdict | None

    @property
    def label(self) -> str:
        """The Trading 212 ticker, or a stand-in if Trading 212 didn't send one."""
        return self.position.ticker or "unknown ticker"

    @property
    def title(self) -> str:
        """Both tickers, e.g. MO (MO_US_EQ), or just the Trading 212 one if not converted."""
        return f"{self.yahoo} ({self.label})" if self.yahoo else self.label


def fetch_positions(make_client: Callable[[], PositionSource]) -> list[Position]:
    """Get the open positions, closing the client whatever happens."""
    client = make_client()
    try:
        return client.positions()
    finally:
        client.close()


def screen_holdings(
    positions: Sequence[Position],
    config: ScreeningConfig,
    compare: bool = False,
    get: Callable[..., CompanyFinancials] = get_financials,
) -> list[Holding]:
    """Convert each position's ticker and screen it."""
    holdings = []
    for position in positions:
        t212 = position.ticker
        yahoo = t212_to_yahoo(t212) if t212 is not None else None
        if yahoo is None:
            # guessing a ticker could screen the wrong company, so leave it to a human
            holdings.append(Holding(position, None, [], None))
            continue
        if compare:
            verdicts = compare_stock(yahoo, config, get=get)
            # pass or fail still follows the methodology picked in the config
            chosen = next(v for v in verdicts if v.methodology == config.methodology.label)
        else:
            chosen = screen_stock(yahoo, config, get=get)
            verdicts = [chosen]
        holdings.append(Holding(position, yahoo, verdicts, chosen))
    return holdings


def review_lines(holdings: Sequence[Holding]) -> list[str]:
    """List the holdings that failed or couldn't be checked, with the reason for each."""
    lines = []
    for holding in holdings:
        if holding.verdict is None:
            lines.append(f"{holding.label}: not checked, {NOT_CONVERTED}")
        elif not holding.verdict.passes:
            lines.append(f"{holding.title}: FAIL, {review_reason(holding.verdict)}")
    return lines


def review_reason(verdict: StockVerdict) -> str:
    """Pick the one reason that best explains why a stock didn't pass."""
    # the screen that set the overall status holds the reason that matters
    business, ratios = verdict.business, verdict.ratios
    if business.status == verdict.status and business.reasons:
        return business.reasons[0]
    # an excluded ratio result only keeps the reasons that didn't pass
    if ratios.status == "excluded" and ratios.reasons:
        return ratios.reasons[0]
    # a doubtful one keeps every reason, so the first could be a harmless pass.
    # Doubt only ever comes from interest income
    if ratios.status == "doubtful":
        return "interest income isn't in the latest report, check by hand"
    return verdict.status


def portfolio_summary(holdings: Sequence[Holding]) -> str:
    """Count the holdings that pass, fail and weren't checked."""
    checked = [h.verdict for h in holdings if h.verdict is not None]
    passed = sum(v.passes for v in checked)
    count = len(holdings)
    return (
        f"{count} holding{'' if count == 1 else 's'}: {passed} pass, "
        f"{len(checked) - passed} fail, {count - len(checked)} not checked"
    )


def quantity_text(quantity: float | None) -> str:
    """Show a quantity without trailing zeros, or 'unknown' if there isn't one."""
    if quantity is None:
        return "unknown"
    # fractional shares go to 6 places, but whole ones shouldn't show as 5.000000
    return f"{quantity:.6f}".rstrip("0").rstrip(".")
