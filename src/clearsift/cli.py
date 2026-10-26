from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import fields

from clearsift.config import ConfigError, load_config
from clearsift.data.cache import get_financials
from clearsift.data.models import CompanyFinancials
from clearsift.screening.screen import StockVerdict, compare_stock, screen_stock


def main(
    argv: list[str] | None = None,
    get: Callable[..., CompanyFinancials] = get_financials,
) -> int:
    """Run the clearsift command line and return the exit code."""
    parser = argparse.ArgumentParser(prog="clearsift", description="Halal stock screener.")
    commands = parser.add_subparsers(dest="command", required=True)
    screen = commands.add_parser("screen", help="screen one or more stocks")
    screen.add_argument("tickers", nargs="+", metavar="TICKER")
    screen.add_argument("--config", default="config.yaml", help="path to config.yaml")
    screen.add_argument(
        "--compare", action="store_true", help="show the result under every methodology"
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    all_pass = True
    for i, ticker in enumerate(args.tickers):
        try:
            if args.compare:
                verdicts = compare_stock(ticker, config.screening, get=get)
                text = format_comparison(verdicts)
                # the exit code still follows the methodology picked in the config
                chosen = config.screening.methodology.label
                passes = next(v.passes for v in verdicts if v.methodology == chosen)
            else:
                verdict = screen_stock(ticker, config.screening, get=get)
                text = format_verdict(verdict)
                passes = verdict.passes
        except ValueError as exc:
            # screen_business raises this when config.yaml names a group it can't map
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if i:
            print()
        print(text)
        all_pass = all_pass and passes

    return 0 if all_pass else 1


def format_verdict(verdict: StockVerdict) -> str:
    """Turn a stock's verdict into a short block of text."""
    lines = [f"{verdict.ticker}: {_pass_fail(verdict)}", *_company_lines(verdict)]
    if verdict.needs_review and verdict.business.status == "doubtful":
        lines.append(_BUSINESS_WARNING)
    if verdict.needs_review and verdict.ratios.status == "doubtful":
        lines.append(_INTEREST_WARNING)
    lines += [f"  - {reason}" for reason in verdict.business.reasons + verdict.ratios.reasons]
    return "\n".join(lines)


def format_comparison(verdicts: list[StockVerdict]) -> str:
    """Turn one stock's verdicts under several methodologies into a block of text."""
    # the business screen and the data are the same for every methodology
    first = verdicts[0]
    lines = [first.ticker, *_company_lines(first)]
    if first.business.status == "doubtful":
        lines.append(_BUSINESS_WARNING)
    lines += [f"  - {reason}" for reason in first.business.reasons]

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


def _pass_fail(verdict: StockVerdict) -> str:
    return f"{'PASS' if verdict.passes else 'FAIL'} ({verdict.status})"


def _company_lines(verdict: StockVerdict) -> list[str]:
    financials = verdict.financials
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
