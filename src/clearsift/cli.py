from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import fields
from decimal import ROUND_CEILING, Decimal
from functools import partial
from typing import Protocol

from clearsift.config import ConfigError, ScreeningConfig, load_config
from clearsift.data.cache import get_financials
from clearsift.data.models import CompanyFinancials
from clearsift.screening.business import check_excluded_sectors
from clearsift.screening.purification import purification_ratio
from clearsift.screening.screen import StockVerdict, compare_stock, screen_stock
from clearsift.t212.client import T212Client, T212Error
from clearsift.t212.models import Position
from clearsift.t212.tickers import t212_to_yahoo


class PositionSource(Protocol):
    """Anything that can list open positions, e.g. T212Client."""

    def positions(self) -> list[Position]: ...

    def close(self) -> None: ...


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
        client = make_client()
        try:
            positions = client.positions()
        finally:
            client.close()
    except T212Error as exc:
        # these messages never hold the key, secret or response body
        print(f"trading 212 error: {exc}", file=sys.stderr)
        return 2

    if not positions:
        print("no open positions")
        return 0

    holdings: list[str] = []
    not_checked: list[str] = []
    review: list[str] = []
    passed = failed = 0
    for position in positions:
        t212 = position.ticker
        yahoo = t212_to_yahoo(t212) if t212 is not None else None
        if yahoo is None:
            # guessing a ticker could screen the wrong company, so leave it to a human
            label = t212 or "unknown ticker"
            not_checked.append(f"  {label}, {_quantity(position.quantity)}: {_NOT_CONVERTED}")
            review.append(f"  {label}: not checked, {_NOT_CONVERTED}")
            continue

        try:
            text, verdict = _screen_one(yahoo, config, compare, get)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        holdings.append(f"{yahoo} ({t212}), {_quantity(position.quantity)}\n{text}")
        if verdict.passes:
            passed += 1
        else:
            failed += 1
            review.append(f"  {yahoo} ({t212}): FAIL, {_main_reason(verdict)}")

    sections = holdings[:]
    if not_checked:
        sections.append("\n".join(["Not checked", *not_checked]))
    sections.append("\n".join(["Review", *(review or ["  nothing to review"])]))
    count = len(positions)
    sections.append(
        f"{count} holding{'' if count == 1 else 's'}: {passed} pass, {failed} fail, "
        f"{len(not_checked)} not checked"
    )
    print("\n\n".join(sections))

    return 0 if failed == 0 and not not_checked else 1


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
    lines = [f"{verdict.ticker}: {_pass_fail(verdict)}", *_company_lines(verdict)]
    # a fund's own reason already says what to check, the industry warning doesn't fit
    if verdict.needs_review and verdict.business.status == "doubtful" and not verdict.is_fund:
        lines.append(_BUSINESS_WARNING)
    if verdict.needs_review and verdict.ratios.status == "doubtful":
        lines.append(_INTEREST_WARNING)
    if verdict.passes:
        lines.append(_purification_line(verdict))
    lines += [f"  - {reason}" for reason in verdict.business.reasons + verdict.ratios.reasons]
    return "\n".join(lines)


def format_comparison(verdicts: list[StockVerdict]) -> str:
    """Turn one stock's verdicts under several methodologies into a block of text."""
    # the business screen and the data are the same for every methodology
    first = verdicts[0]
    lines = [first.ticker, *_company_lines(first)]
    if first.business.status == "doubtful" and not first.is_fund:
        lines.append(_BUSINESS_WARNING)
    lines += [f"  - {reason}" for reason in first.business.reasons]
    # the ratio is the same under every standard, so show it once
    passing = next((v for v in verdicts if v.passes), None)
    if passing is not None:
        lines.append(_purification_line(passing))

    for verdict in verdicts:
        lines.append(f"  {verdict.methodology}: {_pass_fail(verdict)}")
        if verdict.needs_review and verdict.ratios.status == "doubtful":
            lines.append("  " + _INTEREST_WARNING)
        lines += [f"    - {reason}" for reason in verdict.ratios.reasons]

    passed = sum(v.passes for v in verdicts)
    lines.append(f"  passes under {passed} of {len(verdicts)} standards")
    return "\n".join(lines)


_BUSINESS_WARNING = "  check by hand: the industry label alone can't confirm this business is halal"
_INTEREST_WARNING = "  check by hand: interest income isn't in the latest report"


_NOT_CONVERTED = "couldn't convert ticker, check by hand"


def _main_reason(verdict: StockVerdict) -> str:
    # the screen that set the overall status holds the reason that matters
    business, ratios = verdict.business, verdict.ratios
    if business.status == verdict.status and business.reasons:
        return business.reasons[0]
    # an excluded ratio result only keeps the reasons that didn't pass
    if ratios.status == "excluded" and ratios.reasons:
        return ratios.reasons[0]
    # a doubtful one keeps every reason, so the first could be a harmless pass.
    # Doubt only ever comes from interest income
    if ratios.status == "doubtful":
        return "interest income isn't in the latest report, check by hand"
    return verdict.status


def _quantity(quantity: float | None) -> str:
    if quantity is None:
        return "quantity unknown"
    # fractional shares go to 6 places, but whole ones shouldn't show as 5.000000
    return f"quantity {f'{quantity:.6f}'.rstrip('0').rstrip('.')}"


def _purification_line(verdict: StockVerdict) -> str:
    if verdict.is_fund:
        return "  purification: check the fund's own reports"
    ratio = purification_ratio(verdict)
    # the stock passed, so any other missing number would have failed it. That leaves
    # interest income not being disclosed, which standard mode lets through
    if ratio is None:
        return "  purification: can't work out, interest income not disclosed"
    # round up so following the percentage never means giving too little
    percent = (Decimal(str(ratio)) * 100).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    line = f"  purify {percent}% of dividends"
    year = verdict.ratios.interest_year
    if year != verdict.financials.latest_income_statement_year:
        line += f" (based on {year})"
    return line


def _pass_fail(verdict: StockVerdict) -> str:
    return f"{'PASS' if verdict.passes else 'FAIL'} ({verdict.status})"


def _company_lines(verdict: StockVerdict) -> list[str]:
    financials = verdict.financials
    if financials.is_fund:
        # funds have no sector or industry, so say what kind of fund it is instead
        return [f"  fund ({financials.quote_type})"]
    lines = [f"  {financials.sector or 'unknown'} / {financials.industry or 'unknown'}"]
    # an empty fetch usually means yfinance fell over, not that the company is bad
    if _has_no_data(financials):
        lines.append("  no data from yfinance, try again later")
    return lines


def _has_no_data(financials: CompanyFinancials) -> bool:
    return all(
        getattr(financials, f.name) is None
        for f in fields(financials)
        if f.name not in ("ticker", "fetched_at")
    )
