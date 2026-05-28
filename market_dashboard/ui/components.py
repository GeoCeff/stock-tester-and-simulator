"""Shared broker-style UI components for the Streamlit dashboard."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

try:
    from market_dashboard.modules.data import get_ticker_frame
except ImportError:
    from modules.data import get_ticker_frame


def _fmt_money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_pct(value) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "N/A"


def metric_strip_html(items: list[tuple[str, str]]) -> str:
    """Build compact metric strip HTML."""
    cells = []
    for label, value in items:
        cells.append(
            "<div class='qma-status-item'>"
            f"<div class='qma-status-label'>{html.escape(str(label))}</div>"
            f"<div class='qma-status-value'>{html.escape(str(value))}</div>"
            "</div>"
        )
    return f"<div class='qma-status-strip'>{''.join(cells)}</div>"


def render_metric_strip(items: list[tuple[str, str]]) -> None:
    """Render a compact metric strip."""
    st.markdown(metric_strip_html(items), unsafe_allow_html=True)


def render_top_bar(app_name: str, tickers: list[str], workflow: str, data_status: dict | None, ui_mode: str, theme: str) -> None:
    """Render the broker-style app top bar."""
    status = data_status or {}
    loaded = ", ".join(status.get("loaded_tickers", tickers[:4])) or "No symbols"
    source = status.get("source", "N/A")
    latest = status.get("latest_bar", "N/A")
    state = status.get("status", "unavailable")
    st.markdown(
        "<div class='qma-topbar'>"
        f"<div><div class='qma-topbar-title'>{html.escape(app_name)}</div>"
        f"<div class='qma-topbar-subtitle'>{html.escape(loaded)}</div></div>"
        "<div class='qma-topbar-meta'>"
        f"<span class='qma-status qma-status-{html.escape(state)}'>{html.escape(source)}</span>"
        f"<span>{html.escape(workflow)}</span>"
        f"<span>{html.escape(ui_mode.title())}</span>"
        f"<span>{html.escape(theme.title())}</span>"
        f"<span>{html.escape(str(latest))}</span>"
        "</div></div>",
        unsafe_allow_html=True,
    )


def quote_snapshot(data: pd.DataFrame, ticker: str) -> dict:
    """Return the latest quote snapshot for one loaded ticker."""
    ticker_data = get_ticker_frame(data, ticker)
    close = pd.to_numeric(ticker_data["Close"], errors="coerce").dropna()
    open_price = pd.to_numeric(ticker_data["Open"], errors="coerce").dropna()
    high = pd.to_numeric(ticker_data["High"], errors="coerce").dropna()
    low = pd.to_numeric(ticker_data["Low"], errors="coerce").dropna()
    volume = pd.to_numeric(ticker_data["Volume"], errors="coerce").dropna()
    if close.empty:
        return {"ticker": ticker, "price": None, "change_pct": None, "latest": "N/A", "volume": None}

    last = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else last
    change_pct = ((last / prev) - 1) * 100 if prev else 0.0
    latest = pd.Timestamp(close.index[-1]).strftime("%Y-%m-%d")
    last_volume = float(volume.iloc[-1]) if not volume.empty else None
    return {
        "ticker": ticker,
        "price": last,
        "change_pct": change_pct,
        "latest": latest,
        "volume": last_volume,
        "open": float(open_price.iloc[-1]) if not open_price.empty else None,
        "high": float(high.iloc[-1]) if not high.empty else None,
        "low": float(low.iloc[-1]) if not low.empty else None,
    }


def render_quote_header(data: pd.DataFrame, ticker: str, data_status: dict | None) -> None:
    """Render a quote header for the active ticker."""
    quote = quote_snapshot(data, ticker)
    change_class = "qma-price-up" if (quote.get("change_pct") or 0) >= 0 else "qma-price-down"
    source = (data_status or {}).get("source", "N/A")
    rows = [
        ("Change", _fmt_pct(quote.get("change_pct"))),
        ("Open", _fmt_money(quote.get("open"))),
        ("High", _fmt_money(quote.get("high"))),
        ("Low", _fmt_money(quote.get("low"))),
        ("Latest Bar", quote.get("latest", "N/A")),
        ("Volume", f"{quote.get('volume'):,.0f}" if quote.get("volume") is not None else "N/A"),
        ("Source", source),
    ]
    cells = []
    for label, value in rows:
        value_class = f"qma-status-value {change_class}" if label == "Change" else "qma-status-value"
        cells.append(
            "<div class='qma-status-item'>"
            f"<div class='qma-status-label'>{html.escape(label)}</div>"
            f"<div class='{value_class}'>{html.escape(str(value))}</div>"
            "</div>"
        )

    st.markdown(
        "<div class='qma-quote-header'>"
        f"<div><div class='qma-quote-symbol'>{html.escape(str(ticker))}</div>"
        f"<div class='qma-quote-price'>{html.escape(_fmt_money(quote.get('price')))}</div>"
        f"<div class='{change_class}'>{html.escape(_fmt_pct(quote.get('change_pct')))}</div></div>"
        f"<div class='qma-status-strip qma-quote-strip'>{''.join(cells)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def watchlist_snapshot(data: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Return a compact watchlist table for the sidebar."""
    rows = []
    for ticker in tickers:
        try:
            quote = quote_snapshot(data, ticker)
            rows.append(
                {
                    "Ticker": ticker,
                    "Last": _fmt_money(quote.get("price")),
                    "Change": _fmt_pct(quote.get("change_pct")),
                    "Volume": f"{quote.get('volume'):,.0f}" if quote.get("volume") is not None else "N/A",
                    "Latest": quote.get("latest", "N/A"),
                }
            )
        except Exception:
            rows.append({"Ticker": ticker, "Last": "N/A", "Change": "N/A", "Volume": "N/A", "Latest": "N/A"})
    return pd.DataFrame(rows)
