from __future__ import annotations

import math
from decimal import ROUND_CEILING, Decimal

from clearsift.screening.screen import StockVerdict


def purification_ratio(verdict: StockVerdict) -> float | None:
    """Return the share of each dividend to give to charity, or None if it can't be worked out."""
    # a stock that fails shouldn't be held, so there's no dividend to purify
    if not verdict.passes:
        return None
    # we never saw the fund's income, and many Islamic funds purify for you
    if verdict.is_fund:
        return None
    return verdict.ratios.interest_ratio


def purification_amount(dividend: float, ratio: float) -> float:
    """Return how much of a dividend to give away, rounded up to the penny."""
    if not math.isfinite(dividend) or dividend < 0:
        raise ValueError(f"dividend must be zero or more, got {dividend}")
    # go through str so float noise (100 * 0.0098 = 0.9800000000000001) doesn't get
    # rounded up a whole penny. Always round up so we never give less than we should
    amount = Decimal(str(dividend)) * Decimal(str(ratio))
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_CEILING))
