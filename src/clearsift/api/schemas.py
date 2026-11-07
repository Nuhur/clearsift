from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from clearsift.dashboard_data import Colour, comparison_card, stock_card
from clearsift.data.prices import PricePoint
from clearsift.portfolio import NOT_CONVERTED, Holding
from clearsift.screening.business import Base, Outcome, RatioCheck, RatioValue, Status
from clearsift.screening.purification import purification_ratio
from clearsift.screening.screen import StockVerdict


class RatioOut(BaseModel):
    name: str
    value: float
    limit: float
    passed: bool


class RatioCheckOut(BaseModel):
    name: str
    # null when the figure was missing, so there's nothing to draw
    value: float | None
    limit: float
    base: Base
    outcome: Outcome


class CompanyOut(BaseModel):
    # falls back to the ticker when yfinance has no name
    name: str
    sector: str | None
    industry: str | None
    is_fund: bool
    # only true for a fund on your approved list that isn't also always-excluded
    approved_fund: bool
    # the config group that excluded the business, e.g. conventional_banking
    excluded_group: str | None
    # yfinance gave nothing at all, so it's a fetch problem rather than a bad company
    no_data: bool


class VerdictOut(BaseModel):
    # lets the front end tell the result types apart without guessing from the fields
    kind: Literal["verdict"] = "verdict"
    ticker: str
    methodology: str
    status: Status
    passes: bool
    result: str
    colour: Colour
    company: list[str]
    details: CompanyOut
    warnings: list[str]
    purification: str | None
    # the share of each dividend to give away, null when it fails, is a fund or isn't known
    purification_ratio: float | None
    purification_year: int | None
    reasons: list[str]
    ratios: list[RatioOut]
    checks: list[RatioCheckOut]


class StandardOut(BaseModel):
    methodology: str
    status: Status
    passes: bool
    result: str
    colour: Colour
    warning: str | None
    reasons: list[str]
    ratios: list[RatioOut]
    checks: list[RatioCheckOut]


class ComparisonOut(BaseModel):
    kind: Literal["comparison"] = "comparison"
    ticker: str
    # the standard picked in config.yaml, which decides status and passes
    methodology: str
    status: Status
    passes: bool
    result: str
    colour: Colour
    company: list[str]
    details: CompanyOut
    warnings: list[str]
    purification: str | None
    # these follow the chosen standard, so a fail there means nothing to purify
    purification_ratio: float | None
    purification_year: int | None
    business_reasons: list[str]
    standards: list[StandardOut]
    summary: str


class TickerError(BaseModel):
    kind: Literal["error"] = "error"
    ticker: str
    message: str


ScreenResult = Annotated[VerdictOut | ComparisonOut | TickerError, Field(discriminator="kind")]


class ScreenOut(BaseModel):
    results: list[ScreenResult]


class PricePointOut(BaseModel):
    date: dt.date
    close: float


class StockDetailOut(BaseModel):
    ticker: str
    verdict: ComparisonOut
    # empty when yfinance had nothing, so the page just leaves the chart out
    prices: list[PricePointOut]


class HoldingValuesOut(BaseModel):
    quantity: float | None
    average_price: float | None
    current_price: float | None
    # prices are in the instrument's currency, not the account's
    currency: str | None


class HoldingOut(BaseModel):
    t212_ticker: str
    yahoo_ticker: str | None
    title: str
    # None when the ticker couldn't be converted, so it was never screened
    verdict: VerdictOut | ComparisonOut | None
    message: str | None
    # left out unless asked for, so a screenshot of the page doesn't give the amounts away
    values: HoldingValuesOut | None


class PortfolioOut(BaseModel):
    holdings: list[HoldingOut]
    summary: str
    review: list[str]


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorOut(BaseModel):
    message: str


def ratios_out(ratios: Sequence[RatioValue]) -> list[RatioOut]:
    """Turn ratio values into their response models."""
    return [RatioOut(name=r.name, value=r.ratio, limit=r.limit, passed=r.passed) for r in ratios]


def checks_out(checks: Sequence[RatioCheck]) -> list[RatioCheckOut]:
    """Turn every ratio check into its response model."""
    return [
        RatioCheckOut(name=c.name, value=c.value, limit=c.limit, base=c.base, outcome=c.outcome)
        for c in checks
    ]


def company_out(verdict: StockVerdict) -> CompanyOut:
    """Describe the company or fund behind a verdict, field by field."""
    financials = verdict.financials
    return CompanyOut(
        name=financials.company_name or verdict.ticker,
        sector=financials.sector,
        industry=financials.industry,
        is_fund=verdict.is_fund,
        approved_fund=verdict.is_fund and verdict.business.status == "compliant",
        excluded_group=verdict.business.excluded_group,
        no_data=financials.has_no_data,
    )


def _purification_year(verdict: StockVerdict) -> int | None:
    return verdict.ratios.interest_year if purification_ratio(verdict) is not None else None


def verdict_out(verdict: StockVerdict) -> VerdictOut:
    """Turn one verdict into its response model."""
    card = stock_card(verdict)
    return VerdictOut(
        ticker=card.ticker,
        methodology=verdict.methodology,
        status=verdict.status,
        passes=verdict.passes,
        result=card.result,
        colour=card.colour,
        company=card.company,
        details=company_out(verdict),
        warnings=card.warnings,
        purification=card.purification,
        purification_ratio=purification_ratio(verdict),
        purification_year=_purification_year(verdict),
        reasons=card.reasons,
        ratios=ratios_out(card.ratios),
        checks=checks_out(verdict.ratios.ratio_checks),
    )


def comparison_out(verdicts: list[StockVerdict], chosen: str) -> ComparisonOut:
    """Turn one stock's verdicts under every standard into its response model."""
    card = comparison_card(verdicts, chosen)
    by_name = {v.methodology: v for v in verdicts}
    main = by_name[chosen]
    return ComparisonOut(
        ticker=card.ticker,
        methodology=card.methodology,
        status=main.status,
        passes=main.passes,
        result=card.result,
        colour=card.colour,
        company=card.company,
        details=company_out(main),
        warnings=card.warnings,
        purification=card.purification,
        purification_ratio=purification_ratio(main),
        purification_year=_purification_year(main),
        business_reasons=card.business_reasons,
        standards=[
            StandardOut(
                methodology=s.methodology,
                status=by_name[s.methodology].status,
                passes=by_name[s.methodology].passes,
                result=s.result,
                colour=s.colour,
                warning=s.warning,
                reasons=s.reasons,
                ratios=ratios_out(s.ratios),
                checks=checks_out(by_name[s.methodology].ratios.ratio_checks),
            )
            for s in card.standards
        ],
        summary=card.summary,
    )


def prices_out(points: Sequence[PricePoint]) -> list[PricePointOut]:
    """Turn closing prices into their response models."""
    return [PricePointOut(date=p.day, close=p.close) for p in points]


def holding_out(holding: Holding, compare: bool, show_values: bool) -> HoldingOut:
    """Turn one holding into its response model."""
    verdict: VerdictOut | ComparisonOut | None = None
    if holding.verdict is not None:
        # the holding's own verdict is the standard picked in config.yaml
        if compare:
            verdict = comparison_out(holding.verdicts, holding.verdict.methodology)
        else:
            verdict = verdict_out(holding.verdict)
    position = holding.position
    values = None
    if show_values:
        values = HoldingValuesOut(
            quantity=position.quantity,
            average_price=position.average_price,
            current_price=position.current_price,
            currency=position.currency,
        )
    return HoldingOut(
        t212_ticker=holding.label,
        yahoo_ticker=holding.yahoo,
        title=holding.title,
        verdict=verdict,
        message=NOT_CONVERTED if verdict is None else None,
        values=values,
    )
