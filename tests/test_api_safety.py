from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Mount, Route, WebSocketRoute

from clearsift.api import create_app
from clearsift.api.app import ALLOWED_ORIGINS, HOST, PORT, serve


def no_client() -> Any:
    raise AssertionError("these tests should never talk to Trading 212")


def no_get(ticker: str, **kwargs: Any) -> Any:
    raise AssertionError("these tests should never fetch data")


@pytest.fixture
def app(tmp_path: Path) -> Any:
    # the config is only read per request, so it doesn't need to exist for these
    return create_app(tmp_path / "config.yaml", get=no_get, make_client=no_client)


def test_every_route_is_get_only(app: Any) -> None:
    # if this fails, someone added a route that could change something. Nothing in
    # clearsift should place orders or edit anything through the API
    for route in app.routes:
        assert not isinstance(route, (Mount, WebSocketRoute)), route
        assert isinstance(route, Route), route
        assert route.methods is not None
        assert route.methods <= {"GET", "HEAD"}, f"{route.path} allows {route.methods}"


def test_every_api_route_lives_under_api(app: Any) -> None:
    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert paths == {"/api/health", "/api/screen", "/api/stocks/{ticker}", "/api/portfolio"}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/api/screen", "/api/portfolio", "/api/stocks/MSFT"])
def test_writes_are_refused(app: Any, method: str, path: str) -> None:
    response = TestClient(app).request(method, path)

    assert response.status_code == 405
    assert response.json() == {"message": "Method Not Allowed"}


def test_cors_allows_the_react_app(app: Any) -> None:
    response = TestClient(app).get("/api/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize(
    "origin", ["http://evil.example", "http://localhost:3000", "http://127.0.0.1:5173"]
)
def test_cors_refuses_other_sites(app: Any, origin: str) -> None:
    response = TestClient(app).get("/api/health", headers={"Origin": origin})

    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_only_allows_get(app: Any) -> None:
    response = TestClient(app).options(
        "/api/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-methods"] == "GET"


def test_cors_preflight_refuses_post(app: Any) -> None:
    response = TestClient(app).options(
        "/api/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 400


def test_allowed_origins() -> None:
    assert ALLOWED_ORIGINS == ("http://localhost:5173",)


def test_serve_binds_to_this_machine_only(tmp_path: Path) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []

    def fake_run(app: Any, **kwargs: Any) -> None:
        calls.append((app, kwargs))

    serve(tmp_path / "config.yaml", get=no_get, make_client=no_client, run=fake_run)

    [(app, kwargs)] = calls
    assert kwargs == {"host": "127.0.0.1", "port": 8000}
    assert (HOST, PORT) == ("127.0.0.1", 8000)
    assert any(getattr(r, "path", None) == "/api/health" for r in app.routes)
