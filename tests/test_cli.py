import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from clearsift.cli import main
from clearsift.data.models import CompanyFinancials

CONFIG: dict[str, Any] = {
    "screening": {
        "mode": "strict",
        "fail_closed": True,
        "max_data_age_days": 120,
        "market_cap_max_age_days": 1,
        "ratios": {
            "max_debt_to_market_cap": 0.30,
            "max_cash_to_market_cap": 0.30,
            "max_impermissible_income": 0.05,
        },
        "excluded_sectors": ["alcohol", "tobacco"],
        "always_exclude_tickers": [],
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
    assert "  - debt is 10.00% of market cap, limit is 30%" in out


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
    assert "  - debt is 40.00% of market cap, limit is 30%" in out


def test_doubtful_fails(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    grocer = {**GOOD, "sector": "Consumer Defensive", "industry": "Grocery Stores"}

    code = _run(config_path, "KR", data={"KR": grocer})

    assert code == 1
    assert "KR: FAIL (doubtful)" in capsys.readouterr().out


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
    assert "screening.mode must be 'strict'" in capsys.readouterr().err


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
