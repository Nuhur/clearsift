from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import Literal

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from clearsift.config import ConfigError, ScreeningConfig
from clearsift.dashboard_data import (
    Card,
    Colour,
    ComparisonCard,
    ErrorCard,
    NotCheckedCard,
    StockCard,
    chart_rows,
    holding_card,
    holding_values,
    load_screening_config,
    parse_tickers,
    screen_cards,
)
from clearsift.data.cache import get_financials
from clearsift.portfolio import fetch_positions, portfolio_summary, review_lines, screen_holdings
from clearsift.screening.business import RatioValue
from clearsift.t212.client import T212Client, T212Error

# next to the dashboard folder, so it works whichever folder streamlit is run from
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

# streamlit has no amber, orange is the nearest
BADGE_COLOURS: dict[Colour, Literal["green", "orange", "red"]] = {
    "green": "green",
    "amber": "orange",
    "red": "red",
}


@st.cache_resource
def load_config() -> ScreeningConfig:
    """Load config.yaml once for the whole session."""
    return load_screening_config(CONFIG_PATH)


def main() -> None:
    """Draw the dashboard."""
    st.set_page_config(page_title="Clearsift", page_icon=":material/filter_alt:", layout="wide")
    page = st.sidebar.radio("Page", ["Screener", "My portfolio"])
    st.title("Clearsift")
    try:
        config = load_config()
    except ConfigError as exc:
        st.error(f"config.yaml has a problem: {exc}")
        st.stop()
    if page == "My portfolio":
        portfolio_page(config)
    else:
        screener_page(config)


def screener_page(config: ScreeningConfig) -> None:
    """Screen the tickers typed in and show a card for each."""
    st.header("Screener")
    st.caption(f"{config.methodology.label} standard, {config.mode} mode")

    with st.form("screener"):
        text = st.text_input("Tickers", placeholder="AAPL, MSFT, VOD.L")
        compare = st.toggle("Compare standards")
        refresh = st.toggle("Refresh data")
        submitted = st.form_submit_button("Screen", type="primary")

    if submitted:
        tickers = parse_tickers(text)
        if not tickers:
            st.warning("Type at least one ticker.")
            return
        get = partial(get_financials, refresh=True) if refresh else get_financials
        with st.spinner("Screening..."):
            # kept in the session so the results don't vanish when the page redraws
            st.session_state.screener_cards = screen_cards(tickers, config, compare, get)

    for card in st.session_state.get("screener_cards", []):
        show_card(card)


def portfolio_page(config: ScreeningConfig) -> None:
    """Load the Trading 212 positions when asked, then screen and show each one."""
    st.header("My portfolio")
    st.caption(
        f"{config.methodology.label} standard, {config.mode} mode. "
        "Read-only, nothing here can place, change or cancel an order."
    )

    # outside the form, so switching it on doesn't fetch everything again
    show_values = st.toggle("Show values")
    with st.form("portfolio"):
        compare = st.toggle("Compare standards")
        refresh = st.toggle("Refresh data")
        submitted = st.form_submit_button("Load portfolio", type="primary")

    if submitted:
        # drop the last load first, so an error never sits next to old results
        st.session_state.pop("portfolio_result", None)
        try:
            with st.spinner("Loading positions from Trading 212..."):
                positions = fetch_positions(T212Client.from_env)
        except T212Error as exc:
            # these messages never hold the key, secret or response body
            st.error(f"Trading 212 error: {exc}")
            return
        get = partial(get_financials, refresh=True) if refresh else get_financials
        try:
            with st.spinner("Screening..."):
                holdings = screen_holdings(positions, config, compare, get)
        except ValueError as exc:
            st.error(f"Screening error: {exc}")
            return
        # keep compare with the results, since the toggle can change before the next load
        st.session_state.portfolio_result = (holdings, compare)

    if "portfolio_result" not in st.session_state:
        st.info("Click Load portfolio to read your open positions from Trading 212.")
        return
    holdings, compared = st.session_state.portfolio_result
    if not holdings:
        st.info("No open positions.")
        return

    st.subheader(portfolio_summary(holdings))
    for holding in holdings:
        values = holding_values(holding.position) if show_values else None
        show_card(holding_card(holding, compared), values)

    st.subheader("Review")
    review = review_lines(holdings)
    if review:
        _bullets(review)
    else:
        st.success("Nothing to review.")


def show_card(card: Card, values: list[tuple[str, str]] | None = None) -> None:
    """Draw one card, whichever kind it is."""
    with st.container(border=True):
        if isinstance(card, ErrorCard):
            st.subheader(_escape(card.ticker))
            st.error(card.message)
        elif isinstance(card, NotCheckedCard):
            st.subheader(_escape(card.ticker))
            st.badge("NOT CHECKED", color="orange")
            _values(values)
            st.warning(card.message)
        elif isinstance(card, ComparisonCard):
            show_comparison(card, values)
        else:
            show_stock(card, values)


def show_stock(card: StockCard, values: list[tuple[str, str]] | None = None) -> None:
    """Draw a card for one stock under one standard."""
    _heading(card.ticker, card.result, card.colour, card.company)
    _values(values)
    _warnings(card.warnings)
    if card.purification:
        st.markdown(_escape(card.purification))
    if card.ratios:
        _chart(card.ratios, key=card.ticker)
    _bullets(card.reasons)


def show_comparison(card: ComparisonCard, values: list[tuple[str, str]] | None = None) -> None:
    """Draw a card for one stock under every standard in the config."""
    _heading(card.ticker, f"{card.methodology}: {card.result}", card.colour, card.company)
    _values(values)
    _warnings(card.warnings)
    if card.purification:
        st.markdown(_escape(card.purification))
    _bullets(card.business_reasons)

    tabs = st.tabs([standard.methodology for standard in card.standards])
    for tab, standard in zip(tabs, card.standards, strict=True):
        with tab:
            st.badge(standard.result, color=BADGE_COLOURS[standard.colour])
            if standard.warning:
                st.warning(standard.warning)
            if standard.ratios:
                _chart(standard.ratios, key=f"{card.ticker}-{standard.methodology}")
            _bullets(standard.reasons)

    st.markdown(f"**{_escape(card.summary)}**")


def _heading(ticker: str, result: str, colour: Colour, company: list[str]) -> None:
    st.subheader(_escape(ticker))
    st.badge(result, color=BADGE_COLOURS[colour])
    for line in company:
        st.caption(_escape(line))


def _values(values: list[tuple[str, str]] | None) -> None:
    if values:
        st.markdown("  \n".join(f"**{name}:** {_escape(value)}" for name, value in values))


def _warnings(warnings: list[str]) -> None:
    for warning in warnings:
        st.warning(warning)


def _bullets(lines: list[str]) -> None:
    if lines:
        st.markdown("\n".join(f"- {_escape(line)}" for line in lines))


def _escape(text: str) -> str:
    # streamlit reads $ as maths and * or _ as formatting
    for char in "\\$*_`":
        text = text.replace(char, "\\" + char)
    return text


def _chart(ratios: Sequence[RatioValue], key: str) -> None:
    rows = chart_rows(ratios)
    # one small chart per ratio, each with its own scale, since a 5% limit would
    # look like nothing next to a 50% one
    figure = make_subplots(rows=len(rows), cols=1, vertical_spacing=0.25 / len(rows))
    for i, row in enumerate(rows, start=1):
        figure.add_trace(
            go.Bar(
                x=[row.value],
                y=[row.label],
                orientation="h",
                marker_color=row.colour,
                text=[row.text],
                textposition="auto",
                hovertemplate=f"{row.label}: {row.text}, limit {row.limit:g}%<extra></extra>",
            ),
            row=i,
            col=1,
        )
        figure.add_vline(
            x=row.limit,
            line_dash="dash",
            line_width=2,
            annotation_text=f"limit {row.limit:g}%",
            annotation_position="top",
            row=i,
            col=1,
        )
        figure.update_xaxes(range=[0, row.axis_max], ticksuffix="%", row=i, col=1)
    figure.update_layout(
        height=90 * len(rows) + 30,
        showlegend=False,
        margin={"l": 10, "r": 10, "t": 25, "b": 10},
        bargap=0.3,
    )
    st.plotly_chart(figure, key=key, config={"displayModeBar": False})


main()
