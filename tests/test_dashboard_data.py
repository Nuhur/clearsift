import copy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from clearsift.cli import BUSINESS_WARNING, INTEREST_WARNING
from clearsift.config import ConfigError, ScreeningConfig, load_config
from clearsift.dashboard_data import (
    COLOURS,
    ComparisonCard,
    ErrorCard,
    NotCheckedCard,
    StockCard,
    chart_rows,
    colour,
    comparison_card,
    holding_card,
    holding_values,
    load_screening_config,
    parse_tickers,
    screen_cards,
    stock_card,
)
from clearsift.data.models import CompanyFinancials
from clearsift.portfolio import Holding, screen_holdings
from clearsift.screening.business import RatioValue
from clearsift.screening.screen import compare_stock, screen_stock
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
GROCER = {**GOOD, "sector": "Consumer Defensive", "industry": "Grocery Stores"}
TOBACCO = {**GOOD, "sector": "Consumer Defensive", "industry": "Tobacco"}
ETF: dict[str, Any] = {"quote_type": "ETF"}


class FakeGet:
    """Stands in for get_financials, with made-up data for each ticker."""

    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.data = data
        self.calls: list[str] = []

    def __call__(self, ticker: str, **kwargs: Any) -> CompanyFinancials:
        self.calls.append(ticker)
        return CompanyFinancials(ticker=ticker, **self.data.get(ticker, {}))


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.fixture
def strict(tmp_path: Path) -> ScreeningConfig:
    return load_config(_write(tmp_path, CONFIG)).screening


@pytest.fixture
def standard(strict: ScreeningConfig) -> ScreeningConfig:
    return replace(strict, mode="standard")


def _screen(config: ScreeningConfig, data: dict[str, Any], ticker: str = "ABC") -> StockCard:
    return stock_card(screen_stock(ticker, config, get=FakeGet({ticker: data})))


def _compare(config: ScreeningConfig, data: dict[str, Any], ticker: str = "ABC") -> ComparisonCard:
    verdicts = compare_stock(ticker, config, get=FakeGet({ticker: data}))
    return comparison_card(verdicts, config.methodology.label)


# load_screening_config


def test_load_screening_config(tmp_path: Path) -> None:
    config = load_screening_config(_write(tmp_path, CONFIG))

    assert config.methodology.label == "AAOIFI"
    assert [m.label for m in config.methodologies] == ["AAOIFI", "FTSE"]


def test_load_screening_config_broken_file(tmp_path: Path) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["mode"] = "relaxed"

    with pytest.raises(ConfigError):
        load_screening_config(_write(tmp_path, data))


def test_load_screening_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_screening_config(tmp_path / "nope.yaml")


def test_load_screening_config_sector_typo(tmp_path: Path) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["excluded_sectors"] = ["alchohol"]

    with pytest.raises(ConfigError, match="alchohol"):
        load_screening_config(_write(tmp_path, data))


# parse_tickers


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("AAPL", ["AAPL"]),
        ("aapl, msft,xom", ["AAPL", "MSFT", "XOM"]),
        (" aapl ,, msft , ", ["AAPL", "MSFT"]),
        ("AAPL MSFT\nXOM", ["AAPL", "MSFT", "XOM"]),
        ("AAPL, aapl, MSFT", ["AAPL", "MSFT"]),
        ("igda.l", ["IGDA.L"]),
        ("", []),
        (" , ", []),
    ],
)
def test_parse_tickers(text: str, expected: list[str]) -> None:
    assert parse_tickers(text) == expected


# colour


def test_colour_green_for_compliant(strict: ScreeningConfig) -> None:
    assert colour(screen_stock("ABC", strict, get=FakeGet({"ABC": GOOD}))) == "green"


def test_colour_amber_for_doubtful_pass(standard: ScreeningConfig) -> None:
    assert colour(screen_stock("ABC", standard, get=FakeGet({"ABC": GROCER}))) == "amber"


def test_colour_red_for_doubtful_fail_in_strict_mode(strict: ScreeningConfig) -> None:
    assert colour(screen_stock("ABC", strict, get=FakeGet({"ABC": GROCER}))) == "red"


def test_colour_red_for_excluded(standard: ScreeningConfig) -> None:
    assert colour(screen_stock("ABC", standard, get=FakeGet({"ABC": TOBACCO}))) == "red"


# stock_card


def test_stock_card_for_compliant_company(strict: ScreeningConfig) -> None:
    card = _screen(strict, GOOD)

    assert card == StockCard(
        ticker="ABC",
        company=["Technology / Software - Infrastructure"],
        result="PASS (compliant)",
        colour="green",
        warnings=[],
        purification="purify 2.00% of dividends",
        reasons=[
            "industry 'Software - Infrastructure' isn't excluded or marked for review",
            "debt is 10.00% of market cap, AAOIFI limit is 30%",
            "cash is 20.00% of market cap, AAOIFI limit is 30%",
            "interest income is 2.00% of revenue, AAOIFI limit is 5%",
        ],
        ratios=(
            RatioValue("debt", pytest.approx(0.10), 0.30, True),
            RatioValue("cash", pytest.approx(0.20), 0.30, True),
            RatioValue("interest income", pytest.approx(0.02), 0.05, True),
        ),
    )


def test_stock_card_failed_has_no_purification(strict: ScreeningConfig) -> None:
    card = _screen(strict, TOBACCO)

    assert card.result == "FAIL (excluded)"
    assert card.colour == "red"
    assert card.purification is None
    assert card.reasons[0] == "industry 'Tobacco' falls under excluded group 'tobacco'"


def test_stock_card_business_warning(standard: ScreeningConfig) -> None:
    card = _screen(standard, GROCER)

    assert card.result == "PASS (doubtful)"
    assert card.warnings == [BUSINESS_WARNING]


def test_stock_card_interest_warning(standard: ScreeningConfig) -> None:
    card = _screen(standard, {**GOOD, "interest_income_year": 2023})

    assert card.warnings == [INTEREST_WARNING]
    assert card.purification == "purify 2.00% of dividends (based on 2023)"


def test_stock_card_both_warnings(standard: ScreeningConfig) -> None:
    card = _screen(standard, {**GROCER, "interest_income_year": 2023})

    assert card.warnings == [BUSINESS_WARNING, INTEREST_WARNING]


def test_stock_card_ratio_fail_keeps_every_bar(strict: ScreeningConfig) -> None:
    card = _screen(strict, {**GOOD, "total_debt": 400.0})

    assert [(r.name, r.passed) for r in card.ratios] == [
        ("debt", False),
        ("cash", True),
        ("interest income", True),
    ]


def test_stock_card_for_fund(strict: ScreeningConfig) -> None:
    card = _screen(strict, ETF, ticker="IGDA.L")

    assert card.company == ["fund (ETF)"]
    assert card.result == "PASS (compliant)"
    assert card.purification == "purification: check the fund's own reports"
    assert card.ratios == ()


def test_stock_card_unapproved_fund_has_no_industry_warning(standard: ScreeningConfig) -> None:
    card = _screen(standard, ETF, ticker="VUSA.L")

    assert card.colour == "amber"
    assert card.warnings == []
    assert card.reasons == ["fund: check its Sharia certification"]


def test_stock_card_no_data(strict: ScreeningConfig) -> None:
    card = _screen(strict, {})

    assert card.company == ["unknown / unknown", "no data from yfinance, try again later"]
    assert card.colour == "red"


# comparison_card


def test_comparison_card_all_pass(strict: ScreeningConfig) -> None:
    card = _compare(strict, GOOD)

    assert card.ticker == "ABC"
    assert card.methodology == "AAOIFI"
    assert card.result == "PASS (compliant)"
    assert card.colour == "green"
    assert card.purification == "purify 2.00% of dividends"
    assert card.business_reasons == [
        "industry 'Software - Infrastructure' isn't excluded or marked for review"
    ]
    assert [(s.methodology, s.result, s.colour) for s in card.standards] == [
        ("AAOIFI", "PASS (compliant)", "green"),
        ("FTSE", "PASS (compliant)", "green"),
    ]
    assert card.standards[1].reasons[0] == "debt is 5.00% of total assets, FTSE limit is 33.333%"
    assert [r.name for r in card.standards[1].ratios] == [
        "debt",
        "cash",
        "receivables plus cash",
        "interest income",
    ]
    assert card.summary == "passes under 2 of 2 standards"


def test_comparison_card_result_follows_chosen_standard(strict: ScreeningConfig) -> None:
    # fails AAOIFI on debt, passes FTSE, which uses total assets
    card = _compare(strict, {**GOOD, "total_debt": 400.0})

    assert card.result == "FAIL (excluded)"
    assert card.colour == "red"
    assert [s.colour for s in card.standards] == ["red", "green"]
    assert card.summary == "passes under 1 of 2 standards"
    # one standard passed, so the purification still shows
    assert card.purification == "purify 2.00% of dividends"


def test_comparison_card_chosen_can_be_another_standard(strict: ScreeningConfig) -> None:
    verdicts = compare_stock("ABC", strict, get=FakeGet({"ABC": {**GOOD, "total_debt": 400.0}}))

    card = comparison_card(verdicts, "FTSE")

    assert card.methodology == "FTSE"
    assert card.result == "PASS (compliant)"


def test_comparison_card_no_purification_if_every_standard_fails(
    strict: ScreeningConfig,
) -> None:
    card = _compare(strict, TOBACCO)

    assert card.purification is None
    assert card.summary == "passes under 0 of 2 standards"


def test_comparison_card_business_warning_once(standard: ScreeningConfig) -> None:
    card = _compare(standard, GROCER)

    assert card.warnings == [BUSINESS_WARNING]
    assert all(s.warning is None for s in card.standards)


def test_comparison_card_interest_warning_per_standard(standard: ScreeningConfig) -> None:
    card = _compare(standard, {**GOOD, "interest_income_year": 2023})

    assert card.warnings == []
    assert [s.warning for s in card.standards] == [INTEREST_WARNING, INTEREST_WARNING]
    assert [s.colour for s in card.standards] == ["amber", "amber"]


# screen_cards


def test_screen_cards_one_per_ticker(strict: ScreeningConfig) -> None:
    get = FakeGet({"ABC": GOOD, "MO": TOBACCO})

    cards = screen_cards(["ABC", "MO"], strict, compare=False, get=get)

    assert [type(c) for c in cards] == [StockCard, StockCard]
    assert [c.ticker for c in cards] == ["ABC", "MO"]
    assert get.calls == ["ABC", "MO"]


def test_screen_cards_compare(strict: ScreeningConfig) -> None:
    get = FakeGet({"ABC": GOOD})

    cards = screen_cards(["ABC"], strict, compare=True, get=get)

    assert isinstance(cards[0], ComparisonCard)
    # fetched once and judged under both standards
    assert get.calls == ["ABC"]


def test_screen_cards_error_does_not_stop_the_rest(strict: ScreeningConfig) -> None:
    def get(ticker: str, **kwargs: Any) -> CompanyFinancials:
        if ticker == "BAD":
            raise ValueError("something went wrong")
        return CompanyFinancials(ticker=ticker, **GOOD)

    cards = screen_cards(["BAD", "ABC"], strict, compare=False, get=get)

    assert cards[0] == ErrorCard("BAD", "something went wrong")
    assert isinstance(cards[1], StockCard)


def test_screen_cards_empty(strict: ScreeningConfig) -> None:
    assert screen_cards([], strict, compare=False, get=FakeGet({})) == []


# chart_rows


def test_chart_rows() -> None:
    rows = chart_rows(
        [
            RatioValue("debt", 0.1, 0.3, True),
            RatioValue("receivables plus cash", 0.6, 0.5, False),
        ]
    )

    assert [(r.label, r.text, r.colour) for r in rows] == [
        ("Debt", "10.00%", COLOURS["green"]),
        ("Receivables plus cash", "60.00%", COLOURS["red"]),
    ]
    assert rows[0].value == pytest.approx(10.0)
    assert rows[0].limit == pytest.approx(30.0)


def test_chart_axis_fits_the_limit_when_value_is_small() -> None:
    (row,) = chart_rows([RatioValue("debt", 0.01, 0.3, True)])

    assert row.axis_max == pytest.approx(34.5)


def test_chart_axis_fits_the_value_when_over_the_limit() -> None:
    (row,) = chart_rows([RatioValue("debt", 0.5, 0.3, False)])

    assert row.axis_max == pytest.approx(57.5)


def test_chart_axis_with_zero_limit_and_value() -> None:
    (row,) = chart_rows([RatioValue("interest income", 0.0, 0.0, True)])

    assert row.axis_max == 1.0


def test_chart_rows_empty() -> None:
    assert chart_rows([]) == []


# holding_card


def _position(
    ticker: str | None,
    quantity: float | None = 2.0,
    average_price: float | None = 321.5,
    current_price: float | None = 987.25,
    currency: str | None = "USD",
) -> Position:
    return Position(
        ticker=ticker,
        quantity=quantity,
        average_price=average_price,
        current_price=current_price,
        currency=currency,
    )


def _holding(config: ScreeningConfig, ticker: str, data: dict[str, dict[str, Any]]) -> Holding:
    (holding,) = screen_holdings([_position(ticker)], config, get=FakeGet(data))
    return holding


def test_holding_card_titled_with_both_tickers(strict: ScreeningConfig) -> None:
    card = holding_card(_holding(strict, "MO_US_EQ", {"MO": TOBACCO}))

    assert isinstance(card, StockCard)
    assert card.ticker == "MO (MO_US_EQ)"
    assert card.result == "FAIL (excluded)"
    assert card.colour == "red"


def test_holding_card_matches_screener_card(strict: ScreeningConfig) -> None:
    holding = _holding(strict, "MSFT_US_EQ", {"MSFT": GOOD})

    card = holding_card(holding)

    assert card == replace(_screen(strict, GOOD, ticker="MSFT"), ticker="MSFT (MSFT_US_EQ)")


def test_holding_card_not_checked(strict: ScreeningConfig) -> None:
    card = holding_card(_holding(strict, "SAPd_EQ", {}))

    assert card == NotCheckedCard("SAPd_EQ", "couldn't convert ticker, check by hand")


def test_holding_card_has_no_money_values(strict: ScreeningConfig) -> None:
    # values only show when switched on, so the card itself mustn't carry them
    for ticker in ("MSFT_US_EQ", "SAPd_EQ"):
        text = repr(holding_card(_holding(strict, ticker, {"MSFT": GOOD})))

        assert "321.5" not in text
        assert "987.25" not in text
        assert "USD" not in text


# holding_values


def test_holding_values() -> None:
    assert holding_values(_position("MSFT_US_EQ", quantity=3.5)) == [
        ("Quantity", "3.5"),
        ("Average price", "321.50 USD"),
        ("Current price", "987.25 USD"),
    ]


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (5.0, "5.00 GBX"),
        (1234.5, "1,234.50 GBX"),
        (0.0345, "0.0345 GBX"),
        (12.34567, "12.3457 GBX"),
        (None, "unknown"),
    ],
)
def test_holding_values_prices(price: float | None, expected: str) -> None:
    values = holding_values(_position("VODl_EQ", average_price=price, currency="GBX"))

    assert values[1] == ("Average price", expected)


def test_holding_values_unknown_quantity_and_currency() -> None:
    values = holding_values(_position("ABC_US_EQ", quantity=None, currency=None))

    assert values == [
        ("Quantity", "unknown"),
        ("Average price", "321.50"),
        ("Current price", "987.25"),
    ]
