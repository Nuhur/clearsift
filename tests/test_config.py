import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from clearsift.config import ConfigError, load_config

REPO_CONFIG = Path(__file__).parent.parent / "config.yaml"

VALID: dict[str, Any] = {
    "screening": {
        "mode": "strict",
        "fail_closed": True,
        "max_data_age_days": 120,
        "market_cap_max_age_days": 1,
        "max_interest_income_age_years": 3,
        "ratios": {
            "max_debt_to_market_cap": 0.30,
            "max_cash_to_market_cap": 0.30,
            "max_impermissible_income": 0.0,
        },
        "excluded_sectors": ["sector_a", "sector_b"],
        "always_exclude_tickers": ["ABC", "VOD.L"],
    },
    "benchmark": {"ticker": None},
}


def _write(tmp_path: Path, data: Any) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _valid() -> dict[str, Any]:
    return copy.deepcopy(VALID)


def test_repo_config_loads() -> None:
    cfg = load_config(REPO_CONFIG)

    assert cfg.screening.mode == "standard"
    assert cfg.screening.ratios.max_impermissible_income == 0.05
    assert cfg.screening.fail_closed is True
    assert cfg.screening.excluded_sectors


def test_valid_config_values(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _valid()))

    assert cfg.screening.max_data_age_days == 120
    assert cfg.screening.market_cap_max_age_days == 1
    assert cfg.screening.max_interest_income_age_years == 3
    assert cfg.screening.ratios.max_debt_to_market_cap == 0.30
    assert cfg.screening.ratios.max_cash_to_market_cap == 0.30
    assert cfg.screening.ratios.max_impermissible_income == 0.0
    assert cfg.screening.excluded_sectors == ("sector_a", "sector_b")
    assert cfg.screening.always_exclude_tickers == ("ABC", "VOD.L")
    assert cfg.benchmark_ticker is None


def test_benchmark_ticker_set(tmp_path: Path) -> None:
    data = _valid()
    data["benchmark"]["ticker"] = "ISWD"

    assert load_config(_write(tmp_path, data)).benchmark_ticker == "ISWD"


def test_missing_benchmark_is_none(tmp_path: Path) -> None:
    data = _valid()
    del data["benchmark"]

    assert load_config(_write(tmp_path, data)).benchmark_ticker is None


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_bad_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("screening: [unclosed", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(path)


def test_empty_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize("value", [None, True, "0.3", float("nan"), float("inf"), -0.1, 1.5])
def test_bad_ratio_raises(tmp_path: Path, value: Any) -> None:
    data = _valid()
    data["screening"]["ratios"]["max_debt_to_market_cap"] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


def test_missing_ratio_raises(tmp_path: Path) -> None:
    data = _valid()
    del data["screening"]["ratios"]["max_cash_to_market_cap"]

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


def test_missing_ratios_section_raises(tmp_path: Path) -> None:
    data = _valid()
    del data["screening"]["ratios"]

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


@pytest.mark.parametrize("value", ["strict", "standard"])
def test_both_modes_load(tmp_path: Path, value: str) -> None:
    data = _valid()
    data["screening"]["mode"] = value

    assert load_config(_write(tmp_path, data)).screening.mode == value


@pytest.mark.parametrize("value", ["relaxed", "Strict", "", None, True])
def test_bad_mode_raises(tmp_path: Path, value: Any) -> None:
    data = _valid()
    data["screening"]["mode"] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


def test_missing_mode_raises(tmp_path: Path) -> None:
    data = _valid()
    del data["screening"]["mode"]

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


@pytest.mark.parametrize("value", [False, None, "true"])
def test_fail_closed_must_be_true(tmp_path: Path, value: Any) -> None:
    data = _valid()
    data["screening"]["fail_closed"] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


@pytest.mark.parametrize("value", [0, -5, True, 1.5, "120", None])
def test_bad_max_data_age_raises(tmp_path: Path, value: Any) -> None:
    data = _valid()
    data["screening"]["max_data_age_days"] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


@pytest.mark.parametrize("value", [0, -5, True, 1.5, "1", None])
def test_bad_market_cap_max_age_raises(tmp_path: Path, value: Any) -> None:
    data = _valid()
    data["screening"]["market_cap_max_age_days"] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


def test_missing_market_cap_max_age_raises(tmp_path: Path) -> None:
    data = _valid()
    del data["screening"]["market_cap_max_age_days"]

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


def test_market_cap_max_age_bigger_than_max_data_age_raises(tmp_path: Path) -> None:
    data = _valid()
    data["screening"]["market_cap_max_age_days"] = 121

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


def test_market_cap_max_age_equal_to_max_data_age_is_fine(tmp_path: Path) -> None:
    data = _valid()
    data["screening"]["market_cap_max_age_days"] = 120

    assert load_config(_write(tmp_path, data)).screening.market_cap_max_age_days == 120


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "3", None])
def test_bad_interest_income_age_raises(tmp_path: Path, value: Any) -> None:
    data = _valid()
    data["screening"]["max_interest_income_age_years"] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


def test_missing_interest_income_age_raises(tmp_path: Path) -> None:
    data = _valid()
    del data["screening"]["max_interest_income_age_years"]

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


@pytest.mark.parametrize("value", [[], None, "sector_a", ["sector_a", ""], ["sector_a", 3]])
def test_bad_excluded_sectors_raises(tmp_path: Path, value: Any) -> None:
    data = _valid()
    data["screening"]["excluded_sectors"] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


def test_empty_always_exclude_tickers_is_fine(tmp_path: Path) -> None:
    data = _valid()
    data["screening"]["always_exclude_tickers"] = []

    assert load_config(_write(tmp_path, data)).screening.always_exclude_tickers == ()


@pytest.mark.parametrize("value", [None, "ABC", ["abc"], ["ABC", ""], [" ABC"], ["ABC", 3]])
def test_bad_always_exclude_tickers_raises(tmp_path: Path, value: Any) -> None:
    data = _valid()
    data["screening"]["always_exclude_tickers"] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


def test_missing_always_exclude_tickers_raises(tmp_path: Path) -> None:
    data = _valid()
    del data["screening"]["always_exclude_tickers"]

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))


@pytest.mark.parametrize("value", ["", 123])
def test_bad_benchmark_ticker_raises(tmp_path: Path, value: Any) -> None:
    data = _valid()
    data["benchmark"]["ticker"] = value

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))
