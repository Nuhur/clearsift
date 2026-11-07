from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from clearsift.dashboard_data import Colour, comparison_card, stock_card
from clearsift.data.prices import PricePoint
from clearsift.screening.business import RatioValue, Status
from clearsift.screening.screen import StockVerdict


class RatioOut(BaseModel):
    name: str
    value: float
    limit: float
    passed: bool


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
    warnings: list[str]
    purification: str | None
    reasons: list[str]
    ratios: list[RatioOut]


class StandardOut(BaseModel):
    methodology: str
    status: Status
    passes: bool
    result: str
    colour: Colour
    warning: str | None
    reasons: list[str]
    ratios: list[RatioOut]


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
    warnings: list[str]
    purification: str | None
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


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorOut(BaseModel):
    message: str


def ratios_out(ratios: Sequence[RatioValue]) -> list[RatioOut]:
    """Turn ratio values into their response models."""
    return [RatioOut(name=r.name, value=r.ratio, limit=r.limit, passed=r.passed) for r in ratios]


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
        warnings=card.warnings,
        purification=card.purification,
        reasons=card.reasons,
        ratios=ratios_out(card.ratios),
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
        warnings=card.warnings,
        purification=card.purification,
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
            )
            for s in card.standards
        ],
        summary=card.summary,
    )


def prices_out(points: Sequence[PricePoint]) -> list[PricePointOut]:
    """Turn closing prices into their response models."""
    return [PricePointOut(date=p.day, close=p.close) for p in points]
