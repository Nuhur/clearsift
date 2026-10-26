from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import fields

from clearsift.config import ConfigError, load_config
from clearsift.data.cache import get_financials
from clearsift.data.models import CompanyFinancials
from clearsift.screening.screen import StockVerdict, screen_stock


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
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    all_pass = True
    for i, ticker in enumerate(args.tickers):
        try:
            verdict = screen_stock(ticker, config.screening, get=get)
        except ValueError as exc:
            # screen_business raises this when config.yaml names a group it can't map
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if i:
            print()
        print(format_verdict(verdict))
        all_pass = all_pass and verdict.passes

    return 0 if all_pass else 1


def format_verdict(verdict: StockVerdict) -> str:
    """Turn a stock's verdict into a short block of text."""
    financials = verdict.financials
    lines = [
        f"{verdict.ticker}: {'PASS' if verdict.passes else 'FAIL'} ({verdict.status})",
        f"  {financials.sector or 'unknown'} / {financials.industry or 'unknown'}",
    ]
    # an empty fetch usually means yfinance fell over, not that the company is bad
    if _has_no_data(financials):
        lines.append("  no data from yfinance, try again later")
    lines += [f"  - {reason}" for reason in verdict.business.reasons + verdict.ratios.reasons]
    return "\n".join(lines)


def _has_no_data(financials: CompanyFinancials) -> bool:
    return all(
        getattr(financials, f.name) is None
        for f in fields(financials)
        if f.name not in ("ticker", "fetched_at")
    )
