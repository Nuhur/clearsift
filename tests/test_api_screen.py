import copy
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from clearsift.api import create_app
from clearsift.api.app import GENERIC_ERROR, clean_ticker, pick_standard
from clearsift.api.schemas import (
    checks_out,
    comparison_out,
    prices_out,
    ratios_out,
    verdict_out,
)
from clearsift.cli import BUSINESS_WARNING, INTEREST_WARNING
from clearsift.config import load_config
from clearsift.data.models import CompanyFinancials
from clearsift.data.prices import PricePoint
from clearsift.screening.business import RatioCheck, RatioValue
from clearsift.screening.screen import compare_stock, screen_stock

CONFIG: dict[str, Any] = {
    "screening": {
        "mode": "standard",
        "fail_closed": True,
        "max_data_age_days": 120,
        "market_cap_max_age_days": 1,
        "max_interest_income_age_years": 3,
        "trust_older_interest_income": True,
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
GROCER = {**GOOD, "sector": "Consumer Defensive", "industry": "Grocery Stores"}
TOBACCO = {**GOOD, "sector": "Consumer Defensive", "industry": "Tobacco"}
# passes AAOIFI (debt over market cap) but fails FTSE (debt over total assets)
SPLIT = {**GOOD, "market_cap": 10_000.0, "balance_sheet_debt": 1000.0}

DATA = {"MSFT": GOOD, "KR": GROCER, "MO": TOBACCO, "SPLT": SPLIT}

# extra fake companies for the stock page, kept apart so the older tests don't change
NAMED = {**GOOD, "company_name": "Microsoft Corporation"}
# stopped reporting interest income, like Apple
UNDISCLOSED = {**GOOD, "interest_income": None, "interest_income_year": None}
FUND = {"quote_type": "ETF", "company_name": "iShares MSCI World Islamic"}
PAGE_DATA = {
    **DATA,
    "MSFT": NAMED,
    "AAPL": UNDISCLOSED,
    "OLDR": {**GOOD, "interest_income_year": 2023, "latest_income_statement_year": 2025},
    "IGDA.L": FUND,
    "OTHER.L": FUND,
}
# the real config's three standards, with one approved fund
FULL_CONFIG = copy.deepcopy(CONFIG)
FULL_CONFIG["screening"]["approved_funds"] = ["IGDA.L"]
FULL_CONFIG["screening"]["methodologies"]["msci"] = {
    "denominator": "total_assets",
    "max_debt": 0.3333,
    "max_cash": 0.3333,
    "max_receivables_and_cash": 0.3333,
    "max_impermissible_income": 0.05,
}
PRICES = [PricePoint(date(2026, 5, 28), 101.5), PricePoint(date(2026, 5, 29), 102.25)]


class FakeGet:
    """Stands in for get_financials, with made-up data for each ticker."""

    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.data = data
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, ticker: str, **kwargs: Any) -> CompanyFinancials:
        self.calls.append((ticker, kwargs))
        return CompanyFinancials(ticker=ticker, **self.data.get(ticker, {}))


class FakePrices:
    """Stands in for get_closes."""

    def __init__(self, result: list[PricePoint] | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, ticker: str, **kwargs: Any) -> list[PricePoint]:
        self.calls.append((ticker, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def no_client() -> Any:
    raise AssertionError("the screening routes should never talk to Trading 212")


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _client(
    tmp_path: Path,
    get: Any = None,
    prices: Any = None,
    config: dict[str, Any] = CONFIG,
) -> TestClient:
    app = create_app(
        _write(tmp_path, config),
        get=get or FakeGet(DATA),
        make_client=no_client,
        get_prices=prices or FakePrices(PRICES),
    )
    # so a crash comes back as a response we can check, like it would in the browser
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return _client(tmp_path)


# clean_ticker


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("aapl", "AAPL"),
        (" msft ", "MSFT"),
        ("brk-b", "BRK-B"),
        ("vod.l", "VOD.L"),
        ("^gspc", "^GSPC"),
        ("gbpusd=x", "GBPUSD=X"),
    ],
)
def test_clean_ticker_good(text: str, expected: str) -> None:
    assert clean_ticker(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "../etc", "A B", "AAPL;", "<script>", "A" * 21, ".L"])
def test_clean_ticker_bad(text: str) -> None:
    assert clean_ticker(text) is None


# schema helpers


def test_ratios_out() -> None:
    out = ratios_out([RatioValue("debt", 0.1, 0.3, True)])

    assert [r.model_dump() for r in out] == [
        {"name": "debt", "value": 0.1, "limit": 0.3, "passed": True}
    ]


def test_verdict_out(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, CONFIG)).screening
    out = verdict_out(screen_stock("KR", config, get=FakeGet(DATA)))

    assert out.status == "doubtful"
    assert out.passes is True
    assert out.result == "PASS (doubtful)"
    assert out.colour == "amber"
    assert out.warnings == [BUSINESS_WARNING]
    assert out.methodology == "AAOIFI"


def test_comparison_out_follows_the_chosen_standard(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, CONFIG)).screening
    verdicts = compare_stock("SPLT", config, get=FakeGet(DATA))
    out = comparison_out(verdicts, "FTSE")

    assert out.methodology == "FTSE"
    assert out.passes is False
    assert [(s.methodology, s.passes) for s in out.standards] == [("AAOIFI", True), ("FTSE", False)]
    assert out.summary == "passes under 1 of 2 standards"


def test_prices_out() -> None:
    out = prices_out(PRICES)

    assert out[0].model_dump() == {"date": date(2026, 5, 28), "close": 101.5}


# /api/health


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# /api/screen


def test_screen_one_ticker(client: TestClient) -> None:
    response = client.get("/api/screen", params={"tickers": "msft"})

    assert response.status_code == 200
    [result] = response.json()["results"]
    assert result["kind"] == "verdict"
    assert result["ticker"] == "MSFT"
    assert result["status"] == "compliant"
    assert result["passes"] is True
    assert result["result"] == "PASS (compliant)"
    assert result["company"] == ["Technology / Software - Infrastructure"]
    assert result["purification"] == "purify 2.00% of dividends"
    assert result["warnings"] == []
    assert result["reasons"]
    assert {"name": "debt", "value": 0.1, "limit": 0.3, "passed": True} in result["ratios"]


def test_screen_several_tickers_in_order(client: TestClient) -> None:
    response = client.get("/api/screen", params={"tickers": "MO, KR msft,KR"})

    results = response.json()["results"]
    assert [r["ticker"] for r in results] == ["MO", "KR", "MSFT"]
    assert [r["passes"] for r in results] == [False, True, True]
    # a failing stock gets nothing to purify
    assert results[0]["purification"] is None
    assert results[0]["colour"] == "red"


def test_screen_compare(client: TestClient) -> None:
    response = client.get("/api/screen", params={"tickers": "SPLT", "compare": "true"})

    [result] = response.json()["results"]
    assert result["kind"] == "comparison"
    assert result["methodology"] == "AAOIFI"
    assert result["passes"] is True
    assert [s["methodology"] for s in result["standards"]] == ["AAOIFI", "FTSE"]
    assert [s["passes"] for s in result["standards"]] == [True, False]
    assert result["standards"][1]["ratios"]
    assert result["summary"] == "passes under 1 of 2 standards"


def test_screen_missing_data_is_excluded(client: TestClient) -> None:
    response = client.get("/api/screen", params={"tickers": "NODATA"})

    [result] = response.json()["results"]
    assert result["status"] == "excluded"
    assert result["passes"] is False
    assert "no data from yfinance, try again later" in result["company"]


def test_screen_bad_ticker_next_to_a_good_one(tmp_path: Path) -> None:
    get = FakeGet(DATA)
    client = _client(tmp_path, get=get)

    response = client.get("/api/screen", params={"tickers": "<script>,MSFT"})

    assert response.status_code == 200
    bad, good = response.json()["results"]
    assert bad == {
        "kind": "error",
        "ticker": "<SCRIPT>",
        "message": "that doesn't look like a ticker",
    }
    assert good["passes"] is True
    # the bad one never got as far as yfinance
    assert [ticker for ticker, _ in get.calls] == ["MSFT"]


def test_screen_value_error_only_hits_that_ticker(tmp_path: Path) -> None:
    class Picky(FakeGet):
        def __call__(self, ticker: str, **kwargs: Any) -> CompanyFinancials:
            if ticker == "MO":
                raise ValueError("bad mapping for MO")
            return super().__call__(ticker, **kwargs)

    client = _client(tmp_path, get=Picky(DATA))
    response = client.get("/api/screen", params={"tickers": "MO,MSFT"})

    bad, good = response.json()["results"]
    assert bad == {"kind": "error", "ticker": "MO", "message": "bad mapping for MO"}
    assert good["kind"] == "verdict"


def test_screen_refresh_reaches_get(tmp_path: Path) -> None:
    get = FakeGet(DATA)
    client = _client(tmp_path, get=get)

    client.get("/api/screen", params={"tickers": "MSFT"})
    client.get("/api/screen", params={"tickers": "MSFT", "refresh": "true"})

    assert "refresh" not in get.calls[0][1]
    assert get.calls[1][1]["refresh"] is True


@pytest.mark.parametrize("tickers", ["", " , ,"])
def test_screen_no_tickers(client: TestClient, tickers: str) -> None:
    response = client.get("/api/screen", params={"tickers": tickers})

    assert response.status_code == 400
    assert response.json() == {"message": "give at least one ticker"}


def test_screen_tickers_left_out(client: TestClient) -> None:
    response = client.get("/api/screen")

    assert response.status_code == 422
    assert response.json() == {"message": "bad or missing parameter: tickers"}


def test_screen_bad_flag_does_not_echo_it_back(client: TestClient) -> None:
    response = client.get("/api/screen", params={"tickers": "MSFT", "compare": "<b>sneaky</b>"})

    assert response.status_code == 422
    assert response.json() == {"message": "bad or missing parameter: compare"}


def test_screen_broken_config(tmp_path: Path) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["mode"] = "relaxed"
    client = _client(tmp_path, config=data)

    response = client.get("/api/screen", params={"tickers": "MSFT"})

    assert response.status_code == 500
    assert response.json() == {
        "message": "config error: screening.mode must be 'strict' or 'standard'"
    }


def test_screen_unmapped_sector_is_a_config_error(tmp_path: Path) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["excluded_sectors"] = ["alcohol", "crypto"]
    client = _client(tmp_path, config=data)

    response = client.get("/api/screen", params={"tickers": "MSFT"})

    assert response.status_code == 500
    assert response.json()["message"].startswith("config error: ")
    assert "crypto" in response.json()["message"]


def test_screen_crash_gives_a_safe_message(tmp_path: Path) -> None:
    def crash(ticker: str, **kwargs: Any) -> CompanyFinancials:
        raise RuntimeError("secret-key-123 in a traceback")

    client = _client(tmp_path, get=crash)
    response = client.get("/api/screen", params={"tickers": "MSFT"})

    assert response.status_code == 500
    assert response.json() == {"message": GENERIC_ERROR}
    assert "secret-key-123" not in response.text
    assert "Traceback" not in response.text


def test_unknown_route_uses_the_same_error_shape(client: TestClient) -> None:
    response = client.get("/api/nope")

    assert response.status_code == 404
    assert response.json() == {"message": "Not Found"}


# /api/stocks/{ticker}


def test_stock_detail(tmp_path: Path) -> None:
    prices = FakePrices(PRICES)
    client = _client(tmp_path, prices=prices)

    response = client.get("/api/stocks/splt")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "SPLT"
    assert body["verdict"]["kind"] == "comparison"
    assert body["verdict"]["passes"] is True
    assert [s["methodology"] for s in body["verdict"]["standards"]] == ["AAOIFI", "FTSE"]
    assert body["prices"] == [
        {"date": "2026-05-28", "close": 101.5},
        {"date": "2026-05-29", "close": 102.25},
    ]
    assert prices.calls == [("SPLT", {"refresh": False})]


def test_stock_detail_refresh(tmp_path: Path) -> None:
    get = FakeGet(DATA)
    prices = FakePrices(PRICES)
    client = _client(tmp_path, get=get, prices=prices)

    client.get("/api/stocks/MSFT", params={"refresh": "true"})

    assert get.calls[0][1]["refresh"] is True
    assert prices.calls == [("MSFT", {"refresh": True})]


def test_stock_detail_no_prices(tmp_path: Path) -> None:
    client = _client(tmp_path, prices=FakePrices([]))

    response = client.get("/api/stocks/MSFT")

    assert response.status_code == 200
    assert response.json()["prices"] == []


def test_stock_detail_broken_prices_still_shows_verdict(tmp_path: Path) -> None:
    client = _client(tmp_path, prices=FakePrices(RuntimeError("disk on fire")))

    response = client.get("/api/stocks/MSFT")

    assert response.status_code == 200
    assert response.json()["verdict"]["passes"] is True
    assert response.json()["prices"] == []
    assert "disk on fire" not in response.text


def test_stock_detail_bad_ticker(tmp_path: Path) -> None:
    get = FakeGet(DATA)
    client = _client(tmp_path, get=get)

    response = client.get("/api/stocks/AAPL;DROP")

    assert response.status_code == 400
    assert response.json() == {"message": "that doesn't look like a ticker"}
    assert get.calls == []


def test_stock_detail_value_error(tmp_path: Path) -> None:
    def picky(ticker: str, **kwargs: Any) -> CompanyFinancials:
        raise ValueError("bad mapping")

    client = _client(tmp_path, get=picky)
    response = client.get("/api/stocks/MSFT")

    assert response.status_code == 500
    assert response.json() == {"message": "bad mapping"}


# stock page details


def test_checks_out() -> None:
    out = checks_out([RatioCheck("debt", None, 0.3, "market_cap", "fail")])

    assert [c.model_dump() for c in out] == [
        {
            "name": "debt",
            "value": None,
            "limit": 0.3,
            "base": "market_cap",
            "outcome": "fail",
            "year": None,
        }
    ]


def _page_client(tmp_path: Path) -> TestClient:
    return _client(tmp_path, get=FakeGet(PAGE_DATA), config=FULL_CONFIG)


def _details(tmp_path: Path, ticker: str) -> dict[str, Any]:
    response = _page_client(tmp_path).get(f"/api/stocks/{ticker}")
    assert response.status_code == 200
    return response.json()["verdict"]


def test_company_details(tmp_path: Path) -> None:
    verdict = _details(tmp_path, "MSFT")

    assert verdict["details"] == {
        "name": "Microsoft Corporation",
        "sector": "Technology",
        "industry": "Software - Infrastructure",
        "is_fund": False,
        "business_status": "compliant",
        "approved_fund": False,
        "excluded_group": None,
        "no_data": False,
    }


def test_name_falls_back_to_the_ticker(tmp_path: Path) -> None:
    assert _details(tmp_path, "KR")["details"]["name"] == "KR"


def test_missing_labels_are_null_not_unknown(tmp_path: Path) -> None:
    details = _details(tmp_path, "NODATA")["details"]

    assert (details["sector"], details["industry"]) == (None, None)
    assert details["no_data"] is True


def test_excluded_group_in_details(tmp_path: Path) -> None:
    verdict = _details(tmp_path, "MO")

    assert verdict["details"]["excluded_group"] == "tobacco"
    assert verdict["passes"] is False


@pytest.mark.parametrize(
    ("ticker", "approved", "passes"),
    [("IGDA.L", True, True), ("OTHER.L", False, True)],
)
def test_fund_details(tmp_path: Path, ticker: str, approved: bool, passes: bool) -> None:
    verdict = _details(tmp_path, ticker)

    assert verdict["details"]["is_fund"] is True
    assert verdict["details"]["approved_fund"] is approved
    assert verdict["passes"] is passes
    # funds purify their own income, so there's no number to give
    assert verdict["purification_ratio"] is None
    assert all(s["checks"] == [] for s in verdict["standards"])


def test_purification_fields(tmp_path: Path) -> None:
    verdict = _details(tmp_path, "MSFT")

    assert verdict["purification_ratio"] == pytest.approx(0.02)
    assert verdict["purification_year"] == 2025


def test_purification_follows_the_chosen_standard(tmp_path: Path) -> None:
    client = _page_client(tmp_path)

    passing = client.get("/api/stocks/SPLT", params={"standard": "aaoifi"}).json()["verdict"]
    failing = client.get("/api/stocks/SPLT", params={"standard": "ftse"}).json()["verdict"]

    assert passing["purification_ratio"] == pytest.approx(0.02)
    assert failing["passes"] is False
    assert failing["purification_ratio"] is None
    assert failing["purification_year"] is None


def test_every_standard_has_its_checks(tmp_path: Path) -> None:
    standards = _details(tmp_path, "MSFT")["standards"]

    assert [len(s["checks"]) for s in standards] == [3, 4, 4]
    assert standards[1]["checks"][2] == {
        "name": "receivables plus cash",
        "value": pytest.approx(0.15),
        "limit": 0.5,
        "base": "total_assets",
        "outcome": "pass",
        "year": None,
    }


def test_undisclosed_interest_shows_as_a_doubt(tmp_path: Path) -> None:
    standards = _details(tmp_path, "AAPL")["standards"]

    assert standards[0]["checks"][-1] == {
        "name": "interest income",
        "value": None,
        "limit": 0.05,
        "base": "revenue",
        "outcome": "doubt",
        "year": None,
    }
    assert standards[0]["warning"] == INTEREST_WARNING


@pytest.mark.parametrize(("standard", "label"), [("ftse", "FTSE"), (" FTSE ", "FTSE")])
def test_stock_detail_picks_a_standard(tmp_path: Path, standard: str, label: str) -> None:
    client = _client(tmp_path)

    verdict = client.get("/api/stocks/SPLT", params={"standard": standard}).json()["verdict"]

    assert verdict["methodology"] == label
    assert verdict["passes"] is False
    # the other standards still come back, so the page can mention them
    assert [s["methodology"] for s in verdict["standards"]] == ["AAOIFI", "FTSE"]


def test_stock_detail_defaults_to_the_config_standard(tmp_path: Path) -> None:
    verdict = _client(tmp_path).get("/api/stocks/SPLT").json()["verdict"]

    assert verdict["methodology"] == "AAOIFI"


def test_stock_detail_unknown_standard(tmp_path: Path) -> None:
    get = FakeGet(DATA)
    client = _client(tmp_path, get=get)

    response = client.get("/api/stocks/MSFT", params={"standard": "<b>nope</b>"})

    assert response.status_code == 422
    assert response.json() == {"message": "standard must be one of: aaoifi, ftse"}
    assert get.calls == []


def test_pick_standard(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, FULL_CONFIG)).screening

    assert pick_standard(config, None) == "AAOIFI"
    assert pick_standard(config, "msci") == "MSCI"


def test_stock_detail_is_get_only(client: TestClient) -> None:
    assert client.post("/api/stocks/MSFT").status_code == 405


@pytest.mark.parametrize(
    ("ticker", "status"),
    [("MSFT", "compliant"), ("KR", "doubtful"), ("MO", "excluded"), ("OTHER.L", "doubtful")],
)
def test_business_status_is_the_business_screen_alone(
    tmp_path: Path, ticker: str, status: str
) -> None:
    assert _details(tmp_path, ticker)["details"]["business_status"] == status


def test_business_status_ignores_failing_ratios(tmp_path: Path) -> None:
    verdict = _details(tmp_path, "SPLT")

    # SPLT fails FTSE on debt, but its business is fine
    assert verdict["details"]["business_status"] == "compliant"


def test_trusted_older_interest_income_passes_with_its_year(tmp_path: Path) -> None:
    verdict = _details(tmp_path, "OLDR")

    assert verdict["status"] == "compliant"
    aaoifi = verdict["standards"][0]
    assert aaoifi["warning"] is None
    assert aaoifi["checks"][-1]["outcome"] == "pass"
    assert aaoifi["checks"][-1]["year"] == 2023
    assert verdict["purification_ratio"] == pytest.approx(0.02)
    assert verdict["purification_year"] == 2023
