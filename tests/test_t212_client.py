import base64
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

import clearsift.t212.client as client_module
from clearsift.t212.client import (
    T212APIError,
    T212Client,
    T212ConfigError,
    T212RateLimitError,
)
from clearsift.t212.models import AccountSummary, Dividend, Order, Position

# made up, so nothing real can leak from a test
KEY = "fake-key-123"
SECRET = "fake-secret-456"
NOW = 1_000_000.0


@pytest.fixture(autouse=True)
def no_real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("T212_API_KEY", "T212_API_SECRET", "T212_ENV"):
        monkeypatch.delenv(name, raising=False)

    # no test should ever read the real .env, so make it blow up if one tries
    def refuse(*args: Any, **kwargs: Any) -> bool:
        raise AssertionError("a test tried to load a .env file")

    monkeypatch.setattr(client_module, "load_dotenv", refuse)


class FakeAPI:
    """Stands in for Trading 212, handing out canned responses per path in order."""

    def __init__(self, routes: dict[str, list[httpx.Response]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.routes[request.url.path].pop(0)


class Sleeps:
    """Records how long the client asked to wait, without waiting."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _client(
    api: Callable[[httpx.Request], httpx.Response], env: str = "demo", sleeps: Sleeps | None = None
) -> T212Client:
    return T212Client(
        KEY,
        SECRET,
        env,
        transport=httpx.MockTransport(api),
        sleep=sleeps or Sleeps(),
        now=lambda: NOW,
    )


def _set_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for name, value in values.items():
        monkeypatch.setenv(name, value)


SUMMARY = {
    "id": 123,
    "currency": "GBP",
    "totalValue": 1500.0,
    "cash": {"availableToTrade": 250.5, "inPies": 0, "reservedForOrders": 0},
    "investments": {"currentValue": 1249.5, "totalCost": 1100.0},
}
POSITION = {
    "instrument": {"ticker": "AAPL_US_EQ", "currency": "USD", "name": "Apple"},
    "quantity": 3.5,
    "averagePricePaid": 180.25,
    "currentPrice": 230.0,
}
ORDER = {
    "order": {
        "id": 42,
        "ticker": "AAPL_US_EQ",
        "side": "BUY",
        "status": "FILLED",
        "quantity": 2,
        "filledQuantity": 2,
        "currency": "USD",
        "createdAt": "2026-10-01T14:30:00Z",
    },
    "fill": {"price": 230.5, "filledAt": "2026-10-01T14:30:01Z"},
}
DIVIDEND = {
    "ticker": "AAPL_US_EQ",
    "amount": 0.62,
    "currency": "GBP",
    "grossAmountPerShare": 0.25,
    "quantity": 3.5,
    "paidOn": "2026-08-14T00:00:00Z",
}

SUMMARY_PATH = "/api/v0/equity/account/summary"
POSITIONS_PATH = "/api/v0/equity/positions"
ORDERS_PATH = "/api/v0/equity/history/orders"
DIVIDENDS_PATH = "/api/v0/equity/history/dividends"


def _page(items: list[dict[str, Any]], next_path: str | None = None) -> httpx.Response:
    return httpx.Response(200, json={"items": items, "nextPagePath": next_path})


# --- building the client ---


def test_from_env_reads_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, T212_API_KEY=KEY, T212_API_SECRET=SECRET, T212_ENV="demo")

    client = T212Client.from_env(load_env_file=False)

    assert client.env == "demo"


@pytest.mark.parametrize(("env", "host"), [("demo", "demo"), ("LIVE", "live"), (" live ", "live")])
def test_env_picks_base_url(monkeypatch: pytest.MonkeyPatch, env: str, host: str) -> None:
    _set_env(monkeypatch, T212_API_KEY=KEY, T212_API_SECRET=SECRET, T212_ENV=env)
    api = FakeAPI({SUMMARY_PATH: [httpx.Response(200, json=SUMMARY)]})

    T212Client.from_env(load_env_file=False, transport=httpx.MockTransport(api)).account_summary()

    assert str(api.requests[0].url) == f"https://{host}.trading212.com{SUMMARY_PATH}"


def test_missing_credentials_names_them_without_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, T212_API_SECRET=SECRET, T212_ENV="demo")

    with pytest.raises(T212ConfigError) as exc:
        T212Client.from_env(load_env_file=False)

    message = str(exc.value)
    assert "T212_API_KEY" in message
    assert "T212_API_SECRET" not in message
    assert SECRET not in message


def test_blank_credentials_count_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, T212_API_KEY="  ", T212_API_SECRET=SECRET, T212_ENV="demo")

    with pytest.raises(T212ConfigError, match="T212_API_KEY"):
        T212Client.from_env(load_env_file=False)


def test_missing_env_is_an_error_not_a_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, T212_API_KEY=KEY, T212_API_SECRET=SECRET)

    with pytest.raises(T212ConfigError, match="T212_ENV"):
        T212Client.from_env(load_env_file=False)


def test_unknown_env_rejected_without_printing_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, T212_API_KEY=KEY, T212_API_SECRET=SECRET, T212_ENV="production")

    with pytest.raises(T212ConfigError) as exc:
        T212Client.from_env(load_env_file=False)

    assert "'demo' or 'live'" in str(exc.value)
    assert KEY not in str(exc.value)
    assert SECRET not in str(exc.value)


def test_empty_key_rejected() -> None:
    with pytest.raises(T212ConfigError):
        T212Client("", SECRET, "demo")


def test_from_env_without_env_file_reads_no_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # a .env right where we're running, which must be ignored
    (tmp_path / ".env").write_text(
        f"T212_API_KEY={KEY}\nT212_API_SECRET={SECRET}\nT212_ENV=demo\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    calls: list[Any] = []
    monkeypatch.setattr(client_module, "load_dotenv", lambda *a, **kw: calls.append(a))

    with pytest.raises(T212ConfigError):
        T212Client.from_env(load_env_file=False)

    assert calls == []


def test_from_env_loads_env_file_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # pretend to be python-dotenv, so the real .env is never touched
    def fake_load_dotenv(*args: Any, **kwargs: Any) -> bool:
        _set_env(monkeypatch, T212_API_KEY=KEY, T212_API_SECRET=SECRET, T212_ENV="demo")
        return True

    monkeypatch.setattr(client_module, "load_dotenv", fake_load_dotenv)

    assert T212Client.from_env().env == "demo"


def test_secret_not_in_client_repr() -> None:
    client = _client(FakeAPI({}))

    assert SECRET not in repr(client)
    assert all(SECRET not in repr(value) for value in vars(client).values())


# --- endpoints ---


def test_sends_basic_auth() -> None:
    api = FakeAPI({SUMMARY_PATH: [httpx.Response(200, json=SUMMARY)]})

    _client(api).account_summary()

    expected = base64.b64encode(f"{KEY}:{SECRET}".encode()).decode()
    assert api.requests[0].headers["Authorization"] == f"Basic {expected}"


def test_account_summary() -> None:
    api = FakeAPI({SUMMARY_PATH: [httpx.Response(200, json=SUMMARY)]})

    assert _client(api).account_summary() == AccountSummary(
        currency="GBP", cash=250.5, total_value=1500.0, investments_value=1249.5
    )


def test_positions() -> None:
    api = FakeAPI({POSITIONS_PATH: [httpx.Response(200, json=[POSITION])]})

    assert _client(api).positions() == [
        Position(
            ticker="AAPL_US_EQ",
            quantity=3.5,
            average_price=180.25,
            current_price=230.0,
            currency="USD",
        )
    ]


def test_positions_in_odd_shape_raises() -> None:
    api = FakeAPI({POSITIONS_PATH: [httpx.Response(200, json={"items": []})]})

    with pytest.raises(T212APIError):
        _client(api).positions()


def test_orders() -> None:
    api = FakeAPI({ORDERS_PATH: [_page([ORDER])]})

    assert _client(api).orders() == [
        Order(
            id=42,
            ticker="AAPL_US_EQ",
            side="BUY",
            status="FILLED",
            quantity=2.0,
            filled_quantity=2.0,
            fill_price=230.5,
            created_at=datetime(2026, 10, 1, 14, 30, tzinfo=UTC),
            filled_at=datetime(2026, 10, 1, 14, 30, 1, tzinfo=UTC),
            currency="USD",
        )
    ]


def test_dividends() -> None:
    api = FakeAPI({DIVIDENDS_PATH: [_page([DIVIDEND])]})

    assert _client(api).dividends() == [
        Dividend(
            ticker="AAPL_US_EQ",
            amount=0.62,
            currency="GBP",
            gross_amount_per_share=0.25,
            quantity=3.5,
            paid_on=datetime(2026, 8, 14, tzinfo=UTC),
        )
    ]


# --- pagination ---


def test_orders_follow_every_page() -> None:
    second = {**ORDER, "order": {**ORDER["order"], "id": 43}}
    api = FakeAPI(
        {ORDERS_PATH: [_page([ORDER], f"{ORDERS_PATH}?limit=50&cursor=43"), _page([second])]}
    )

    orders = _client(api).orders()

    assert [order.id for order in orders] == [42, 43]
    assert api.requests[0].url.params["limit"] == "50"
    assert (
        str(api.requests[1].url) == f"https://demo.trading212.com{ORDERS_PATH}?limit=50&cursor=43"
    )


def test_dividends_follow_every_page() -> None:
    api = FakeAPI(
        {
            DIVIDENDS_PATH: [
                _page([DIVIDEND], f"{DIVIDENDS_PATH}?cursor=2"),
                _page([DIVIDEND], f"{DIVIDENDS_PATH}?cursor=3"),
                _page([DIVIDEND]),
            ]
        }
    )

    assert len(_client(api).dividends()) == 3
    assert len(api.requests) == 3


def test_empty_history() -> None:
    api = FakeAPI({DIVIDENDS_PATH: [_page([])]})

    assert _client(api).dividends() == []


@pytest.mark.parametrize(
    "next_path",
    [
        "https://evil.example.com/api/v0/equity/history/orders?cursor=2",
        "//evil.example.com/api/v0/equity/history/orders?cursor=2",
        "api/v0/equity/history/orders?cursor=2",
        123,
    ],
)
def test_next_page_off_our_host_is_refused(next_path: Any) -> None:
    api = FakeAPI({ORDERS_PATH: [_page([ORDER], next_path)]})

    with pytest.raises(T212APIError, match="won't follow"):
        _client(api).orders()

    assert len(api.requests) == 1


def test_page_without_items_raises() -> None:
    api = FakeAPI({ORDERS_PATH: [httpx.Response(200, json={"nextPagePath": None})]})

    with pytest.raises(T212APIError):
        _client(api).orders()


def test_page_that_never_ends_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "_MAX_PAGES", 3)
    looping = f"{ORDERS_PATH}?cursor=1"
    api = FakeAPI({ORDERS_PATH: [_page([ORDER], looping) for _ in range(5)]})

    with pytest.raises(T212APIError, match="gave up"):
        _client(api).orders()

    assert len(api.requests) == 3


# --- rate limits and errors ---


def _rate_limited(reset: float | None = None) -> httpx.Response:
    headers = {} if reset is None else {"x-ratelimit-reset": str(reset)}
    return httpx.Response(429, headers=headers)


def test_429_waits_until_reset_then_retries() -> None:
    api = FakeAPI({SUMMARY_PATH: [_rate_limited(NOW + 3), httpx.Response(200, json=SUMMARY)]})
    sleeps = Sleeps()

    summary = _client(api, sleeps=sleeps).account_summary()

    assert summary.cash == 250.5
    assert sleeps.calls == [3.0]
    assert len(api.requests) == 2


def test_429_without_reset_header_waits_default() -> None:
    api = FakeAPI({SUMMARY_PATH: [_rate_limited(), httpx.Response(200, json=SUMMARY)]})
    sleeps = Sleeps()

    _client(api, sleeps=sleeps).account_summary()

    assert sleeps.calls == [5.0]


@pytest.mark.parametrize(("reset", "expected"), [(NOW + 600, 60.0), (NOW - 10, 1.0)])
def test_429_wait_is_kept_sensible(reset: float, expected: float) -> None:
    api = FakeAPI({SUMMARY_PATH: [_rate_limited(reset), httpx.Response(200, json=SUMMARY)]})
    sleeps = Sleeps()

    _client(api, sleeps=sleeps).account_summary()

    assert sleeps.calls == [expected]


def test_429_gives_up_after_retries() -> None:
    api = FakeAPI({SUMMARY_PATH: [_rate_limited(NOW + 1) for _ in range(4)]})
    sleeps = Sleeps()

    with pytest.raises(T212RateLimitError, match="still rate limiting"):
        _client(api, sleeps=sleeps).account_summary()

    assert len(api.requests) == 4
    assert len(sleeps.calls) == 3


def test_429_on_a_later_page_is_retried() -> None:
    api = FakeAPI(
        {
            ORDERS_PATH: [
                _page([ORDER], f"{ORDERS_PATH}?cursor=2"),
                _rate_limited(NOW + 2),
                _page([ORDER]),
            ]
        }
    )

    assert len(_client(api).orders()) == 2


@pytest.mark.parametrize(
    ("status", "text"),
    [(401, "rejected the API key or secret"), (403, "isn't allowed"), (500, "returned 500")],
)
def test_error_statuses_raise_clearly(status: int, text: str) -> None:
    api = FakeAPI({SUMMARY_PATH: [httpx.Response(status, text="nope")]})

    with pytest.raises(T212APIError, match=text) as exc:
        _client(api).account_summary()

    assert SECRET not in str(exc.value)


def test_non_json_response_raises() -> None:
    api = FakeAPI({SUMMARY_PATH: [httpx.Response(200, text="<html>maintenance</html>")]})

    with pytest.raises(T212APIError, match="isn't JSON"):
        _client(api).account_summary()


def test_network_error_raises_clearly() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(T212APIError, match="couldn't reach Trading 212"):
        _client(unreachable).account_summary()


# --- read-only ---


def test_every_request_is_a_get() -> None:
    api = FakeAPI(
        {
            SUMMARY_PATH: [httpx.Response(200, json=SUMMARY)],
            POSITIONS_PATH: [httpx.Response(200, json=[POSITION])],
            ORDERS_PATH: [_page([ORDER])],
            DIVIDENDS_PATH: [_page([DIVIDEND])],
        }
    )
    client = _client(api)

    client.account_summary()
    client.positions()
    client.orders()
    client.dividends()

    assert [request.method for request in api.requests] == ["GET"] * 4


def test_only_read_methods_are_public() -> None:
    # if this fails, someone added a method. Make sure it can't place, change or cancel
    public = {name for name in dir(T212Client) if not name.startswith("_")}

    assert public == {"from_env", "account_summary", "positions", "orders", "dividends", "close"}


def test_works_as_context_manager() -> None:
    api = FakeAPI({SUMMARY_PATH: [httpx.Response(200, json=SUMMARY)]})

    with _client(api) as client:
        client.account_summary()

    assert client._http.is_closed
