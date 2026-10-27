from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from clearsift.data.fetcher import fetch_financials
from clearsift.data.models import CompanyFinancials

DEFAULT_DB_PATH = Path("data/cache.db")

_FIELDS = (
    "sector",
    "industry",
    "market_cap",
    "total_debt",
    "cash_and_short_term_investments",
    "total_revenue",
    "interest_income",
    "interest_income_revenue",
    "interest_income_year",
    "latest_income_statement_year",
    "total_assets",
    "accounts_receivable",
    "balance_sheet_debt",
    "balance_sheet_cash",
)

# bump this whenever the table changes, so old cache files get cleared out
_SCHEMA_VERSION = 5

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS financials (
    ticker TEXT PRIMARY KEY,
    sector TEXT,
    industry TEXT,
    market_cap REAL,
    total_debt REAL,
    cash_and_short_term_investments REAL,
    total_revenue REAL,
    interest_income REAL,
    interest_income_revenue REAL,
    interest_income_year INTEGER,
    latest_income_statement_year INTEGER,
    total_assets REAL,
    accounts_receivable REAL,
    balance_sheet_debt REAL,
    balance_sheet_cash REAL,
    fetched_at TEXT NOT NULL
)
"""


def save_financials(financials: CompanyFinancials, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Save a company's financials to the cache, replacing any older copy."""
    # without a timezone we can't tell how old the data really is
    if financials.fetched_at.tzinfo is None:
        raise ValueError("fetched_at must have a timezone")

    values = (
        financials.ticker,
        *(getattr(financials, name) for name in _FIELDS),
        financials.fetched_at.astimezone(UTC).isoformat(),
    )
    columns = ", ".join(("ticker", *_FIELDS, "fetched_at"))
    placeholders = ", ".join("?" * len(values))
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            f"INSERT OR REPLACE INTO financials ({columns}) VALUES ({placeholders})", values
        )


def load_financials(
    ticker: str,
    *,
    max_age_days: int,
    market_cap_max_age_days: int,
    db_path: Path = DEFAULT_DB_PATH,
    now: datetime | None = None,
) -> CompanyFinancials | None:
    """Return a company's cached financials, or None if they're missing or stale."""
    if not db_path.exists():
        return None

    columns = ", ".join((*_FIELDS, "fetched_at"))
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            f"SELECT {columns} FROM financials WHERE ticker = ?", (ticker,)
        ).fetchone()
    if row is None:
        return None

    *values, raw_fetched_at = row
    try:
        fetched_at = datetime.fromisoformat(raw_fetched_at)
    except (TypeError, ValueError):
        # fail closed: if we can't tell how old it is, treat it as missing
        return None
    if fetched_at.tzinfo is None:
        return None

    age = (now or datetime.now(UTC)) - fetched_at
    # a date in the future means the clock or the data is off, so don't trust it
    if age < timedelta(0) or age >= timedelta(days=max_age_days):
        return None

    financials = CompanyFinancials(
        ticker=ticker, **dict(zip(_FIELDS, values, strict=True)), fetched_at=fetched_at
    )
    # market cap moves daily, so it goes stale long before the rest of the row
    if age >= timedelta(days=market_cap_max_age_days):
        financials.market_cap = None
    return financials


def get_financials(
    ticker: str,
    *,
    max_age_days: int,
    market_cap_max_age_days: int,
    db_path: Path = DEFAULT_DB_PATH,
    fetch: Callable[[str], CompanyFinancials] = fetch_financials,
    now: datetime | None = None,
    refresh: bool = False,
) -> CompanyFinancials:
    """Return a company's financials from the cache, or fetch and save fresh ones."""
    if not refresh:
        cached = load_financials(
            ticker,
            max_age_days=max_age_days,
            market_cap_max_age_days=market_cap_max_age_days,
            db_path=db_path,
            now=now,
        )
        if cached is not None and cached.market_cap is not None:
            return cached

    fresh = fetch(ticker)
    # all None usually means yfinance fell over, so don't cache it or we'd be stuck with it
    if any(getattr(fresh, name) is not None for name in _FIELDS):
        save_financials(fresh, db_path)
    return fresh


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # an old cache file has the wrong columns. It's only a cache, so wipe it and every
    # ticker gets fetched again
    if conn.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
        conn.execute("DROP TABLE IF EXISTS financials")
        conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
    conn.execute(_CREATE_TABLE)
    return conn
