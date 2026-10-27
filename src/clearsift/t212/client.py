from __future__ import annotations

import os
import time
from collections.abc import Callable
from types import TracebackType
from typing import Any
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

from clearsift.t212.models import AccountSummary, Dividend, Order, Position

BASE_URLS: dict[str, str] = {
    "demo": "https://demo.trading212.com/api/v0",
    "live": "https://live.trading212.com/api/v0",
}

# the API's own maximum page size
_PAGE_SIZE = 50
# a cursor that keeps pointing at itself would otherwise loop forever
_MAX_PAGES = 1000
_MAX_RETRIES = 3
# used when a 429 doesn't say when the limit resets
_DEFAULT_RETRY_SECONDS = 5.0
_MAX_RETRY_SECONDS = 60.0


class T212Error(Exception):
    """Something went wrong talking to Trading 212."""


class T212ConfigError(T212Error):
    """The credentials or environment settings are missing or wrong."""


class T212APIError(T212Error):
    """Trading 212 sent back an error or something we can't read."""


class T212RateLimitError(T212APIError):
    """Trading 212 kept saying we're sending too many requests."""


class T212Client:
    """A read-only Trading 212 client with no way to place, change or cancel anything."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        env: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
    ) -> None:
        if env not in BASE_URLS:
            raise T212ConfigError("T212_ENV must be 'demo' or 'live'")
        if not api_key or not api_secret:
            raise T212ConfigError("the Trading 212 API key and secret can't be empty")
        self.env = env
        base = urlsplit(BASE_URLS[env])
        self._origin = f"{base.scheme}://{base.netloc}"
        self._sleep = sleep
        self._now = now
        # the key and secret only live inside httpx's auth, so they don't end up in a repr
        self._http = httpx.Client(
            base_url=BASE_URLS[env],
            auth=httpx.BasicAuth(api_key, api_secret),
            transport=transport,
            timeout=10.0,
            headers={"Accept": "application/json"},
        )

    @classmethod
    def from_env(
        cls,
        *,
        load_env_file: bool = True,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
    ) -> T212Client:
        """Build a client from T212_API_KEY, T212_API_SECRET and T212_ENV."""
        if load_env_file:
            load_dotenv()
        names = ("T212_API_KEY", "T212_API_SECRET", "T212_ENV")
        # only ever say which ones are missing, never what the others hold
        missing = [name for name in names if not os.environ.get(name, "").strip()]
        if missing:
            raise T212ConfigError(
                f"missing {', '.join(missing)}, set them in .env (see .env.example)"
            )
        return cls(
            os.environ["T212_API_KEY"].strip(),
            os.environ["T212_API_SECRET"].strip(),
            os.environ["T212_ENV"].strip().lower(),
            transport=transport,
            sleep=sleep,
            now=now,
        )

    def account_summary(self) -> AccountSummary:
        """Get the account's cash and total value."""
        return AccountSummary.from_api(self._get_dict("/equity/account/summary"))

    def positions(self) -> list[Position]:
        """Get every open position."""
        data = self._get("/equity/positions")
        if not isinstance(data, list):
            raise T212APIError("Trading 212 sent positions in a shape we don't recognise")
        return [Position.from_api(item) for item in data if isinstance(item, dict)]

    def orders(self) -> list[Order]:
        """Get the full order history, every page of it."""
        return [Order.from_api(item) for item in self._all_pages("/equity/history/orders")]

    def dividends(self) -> list[Dividend]:
        """Get the full dividend history, every page of it."""
        return [Dividend.from_api(item) for item in self._all_pages("/equity/history/dividends")]

    def close(self) -> None:
        """Close the connection."""
        self._http.close()

    def __enter__(self) -> T212Client:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _all_pages(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        url: str = path
        # the next page link already carries the limit and cursor
        params: dict[str, Any] | None = {"limit": _PAGE_SIZE}
        for _ in range(_MAX_PAGES):
            data = self._get_dict(url, params)
            page = data.get("items")
            if not isinstance(page, list):
                raise T212APIError(f"Trading 212 sent a page from {path} without any items")
            items += [item for item in page if isinstance(item, dict)]
            next_path = data.get("nextPagePath")
            if not next_path:
                return items
            url, params = self._next_page_url(next_path), None
        raise T212APIError(f"gave up on {path} after {_MAX_PAGES} pages")

    def _next_page_url(self, next_path: Any) -> str:
        # this request carries our credentials, so only follow a plain path on the same
        # host. A full URL could send them somewhere else
        parts = urlsplit(next_path) if isinstance(next_path, str) else None
        if parts is None or parts.scheme or parts.netloc or not next_path.startswith("/"):
            raise T212APIError("Trading 212 sent a next page link we won't follow")
        return self._origin + next_path

    def _get_dict(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self._get(url, params)
        if not isinstance(data, dict):
            raise T212APIError(f"Trading 212 sent {url} in a shape we don't recognise")
        return data

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        # GET only. Nothing in this client should ever be able to change the account
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._http.get(url, params=params)
            except httpx.HTTPError as exc:
                raise T212APIError(f"couldn't reach Trading 212: {type(exc).__name__}") from exc
            if response.status_code != 429:
                break
            if attempt == _MAX_RETRIES:
                raise T212RateLimitError(
                    f"Trading 212 is still rate limiting after {_MAX_RETRIES} retries, "
                    "try again in a minute"
                )
            self._sleep(self._retry_delay(response))

        if response.is_error:
            raise T212APIError(_error_message(response.status_code, response.url.path))
        try:
            return response.json()
        except ValueError as exc:
            raise T212APIError(f"Trading 212 sent something that isn't JSON for {url}") from exc

    def _retry_delay(self, response: httpx.Response) -> float:
        try:
            reset = float(response.headers["x-ratelimit-reset"])
        except (KeyError, ValueError):
            return _DEFAULT_RETRY_SECONDS
        # at least a second, so a reset time that's just passed doesn't hammer the API
        return min(max(reset - self._now(), 1.0), _MAX_RETRY_SECONDS)


def _error_message(status: int, path: str) -> str:
    if status == 401:
        return "Trading 212 rejected the API key or secret (401), check they're right"
    if status == 403:
        return f"the API key isn't allowed to read {path} (403), check its permissions"
    return f"Trading 212 returned {status} for {path}"
