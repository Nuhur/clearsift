from functools import partial
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

import clearsift.t212.client as client_module
from clearsift.api import create_app
from clearsift.api.schemas import holding_out
from clearsift.config import load_config
from clearsift.data.models import CompanyFinancials
from clearsift.portfolio import NOT_CONVERTED, screen_holdings
from clearsift.t212.client import T212APIError, T212Client
from clearsift.t212.models import Position

# made up, so nothing real can leak from a test
KEY = "fake-key-123"
SECRET = "fake-secret-456"
BODY = "fake-body-789"

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
        "approved_funds": [],
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
DATA = {"MSFT": GOOD, "MO": TOBACCO}

MSFT = Position("MSFT_US_EQ", 1.5, 300.0, 410.25, "USD")
MO = Position("MO_US_EQ", 10.0, 45.0, 52.5, "USD")
# not a ticker format we know how to convert
ODD = Position("WEIRD", 2.0, 1.0, 1.5, "GBP")


@pytest.fixture(autouse=True)
def no_real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("T212_API_KEY", "T212_API_SECRET", "T212_ENV"):
        monkeypatch.delenv(name, raising=False)

    # no test should ever read the real .env, so make it blow up if one tries
    def refuse(*args: Any, **kwargs: Any) -> bool:
        raise AssertionError("a test tried to load a .env file")

    monkeypatch.setattr(client_module, "load_dotenv", refuse)


class FakeGet:
    """Stands in for get_financials, with made-up data for each ticker."""

    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.data = data
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, ticker: str, **kwargs: Any) -> CompanyFinancials:
        self.calls.append((ticker, kwargs))
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


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    return path


def _client(tmp_path: Path, make_client: Any, get: Any = None) -> TestClient:
    app = create_app(_write(tmp_path), get=get or FakeGet(DATA), make_client=make_client)
    return TestClient(app, raise_server_exceptions=False)


def _real_client(handler: Any) -> T212Client:
    return T212Client(KEY, SECRET, "demo", transport=httpx.MockTransport(handler))


def _assert_nothing_leaked(response: httpx.Response) -> None:
    for secret in (KEY, SECRET, BODY):
        assert secret not in response.text
    assert "Traceback" not in response.text


# holding_out


def test_holding_out_hides_values_by_default(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path)).screening
    [holding] = screen_holdings([MSFT], config, get=FakeGet(DATA))

    out = holding_out(holding, compare=False, show_values=False)

    assert out.t212_ticker == "MSFT_US_EQ"
    assert out.yahoo_ticker == "MSFT"
    assert out.title == "MSFT (MSFT_US_EQ)"
    assert out.verdict is not None and out.verdict.kind == "verdict"
    assert out.message is None
    assert out.values is None


def test_holding_out_with_values(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path)).screening
    [holding] = screen_holdings([MSFT], config, get=FakeGet(DATA))

    out = holding_out(holding, compare=False, show_values=True)

    assert out.values is not None
    assert out.values.model_dump() == {
        "quantity": 1.5,
        "average_price": 300.0,
        "current_price": 410.25,
        "currency": "USD",
    }


def test_holding_out_compare(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path)).screening
    [holding] = screen_holdings([MSFT], config, compare=True, get=FakeGet(DATA))

    out = holding_out(holding, compare=True, show_values=False)

    assert out.verdict is not None and out.verdict.kind == "comparison"
    assert out.verdict.methodology == "AAOIFI"


def test_holding_out_not_converted(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path)).screening
    [holding] = screen_holdings([ODD], config, get=FakeGet(DATA))

    out = holding_out(holding, compare=False, show_values=False)

    assert out.verdict is None
    assert out.yahoo_ticker is None
    assert out.message == NOT_CONVERTED


# /api/portfolio


def test_portfolio(tmp_path: Path) -> None:
    fake = FakeClient([MSFT, MO, ODD])
    client = _client(tmp_path, lambda: fake)

    response = client.get("/api/portfolio")

    assert response.status_code == 200
    body = response.json()
    assert [h["title"] for h in body["holdings"]] == ["MSFT (MSFT_US_EQ)", "MO (MO_US_EQ)", "WEIRD"]
    assert [h["verdict"] and h["verdict"]["passes"] for h in body["holdings"]] == [
        True,
        False,
        None,
    ]
    assert body["summary"] == "3 holdings: 1 pass, 1 fail, 1 not checked"
    assert body["review"][0].startswith("MO (MO_US_EQ): FAIL, ")
    assert body["review"][1] == f"WEIRD: not checked, {NOT_CONVERTED}"
    assert fake.closed


def test_portfolio_hides_values_unless_asked(tmp_path: Path) -> None:
    client = _client(tmp_path, lambda: FakeClient([MSFT]))

    response = client.get("/api/portfolio")

    [holding] = response.json()["holdings"]
    assert holding["values"] is None
    # the prices and quantity shouldn't show up anywhere else either
    for number in ("1.5", "300", "410.25"):
        assert number not in response.text


def test_portfolio_show_values(tmp_path: Path) -> None:
    client = _client(tmp_path, lambda: FakeClient([MSFT]))

    response = client.get("/api/portfolio", params={"show_values": "true"})

    [holding] = response.json()["holdings"]
    assert holding["values"] == {
        "quantity": 1.5,
        "average_price": 300.0,
        "current_price": 410.25,
        "currency": "USD",
    }


def test_portfolio_compare(tmp_path: Path) -> None:
    client = _client(tmp_path, lambda: FakeClient([MSFT]))

    response = client.get("/api/portfolio", params={"compare": "true"})

    [holding] = response.json()["holdings"]
    assert holding["verdict"]["kind"] == "comparison"
    assert [s["methodology"] for s in holding["verdict"]["standards"]] == ["AAOIFI", "FTSE"]


def test_portfolio_refresh_reaches_get(tmp_path: Path) -> None:
    get = FakeGet(DATA)
    client = _client(tmp_path, lambda: FakeClient([MSFT]), get=get)

    client.get("/api/portfolio", params={"refresh": "true"})

    assert get.calls[0][1]["refresh"] is True


def test_portfolio_no_positions(tmp_path: Path) -> None:
    client = _client(tmp_path, lambda: FakeClient([]))

    response = client.get("/api/portfolio")

    assert response.status_code == 200
    assert response.json() == {
        "holdings": [],
        "summary": "0 holdings: 0 pass, 0 fail, 0 not checked",
        "review": [],
    }


def test_portfolio_missing_credentials(tmp_path: Path) -> None:
    client = _client(tmp_path, partial(T212Client.from_env, load_env_file=False))

    response = client.get("/api/portfolio")

    assert response.status_code == 500
    assert response.json()["message"].startswith("Trading 212 error: missing T212_API_KEY")


def test_portfolio_api_error_leaks_nothing(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"{BODY} {KEY} {SECRET}")

    fake = _real_client(handler)
    client = _client(tmp_path, lambda: fake)

    response = client.get("/api/portfolio")

    assert response.status_code == 502
    assert response.json() == {
        "message": "Trading 212 error: Trading 212 returned 500 for /api/v0/equity/positions"
    }
    _assert_nothing_leaked(response)


def test_portfolio_bad_key_leaks_nothing(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=BODY)

    fake = _real_client(handler)
    client = _client(tmp_path, lambda: fake)

    response = client.get("/api/portfolio")

    assert response.status_code == 502
    assert "401" in response.json()["message"]
    _assert_nothing_leaked(response)


def test_portfolio_unreachable_leaks_nothing(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"{KEY} {SECRET} {BODY}")

    fake = _real_client(handler)
    client = _client(tmp_path, lambda: fake)

    response = client.get("/api/portfolio")

    assert response.status_code == 502
    assert response.json() == {
        "message": "Trading 212 error: couldn't reach Trading 212: ConnectError"
    }
    _assert_nothing_leaked(response)


def test_portfolio_t212_error_closes_client(tmp_path: Path) -> None:
    fake = FakeClient(error=T212APIError("Trading 212 returned 503 for /x"))
    client = _client(tmp_path, lambda: fake)

    response = client.get("/api/portfolio")

    assert response.status_code == 502
    assert fake.closed


def test_portfolio_crash_leaks_nothing(tmp_path: Path) -> None:
    fake = FakeClient(error=RuntimeError(f"{KEY} {SECRET}"))
    client = _client(tmp_path, lambda: fake)

    response = client.get("/api/portfolio")

    assert response.status_code == 500
    assert response.json() == {"message": "something went wrong"}
    _assert_nothing_leaked(response)


def test_portfolio_screening_error(tmp_path: Path) -> None:
    def picky(ticker: str, **kwargs: Any) -> CompanyFinancials:
        raise ValueError("bad mapping")

    client = _client(tmp_path, lambda: FakeClient([MSFT]), get=picky)

    response = client.get("/api/portfolio")

    assert response.status_code == 500
    assert response.json() == {"message": "screening error: bad mapping"}
