from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

import yaml

Mode = Literal["strict", "standard"]


class ConfigError(ValueError):
    """Raised when config.yaml is missing a setting or has a bad value."""


@dataclass(frozen=True)
class RatioLimits:
    max_debt_to_market_cap: float
    max_cash_to_market_cap: float
    max_impermissible_income: float


@dataclass(frozen=True)
class ScreeningConfig:
    mode: Mode
    fail_closed: bool
    max_data_age_days: int
    market_cap_max_age_days: int
    ratios: RatioLimits
    excluded_sectors: tuple[str, ...]
    always_exclude_tickers: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    screening: ScreeningConfig
    benchmark_ticker: str | None


def load_config(path: str | Path = "config.yaml") -> Config:
    """Read config.yaml and check every setting is there and makes sense."""
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"can't read {path}: {exc}") from exc

    # fail closed: a broken config should stop everything, not fall back to defaults
    root = _section(raw, "config")
    screening = _section(root.get("screening"), "screening")
    ratios = _section(screening.get("ratios"), "screening.ratios")

    # no fallback: quietly picking a mode could let in stocks you meant to keep out
    mode = screening.get("mode")
    if mode not in get_args(Mode):
        raise ConfigError("screening.mode must be 'strict' or 'standard'")
    # failing closed is a project rule, so the config can't switch it off
    if screening.get("fail_closed") is not True:
        raise ConfigError("screening.fail_closed must be true")

    max_age = _days(screening, "max_data_age_days")
    market_cap_max_age = _days(screening, "market_cap_max_age_days")
    # the whole row goes stale first, so a bigger market cap limit would never kick in
    if market_cap_max_age > max_age:
        raise ConfigError(
            "screening.market_cap_max_age_days can't be bigger than max_data_age_days"
        )

    sectors = screening.get("excluded_sectors")
    # an empty list would let every sector through, so treat it as a mistake
    if (
        not isinstance(sectors, list)
        or not sectors
        or not all(isinstance(s, str) and s.strip() for s in sectors)
    ):
        raise ConfigError("screening.excluded_sectors must be a non-empty list of names")

    tickers = screening.get("always_exclude_tickers")
    # an empty list is fine here, it just means nothing extra gets excluded.
    # Lowercase or padded tickers would silently never match, so refuse them
    if not isinstance(tickers, list) or not all(
        isinstance(t, str) and t and t == t.strip().upper() for t in tickers
    ):
        raise ConfigError("screening.always_exclude_tickers must be a list of uppercase tickers")

    # the benchmark isn't needed for screening, so it can be left out for now
    benchmark = _section(root.get("benchmark") or {}, "benchmark")
    ticker = benchmark.get("ticker")
    if ticker is not None and (not isinstance(ticker, str) or not ticker.strip()):
        raise ConfigError("benchmark.ticker must be a ticker or null")

    return Config(
        screening=ScreeningConfig(
            mode=mode,
            fail_closed=True,
            max_data_age_days=max_age,
            market_cap_max_age_days=market_cap_max_age,
            ratios=RatioLimits(
                max_debt_to_market_cap=_ratio(ratios, "max_debt_to_market_cap"),
                max_cash_to_market_cap=_ratio(ratios, "max_cash_to_market_cap"),
                max_impermissible_income=_ratio(ratios, "max_impermissible_income"),
            ),
            excluded_sectors=tuple(s.strip() for s in sectors),
            always_exclude_tickers=tuple(tickers),
        ),
        benchmark_ticker=ticker.strip() if ticker else None,
    )


def _section(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} is missing or isn't a section")
    return value


def _days(screening: dict[str, Any], name: str) -> int:
    value = screening.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"screening.{name} must be a whole number above 0")
    return value


def _ratio(ratios: dict[str, Any], name: str) -> float:
    value = ratios.get(name)
    # Python counts True and False as numbers, so skip those
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"screening.ratios.{name} must be a number")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ConfigError(f"screening.ratios.{name} must be between 0 and 1")
    return float(value)
