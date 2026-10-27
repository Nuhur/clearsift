from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from clearsift.config import ScreeningConfig
from clearsift.data.models import CompanyFinancials

Status = Literal["compliant", "doubtful", "excluded"]


@dataclass(frozen=True)
class ScreenResult:
    status: Status
    reasons: list[str]
    # only the ratio screen fills these, purification needs the actual number
    interest_ratio: float | None = None
    interest_year: int | None = None


# Which Yahoo industries each excluded group in config.yaml covers.
# A group only gets excluded if it's also listed in screening.excluded_sectors.
EXCLUDED_INDUSTRIES: dict[str, tuple[str, ...]] = {
    "conventional_banking": ("Banks - Diversified", "Banks - Regional"),
    "conventional_insurance": (
        "Insurance - Diversified",
        "Insurance - Life",
        "Insurance - Property & Casualty",
        "Insurance - Reinsurance",
        "Insurance - Specialty",
        "Insurance Brokers",
        # health insurers, e.g. UnitedHealth
        "Healthcare Plans",
    ),
    "lending": ("Credit Services", "Mortgage Finance", "REIT - Mortgage"),
    "alcohol": ("Beverages - Brewers", "Beverages - Wineries & Distilleries"),
    # no label is pork-only, so pork producers get caught by the review set
    "pork": (),
    "tobacco": ("Tobacco",),
    "gambling": ("Gambling", "Resorts & Casinos"),
    # no label is adult-only, so use always_exclude_tickers for these
    "adult_entertainment": (),
    "weapons_and_defence": ("Aerospace & Defense",),
}

# Industries where the label alone can't tell us if the business is halal.
NEEDS_REVIEW_INDUSTRIES: frozenset[str] = frozenset(
    {
        "Packaged Foods",
        "Restaurants",
        "Lodging",
        "Entertainment",
        "Asset Management",
        "Capital Markets",
        # meat producers, could be pork
        "Farm Products",
        # often distributes alcohol and pork
        "Food Distribution",
        # zero tolerance on impermissible income, and these sell alcohol and pork
        "Grocery Stores",
        "Discount Stores",
        "Department Stores",
        # same problem as Lodging
        "REIT - Hotel & Motel",
        # cruise lines run casinos and bars
        "Travel Services",
        # mixed, usually includes banking
        "Financial Conglomerates",
        # exchanges trade interest products
        "Financial Data & Stock Exchanges",
        # SPACs, the real business isn't known yet
        "Shell Companies",
        # mixed businesses, the label tells us nothing
        "Conglomerates",
    }
)

# Every Yahoo sector and its industries, copied from yfinance 1.7.0 (yfinance/const.py).
# Copied rather than imported because that file is yfinance's internals and could change.
KNOWN_INDUSTRIES_BY_SECTOR: dict[str, frozenset[str]] = {
    "Basic Materials": frozenset(
        {
            "Agricultural Inputs",
            "Aluminum",
            "Building Materials",
            "Chemicals",
            "Coking Coal",
            "Copper",
            "Gold",
            "Lumber & Wood Production",
            "Other Industrial Metals & Mining",
            "Other Precious Metals & Mining",
            "Paper & Paper Products",
            "Silver",
            "Specialty Chemicals",
            "Steel",
        }
    ),
    "Communication Services": frozenset(
        {
            "Advertising Agencies",
            "Broadcasting",
            "Electronic Gaming & Multimedia",
            "Entertainment",
            "Internet Content & Information",
            "Publishing",
            "Telecom Services",
        }
    ),
    "Consumer Cyclical": frozenset(
        {
            "Apparel Manufacturing",
            "Apparel Retail",
            "Auto & Truck Dealerships",
            "Auto Manufacturers",
            "Auto Parts",
            "Department Stores",
            "Footwear & Accessories",
            "Furnishings, Fixtures & Appliances",
            "Gambling",
            "Home Improvement Retail",
            "Internet Retail",
            "Leisure",
            "Lodging",
            "Luxury Goods",
            "Packaging & Containers",
            "Personal Services",
            "Recreational Vehicles",
            "Residential Construction",
            "Resorts & Casinos",
            "Restaurants",
            "Specialty Retail",
            "Textile Manufacturing",
            "Travel Services",
        }
    ),
    "Consumer Defensive": frozenset(
        {
            "Beverages - Brewers",
            "Beverages - Non-Alcoholic",
            "Beverages - Wineries & Distilleries",
            "Confectioners",
            "Discount Stores",
            "Education & Training Services",
            "Farm Products",
            "Food Distribution",
            "Grocery Stores",
            "Household & Personal Products",
            "Packaged Foods",
            "Tobacco",
        }
    ),
    "Energy": frozenset(
        {
            "Oil & Gas Drilling",
            "Oil & Gas E&P",
            "Oil & Gas Equipment & Services",
            "Oil & Gas Integrated",
            "Oil & Gas Midstream",
            "Oil & Gas Refining & Marketing",
            "Thermal Coal",
            "Uranium",
        }
    ),
    "Financial Services": frozenset(
        {
            "Asset Management",
            "Banks - Diversified",
            "Banks - Regional",
            "Capital Markets",
            "Credit Services",
            "Financial Conglomerates",
            "Financial Data & Stock Exchanges",
            "Insurance Brokers",
            "Insurance - Diversified",
            "Insurance - Life",
            "Insurance - Property & Casualty",
            "Insurance - Reinsurance",
            "Insurance - Specialty",
            "Mortgage Finance",
            "Shell Companies",
        }
    ),
    "Healthcare": frozenset(
        {
            "Biotechnology",
            "Diagnostics & Research",
            "Drug Manufacturers - General",
            "Drug Manufacturers - Specialty & Generic",
            "Health Information Services",
            "Healthcare Plans",
            "Medical Care Facilities",
            "Medical Devices",
            "Medical Distribution",
            "Medical Instruments & Supplies",
            "Pharmaceutical Retailers",
        }
    ),
    "Industrials": frozenset(
        {
            "Aerospace & Defense",
            "Airlines",
            "Airports & Air Services",
            "Building Products & Equipment",
            "Business Equipment & Supplies",
            "Conglomerates",
            "Consulting Services",
            "Electrical Equipment & Parts",
            "Engineering & Construction",
            "Farm & Heavy Construction Machinery",
            "Industrial Distribution",
            "Infrastructure Operations",
            "Integrated Freight & Logistics",
            "Marine Shipping",
            "Metal Fabrication",
            "Pollution & Treatment Controls",
            "Railroads",
            "Rental & Leasing Services",
            "Security & Protection Services",
            "Specialty Business Services",
            "Specialty Industrial Machinery",
            "Staffing & Employment Services",
            "Tools & Accessories",
            "Trucking",
            "Waste Management",
        }
    ),
    "Real Estate": frozenset(
        {
            "REIT - Diversified",
            "REIT - Healthcare Facilities",
            "REIT - Hotel & Motel",
            "REIT - Industrial",
            "REIT - Mortgage",
            "REIT - Office",
            "REIT - Residential",
            "REIT - Retail",
            "REIT - Specialty",
            "Real Estate Services",
            "Real Estate - Development",
            "Real Estate - Diversified",
        }
    ),
    "Technology": frozenset(
        {
            "Communication Equipment",
            "Computer Hardware",
            "Consumer Electronics",
            "Electronic Components",
            "Electronics & Computer Distribution",
            "Information Technology Services",
            "Scientific & Technical Instruments",
            "Semiconductor Equipment & Materials",
            "Semiconductors",
            "Software - Application",
            "Software - Infrastructure",
            "Solar",
        }
    ),
    "Utilities": frozenset(
        {
            "Utilities - Diversified",
            "Utilities - Independent Power Producers",
            "Utilities - Regulated Electric",
            "Utilities - Regulated Gas",
            "Utilities - Regulated Water",
            "Utilities - Renewable",
        }
    ),
}


def check_excluded_sectors(config: ScreeningConfig) -> None:
    """Raise ValueError if any excluded sector in the config has no industry mapping."""
    unmapped = [name for name in config.excluded_sectors if name not in EXCLUDED_INDUSTRIES]
    # a typo in config.yaml would quietly let a whole group through, so stop here
    if unmapped:
        raise ValueError(f"no industry mapping for excluded sectors: {', '.join(unmapped)}")


def screen_business(financials: CompanyFinancials, config: ScreeningConfig) -> ScreenResult:
    """Check whether a company's line of business is allowed."""
    # the CLI checks this up front too, but anything else calling in still needs stopping
    check_excluded_sectors(config)

    ticker = financials.ticker.strip().upper()
    if ticker in config.always_exclude_tickers:
        return ScreenResult("excluded", [f"{ticker} is on the always-exclude list"])

    # fail closed: without both labels we can't tell what the company does
    missing = [
        f"{name} is missing"
        for name, value in (("sector", financials.sector), ("industry", financials.industry))
        if value is None
    ]
    if missing:
        return ScreenResult("excluded", missing)

    sector = _normalise(financials.sector)
    industry = _normalise(financials.industry)
    if sector not in KNOWN_INDUSTRIES_BY_SECTOR:
        return ScreenResult("excluded", [f"sector '{sector}' isn't one we recognise"])
    if not any(industry in industries for industries in KNOWN_INDUSTRIES_BY_SECTOR.values()):
        return ScreenResult("excluded", [f"industry '{industry}' isn't one we recognise"])
    # the labels contradict each other, so we can't trust either of them
    if industry not in KNOWN_INDUSTRIES_BY_SECTOR[sector]:
        return ScreenResult(
            "excluded", [f"industry '{industry}' doesn't belong to sector '{sector}'"]
        )

    for name in config.excluded_sectors:
        if industry in EXCLUDED_INDUSTRIES[name]:
            return ScreenResult(
                "excluded", [f"industry '{industry}' falls under excluded group '{name}'"]
            )

    if industry in NEEDS_REVIEW_INDUSTRIES:
        return ScreenResult(
            "doubtful", [f"industry '{industry}' can't be judged from its label, check by hand"]
        )

    return ScreenResult("compliant", [f"industry '{industry}' isn't excluded or marked for review"])


def _normalise(label: str) -> str:
    # yfinance has used both "Banks—Diversified" and "Banks - Diversified" over time
    label = label.replace("—", " - ").replace("–", " - ")
    return " ".join(label.split())
