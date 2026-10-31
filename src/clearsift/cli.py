from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import fields
from decimal import ROUND_CEILING, Decimal
from functools import partial

from clearsift.config import ConfigError, ScreeningConfig, load_config
from clearsift.data.cache import get_financials
from clearsift.data.models import CompanyFinancials
from clearsift.portfolio import (
    NOT_CONVERTED,
    Holding,
    PositionSource,
    fetch_positions,
    portfolio_summary,
    quantity_text,
    review_lines,
    screen_holdings,
)
from clearsift.screening.business import check_excluded_sectors
from clearsift.screening.purification import purification_ratio
from clearsift.screening.screen import StockVerdict, compare_stock, screen_stock
from clearsift.t212.client import T212Client, T212Error


def main(
    argv: list[str] | None = None,
    get: Callable[..., CompanyFinancials] = get_financials,
    make_client: Callable[[], PositionSource] = T212Client.from_env,
) -> int:
    """Run the clearsift command line and return the exit code."""
    parser = argparse.ArgumentParser(prog="clearsift", description="Halal stock screener.")
    commands = parser.add_subparsers(dest="command", required=True)
    screen = commands.add_parser("screen", help="screen one or more stocks")
    screen.add_argument("tickers", nargs="+", metavar="TICKER")
    portfolio = commands.add_parser("portfolio", help="screen your open Trading 212 positions")
    for command in (screen, portfolio):
        command.add_argument("--config", default="config.yaml", help="path to config.yaml")
        command.add_argument(
            "--compare", action="store_true", help="show the result under every methodology"
        )
        command.add_argument(
            "--refresh", action="store_true", help="ignore the cache and fetch fresh data"
        )
    args = parser.parse_args(argv)

    if args.refresh:
        get = partial(get, refresh=True)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    # funds skip the business screen, so a funds-only run would never hit this otherwise
    try:
        check_excluded_sectors(config.screening)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "portfolio":
        return _run_portfolio(config.screening, args.compare, get, make_client)
    return _run_screen(args.tickers, config.screening, args.compare, get)


def _run_screen(
    tickers: list[str],
    config: ScreeningConfig,
    compare: bool,
    get: Callable[..., CompanyFinancials],
) -> int:
    all_pass = True
    for i, ticker in enumerate(tickers):
        try:
            text, verdict = _screen_one(ticker, config, compare, get)
        except ValueError as exc:
            # screen_business raises this when config.yaml names a group it can't map
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if i:
            print()
        print(text)
        all_pass = all_pass and verdict.passes

    return 0 if all_pass else 1


def _run_portfolio(
    config: ScreeningConfig,
    compare: bool,
    get: Callable[..., CompanyFinancials],
    make_client: Callable[[], PositionSource],
) -> int:
    try:
        positions = fetch_positions(make_client)
    except T212Error as exc:
        # these messages never hold the key, secret or response body
        print(f"trading 212 error: {exc}", file=sys.stderr)
        return 2

    if not positions:
        print("no open positions")
        return 0

    try:
        holdings = screen_holdings(positions, config, compare, get)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    checked = [h for h in holdings if h.verdict is not None]
    not_checked = [
        f"  {h.label}, {_quantity(h)}: {NOT_CONVERTED}" for h in holdings if h.verdict is None
    ]
    sections = [f"{h.title}, {_quantity(h)}\n{_holding_text(h, compare)}" for h in checked]
    if not_checked:
        sections.append("\n".join(["Not checked", *not_checked]))
    review = _indent(review_lines(holdings)) or ["  nothing to review"]
    sections.append("\n".join(["Review", *review]))
    sections.append(portfolio_summary(holdings))
    print("\n\n".join(sections))

    return 0 if all(h.verdict is not None and h.verdict.passes for h in holdings) else 1


def _holding_text(holding: Holding, compare: bool) -> str:
    # without compare there's only the one verdict
    if compare:
        return format_comparison(holding.verdicts)
    return format_verdict(holding.verdicts[0])


def _quantity(holding: Holding) -> str:
    return f"quantity {quantity_text(holding.position.quantity)}"


def _screen_one(
    ticker: str,
    config: ScreeningConfig,
    compare: bool,
    get: Callable[..., CompanyFinancials],
) -> tuple[str, StockVerdict]:
    if not compare:
        verdict = screen_stock(ticker, config, get=get)
        return format_verdict(verdict), verdict
    verdicts = compare_stock(ticker, config, get=get)
    # pass or fail still follows the methodology picked in the config
    chosen = next(v for v in verdicts if v.methodology == config.methodology.label)
    return format_comparison(verdicts), chosen


def format_verdict(verdict: StockVerdict) -> str:
    """Turn a stock's verdict into a short block of text."""
    lines = [f"{verdict.ticker}: {pass_fail(verdict)}", *_indent(company_lines(verdict))]
    lines += _indent(warnings(verdict))
    if verdict.passes:
        lines.append("  " + purification_line(verdict))
    lines += [f"  - {reason}" for reason in verdict.business.reasons + verdict.ratios.reasons]
    return "\n".join(lines)


def format_comparison(verdicts: list[StockVerdict]) -> str:
    """Turn one stock's verdicts under several methodologies into a block of text."""
    # the business screen and the data are the same for every methodology
    first = verdicts[0]
    lines = [first.ticker, *_indent(company_lines(first))]
    if warning := business_warning(first):
        lines.append("  " + warning)
    lines += [f"  - {reason}" for reason in first.business.reasons]
    # the ratio is the same under every standard, so show it once
    passing = next((v for v in verdicts if v.passes), None)
    if passing is not None:
        lines.append("  " + purification_line(passing))

    for verdict in verdicts:
        lines.append(f"  {verdict.methodology}: {pass_fail(verdict)}")
        if warning := interest_warning(verdict):
            lines.append("    " + warning)
        lines += [f"    - {reason}" for reason in verdict.ratios.reasons]

    lines.append("  " + standards_summary(verdicts))
    return "\n".join(lines)


BUSINESS_WARNING = "check by hand: the industry label alone can't confirm this business is halal"
INTEREST_WARNING = "check by hand: interest income isn't in the latest report"


def warnings(verdict: StockVerdict) -> list[str]:
    """List the check-by-hand warnings for one verdict."""
    if not verdict.needs_review:
        return []
    found = [business_warning(verdict), interest_warning(verdict)]
    return [warning for warning in found if warning]


def business_warning(verdict: StockVerdict) -> str | None:
    """Give the industry warning if the business screen was doubtful."""
    # a fund's own reason already says what to check, the industry warning doesn't fit
    if verdict.business.status == "doubtful" and not verdict.is_fund:
        return BUSINESS_WARNING
    return None


def interest_warning(verdict: StockVerdict) -> str | None:
    """Give the interest income warning if that's what made the verdict doubtful."""
    if verdict.needs_review and verdict.ratios.status == "doubtful":
        return INTEREST_WARNING
    return None


def standards_summary(verdicts: list[StockVerdict]) -> str:
    """Say how many of the standards a stock passes under."""
    passed = sum(v.passes for v in verdicts)
    return f"passes under {passed} of {len(verdicts)} standards"


def purification_line(verdict: StockVerdict) -> str:
    """Say how much of a passing stock's dividends to give away."""
    if verdict.is_fund:
        return "purification: check the fund's own reports"
    ratio = purification_ratio(verdict)
    # the stock passed, so any other missing number would have failed it. That leaves
    # interest income not being disclosed, which standard mode lets through
    if ratio is None:
        return "purification: can't work out, interest income not disclosed"
    # round up so following the percentage never means giving too little
    percent = (Decimal(str(ratio)) * 100).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    line = f"purify {percent}% of dividends"
    year = verdict.ratios.interest_year
    if year != verdict.financials.latest_income_statement_year:
        line += f" (based on {year})"
    return line


def pass_fail(verdict: StockVerdict) -> str:
    """Say PASS or FAIL with the status, e.g. PASS (doubtful)."""
    return f"{'PASS' if verdict.passes else 'FAIL'} ({verdict.status})"


def company_lines(verdict: StockVerdict) -> list[str]:
    """Describe what the company does, or what kind of fund it is."""
    financials = verdict.financials
    if financials.is_fund:
        # funds have no sector or industry, so say what kind of fund it is instead
        return [f"fund ({financials.quote_type})"]
    lines = [f"{financials.sector or 'unknown'} / {financials.industry or 'unknown'}"]
    # an empty fetch usually means yfinance fell over, not that the company is bad
    if _has_no_data(financials):
        lines.append("no data from yfinance, try again later")
    return lines


def _indent(lines: list[str]) -> list[str]:
    return ["  " + line for line in lines]


def _has_no_data(financials: CompanyFinancials) -> bool:
    return all(
        getattr(financials, f.name) is None
        for f in fields(financials)
        if f.name not in ("ticker", "fetched_at")
    )
