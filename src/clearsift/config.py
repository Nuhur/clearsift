from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

import yaml

Mode = Literal["strict", "standard"]
Denominator = Literal["market_cap", "total_assets"]


class ConfigError(ValueError):
    """Raised when config.yaml is missing a setting or has a bad value."""


@dataclass(frozen=True)
class Methodology:
    name: str
    denominator: Denominator
    max_debt: float
    max_cash: float
    max_receivables_and_cash: float | None
    max_impermissible_income: float

    @property
    def label(self) -> str:
        """The name as it should appear in reasons, e.g. AAOIFI."""
        return self.name.upper()


@dataclass(frozen=True)
class ScreeningConfig:
    mode: Mode
    fail_closed: bool
    max_data_age_days: int
    market_cap_max_age_days: int
    max_interest_income_age_years: int
    # the one used for screening, plus every one in the config for comparing
    methodology: Methodology
    methodologies: tuple[Methodology, ...]
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
    interest_income_max_age = _days(screening, "max_interest_income_age_years")

    raw_methodologies = _section(screening.get("methodologies"), "screening.methodologies")
    if not raw_methodologies:
        raise ConfigError("screening.methodologies must list at least one standard")
    methodologies = tuple(_methodology(name, value) for name, value in raw_methodologies.items())
    chosen = screening.get("methodology")
    by_name = {m.name: m for m in methodologies}
    if chosen not in by_name:
        raise ConfigError(f"screening.methodology must be one of: {', '.join(by_name)}")

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
            max_interest_income_age_years=interest_income_max_age,
            methodology=by_name[chosen],
            methodologies=methodologies,
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


def _methodology(name: Any, value: Any) -> Methodology:
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("screening.methodologies names must be text")
    path = f"screening.methodologies.{name}"
    section = _section(value, path)

    denominator = section.get("denominator")
    if denominator not in get_args(Denominator):
        raise ConfigError(f"{path}.denominator must be 'market_cap' or 'total_assets'")

    # null switches the check off, but leaving the key out is more likely a mistake
    if "max_receivables_and_cash" not in section:
        raise ConfigError(f"{path}.max_receivables_and_cash is missing (use null to skip it)")
    receivables = section["max_receivables_and_cash"]

    return Methodology(
        name=name,
        denominator=denominator,
        max_debt=_ratio(section, "max_debt", path),
        max_cash=_ratio(section, "max_cash", path),
        max_receivables_and_cash=(
            None if receivables is None else _ratio(section, "max_receivables_and_cash", path)
        ),
        max_impermissible_income=_ratio(section, "max_impermissible_income", path),
    )


def _ratio(section: dict[str, Any], name: str, path: str) -> float:
    value = section.get(name)
    # Python counts True and False as numbers, so skip those
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path}.{name} must be a number")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ConfigError(f"{path}.{name} must be between 0 and 1")
    return float(value)
