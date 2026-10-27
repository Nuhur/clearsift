import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from clearsift.data.cache import get_financials, load_financials, save_financials
from clearsift.data.models import CompanyFinancials

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
MAX_AGE = 120
MARKET_CAP_MAX_AGE = 1


def _financials(ticker: str = "MSFT", fetched_at: datetime = NOW, **overrides) -> CompanyFinancials:
    values = {
        "sector": "Technology",
        "industry": "Software",
        "market_cap": 3e12,
        "total_debt": 5e10,
        "cash_and_short_term_investments": 1e11,
        "total_revenue": 2e11,
        "interest_income": 1e9,
        "interest_income_revenue": 2e11,
        "interest_income_year": 2025,
        "latest_income_statement_year": 2025,
        "total_assets": 4e11,
        "accounts_receivable": 3e10,
        "balance_sheet_debt": 9e10,
        "balance_sheet_cash": 6e10,
    }
    values.update(overrides)
    return CompanyFinancials(ticker=ticker, fetched_at=fetched_at, **values)


def _load(db_path: Path, ticker: str = "MSFT", now: datetime = NOW) -> CompanyFinancials | None:
    return load_financials(
        ticker,
        max_age_days=MAX_AGE,
        market_cap_max_age_days=MARKET_CAP_MAX_AGE,
        db_path=db_path,
        now=now,
    )


class FakeFetch:
    """Stands in for yfinance and counts how often it's called."""

    def __init__(self, result: CompanyFinancials) -> None:
        self.result = result
        self.calls: list[str] = []

    def __call__(self, ticker: str) -> CompanyFinancials:
        self.calls.append(ticker)
        return self.result


def _get(db_path: Path, fetch: FakeFetch, now: datetime = NOW) -> CompanyFinancials:
    return get_financials(
        "MSFT",
        max_age_days=MAX_AGE,
        market_cap_max_age_days=MARKET_CAP_MAX_AGE,
        db_path=db_path,
        fetch=fetch,
        now=now,
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "cache.db"


def test_save_then_load_round_trip(db_path: Path) -> None:
    saved = _financials(total_debt=None, industry=None)
    save_financials(saved, db_path)

    assert _load(db_path) == saved


def test_save_creates_data_folder(db_path: Path) -> None:
    assert not db_path.parent.exists()

    save_financials(_financials(), db_path)

    assert db_path.exists()


def test_save_replaces_older_copy(db_path: Path) -> None:
    save_financials(_financials(fetched_at=NOW - timedelta(hours=2), total_debt=1.0), db_path)
    save_financials(_financials(fetched_at=NOW - timedelta(hours=1), total_debt=2.0), db_path)

    loaded = _load(db_path)
    assert loaded is not None
    assert loaded.total_debt == 2.0
    with closing(sqlite3.connect(db_path)) as conn, conn:
        assert conn.execute("SELECT COUNT(*) FROM financials").fetchone()[0] == 1


def test_save_without_timezone_raises(db_path: Path) -> None:
    with pytest.raises(ValueError):
        save_financials(_financials(fetched_at=datetime(2026, 6, 1)), db_path)


def test_load_missing_database_returns_none(db_path: Path) -> None:
    assert _load(db_path) is None
    assert not db_path.parent.exists()


def test_load_unknown_ticker_returns_none(db_path: Path) -> None:
    save_financials(_financials(), db_path)

    assert _load(db_path, ticker="AAPL") is None


def test_load_stale_returns_none(db_path: Path) -> None:
    save_financials(_financials(fetched_at=NOW - timedelta(days=MAX_AGE + 1)), db_path)

    assert _load(db_path) is None


def test_load_exactly_max_age_is_stale(db_path: Path) -> None:
    save_financials(_financials(fetched_at=NOW - timedelta(days=MAX_AGE)), db_path)

    assert _load(db_path) is None


def test_load_future_fetched_at_returns_none(db_path: Path) -> None:
    save_financials(_financials(fetched_at=NOW + timedelta(hours=1)), db_path)

    assert _load(db_path) is None


def test_load_unreadable_fetched_at_returns_none(db_path: Path) -> None:
    save_financials(_financials(), db_path)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE financials SET fetched_at = 'yesterday'")

    assert _load(db_path) is None


def test_load_old_market_cap_is_dropped(db_path: Path) -> None:
    save_financials(_financials(fetched_at=NOW - timedelta(days=MARKET_CAP_MAX_AGE)), db_path)

    loaded = _load(db_path)
    assert loaded is not None
    assert loaded.market_cap is None
    assert loaded.total_debt == 5e10


def test_load_recent_market_cap_is_kept(db_path: Path) -> None:
    save_financials(_financials(fetched_at=NOW - timedelta(hours=23)), db_path)

    loaded = _load(db_path)
    assert loaded is not None
    assert loaded.market_cap == 3e12


def test_get_uses_fresh_cache(db_path: Path) -> None:
    cached = _financials(fetched_at=NOW - timedelta(hours=1))
    save_financials(cached, db_path)
    fetch = FakeFetch(_financials(total_debt=999.0))

    assert _get(db_path, fetch) == cached
    assert fetch.calls == []


def test_get_fetches_and_saves_when_not_cached(db_path: Path) -> None:
    fresh = _financials()
    fetch = FakeFetch(fresh)

    assert _get(db_path, fetch) == fresh
    assert fetch.calls == ["MSFT"]
    assert _load(db_path) == fresh


def test_get_refetches_when_stale(db_path: Path) -> None:
    save_financials(_financials(fetched_at=NOW - timedelta(days=MAX_AGE), total_debt=1.0), db_path)
    fresh = _financials(total_debt=2.0)
    fetch = FakeFetch(fresh)

    assert _get(db_path, fetch) == fresh
    assert fetch.calls == ["MSFT"]
    assert _load(db_path) == fresh


def test_get_refetches_when_market_cap_is_old(db_path: Path) -> None:
    save_financials(_financials(fetched_at=NOW - timedelta(days=2), market_cap=1e12), db_path)
    fresh = _financials(market_cap=2e12)
    fetch = FakeFetch(fresh)

    assert _get(db_path, fetch).market_cap == 2e12
    assert fetch.calls == ["MSFT"]
    loaded = _load(db_path)
    assert loaded is not None
    assert loaded.market_cap == 2e12


def test_get_refetches_when_cached_market_cap_is_missing(db_path: Path) -> None:
    save_financials(_financials(market_cap=None), db_path)
    fetch = FakeFetch(_financials())

    _get(db_path, fetch)

    assert fetch.calls == ["MSFT"]


def test_get_does_not_cache_all_none_result(db_path: Path) -> None:
    empty = CompanyFinancials(ticker="MSFT", fetched_at=NOW)
    fetch = FakeFetch(empty)

    assert _get(db_path, fetch) == empty
    assert _load(db_path) is None


def test_get_all_none_result_keeps_older_cache(db_path: Path) -> None:
    older = _financials(fetched_at=NOW - timedelta(days=2))
    save_financials(older, db_path)
    fetch = FakeFetch(CompanyFinancials(ticker="MSFT", fetched_at=NOW))

    _get(db_path, fetch)

    loaded = _load(db_path)
    assert loaded is not None
    assert loaded.total_debt == older.total_debt


def test_get_caches_partial_result(db_path: Path) -> None:
    partial = CompanyFinancials(ticker="MSFT", sector="Technology", fetched_at=NOW)
    fetch = FakeFetch(partial)

    _get(db_path, fetch)

    assert _load(db_path) == partial


def test_get_refresh_skips_fresh_cache_and_saves(db_path: Path) -> None:
    save_financials(_financials(fetched_at=NOW - timedelta(hours=1), total_debt=1.0), db_path)
    fresh = _financials(total_debt=2.0)
    fetch = FakeFetch(fresh)

    result = get_financials(
        "MSFT",
        max_age_days=MAX_AGE,
        market_cap_max_age_days=MARKET_CAP_MAX_AGE,
        db_path=db_path,
        fetch=fetch,
        now=NOW,
        refresh=True,
    )

    assert result == fresh
    assert fetch.calls == ["MSFT"]
    assert _load(db_path) == fresh


def test_get_refresh_all_none_result_keeps_older_cache(db_path: Path) -> None:
    older = _financials(fetched_at=NOW - timedelta(hours=1))
    save_financials(older, db_path)
    empty = CompanyFinancials(ticker="MSFT", fetched_at=NOW)

    result = get_financials(
        "MSFT",
        max_age_days=MAX_AGE,
        market_cap_max_age_days=MARKET_CAP_MAX_AGE,
        db_path=db_path,
        fetch=FakeFetch(empty),
        now=NOW,
        refresh=True,
    )

    assert result == empty
    assert _load(db_path) == older


def _write_old_style_cache(db_path: Path, fetched_at: datetime) -> None:
    # the table as it was before interest_income was added
    db_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            """
            CREATE TABLE financials (
                ticker TEXT PRIMARY KEY,
                sector TEXT,
                industry TEXT,
                market_cap REAL,
                total_debt REAL,
                cash_and_short_term_investments REAL,
                total_revenue REAL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO financials VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("MSFT", "Technology", "Software", 3e12, 5e10, 1e11, 2e11, fetched_at.isoformat()),
        )


def test_save_then_load_keeps_interest_income(db_path: Path) -> None:
    save_financials(_financials(interest_income=4.5e9), db_path)

    loaded = _load(db_path)
    assert loaded is not None
    assert loaded.interest_income == 4.5e9


def test_old_style_cache_counts_as_missing(db_path: Path) -> None:
    _write_old_style_cache(db_path, fetched_at=NOW - timedelta(hours=1))

    assert _load(db_path) is None


def test_old_style_cache_gets_refetched_and_saved(db_path: Path) -> None:
    _write_old_style_cache(db_path, fetched_at=NOW - timedelta(hours=1))
    fresh = _financials()
    fetch = FakeFetch(fresh)

    assert _get(db_path, fetch) == fresh
    assert fetch.calls == ["MSFT"]
    assert _load(db_path) == fresh


def test_save_then_load_keeps_interest_income_year_fields(db_path: Path) -> None:
    saved = _financials(interest_income_revenue=3e11, interest_income_year=2023)
    save_financials(saved, db_path)

    loaded = _load(db_path)
    assert loaded is not None
    assert loaded.interest_income_revenue == 3e11
    assert loaded.interest_income_year == 2023
    assert loaded.latest_income_statement_year == 2025


def test_save_then_load_keeps_balance_sheet_fields(db_path: Path) -> None:
    save_financials(_financials(total_assets=5e11, accounts_receivable=None), db_path)

    loaded = _load(db_path)
    assert loaded is not None
    assert loaded.total_assets == 5e11
    assert loaded.accounts_receivable is None


def test_save_then_load_keeps_balance_sheet_debt_and_cash(db_path: Path) -> None:
    save_financials(_financials(balance_sheet_debt=1.2e11, balance_sheet_cash=None), db_path)

    loaded = _load(db_path)
    assert loaded is not None
    assert loaded.balance_sheet_debt == 1.2e11
    assert loaded.balance_sheet_cash is None
