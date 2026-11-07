from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from clearsift.data.fetcher import clean_number

# kept out of cache.db, which wipes its table whenever the financials columns change
DEFAULT_PRICES_PATH = Path("data/prices.db")

# prices are only for the chart, so a day old is fine
MAX_PRICE_AGE = timedelta(days=1)

# bump this whenever the table changes, so old cache files get cleared out
_SCHEMA_VERSION = 1

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS closes (
    ticker TEXT PRIMARY KEY,
    closes TEXT NOT NULL,
    fetched_at TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class PricePoint:
    day: date
    close: float


def fetch_closes(ticker: str) -> list[PricePoint]:
    """Get a year of daily closing prices from yfinance, oldest first."""
    try:
        # not adjusted, so the chart shows the price people actually paid that day
        history = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=False)
    except Exception:
        # fail closed: no prices means no chart, never made-up ones
        return []
    if not isinstance(history, pd.DataFrame) or history.empty or "Close" not in history:
        return []

    points: dict[date, float] = {}
    try:
        for stamp, raw in history["Close"].items():
            close = clean_number(raw)
            # a price of zero or below is bad data, not a real close
            if close is None or close <= 0:
                continue
            points[pd.Timestamp(stamp).date()] = close
    except Exception:
        return []
    return [PricePoint(day, close) for day, close in sorted(points.items())]


def save_closes(
    ticker: str,
    closes: list[PricePoint],
    fetched_at: datetime,
    db_path: Path = DEFAULT_PRICES_PATH,
) -> None:
    """Save a ticker's closing prices to the cache, replacing any older copy."""
    # without a timezone we can't tell how old the prices really are
    if fetched_at.tzinfo is None:
        raise ValueError("fetched_at must have a timezone")
    payload = json.dumps([[p.day.isoformat(), p.close] for p in closes])
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO closes (ticker, closes, fetched_at) VALUES (?, ?, ?)",
            (ticker, payload, fetched_at.astimezone(UTC).isoformat()),
        )


def load_closes(
    ticker: str,
    *,
    db_path: Path = DEFAULT_PRICES_PATH,
    now: datetime | None = None,
    max_age: timedelta = MAX_PRICE_AGE,
) -> list[PricePoint] | None:
    """Return a ticker's cached closing prices, or None if they're missing or stale."""
    if not db_path.exists():
        return None
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT closes, fetched_at FROM closes WHERE ticker = ?", (ticker,)
        ).fetchone()
    if row is None:
        return None

    payload, raw_fetched_at = row
    try:
        fetched_at = datetime.fromisoformat(raw_fetched_at)
        points = [_point(day, close) for day, close in json.loads(payload)]
    except (TypeError, ValueError):
        # fail closed: a broken row counts as missing and gets fetched again
        return None
    if fetched_at.tzinfo is None or not points:
        return None
    age = (now or datetime.now(UTC)) - fetched_at
    # a date in the future means the clock or the data is off, so don't trust it
    if age < timedelta(0) or age >= max_age:
        return None
    return points


def get_closes(
    ticker: str,
    *,
    db_path: Path = DEFAULT_PRICES_PATH,
    fetch: Callable[[str], list[PricePoint]] = fetch_closes,
    now: datetime | None = None,
    refresh: bool = False,
) -> list[PricePoint]:
    """Return a ticker's closing prices from the cache, or fetch and save fresh ones."""
    if not refresh:
        cached = load_closes(ticker, db_path=db_path, now=now)
        if cached is not None:
            return cached

    fresh = fetch(ticker)
    # nothing back usually means yfinance fell over, so don't cache it or we'd be stuck with it
    if fresh:
        save_closes(ticker, fresh, now or datetime.now(UTC), db_path)
    return fresh


def _point(day: str, raw: object) -> PricePoint:
    close = clean_number(raw)
    # someone could have edited the file, so check it the same way as fresh prices
    if close is None or close <= 0:
        raise ValueError("bad cached close")
    return PricePoint(date.fromisoformat(day), close)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # an old cache file might have the wrong columns. It's only a cache, so start again
    if conn.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
        conn.execute("DROP TABLE IF EXISTS closes")
        conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
    conn.execute(_CREATE_TABLE)
    return conn
