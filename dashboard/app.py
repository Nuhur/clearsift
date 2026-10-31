from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from clearsift.config import ConfigError, ScreeningConfig
from clearsift.dashboard_data import (
    Card,
    Colour,
    ComparisonCard,
    ErrorCard,
    StockCard,
    chart_rows,
    load_screening_config,
    parse_tickers,
    screen_cards,
)
from clearsift.data.cache import get_financials
from clearsift.screening.business import RatioValue

# next to the dashboard folder, so it works whichever folder streamlit is run from
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

# streamlit has no amber, orange is the nearest
BADGE_COLOURS: dict[Colour, str] = {"green": "green", "amber": "orange", "red": "red"}


@st.cache_resource
def load_config() -> ScreeningConfig:
    """Load config.yaml once for the whole session."""
    return load_screening_config(CONFIG_PATH)


def main() -> None:
    """Draw the dashboard."""
    st.set_page_config(page_title="Clearsift", page_icon=":material/filter_alt:")
    st.title("Clearsift")
    try:
        config = load_config()
    except ConfigError as exc:
        st.error(f"config.yaml has a problem: {exc}")
        st.stop()
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


def show_card(card: Card) -> None:
    """Draw one card, whichever kind it is."""
    with st.container(border=True):
        if isinstance(card, ErrorCard):
            st.subheader(card.ticker)
            st.error(card.message)
        elif isinstance(card, ComparisonCard):
            show_comparison(card)
        else:
            show_stock(card)


def show_stock(card: StockCard) -> None:
    """Draw a card for one stock under one standard."""
    _heading(card.ticker, card.result, card.colour, card.company)
    _warnings(card.warnings)
    if card.purification:
        st.markdown(_escape(card.purification))
    if card.ratios:
        _chart(card.ratios, key=card.ticker)
    _bullets(card.reasons)


def show_comparison(card: ComparisonCard) -> None:
    """Draw a card for one stock under every standard in the config."""
    _heading(card.ticker, f"{card.methodology}: {card.result}", card.colour, card.company)
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
    st.subheader(ticker)
    st.badge(result, color=BADGE_COLOURS[colour])
    for line in company:
        st.caption(_escape(line))


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
