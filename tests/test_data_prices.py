import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from clearsift.data import prices
from clearsift.data.prices import (
    PricePoint,
    fetch_closes,
    get_closes,
    load_closes,
    save_closes,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
POINTS = [PricePoint(date(2026, 5, 28), 101.5), PricePoint(date(2026, 5, 29), 102.25)]


class FakeTicker:
    """Stands in for yf.Ticker, handing back whatever history it was given."""

    def __init__(self, history: Any = None, error: Exception | None = None) -> None:
        self._history = history
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def history(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._history


def _use(monkeypatch: pytest.MonkeyPatch, fake: FakeTicker) -> None:
    monkeypatch.setattr(prices.yf, "Ticker", lambda ticker: fake)


def _history(closes: dict[str, Any]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(day, tz="America/New_York") for day in closes])
    return pd.DataFrame({"Close": list(closes.values())}, index=index)


class FakeFetch:
    """Stands in for fetch_closes and counts how often it's called."""

    def __init__(self, result: list[PricePoint]) -> None:
        self.result = result
        self.calls: list[str] = []

    def __call__(self, ticker: str) -> list[PricePoint]:
        self.calls.append(ticker)
        return self.result


# fetch_closes


def test_fetch_closes_oldest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeTicker(_history({"2026-05-29": 102.25, "2026-05-28": 101.5}))
    _use(monkeypatch, fake)

    assert fetch_closes("AAPL") == POINTS
    assert fake.calls == [{"period": "1y", "interval": "1d", "auto_adjust": False}]


def test_fetch_closes_drops_bad_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    history = _history(
        {
            "2026-05-26": float("nan"),
            "2026-05-27": float("inf"),
            "2026-05-28": 101.5,
            "2026-05-29": 0.0,
            "2026-05-30": -3.0,
        }
    )
    _use(monkeypatch, FakeTicker(history))

    assert fetch_closes("AAPL") == [PricePoint(date(2026, 5, 28), 101.5)]


def test_fetch_closes_yfinance_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, FakeTicker(error=RuntimeError("no internet")))

    assert fetch_closes("AAPL") == []


@pytest.mark.parametrize(
    "history",
    [None, pd.DataFrame(), pd.DataFrame({"Open": [1.0]}), "not a frame"],
)
def test_fetch_closes_nothing_useful(monkeypatch: pytest.MonkeyPatch, history: Any) -> None:
    _use(monkeypatch, FakeTicker(history))

    assert fetch_closes("AAPL") == []


def test_fetch_closes_ticker_falls_over(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(ticker: str) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(prices.yf, "Ticker", broken)

    assert fetch_closes("AAPL") == []


# save_closes and load_closes


def test_save_then_load(tmp_path: Path) -> None:
    db = tmp_path / "prices.db"
    save_closes("AAPL", POINTS, NOW, db)

    assert load_closes("AAPL", db_path=db, now=NOW + timedelta(hours=23)) == POINTS


def test_save_needs_a_timezone(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_closes("AAPL", POINTS, datetime(2026, 6, 1), tmp_path / "prices.db")


def test_load_no_file(tmp_path: Path) -> None:
    assert load_closes("AAPL", db_path=tmp_path / "prices.db", now=NOW) is None


def test_load_unknown_ticker(tmp_path: Path) -> None:
    db = tmp_path / "prices.db"
    save_closes("AAPL", POINTS, NOW, db)

    assert load_closes("MSFT", db_path=db, now=NOW) is None


def test_load_a_day_old_is_stale(tmp_path: Path) -> None:
    db = tmp_path / "prices.db"
    save_closes("AAPL", POINTS, NOW, db)

    assert load_closes("AAPL", db_path=db, now=NOW + timedelta(days=1)) is None


def test_load_future_date_is_missing(tmp_path: Path) -> None:
    db = tmp_path / "prices.db"
    save_closes("AAPL", POINTS, NOW + timedelta(hours=1), db)

    assert load_closes("AAPL", db_path=db, now=NOW) is None


@pytest.mark.parametrize(
    ("payload", "fetched_at"),
    [
        ("not json", NOW.isoformat()),
        ('[["2026-05-28", "NaN"]]', NOW.isoformat()),
        ('[["2026-05-28", -1.0]]', NOW.isoformat()),
        ('[["not a date", 1.0]]', NOW.isoformat()),
        ('[["2026-05-28"]]', NOW.isoformat()),
        ("[]", NOW.isoformat()),
        ('[["2026-05-28", 1.0]]', "yesterday"),
        ('[["2026-05-28", 1.0]]', "2026-06-01T12:00:00"),
    ],
)
def test_load_broken_row_is_missing(tmp_path: Path, payload: str, fetched_at: str) -> None:
    db = tmp_path / "prices.db"
    save_closes("AAPL", POINTS, NOW, db)
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(
            "UPDATE closes SET closes = ?, fetched_at = ? WHERE ticker = 'AAPL'",
            (payload, fetched_at),
        )

    assert load_closes("AAPL", db_path=db, now=NOW) is None


def test_old_schema_gets_wiped(tmp_path: Path) -> None:
    db = tmp_path / "prices.db"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("CREATE TABLE closes (ticker TEXT, price REAL)")

    save_closes("AAPL", POINTS, NOW, db)

    assert load_closes("AAPL", db_path=db, now=NOW) == POINTS


# get_closes


def test_get_fetches_then_uses_the_cache(tmp_path: Path) -> None:
    db = tmp_path / "prices.db"
    fetch = FakeFetch(POINTS)

    first = get_closes("AAPL", db_path=db, fetch=fetch, now=NOW)
    second = get_closes("AAPL", db_path=db, fetch=fetch, now=NOW + timedelta(hours=1))

    assert first == second == POINTS
    assert fetch.calls == ["AAPL"]


def test_get_refetches_when_stale(tmp_path: Path) -> None:
    db = tmp_path / "prices.db"
    fetch = FakeFetch(POINTS)

    get_closes("AAPL", db_path=db, fetch=fetch, now=NOW)
    get_closes("AAPL", db_path=db, fetch=fetch, now=NOW + timedelta(days=1))

    assert fetch.calls == ["AAPL", "AAPL"]


def test_get_refresh_skips_the_cache(tmp_path: Path) -> None:
    db = tmp_path / "prices.db"
    fetch = FakeFetch(POINTS)

    get_closes("AAPL", db_path=db, fetch=fetch, now=NOW)
    get_closes("AAPL", db_path=db, fetch=fetch, now=NOW, refresh=True)

    assert fetch.calls == ["AAPL", "AAPL"]


def test_get_does_not_cache_nothing(tmp_path: Path) -> None:
    db = tmp_path / "prices.db"
    fetch = FakeFetch([])

    assert get_closes("AAPL", db_path=db, fetch=fetch, now=NOW) == []
    assert load_closes("AAPL", db_path=db, now=NOW) is None
