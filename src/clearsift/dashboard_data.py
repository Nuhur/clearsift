from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from clearsift.cli import (
    business_warning,
    company_lines,
    interest_warning,
    pass_fail,
    purification_line,
    standards_summary,
    warnings,
)
from clearsift.config import ConfigError, ScreeningConfig, load_config
from clearsift.data.cache import get_financials
from clearsift.data.models import CompanyFinancials
from clearsift.screening.business import RatioValue, check_excluded_sectors
from clearsift.screening.screen import StockVerdict, compare_stock, screen_stock

Colour = Literal["green", "amber", "red"]

COLOURS: dict[Colour, str] = {
    "green": "#1a7f37",
    "amber": "#b7791f",
    "red": "#cf222e",
}


@dataclass(frozen=True)
class StockCard:
    ticker: str
    company: list[str]
    result: str
    colour: Colour
    warnings: list[str]
    purification: str | None
    reasons: list[str]
    ratios: tuple[RatioValue, ...]


@dataclass(frozen=True)
class StandardResult:
    methodology: str
    result: str
    colour: Colour
    warning: str | None
    reasons: list[str]
    ratios: tuple[RatioValue, ...]


@dataclass(frozen=True)
class ComparisonCard:
    ticker: str
    company: list[str]
    # the standard picked in config.yaml, which decides the card's own result
    methodology: str
    result: str
    colour: Colour
    warnings: list[str]
    purification: str | None
    business_reasons: list[str]
    standards: list[StandardResult]
    summary: str


@dataclass(frozen=True)
class ErrorCard:
    ticker: str
    message: str


Card = StockCard | ComparisonCard | ErrorCard


@dataclass(frozen=True)
class ChartRow:
    label: str
    value: float
    limit: float
    colour: str
    text: str
    axis_max: float


def load_screening_config(path: str | Path = "config.yaml") -> ScreeningConfig:
    """Load the screening settings and check them, raising ConfigError if anything's wrong."""
    config = load_config(path).screening
    # funds skip the business screen, so a typo in the sector list could otherwise go unnoticed
    try:
        check_excluded_sectors(config)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    return config


def parse_tickers(text: str) -> list[str]:
    """Split the ticker box into a list of uppercase tickers, without repeats."""
    # people type spaces as well as commas, and a ticker never has either in it
    tickers = [ticker.upper() for ticker in re.split(r"[,\s]+", text) if ticker]
    return list(dict.fromkeys(tickers))


def colour(verdict: StockVerdict) -> Colour:
    """Pick red for a fail, amber for a doubtful pass and green for a clean pass."""
    if not verdict.passes:
        return "red"
    return "amber" if verdict.status == "doubtful" else "green"


def stock_card(verdict: StockVerdict) -> StockCard:
    """Turn one verdict into what the screener shows for it."""
    return StockCard(
        ticker=verdict.ticker,
        company=company_lines(verdict),
        result=pass_fail(verdict),
        colour=colour(verdict),
        warnings=warnings(verdict),
        purification=purification_line(verdict) if verdict.passes else None,
        reasons=verdict.business.reasons + verdict.ratios.reasons,
        ratios=verdict.ratios.ratio_values,
    )


def comparison_card(verdicts: list[StockVerdict], chosen: str) -> ComparisonCard:
    """Turn one stock's verdicts under every standard into what the screener shows."""
    # the business screen and the data are the same for every standard
    first = verdicts[0]
    main = next(v for v in verdicts if v.methodology == chosen)
    # the ratio is the same under every standard, so show it once
    passing = next((v for v in verdicts if v.passes), None)
    warning = business_warning(first)
    return ComparisonCard(
        ticker=first.ticker,
        company=company_lines(first),
        methodology=chosen,
        result=pass_fail(main),
        colour=colour(main),
        warnings=[warning] if warning else [],
        purification=purification_line(passing) if passing is not None else None,
        business_reasons=first.business.reasons,
        standards=[
            StandardResult(
                methodology=v.methodology,
                result=pass_fail(v),
                colour=colour(v),
                warning=interest_warning(v),
                reasons=v.ratios.reasons,
                ratios=v.ratios.ratio_values,
            )
            for v in verdicts
        ],
        summary=standards_summary(verdicts),
    )


def screen_cards(
    tickers: Sequence[str],
    config: ScreeningConfig,
    compare: bool,
    get: Callable[..., CompanyFinancials] = get_financials,
) -> list[Card]:
    """Screen each ticker and turn the results into cards."""
    cards: list[Card] = []
    for ticker in tickers:
        try:
            if compare:
                verdicts = compare_stock(ticker, config, get=get)
                cards.append(comparison_card(verdicts, config.methodology.label))
            else:
                cards.append(stock_card(screen_stock(ticker, config, get=get)))
        except ValueError as exc:
            # one bad ticker shouldn't stop the others from showing
            cards.append(ErrorCard(ticker.strip().upper(), str(exc)))
    return cards


def chart_rows(ratios: Sequence[RatioValue]) -> list[ChartRow]:
    """Turn ratio values into rows for the bar charts, in percent."""
    rows = []
    for ratio in ratios:
        value, limit = ratio.ratio * 100, ratio.limit * 100
        rows.append(
            ChartRow(
                label=ratio.name.capitalize(),
                value=value,
                limit=limit,
                colour=COLOURS["green" if ratio.passed else "red"],
                text=f"{value:.2f}%",
                # room past whichever is bigger, so the limit line never sits on the edge.
                # A zero limit with a zero value still needs an axis to draw on
                axis_max=max(value, limit) * 1.15 or 1.0,
            )
        )
    return rows
