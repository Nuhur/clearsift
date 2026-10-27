from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AccountSummary:
    currency: str | None
    cash: float | None
    # Trading 212 calls this totalValue, so keep its name rather than guess what it covers
    total_value: float | None
    investments_value: float | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> AccountSummary:
        """Build an account summary from the API's JSON."""
        cash = _dict(data.get("cash"))
        investments = _dict(data.get("investments"))
        return cls(
            currency=_text(data.get("currency")),
            cash=_number(cash.get("availableToTrade")),
            total_value=_number(data.get("totalValue")),
            investments_value=_number(investments.get("currentValue")),
        )


@dataclass(frozen=True)
class Position:
    ticker: str | None
    quantity: float | None
    average_price: float | None
    current_price: float | None
    # prices are in the instrument's currency, not the account's
    currency: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Position:
        """Build a position from the API's JSON."""
        instrument = _dict(data.get("instrument"))
        return cls(
            ticker=_text(instrument.get("ticker")),
            quantity=_number(data.get("quantity")),
            average_price=_number(data.get("averagePricePaid")),
            current_price=_number(data.get("currentPrice")),
            currency=_text(instrument.get("currency")),
        )


@dataclass(frozen=True)
class Order:
    id: int | None
    ticker: str | None
    side: str | None
    status: str | None
    quantity: float | None
    filled_quantity: float | None
    fill_price: float | None
    created_at: datetime | None
    filled_at: datetime | None
    currency: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Order:
        """Build a past order from the API's JSON."""
        order = _dict(data.get("order"))
        # orders that never filled come back without a fill
        fill = _dict(data.get("fill"))
        order_id = order.get("id")
        return cls(
            id=order_id if isinstance(order_id, int) and not isinstance(order_id, bool) else None,
            ticker=_text(order.get("ticker")),
            side=_text(order.get("side")),
            status=_text(order.get("status")),
            quantity=_number(order.get("quantity")),
            filled_quantity=_number(order.get("filledQuantity")),
            fill_price=_number(fill.get("price")),
            created_at=_datetime(order.get("createdAt")),
            filled_at=_datetime(fill.get("filledAt")),
            currency=_text(order.get("currency")),
        )


@dataclass(frozen=True)
class Dividend:
    ticker: str | None
    # in the account's currency, after tax
    amount: float | None
    currency: str | None
    # in the instrument's currency
    gross_amount_per_share: float | None
    quantity: float | None
    paid_on: datetime | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Dividend:
        """Build a dividend payment from the API's JSON."""
        return cls(
            ticker=_text(data.get("ticker")),
            amount=_number(data.get("amount")),
            currency=_text(data.get("currency")),
            gross_amount_per_share=_number(data.get("grossAmountPerShare")),
            quantity=_number(data.get("quantity")),
            paid_on=_datetime(data.get("paidOn")),
        )


def _dict(raw: Any) -> dict[str, Any]:
    # a missing or odd-shaped section shouldn't crash the rest of the record
    return raw if isinstance(raw, dict) else {}


def _text(raw: Any) -> str | None:
    return raw if isinstance(raw, str) and raw else None


def _number(raw: Any) -> float | None:
    # Python counts True and False as numbers, so skip those
    if isinstance(raw, bool) or not isinstance(raw, numbers.Real):
        return None
    value = float(raw)
    return value if math.isfinite(value) else None


def _datetime(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
