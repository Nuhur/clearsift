from dataclasses import replace
from pathlib import Path

import pytest

from clearsift.config import Methodology, ScreeningConfig
from clearsift.data.models import CompanyFinancials
from clearsift.screening.business import (
    EXCLUDED_INDUSTRIES,
    KNOWN_INDUSTRIES_BY_SECTOR,
    NEEDS_REVIEW_INDUSTRIES,
    check_excluded_sectors,
    screen_business,
)

AAOIFI = Methodology(
    name="aaoifi",
    denominator="market_cap",
    max_debt=0.30,
    max_cash=0.30,
    max_receivables_and_cash=None,
    max_impermissible_income=0.05,
)

CONFIG = ScreeningConfig(
    mode="strict",
    fail_closed=True,
    max_data_age_days=120,
    market_cap_max_age_days=1,
    max_interest_income_age_years=3,
    methodology=AAOIFI,
    methodologies=(AAOIFI,),
    excluded_sectors=tuple(EXCLUDED_INDUSTRIES),
    always_exclude_tickers=("BAD",),
    approved_funds=(),
)


def _company(
    sector: str | None = "Technology",
    industry: str | None = "Software - Infrastructure",
    ticker: str = "MSFT",
) -> CompanyFinancials:
    return CompanyFinancials(ticker=ticker, sector=sector, industry=industry)


def test_compliant_industry() -> None:
    result = screen_business(_company(), CONFIG)

    assert result.status == "compliant"
    assert result.reasons


@pytest.mark.parametrize(
    ("group", "sector", "industry"),
    [
        ("conventional_banking", "Financial Services", "Banks - Regional"),
        ("conventional_insurance", "Financial Services", "Insurance - Life"),
        ("conventional_insurance", "Healthcare", "Healthcare Plans"),
        ("lending", "Financial Services", "Credit Services"),
        ("alcohol", "Consumer Defensive", "Beverages - Brewers"),
        ("tobacco", "Consumer Defensive", "Tobacco"),
        ("gambling", "Consumer Cyclical", "Resorts & Casinos"),
        ("weapons_and_defence", "Industrials", "Aerospace & Defense"),
    ],
)
def test_excluded_groups(group: str, sector: str, industry: str) -> None:
    result = screen_business(_company(sector, industry), CONFIG)

    assert result.status == "excluded"
    assert group in result.reasons[0]


def test_group_not_in_config_is_not_excluded() -> None:
    config = replace(CONFIG, excluded_sectors=("conventional_banking",))

    result = screen_business(_company("Consumer Defensive", "Tobacco"), config)

    assert result.status == "compliant"


def test_needs_review_industry_is_doubtful() -> None:
    result = screen_business(_company("Consumer Cyclical", "Restaurants"), CONFIG)

    assert result.status == "doubtful"
    assert "Restaurants" in result.reasons[0]


def test_grocery_stores_are_doubtful() -> None:
    result = screen_business(_company("Consumer Defensive", "Grocery Stores"), CONFIG)

    assert result.status == "doubtful"


def test_always_exclude_ticker_beats_compliant_industry() -> None:
    result = screen_business(_company(ticker="BAD"), CONFIG)

    assert result.status == "excluded"
    assert "always-exclude" in result.reasons[0]


def test_always_exclude_ticker_ignores_case() -> None:
    assert screen_business(_company(ticker="bad"), CONFIG).status == "excluded"


def test_always_exclude_checked_before_missing_data() -> None:
    result = screen_business(_company(sector=None, industry=None, ticker="BAD"), CONFIG)

    assert "always-exclude" in result.reasons[0]


def test_missing_sector_is_excluded() -> None:
    result = screen_business(_company(sector=None), CONFIG)

    assert result.status == "excluded"
    assert result.reasons == ["sector is missing"]


def test_missing_industry_is_excluded() -> None:
    result = screen_business(_company(industry=None), CONFIG)

    assert result.status == "excluded"
    assert result.reasons == ["industry is missing"]


def test_unknown_industry_is_excluded() -> None:
    result = screen_business(_company(industry="Quantum Widgets"), CONFIG)

    assert result.status == "excluded"
    assert "Quantum Widgets" in result.reasons[0]


def test_unknown_sector_is_excluded() -> None:
    result = screen_business(_company(sector="Space"), CONFIG)

    assert result.status == "excluded"
    assert "Space" in result.reasons[0]


def test_industry_in_wrong_sector_is_excluded() -> None:
    result = screen_business(_company(sector="Utilities"), CONFIG)

    assert result.status == "excluded"
    assert "doesn't belong" in result.reasons[0]


def test_long_dash_label_is_recognised() -> None:
    result = screen_business(_company(industry="Software—Infrastructure"), CONFIG)

    assert result.status == "compliant"


def test_unmapped_config_group_raises() -> None:
    config = replace(CONFIG, excluded_sectors=("alchohol",))

    with pytest.raises(ValueError, match="alchohol"):
        screen_business(_company(), config)


def test_check_excluded_sectors_names_every_unmapped_group() -> None:
    config = replace(CONFIG, excluded_sectors=("alcohol", "alchohol", "tobaco"))

    with pytest.raises(ValueError, match="alchohol, tobaco"):
        check_excluded_sectors(config)


def test_check_excluded_sectors_passes_when_all_mapped() -> None:
    check_excluded_sectors(replace(CONFIG, excluded_sectors=tuple(EXCLUDED_INDUSTRIES)))


def test_every_mapped_label_is_a_known_industry() -> None:
    known = set().union(*KNOWN_INDUSTRIES_BY_SECTOR.values())
    mapped = {label for labels in EXCLUDED_INDUSTRIES.values() for label in labels}

    assert mapped <= known
    assert NEEDS_REVIEW_INDUSTRIES <= known


def test_every_repo_config_group_is_mapped() -> None:
    from clearsift.config import load_config

    repo_config = Path(__file__).parent.parent / "config.yaml"
    assert set(load_config(repo_config).screening.excluded_sectors) <= set(EXCLUDED_INDUSTRIES)


def test_known_industries_match_installed_yfinance() -> None:
    # if a yfinance update changes Yahoo's labels, this fails so the lists get reviewed
    from yfinance.const import SECTOR_INDUSTY_MAPPING

    expected = {
        sector: {label.replace("—", " - ") for label in labels}
        for sector, labels in SECTOR_INDUSTY_MAPPING.items()
    }
    actual = {sector: set(labels) for sector, labels in KNOWN_INDUSTRIES_BY_SECTOR.items()}

    assert actual == expected
