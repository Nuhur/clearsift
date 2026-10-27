from typing import Any

import pytest

from clearsift.t212.tickers import t212_to_yahoo


@pytest.mark.parametrize(
    ("t212", "yahoo"),
    [
        ("AAPL_US_EQ", "AAPL"),
        ("MSFT_US_EQ", "MSFT"),
        ("F_US_EQ", "F"),
        ("GOOGL_US_EQ", "GOOGL"),
    ],
)
def test_us_tickers(t212: str, yahoo: str) -> None:
    assert t212_to_yahoo(t212) == yahoo


@pytest.mark.parametrize(
    ("t212", "yahoo"),
    [
        ("VODl_EQ", "VOD.L"),
        ("RRl_EQ", "RR.L"),
        ("BPl_EQ", "BP.L"),
        ("VUSAl_EQ", "VUSA.L"),
    ],
)
def test_london_tickers(t212: str, yahoo: str) -> None:
    assert t212_to_yahoo(t212) == yahoo


@pytest.mark.parametrize(
    "t212",
    [
        # other exchanges, e.g. Germany
        "SAPd_EQ",
        # share classes use different punctuation on Yahoo
        "BRK_B_US_EQ",
        "BT.Al_EQ",
        # not shares
        "AAPL_US_CFD",
        # lowercase means something in these tickers, so don't fix it up
        "aapl_US_EQ",
        "VODL_EQ",
        # missing or extra bits
        "AAPL",
        "VOD_EQ",
        "_US_EQ",
        "l_EQ",
        "TOOLONG_US_EQ",
        " AAPL_US_EQ",
        "",
    ],
)
def test_unknown_formats_give_none(t212: str) -> None:
    assert t212_to_yahoo(t212) is None


@pytest.mark.parametrize("t212", [None, 123])
def test_non_text_gives_none(t212: Any) -> None:
    assert t212_to_yahoo(t212) is None
