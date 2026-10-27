import copy
from functools import partial
from pathlib import Path
from typing import Any

import pytest
import yaml

import clearsift.t212.client as client_module
from clearsift.cli import main
from clearsift.data.models import CompanyFinancials
from clearsift.t212.client import T212APIError, T212Client
from clearsift.t212.models import Position

# made up, so nothing real can leak from a test
SECRET = "fake-secret-456"

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
ETF: dict[str, Any] = {"quote_type": "ETF"}


@pytest.fixture(autouse=True)
def no_real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("T212_API_KEY", "T212_API_SECRET", "T212_ENV"):
        monkeypatch.delenv(name, raising=False)

    # no test should ever read the real .env, so make it blow up if one tries
    def refuse(*args: Any, **kwargs: Any) -> bool:
        raise AssertionError("a test tried to load a .env file")

    monkeypatch.setattr(client_module, "load_dotenv", refuse)


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


class FakeGet:
    """Stands in for get_financials, with made-up data per Yahoo ticker."""

    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.data = data
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, ticker: str, **kwargs: Any) -> CompanyFinancials:
        self.calls.append((ticker, kwargs))
        return CompanyFinancials(ticker=ticker, **self.data.get(ticker, {}))


def _position(ticker: str | None, quantity: float | None = 1.0) -> Position:
    return Position(
        ticker=ticker, quantity=quantity, average_price=None, current_price=None, currency=None
    )


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return _write_config(tmp_path, CONFIG)


def _write_config(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _run(
    config_path: Path,
    positions: list[Position],
    data: dict[str, dict[str, Any]],
    *extra: str,
) -> int:
    return main(
        ["portfolio", "--config", str(config_path), *extra],
        get=FakeGet(data),
        make_client=lambda: FakeClient(positions),
    )


def test_all_pass(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    positions = [_position("AAPL_US_EQ", 3.5), _position("MSFT_US_EQ", 2.0)]

    code = _run(config_path, positions, {"AAPL": GOOD, "MSFT": GOOD})

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("AAPL (AAPL_US_EQ), quantity 3.5\nAAPL: PASS (compliant)\n")
    assert "MSFT (MSFT_US_EQ), quantity 2\nMSFT: PASS (compliant)\n" in out
    assert "Not checked" not in out
    assert "\nReview\n  nothing to review\n" in out
    assert out.endswith("\n2 holdings: 2 pass, 0 fail, 0 not checked\n")


def test_one_fail_goes_to_review(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    positions = [_position("MSFT_US_EQ"), _position("MO_US_EQ")]

    code = _run(config_path, positions, {"MSFT": GOOD, "MO": TOBACCO})

    out = capsys.readouterr().out
    assert code == 1
    assert "MO: FAIL (excluded)" in out
    review = out.split("\nReview\n")[1]
    assert review.startswith(
        "  MO (MO_US_EQ): FAIL, industry 'Tobacco' falls under excluded group 'tobacco'\n"
    )
    assert "MSFT" not in review.split("\n\n")[0]
    assert out.endswith("2 holdings: 1 pass, 1 fail, 0 not checked\n")


def test_review_reason_for_ratio_fail(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(config_path, [_position("ABC_US_EQ")], {"ABC": {**GOOD, "total_debt": 400.0}})

    assert (
        "  ABC (ABC_US_EQ): FAIL, debt is 40.00% of market cap, AAOIFI limit is 30%"
        in capsys.readouterr().out
    )


def test_review_reason_for_older_interest_income_in_strict_mode(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # the first ratio reason is the debt line, which passed, so it mustn't be picked
    _run(config_path, [_position("AAPL_US_EQ")], {"AAPL": {**GOOD, "interest_income_year": 2023}})

    assert (
        "  AAPL (AAPL_US_EQ): FAIL, interest income isn't in the latest report, check by hand"
        in capsys.readouterr().out
    )


def test_unconverted_ticker_is_not_checked(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    get = FakeGet({"MSFT": GOOD})

    code = main(
        ["portfolio", "--config", str(config_path)],
        get=get,
        make_client=lambda: FakeClient([_position("MSFT_US_EQ"), _position("SAPd_EQ", 2.0)]),
    )

    out = capsys.readouterr().out
    assert code == 1
    assert [ticker for ticker, _ in get.calls] == ["MSFT"]
    assert "\nNot checked\n  SAPd_EQ, quantity 2: couldn't convert ticker, check by hand\n" in out
    assert "  SAPd_EQ: not checked, couldn't convert ticker, check by hand" in out
    assert out.endswith("2 holdings: 1 pass, 0 fail, 1 not checked\n")


def test_position_without_ticker_is_not_checked(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(config_path, [_position(None, None)], {})

    out = capsys.readouterr().out
    assert code == 1
    assert "  unknown ticker, quantity unknown: couldn't convert ticker" in out
    assert out.endswith("1 holding: 0 pass, 0 fail, 1 not checked\n")


def test_fund(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = _run(config_path, [_position("IGDAl_EQ", 12.5)], {"IGDA.L": ETF})

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("IGDA.L (IGDAl_EQ), quantity 12.5\nIGDA.L: PASS (compliant)\n")
    assert "  fund (ETF)\n" in out
    assert "  purification: check the fund's own reports" in out
    assert out.endswith("1 holding: 1 pass, 0 fail, 0 not checked\n")


def test_unapproved_fund_fails_in_strict_mode(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(config_path, [_position("VUSAl_EQ")], {"VUSA.L": ETF})

    assert code == 1
    assert (
        "  VUSA.L (VUSAl_EQ): FAIL, fund: check its Sharia certification" in capsys.readouterr().out
    )


def test_fractional_quantity(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(config_path, [_position("AAPL_US_EQ", 0.0123456789)], {"AAPL": GOOD})

    assert "AAPL (AAPL_US_EQ), quantity 0.012346\n" in capsys.readouterr().out


def test_empty_portfolio(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = _run(config_path, [], {})

    assert code == 0
    assert capsys.readouterr().out == "no open positions\n"


def test_missing_credentials_exits_2(
    config_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("T212_API_SECRET", SECRET)
    monkeypatch.setenv("T212_ENV", "demo")

    code = main(
        ["portfolio", "--config", str(config_path)],
        get=FakeGet({}),
        make_client=partial(T212Client.from_env, load_env_file=False),
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err.startswith("trading 212 error: missing T212_API_KEY")
    assert captured.err.count("\n") == 1
    assert SECRET not in captured.err


def test_api_error_exits_2_and_closes_client(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeClient(error=T212APIError("Trading 212 returned 500 for /api/v0/equity/positions"))

    code = main(["portfolio", "--config", str(config_path)], make_client=lambda: client)

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err == (
        "trading 212 error: Trading 212 returned 500 for /api/v0/equity/positions\n"
    )
    assert client.closed


def test_client_closed_after_success(config_path: Path) -> None:
    client = FakeClient([_position("MSFT_US_EQ")])

    main(
        ["portfolio", "--config", str(config_path)],
        get=FakeGet({"MSFT": GOOD}),
        make_client=lambda: client,
    )

    assert client.closed


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "relaxed"},
        {"excluded_sectors": ["alchohol"]},
    ],
    ids=["bad-config", "sector-typo"],
)
def test_config_problem_exits_2_before_contacting_trading_212(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: dict[str, Any]
) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"].update(change)
    built: list[bool] = []

    def make_client() -> FakeClient:
        built.append(True)
        return FakeClient()

    code = main(
        ["portfolio", "--config", str(_write_config(tmp_path, data))], make_client=make_client
    )

    assert code == 2
    assert capsys.readouterr().out == ""
    assert built == []


FTSE = {
    "denominator": "total_assets",
    "max_debt": 0.33333,
    "max_cash": 0.33333,
    "max_receivables_and_cash": 0.50,
    "max_impermissible_income": 0.05,
}


def test_compare(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["methodologies"]["ftse"] = FTSE
    # fails AAOIFI (the one picked in the config) on debt, passes FTSE
    company = {**GOOD, "total_debt": 400.0}

    code = _run(
        _write_config(tmp_path, data), [_position("ABC_US_EQ")], {"ABC": company}, "--compare"
    )

    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith("ABC (ABC_US_EQ), quantity 1\nABC\n")
    assert "  AAOIFI: FAIL (excluded)" in out
    assert "  FTSE: PASS (compliant)" in out
    assert "passes under 1 of 2 standards" in out
    assert "  ABC (ABC_US_EQ): FAIL, debt is 40.00% of market cap, AAOIFI limit is 30%" in out
    assert out.endswith("1 holding: 0 pass, 1 fail, 0 not checked\n")


def test_refresh_is_passed_on(config_path: Path) -> None:
    get = FakeGet({"MSFT": GOOD})

    main(
        ["portfolio", "--refresh", "--config", str(config_path)],
        get=get,
        make_client=lambda: FakeClient([_position("MSFT_US_EQ")]),
    )

    assert get.calls[0][1].get("refresh") is True


def test_no_money_values_printed(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    position = Position(
        ticker="MSFT_US_EQ", quantity=2.0, average_price=321.5, current_price=987.25, currency="USD"
    )

    main(
        ["portfolio", "--config", str(config_path)],
        get=FakeGet({"MSFT": GOOD}),
        make_client=lambda: FakeClient([position]),
    )

    out = capsys.readouterr().out
    assert "321.5" not in out
    assert "987.25" not in out
    assert "USD" not in out
