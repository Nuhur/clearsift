from __future__ import annotations

import logging
import re
from collections.abc import Callable
from functools import partial
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from clearsift.api.schemas import (
    ComparisonOut,
    HealthOut,
    PortfolioOut,
    ScreenOut,
    ScreenResult,
    StockDetailOut,
    TickerError,
    comparison_out,
    holding_out,
    prices_out,
    verdict_out,
)
from clearsift.config import ConfigError, ScreeningConfig
from clearsift.dashboard_data import load_screening_config, parse_tickers
from clearsift.data.cache import get_financials
from clearsift.data.models import CompanyFinancials
from clearsift.data.prices import PricePoint, get_closes
from clearsift.portfolio import (
    PositionSource,
    fetch_positions,
    portfolio_summary,
    review_lines,
    screen_holdings,
)
from clearsift.screening.screen import compare_stock, screen_stock
from clearsift.t212.client import T212Client, T212ConfigError, T212Error

logger = logging.getLogger(__name__)

# letters, digits and the bits yfinance uses, e.g. BRK-B, VOD.L, ^GSPC, GBPUSD=X
_TICKER = re.compile(r"\^?[A-Z0-9][A-Z0-9.\-=]{0,19}")

GENERIC_ERROR = "something went wrong"

# this talks to your Trading 212 account, so only this machine can reach it
HOST = "127.0.0.1"
PORT = 8000
# where the React app runs in development, nothing else gets to call the API
ALLOWED_ORIGINS = ("http://localhost:5173",)


def clean_ticker(text: str) -> str | None:
    """Return the ticker in uppercase, or None if it doesn't look like a ticker."""
    ticker = text.strip().upper()
    return ticker if _TICKER.fullmatch(ticker) else None


def pick_standard(config: ScreeningConfig, standard: str | None) -> str:
    """Return the label of the asked-for standard, or the config's own if none was asked for."""
    if standard is None:
        return config.methodology.label
    by_name = {m.name.lower(): m for m in config.methodologies}
    method = by_name.get(standard.strip().lower())
    if method is None:
        # the names come from config.yaml, so listing them gives nothing away
        raise HTTPException(422, f"standard must be one of: {', '.join(by_name)}")
    return method.label


def create_app(
    config_path: str | Path = "config.yaml",
    get: Callable[..., CompanyFinancials] = get_financials,
    make_client: Callable[[], PositionSource] = T212Client.from_env,
    get_prices: Callable[..., list[PricePoint]] = get_closes,
) -> FastAPI:
    """Build the clearsift API, with the data sources passed in so tests can fake them."""
    app = FastAPI(
        title="clearsift",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
    )
    # nothing here changes anything, so the browser only ever needs GET
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_methods=["GET"],
        allow_credentials=False,
    )
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
    def stock(ticker: str, refresh: bool = False, standard: str | None = None) -> StockDetailOut:
        cleaned = clean_ticker(ticker)
        if cleaned is None:
            raise HTTPException(400, "that doesn't look like a ticker")
        config = load()
        chosen = pick_standard(config, standard)
        try:
            verdicts = compare_stock(cleaned, config, get=getter(refresh))
        except ValueError as exc:
            raise HTTPException(500, str(exc)) from exc
        verdict: ComparisonOut = comparison_out(verdicts, chosen)
        try:
            prices = get_prices(cleaned, refresh=refresh)
        except Exception:
            # the chart is a nice extra, so a broken price cache shouldn't hide the verdict
            logger.exception("couldn't load prices for %s", cleaned)
            prices = []
        return StockDetailOut(ticker=cleaned, verdict=verdict, prices=prices_out(prices))

    @app.get("/api/portfolio")
    def portfolio(
        compare: bool = False, refresh: bool = False, show_values: bool = False
    ) -> PortfolioOut:
        config = load()
        try:
            positions = fetch_positions(make_client)
        except T212ConfigError as exc:
            # these messages only name what's missing, never what the key or secret hold
            raise HTTPException(500, f"Trading 212 error: {exc}") from exc
        except T212Error as exc:
            # these never hold the key, secret or response body, just the status and path
            raise HTTPException(502, f"Trading 212 error: {exc}") from exc
        try:
            holdings = screen_holdings(positions, config, compare, getter(refresh))
        except ValueError as exc:
            raise HTTPException(500, f"screening error: {exc}") from exc
        return PortfolioOut(
            holdings=[holding_out(h, compare, show_values) for h in holdings],
            summary=portfolio_summary(holdings),
            review=review_lines(holdings),
        )

    return app


def serve(
    config_path: str | Path = "config.yaml",
    *,
    get: Callable[..., CompanyFinancials] = get_financials,
    make_client: Callable[[], PositionSource] = T212Client.from_env,
    run: Callable[..., None] = uvicorn.run,
) -> None:
    """Start the API on this machine only, at http://127.0.0.1:8000."""
    run(create_app(config_path, get=get, make_client=make_client), host=HOST, port=PORT)


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
