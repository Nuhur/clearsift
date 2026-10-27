from __future__ import annotations

import re

# US shares look like AAPL_US_EQ
_US = re.compile(r"([A-Z]{1,5})_US_EQ")
# London shares look like VODl_EQ, the lowercase l is how Trading 212 marks the LSE
_LONDON = re.compile(r"([A-Z]{1,4})l_EQ")


def t212_to_yahoo(ticker: str) -> str | None:
    """Turn a Trading 212 ticker into a Yahoo one, or None if we can't be sure."""
    # anything else (other exchanges, share classes like BRK.B or BT.A) would be a guess,
    # and a wrong ticker would screen the wrong company
    if not isinstance(ticker, str):
        return None
    if match := _US.fullmatch(ticker):
        return match.group(1)
    if match := _LONDON.fullmatch(ticker):
        return f"{match.group(1)}.L"
    return None
