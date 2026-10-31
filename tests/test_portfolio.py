from pathlib import Path
from typing import Any

import pytest
import yaml

from clearsift.config import ScreeningConfig, load_config
from clearsift.data.models import CompanyFinancials
from clearsift.portfolio import (
    NOT_CONVERTED,
    Holding,
    fetch_positions,
    portfolio_summary,
    quantity_text,
    review_lines,
    review_reason,
    screen_holdings,
)
from clearsift.screening.screen import screen_stock
from clearsift.t212.client import T212APIError
from clearsift.t212.models import Position

CONFIG: dict[str, Any] = {
    "screening": {
        "mode": "strict",
        "fail_closed": True,
        "max_data_age_days": 120,
        "market_cap_max_age_days": 1,
        "max_interest_income_age_years": 3,
        "methodology": "aaoifi",
        "methodologies": {
            "aaoifi": {
                "denominator": "market_cap",
                "max_debt": 0.30,
                "max_cash": 0.30,
                "max_receivables_and_cash": None,
                "max_impermissible_income": 0.05,
            },
            "ftse": {
                "denominator": "total_assets",
                "max_debt": 0.33333,
                "max_cash": 0.33333,
                "max_receivables_and_cash": 0.50,
                "max_impermissible_income": 0.05,
            },
        },
        "excluded_sectors": ["alcohol", "tobacco"],
        "always_exclude_tickers": [],
        "approved_funds": ["IGDA.L"],
    },
    "benchmark": {"ticker": None},
}

# a software company with every ratio well under its limit
GOOD: dict[str, Any] = {
    "sector": "Technology",
    "industry": "Software - Infrastructure",
    "market_cap": 1000.0,
    "total_debt": 100.0,
    "cash_and_short_term_investments": 200.0,
    "total_revenue": 500.0,
    "interest_income_revenue": 500.0,
    "interest_income_year": 2025,
    "latest_income_statement_year": 2025,
    "total_assets": 2000.0,
    "accounts_receivable": 100.0,
    "balance_sheet_debt": 100.0,
    "balance_sheet_cash": 200.0,
    "interest_income": 10.0,
}
TOBACCO = {**GOOD, "sector": "Consumer Defensive", "industry": "Tobacco"}


class FakeGet:
    """Stands in for get_financials, with made-up data per Yahoo ticker."""

    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.data = data
        self.calls: list[str] = []

    def __call__(self, ticker: str, **kwargs: Any) -> CompanyFinancials:
        self.calls.append(ticker)
        return CompanyFinancials(ticker=ticker, **self.data.get(ticker, {}))


class FakeClient:
    """Stands in for T212Client, handing back canned positions or an error."""

    def __init__(self, positions: list[Position] | None = None, error: Exception | None = None):
        self._positions = positions or []
        self._error = error
        self.closed = False

    def positions(self) -> list[Position]:
        if self._error is not None:
            raise self._error
        return self._positions

    def close(self) -> None:
        self.closed = True


def _position(ticker: str | None, quantity: float | None = 1.0) -> Position:
    return Position(
        ticker=ticker, quantity=quantity, average_price=None, current_price=None, currency=None
    )


@pytest.fixture
def config(tmp_path: Path) -> ScreeningConfig:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    return load_config(path).screening


def _holdings(
    config: ScreeningConfig, positions: list[Position], data: dict[str, dict[str, Any]]
) -> list[Holding]:
    return screen_holdings(positions, config, get=FakeGet(data))


# fetch_positions


def test_fetch_positions_closes_client() -> None:
    client = FakeClient([_position("MSFT_US_EQ")])

    assert fetch_positions(lambda: client) == [_position("MSFT_US_EQ")]
    assert client.closed


def test_fetch_positions_closes_client_on_error() -> None:
    client = FakeClient(error=T212APIError("Trading 212 returned 500 for /x"))

    with pytest.raises(T212APIError):
        fetch_positions(lambda: client)
    assert client.closed


# screen_holdings


def test_screen_holdings_converts_and_screens(config: ScreeningConfig) -> None:
    get = FakeGet({"MSFT": GOOD, "VOD.L": GOOD})

    holdings = screen_holdings(
        [_position("MSFT_US_EQ"), _position("VODl_EQ")], config, get=get
    )

    assert get.calls == ["MSFT", "VOD.L"]
    assert [(h.yahoo, h.title) for h in holdings] == [
        ("MSFT", "MSFT (MSFT_US_EQ)"),
        ("VOD.L", "VOD.L (VODl_EQ)"),
    ]
    assert all(h.verdict is not None and h.verdict.passes for h in holdings)
    assert all(h.verdicts == [h.verdict] for h in holdings)


def test_screen_holdings_skips_what_it_cant_convert(config: ScreeningConfig) -> None:
    get = FakeGet({})

    holdings = screen_holdings([_position("SAPd_EQ"), _position(None)], config, get=get)

    assert get.calls == []
    assert [(h.yahoo, h.verdict, h.verdicts) for h in holdings] == [(None, None, [])] * 2
    assert [(h.label, h.title) for h in holdings] == [
        ("SAPd_EQ", "SAPd_EQ"),
        ("unknown ticker", "unknown ticker"),
    ]


def test_screen_holdings_compare(config: ScreeningConfig) -> None:
    # fails AAOIFI on debt, passes FTSE, which uses total assets
    get = FakeGet({"ABC": {**GOOD, "total_debt": 400.0}})

    (holding,) = screen_holdings([_position("ABC_US_EQ")], config, compare=True, get=get)

    assert [v.methodology for v in holding.verdicts] == ["AAOIFI", "FTSE"]
    assert holding.verdict is holding.verdicts[0]
    assert holding.verdict is not None and not holding.verdict.passes
    assert get.calls == ["ABC"]


def test_screen_holdings_keeps_order(config: ScreeningConfig) -> None:
    positions = [_position("SAPd_EQ"), _position("MSFT_US_EQ"), _position("MO_US_EQ")]

    holdings = _holdings(config, positions, {"MSFT": GOOD, "MO": TOBACCO})

    assert [h.label for h in holdings] == ["SAPd_EQ", "MSFT_US_EQ", "MO_US_EQ"]


# review_lines


def test_review_lines(config: ScreeningConfig) -> None:
    positions = [
        _position("MSFT_US_EQ"),
        _position("SAPd_EQ"),
        _position("MO_US_EQ"),
        _position(None),
    ]

    holdings = _holdings(config, positions, {"MSFT": GOOD, "MO": TOBACCO})

    assert review_lines(holdings) == [
        f"SAPd_EQ: not checked, {NOT_CONVERTED}",
        "MO (MO_US_EQ): FAIL, industry 'Tobacco' falls under excluded group 'tobacco'",
        f"unknown ticker: not checked, {NOT_CONVERTED}",
    ]


def test_review_lines_empty_when_all_pass(config: ScreeningConfig) -> None:
    assert review_lines(_holdings(config, [_position("MSFT_US_EQ")], {"MSFT": GOOD})) == []


# review_reason


def _reason(config: ScreeningConfig, data: dict[str, Any]) -> str:
    return review_reason(screen_stock("ABC", config, get=FakeGet({"ABC": data})))


def test_review_reason_business(config: ScreeningConfig) -> None:
    assert _reason(config, TOBACCO) == "industry 'Tobacco' falls under excluded group 'tobacco'"


def test_review_reason_ratio(config: ScreeningConfig) -> None:
    assert (
        _reason(config, {**GOOD, "total_debt": 400.0})
        == "debt is 40.00% of market cap, AAOIFI limit is 30%"
    )


def test_review_reason_older_interest_income(config: ScreeningConfig) -> None:
    # the first ratio reason is the debt line, which passed, so it mustn't be picked
    assert (
        _reason(config, {**GOOD, "interest_income_year": 2023})
        == "interest income isn't in the latest report, check by hand"
    )


def test_review_reason_unapproved_fund(config: ScreeningConfig) -> None:
    assert _reason(config, {"quote_type": "ETF"}) == "fund: check its Sharia certification"


# portfolio_summary


def test_portfolio_summary(config: ScreeningConfig) -> None:
    positions = [_position("MSFT_US_EQ"), _position("MO_US_EQ"), _position("SAPd_EQ")]

    holdings = _holdings(config, positions, {"MSFT": GOOD, "MO": TOBACCO})

    assert portfolio_summary(holdings) == "3 holdings: 1 pass, 1 fail, 1 not checked"


def test_portfolio_summary_one_holding(config: ScreeningConfig) -> None:
    holdings = _holdings(config, [_position("MSFT_US_EQ")], {"MSFT": GOOD})

    assert portfolio_summary(holdings) == "1 holding: 1 pass, 0 fail, 0 not checked"


def test_portfolio_summary_empty() -> None:
    assert portfolio_summary([]) == "0 holdings: 0 pass, 0 fail, 0 not checked"


# quantity_text


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        (5.0, "5"),
        (3.5, "3.5"),
        (0.0123456789, "0.012346"),
        (100.0, "100"),
        (None, "unknown"),
    ],
)
def test_quantity_text(quantity: float | None, expected: str) -> None:
    assert quantity_text(quantity) == expected
