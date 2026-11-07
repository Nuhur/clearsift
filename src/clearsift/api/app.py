from __future__ import annotations

import logging
import re
from collections.abc import Callable
from functools import partial
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from clearsift.api.schemas import (
    ComparisonOut,
    HealthOut,
    ScreenOut,
    ScreenResult,
    StockDetailOut,
    TickerError,
    comparison_out,
    prices_out,
    verdict_out,
)
from clearsift.config import ConfigError, ScreeningConfig
from clearsift.dashboard_data import load_screening_config, parse_tickers
from clearsift.data.cache import get_financials
from clearsift.data.models import CompanyFinancials
from clearsift.data.prices import PricePoint, get_closes
from clearsift.portfolio import PositionSource
from clearsift.screening.screen import compare_stock, screen_stock
from clearsift.t212.client import T212Client

logger = logging.getLogger(__name__)

# letters, digits and the bits yfinance uses, e.g. BRK-B, VOD.L, ^GSPC, GBPUSD=X
_TICKER = re.compile(r"\^?[A-Z0-9][A-Z0-9.\-=]{0,19}")

GENERIC_ERROR = "something went wrong"


def clean_ticker(text: str) -> str | None:
    """Return the ticker in uppercase, or None if it doesn't look like a ticker."""
    ticker = text.strip().upper()
    return ticker if _TICKER.fullmatch(ticker) else None


def create_app(
    config_path: str | Path = "config.yaml",
    get: Callable[..., CompanyFinancials] = get_financials,
    make_client: Callable[[], PositionSource] = T212Client.from_env,
    get_prices: Callable[..., list[PricePoint]] = get_closes,
) -> FastAPI:
    """Build the clearsift API, with the data sources passed in so tests can fake them."""
    app = FastAPI(title="clearsift", docs_url="/api/docs", openapi_url="/api/openapi.json")
    # the portfolio routes need this, kept on the app so they can share it
    app.state.make_client = make_client
    _add_error_handlers(app)

    def load() -> ScreeningConfig:
        # read it every time, so edits to config.yaml show up without a restart
        return load_screening_config(config_path)

    def getter(refresh: bool) -> Callable[..., CompanyFinancials]:
        return partial(get, refresh=True) if refresh else get

    @app.get("/api/health")
    def health() -> HealthOut:
        return HealthOut()

    @app.get("/api/screen")
    def screen(tickers: str, compare: bool = False, refresh: bool = False) -> ScreenOut:
        names = parse_tickers(tickers)
        if not names:
            raise HTTPException(400, "give at least one ticker")
        config = load()
        fetch = getter(refresh)
        results: list[ScreenResult] = []
        for name in names:
            ticker = clean_ticker(name)
            if ticker is None:
                results.append(TickerError(ticker=name, message="that doesn't look like a ticker"))
                continue
            try:
                if compare:
                    verdicts = compare_stock(ticker, config, get=fetch)
                    results.append(comparison_out(verdicts, config.methodology.label))
                else:
                    results.append(verdict_out(screen_stock(ticker, config, get=fetch)))
            except ValueError as exc:
                # one bad ticker shouldn't stop the others from showing
                results.append(TickerError(ticker=ticker, message=str(exc)))
        return ScreenOut(results=results)

    @app.get("/api/stocks/{ticker}")
    def stock(ticker: str, refresh: bool = False) -> StockDetailOut:
        cleaned = clean_ticker(ticker)
        if cleaned is None:
            raise HTTPException(400, "that doesn't look like a ticker")
        config = load()
        try:
            verdicts = compare_stock(cleaned, config, get=getter(refresh))
        except ValueError as exc:
            raise HTTPException(500, str(exc)) from exc
        verdict: ComparisonOut = comparison_out(verdicts, config.methodology.label)
        try:
            prices = get_prices(cleaned, refresh=refresh)
        except Exception:
            # the chart is a nice extra, so a broken price cache shouldn't hide the verdict
            logger.exception("couldn't load prices for %s", cleaned)
            prices = []
        return StockDetailOut(ticker=cleaned, verdict=verdict, prices=prices_out(prices))

    return app


def _add_error_handlers(app: FastAPI) -> None:
    # every error comes back as {"message": ...} so the front end only has one shape to read

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse({"message": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's own message echoes back what was sent, so only name the bad parameters
        names = sorted({str(error["loc"][-1]) for error in exc.errors() if error.get("loc")})
        message = f"bad or missing parameter: {', '.join(names)}" if names else "bad request"
        return JSONResponse({"message": message}, status_code=422)

    @app.exception_handler(ConfigError)
    async def config_error(request: Request, exc: ConfigError) -> JSONResponse:
        # these are our own messages about config.yaml, nothing secret in them
        return JSONResponse({"message": f"config error: {exc}"}, status_code=500)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        # the details go in the server log, never to the browser
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"message": GENERIC_ERROR}, status_code=500)
