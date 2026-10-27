import copy
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import pytest
import yaml

from clearsift.cli import main
from clearsift.data.cache import get_financials, load_financials, save_financials
from clearsift.data.models import CompanyFinancials

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


class FakeGet:
    """Stands in for get_financials, with made-up data for each ticker."""

    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.data = data

    def __call__(self, ticker: str, **kwargs: Any) -> CompanyFinancials:
        return CompanyFinancials(ticker=ticker, **self.data.get(ticker, {}))


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    return path


def _run(config_path: Path, *tickers: str, data: dict[str, dict[str, Any]]) -> int:
    return main(["screen", *tickers, "--config", str(config_path)], get=FakeGet(data))


def test_all_pass_exits_0(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = _run(config_path, "MSFT", "ADBE", data={"MSFT": GOOD, "ADBE": GOOD})

    out = capsys.readouterr().out
    assert code == 0
    assert "MSFT: PASS (compliant)" in out
    assert "ADBE: PASS (compliant)" in out
    assert "  Technology / Software - Infrastructure" in out
    assert "  - debt is 10.00% of market cap, AAOIFI limit is 30%" in out


def test_one_fail_exits_1(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tobacco = {**GOOD, "sector": "Consumer Defensive", "industry": "Tobacco"}

    code = _run(config_path, "MSFT", "MO", data={"MSFT": GOOD, "MO": tobacco})

    out = capsys.readouterr().out
    assert code == 1
    assert "MSFT: PASS (compliant)" in out
    assert "MO: FAIL (excluded)" in out


def test_reasons_from_both_screens_shown(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = {**GOOD, "sector": "Consumer Defensive", "industry": "Tobacco", "total_debt": 400.0}

    _run(config_path, "MO", data={"MO": bad})

    out = capsys.readouterr().out
    assert "  - industry 'Tobacco' falls under excluded group 'tobacco'" in out
    assert "  - debt is 40.00% of market cap, AAOIFI limit is 30%" in out


GROCER = {**GOOD, "sector": "Consumer Defensive", "industry": "Grocery Stores"}
CHECK_BY_HAND = "  check by hand: the industry label alone can't confirm this business is halal"


def test_doubtful_fails_in_strict_mode(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(config_path, "KR", data={"KR": GROCER})

    out = capsys.readouterr().out
    assert code == 1
    assert "KR: FAIL (doubtful)" in out
    assert CHECK_BY_HAND in out


def test_doubtful_passes_with_warning_in_standard_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["mode"] = "standard"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    code = _run(path, "KR", data={"KR": GROCER})

    out = capsys.readouterr().out
    assert code == 0
    assert "KR: PASS (doubtful)" in out
    assert CHECK_BY_HAND in out


OLDER_YEAR_WARNING = "  check by hand: interest income isn't in the latest report"


def test_older_interest_income_fails_in_strict_mode(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(config_path, "AAPL", data={"AAPL": {**GOOD, "interest_income_year": 2023}})

    out = capsys.readouterr().out
    assert code == 1
    assert "AAPL: FAIL (doubtful)" in out
    assert OLDER_YEAR_WARNING in out
    assert "(from 2023, newer years not reported)" in out


def test_older_interest_income_passes_with_warning_in_standard_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["mode"] = "standard"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    code = _run(path, "AAPL", data={"AAPL": {**GOOD, "interest_income_year": 2023}})

    out = capsys.readouterr().out
    assert code == 0
    assert "AAPL: PASS (doubtful)" in out
    assert OLDER_YEAR_WARNING in out
    assert CHECK_BY_HAND not in out


def test_no_warning_for_compliant(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(config_path, "MSFT", data={"MSFT": GOOD})

    assert "check by hand" not in capsys.readouterr().out


def test_lowercase_ticker_is_uppercased(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(config_path, "msft", data={"MSFT": GOOD})

    assert code == 0
    assert "MSFT: PASS" in capsys.readouterr().out


def test_no_data_line_when_everything_missing(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(config_path, "GONE", data={})

    out = capsys.readouterr().out
    assert code == 1
    assert "  unknown / unknown" in out
    assert "  no data from yfinance, try again later" in out


def test_no_data_line_not_shown_for_partial_data(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(config_path, "HALF", data={"HALF": {"sector": "Technology"}})

    assert "no data from yfinance" not in capsys.readouterr().out


def _standard_config(tmp_path: Path) -> Path:
    data = copy.deepcopy(CONFIG)
    data["screening"]["mode"] = "standard"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_purification_line_for_passing_stock(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(config_path, "MSFT", data={"MSFT": GOOD})

    assert "  purify 2.00% of dividends\n" in capsys.readouterr().out


def test_purification_percent_rounds_up(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 4.91 / 500 is 0.982%, rounding to nearest would show 0.98%
    _run(config_path, "MSFT", data={"MSFT": {**GOOD, "interest_income": 4.91}})

    assert "  purify 0.99% of dividends\n" in capsys.readouterr().out


def test_purification_line_says_older_year(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(_standard_config(tmp_path), "AAPL", data={"AAPL": {**GOOD, "interest_income_year": 2023}})

    assert "  purify 2.00% of dividends (based on 2023)" in capsys.readouterr().out


def test_purification_line_when_not_disclosed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    company = {**GOOD, "interest_income_year": None, "interest_income": None}

    _run(_standard_config(tmp_path), "AAPL", data={"AAPL": company})

    out = capsys.readouterr().out
    assert "AAPL: PASS (doubtful)" in out
    assert "  purification: can't work out, interest income not disclosed" in out


def test_no_purification_line_for_failed_stock(
    config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(config_path, "ABC", data={"ABC": {**GOOD, "total_debt": 400.0}})

    assert "purif" not in capsys.readouterr().out


ETF: dict[str, Any] = {"quote_type": "ETF"}
FUND_REASON = "  - Sharia-certified fund, on your approved list"
FUND_PURIFICATION = "  purification: check the fund's own reports"


def _funds_config(tmp_path: Path, mode: str = "strict") -> Path:
    data = copy.deepcopy(CONFIG)
    data["screening"]["mode"] = mode
    data["screening"]["approved_funds"] = ["IGDA.L", "ISUS.L", "ISDE.L"]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_approved_funds_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = {"IGDA.L": ETF, "ISUS.L": ETF, "ISDE.L": ETF}

    code = _run(_funds_config(tmp_path), "IGDA.L", "ISUS.L", "ISDE.L", data=data)

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("IGDA.L: PASS (compliant)\n  fund (ETF)\n")
    assert "unknown" not in out
    assert out.count(FUND_REASON) == 3
    assert out.count(FUND_PURIFICATION) == 3
    assert "IGDA.L: PASS (compliant)" in out
    assert "check by hand" not in out


def test_unapproved_fund_fails_in_strict_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(_funds_config(tmp_path), "OTHER.L", data={"OTHER.L": ETF})

    out = capsys.readouterr().out
    assert code == 1
    assert "OTHER.L: FAIL (doubtful)" in out
    assert "  - fund: check its Sharia certification" in out
    # the industry warning is about company labels, it doesn't fit a fund
    assert "industry label" not in out
    assert "purification" not in out


def test_unapproved_fund_passes_in_standard_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(_funds_config(tmp_path, "standard"), "OTHER.L", data={"OTHER.L": ETF})

    out = capsys.readouterr().out
    assert code == 0
    assert "OTHER.L: PASS (doubtful)" in out
    assert FUND_PURIFICATION in out
    assert "industry label" not in out


def test_mutual_fund_label(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(_funds_config(tmp_path), "IGDA.L", data={"IGDA.L": {"quote_type": "MUTUALFUND"}})

    assert "  fund (MUTUALFUND)\n" in capsys.readouterr().out


def test_funds_only_run_still_catches_sector_typo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["approved_funds"] = ["IGDA.L"]
    data["screening"]["excluded_sectors"] = ["alchohol"]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    get = RecordingGet({"IGDA.L": ETF})

    code = main(["screen", "IGDA.L", "--config", str(path)], get=get)

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "alchohol" in captured.err
    # caught before any ticker was even fetched
    assert get.calls == []


def test_compare_approved_fund(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["approved_funds"] = ["IGDA.L"]
    data["screening"]["methodologies"].update({"ftse": FTSE, "msci": MSCI})
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    code = _compare(path, "IGDA.L", data={"IGDA.L": ETF})

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("IGDA.L\n  fund (ETF)\n")
    assert out.count(FUND_REASON) == 1
    assert out.count(FUND_PURIFICATION) == 1
    assert "passes under 3 of 3 standards" in out


def test_missing_config_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = _run(tmp_path / "nope.yaml", "MSFT", data={"MSFT": GOOD})

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "config error" in captured.err
    assert "Traceback" not in captured.err


def test_bad_config_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["mode"] = "relaxed"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    code = _run(path, "MSFT", data={"MSFT": GOOD})

    assert code == 2
    assert "screening.mode must be 'strict' or 'standard'" in capsys.readouterr().err


def test_unmapped_excluded_sector_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = copy.deepcopy(CONFIG)
    data["screening"]["excluded_sectors"] = ["alchohol"]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    code = _run(path, "MSFT", data={"MSFT": GOOD})

    assert code == 2
    assert "alchohol" in capsys.readouterr().err


def test_no_tickers_is_a_usage_error(config_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["screen", "--config", str(config_path)], get=FakeGet({}))

    assert exc.value.code == 2


def test_no_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        main([], get=FakeGet({}))

    assert exc.value.code == 2


FTSE = {
    "denominator": "total_assets",
    "max_debt": 0.33333,
    "max_cash": 0.33333,
    "max_receivables_and_cash": 0.50,
    "max_impermissible_income": 0.05,
}
MSCI = {
    "denominator": "total_assets",
    "max_debt": 0.3333,
    "max_cash": 0.3333,
    "max_receivables_and_cash": 0.3333,
    "max_impermissible_income": 0.05,
}


@pytest.fixture
def three_standards(tmp_path: Path) -> Path:
    data = copy.deepcopy(CONFIG)
    data["screening"]["methodologies"].update({"ftse": FTSE, "msci": MSCI})
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _compare(config_path: Path, *tickers: str, data: dict[str, dict[str, Any]]) -> int:
    args = ["screen", *tickers, "--compare", "--config", str(config_path)]
    return main(args, get=FakeGet(data))


def test_compare_shows_every_standard(
    three_standards: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _compare(three_standards, "MSFT", data={"MSFT": GOOD})

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("MSFT\n  Technology / Software - Infrastructure\n")
    assert "  AAOIFI: PASS (compliant)" in out
    assert "  FTSE: PASS (compliant)" in out
    assert "  MSCI: PASS (compliant)" in out
    assert "    - debt is 5.00% of total assets, FTSE limit is 33.333%" in out
    assert out.rstrip().endswith("passes under 3 of 3 standards")


def test_compare_counts_mixed_results(
    three_standards: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # info's debt is 40% of market cap, which fails AAOIFI. FTSE and MSCI use the
    # balance sheet debt (5% of total assets) instead. Receivables plus cash is 40%
    # of total assets, which fails MSCI only
    company = {**GOOD, "total_debt": 400.0, "accounts_receivable": 600.0}

    _compare(three_standards, "ABC", data={"ABC": company})

    out = capsys.readouterr().out
    assert "  AAOIFI: FAIL (excluded)" in out
    assert "  FTSE: PASS (compliant)" in out
    assert "  MSCI: FAIL (excluded)" in out
    assert "passes under 1 of 3 standards" in out


def test_compare_exit_code_follows_chosen_methodology(
    three_standards: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # fails AAOIFI (the one picked in the config) but passes FTSE and MSCI
    company = {**GOOD, "total_debt": 400.0}

    assert _compare(three_standards, "ABC", data={"ABC": company}) == 1


def test_compare_shows_business_reasons_once(
    three_standards: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tobacco = {**GOOD, "sector": "Consumer Defensive", "industry": "Tobacco"}

    _compare(three_standards, "MO", data={"MO": tobacco})

    out = capsys.readouterr().out
    assert out.count("falls under excluded group 'tobacco'") == 1
    assert "passes under 0 of 3 standards" in out


def test_compare_shows_purification_once(
    three_standards: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _compare(three_standards, "MSFT", data={"MSFT": GOOD})

    assert capsys.readouterr().out.count("purify 2.00% of dividends") == 1


def test_compare_shows_purification_if_any_standard_passes(
    three_standards: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # fails AAOIFI on debt, passes FTSE and MSCI
    _compare(three_standards, "ABC", data={"ABC": {**GOOD, "total_debt": 400.0}})

    assert "  purify 2.00% of dividends" in capsys.readouterr().out


def test_compare_no_purification_if_every_standard_fails(
    three_standards: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tobacco = {**GOOD, "sector": "Consumer Defensive", "industry": "Tobacco"}

    _compare(three_standards, "MO", data={"MO": tobacco})

    assert "purif" not in capsys.readouterr().out


class RecordingGet(FakeGet):
    """A FakeGet that also remembers the keyword arguments of every call."""

    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        super().__init__(data)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, ticker: str, **kwargs: Any) -> CompanyFinancials:
        self.calls.append((ticker, kwargs))
        return super().__call__(ticker, **kwargs)


def test_refresh_asks_for_fresh_data_for_every_ticker(config_path: Path) -> None:
    get = RecordingGet({"MSFT": GOOD, "ADBE": GOOD})

    main(["screen", "MSFT", "ADBE", "--refresh", "--config", str(config_path)], get=get)

    assert [(t, kw.get("refresh")) for t, kw in get.calls] == [("MSFT", True), ("ADBE", True)]


def test_refresh_works_with_compare(three_standards: Path) -> None:
    get = RecordingGet({"MSFT": GOOD})

    main(["screen", "MSFT", "--compare", "--refresh", "--config", str(three_standards)], get=get)

    assert [(t, kw.get("refresh")) for t, kw in get.calls] == [("MSFT", True)]


def test_without_refresh_nothing_is_passed(config_path: Path) -> None:
    get = RecordingGet({"MSFT": GOOD})

    main(["screen", "MSFT", "--config", str(config_path)], get=get)

    assert "refresh" not in get.calls[0][1]


def _cached_get(db_path: Path, fetch: Callable[[str], CompanyFinancials]) -> Callable[..., Any]:
    return partial(get_financials, db_path=db_path, fetch=fetch)


@pytest.mark.parametrize("extra", [[], ["--compare"]])
def test_refresh_bypasses_cache_and_updates_it(
    tmp_path: Path, config_path: Path, extra: list[str]
) -> None:
    db_path = tmp_path / "cache.db"
    # a fresh cached copy that would fail on debt, so a pass proves it wasn't used
    save_financials(CompanyFinancials(ticker="MSFT", **{**GOOD, "total_debt": 900.0}), db_path)
    fetched: list[str] = []

    def fake_fetch(ticker: str) -> CompanyFinancials:
        fetched.append(ticker)
        return CompanyFinancials(ticker=ticker, **GOOD)

    args = ["screen", "MSFT", "--refresh", *extra, "--config", str(config_path)]
    code = main(args, get=_cached_get(db_path, fake_fetch))

    assert code == 0
    assert fetched == ["MSFT"]
    cached = load_financials("MSFT", max_age_days=120, market_cap_max_age_days=1, db_path=db_path)
    assert cached is not None
    assert cached.total_debt == 100.0


def test_without_refresh_cache_is_used(tmp_path: Path, config_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    save_financials(CompanyFinancials(ticker="MSFT", **GOOD), db_path)
    fetched: list[str] = []

    def fake_fetch(ticker: str) -> CompanyFinancials:
        fetched.append(ticker)
        return CompanyFinancials(ticker=ticker, **GOOD)

    main(["screen", "MSFT", "--config", str(config_path)], get=_cached_get(db_path, fake_fetch))

    assert fetched == []


def test_compare_older_interest_income_warning(
    three_standards: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    company = {**GOOD, "interest_income_year": 2023}

    _compare(three_standards, "AAPL", data={"AAPL": company})

    out = capsys.readouterr().out
    # strict mode in the test config, so doubtful fails everywhere
    assert "  AAOIFI: FAIL (doubtful)" in out
    assert "    check by hand: interest income isn't in the latest report" in out
    assert "passes under 0 of 3 standards" in out
