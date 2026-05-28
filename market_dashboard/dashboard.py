"""
Stock Backtester - Quant Market Analytics Dashboard
A Streamlit-based dashboard for analyzing market data and backtesting trading strategies.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.subplots as sp
import numpy as np
import html
from datetime import datetime, timedelta
import traceback

from modules.data import (
    DATA_SOURCE_OPTIONS,
    DATA_SOURCE_STOOQ,
    DEFAULT_DATA_SOURCE,
    available_tickers,
    get_close_prices,
    get_ticker_frame,
    load_market_data,
)
from modules.indicators import moving_averages, rsi, macd, bollinger
from modules.utils import compute_returns, correlation_matrix
from modules.strategies import (
    MovingAverageCrossover, RSIStrategy, BollingerBandsStrategy, 
    buy_hold_equity
)
from modules.portfolio import sharpe_ratio, max_drawdown, win_rate, portfolio_backtest, value_at_risk, conditional_value_at_risk, apply_stop_loss_take_profit
from modules.optimizer import grid_search_strategy
from modules.persistence import save_workspace, load_workspace
from modules.stock_search import (
    search_stocks, get_stock_info, get_popular_stocks, 
    get_stock_categories, get_stock_preset_symbols, get_stock_presets,
    format_market_cap, format_price
)
from modules.simulator import (
    TradingSimulator, create_simulator_session, get_simulator_engine, 
    reset_simulator
)
from modules.quant_lab import QuantLabError, build_strategy_data, run_quant_lab_strategy
from modules.result_explainer import explain_strategy_result
from modules.strategy_sandbox import StrategyExecutionError, StrategyValidationError, validate_strategy_code
from modules.strategy_templates import DEFAULT_TEMPLATE_NAME, get_template, get_template_code, template_names

try:
    from ui.theme import apply_app_theme, get_plotly_template, theme_tokens
except ImportError:
    from market_dashboard.ui.theme import apply_app_theme, get_plotly_template, theme_tokens

try:
    from ui.components import render_quote_header, render_top_bar, watchlist_snapshot
except ImportError:
    from market_dashboard.ui.components import render_quote_header, render_top_bar, watchlist_snapshot

try:
    from . import __version__
except ImportError:
    __version__ = "1.1.2"

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

st.set_page_config(layout="wide", page_title="Quant Market Analytics", page_icon="Q")

TRADING_DAYS_PER_YEAR = 252
HOURS_PER_TRADING_DAY = 6.5

DEFAULT_TICKERS = "AAPL,MSFT,NVDA,TSLA,SPY"
# Dynamic default dates - last 2 years
DEFAULT_END = pd.Timestamp.now().normalize()
DEFAULT_START = DEFAULT_END - pd.DateOffset(years=2)

INTERVALS = ["1m", "5m", "15m", "1h", "1d"]
DEFAULT_INTERVAL = "1d"

STRATEGY_OPTIONS = [
    "None",
    "MA Crossover",
    "RSI (Threshold)",
    "RSI (Mean-Reversion)",
    "Bollinger Bands"
]

TRADING_PRESETS = {
    "Day Trading": {"holding_period": 0, "position_type": "Fixed", "transaction_fee": 0.001},
    "Swing (2-Day)": {"holding_period": 2, "position_type": "Fixed", "transaction_fee": 0.001},
    "Swing (5-Day)": {"holding_period": 5, "position_type": "Fixed", "transaction_fee": 0.001},
    "Position Trading": {"holding_period": 20, "position_type": "Fixed", "transaction_fee": 0.0005},
}

TUTORIAL_STEPS = [
    {
        "Step": "1. Pick symbols",
        "Where": "Sidebar > Stock Search or Ticker Symbols",
        "Why it matters": "The app downloads one or more ticker histories and uses them everywhere else.",
    },
    {
        "Step": "2. Choose dates and source",
        "Where": "Sidebar > Data Selection",
        "Why it matters": "The date range, interval, and data source control how fresh and detailed the analysis is.",
    },
    {
        "Step": "3. Read the data status",
        "Where": "Header under the title",
        "Why it matters": "It tells you whether the app is using Yahoo, Stooq, partial data, or demo data.",
    },
    {
        "Step": "4. Explore the chart",
        "Where": "Overview or Backtest",
        "Why it matters": "Price, moving averages, RSI, MACD, Bollinger Bands, volume, and drawdown give market context.",
    },
    {
        "Step": "5. Test or practice",
        "Where": "Backtest or Simulator",
        "Why it matters": "Backtests automate a strategy. The simulator lets you make manual buy/sell decisions.",
    },
    {
        "Step": "6. Review risk",
        "Where": "Portfolio and Risk",
        "Why it matters": "Correlation, drawdown, VaR, CVaR, rolling volatility, and monthly returns show what could go wrong.",
    },
]

STOCK_TUTORIAL_ROWS = [
    {
        "Term": "Ticker",
        "Meaning": "A short symbol for a traded asset, such as AAPL, MSFT, NVDA, TSLA, or SPY.",
        "How to use it": "Enter comma-separated tickers in the sidebar, or add symbols from categories and presets.",
    },
    {
        "Term": "OHLCV",
        "Meaning": "Open, High, Low, Close, and Volume for each candle.",
        "How to use it": "Most indicators use Close. Candlestick charts show all OHLC fields.",
    },
    {
        "Term": "Interval",
        "Meaning": "The candle size, such as 1m, 5m, 15m, 1h, or 1d.",
        "How to use it": "Use 1d for longer research. Use intraday intervals for shorter-term practice.",
    },
    {
        "Term": "Return",
        "Meaning": "The percent change from one price to another.",
        "How to use it": "Compare tickers, strategies, and portfolios on a percent basis rather than price alone.",
    },
    {
        "Term": "Volume",
        "Meaning": "How many shares traded during a candle.",
        "How to use it": "Rising volume can confirm that more market participants are involved in a move.",
    },
]

DATA_SOURCE_TUTORIAL_ROWS = [
    {
        "Source": "Auto",
        "Best for": "Default research and recent data requests.",
        "Notes": "Tries Yahoo Finance first, then Stooq for daily candles, then demo data if real data is unavailable.",
    },
    {
        "Source": "Yahoo Finance",
        "Best for": "Recent daily and intraday-friendly market data.",
        "Notes": "Availability can vary by ticker, interval, and date range.",
    },
    {
        "Source": "Stooq",
        "Best for": "No-key daily fallback data.",
        "Notes": "This app uses it for daily candles here.",
    },
    {
        "Source": "Demo dataset",
        "Best for": "Learning the app without relying on network data.",
        "Notes": "Generated data is deterministic and illustrative, not real market history.",
    },
]

INDICATOR_TUTORIAL_ROWS = [
    {
        "Indicator": "Moving Averages",
        "What it shows": "Smoothed price trend over 50 and 200 periods.",
        "Common use": "A fast average crossing above a slow average can suggest improving trend; crossing below can suggest weakening trend.",
        "Watch out": "Moving averages lag price and can whipsaw in choppy markets.",
    },
    {
        "Indicator": "RSI",
        "What it shows": "Momentum oscillator from 0 to 100.",
        "Common use": "Below 30 is often treated as oversold; above 70 is often treated as overbought. The mean-reversion mode watches the 50 line.",
        "Watch out": "Strong trends can stay overbought or oversold longer than expected.",
    },
    {
        "Indicator": "MACD",
        "What it shows": "Difference between short and long exponential moving averages, plus a signal line.",
        "Common use": "MACD crossing above its signal can suggest momentum is improving; crossing below can suggest it is weakening.",
        "Watch out": "It is still trend-following and can lag at turning points.",
    },
    {
        "Indicator": "Bollinger Bands",
        "What it shows": "A moving average with upper and lower volatility bands.",
        "Common use": "Touches near the lower band can suggest weakness or mean-reversion setups; upper band touches can suggest strength or stretched price.",
        "Watch out": "A band touch is context, not a trade by itself.",
    },
    {
        "Indicator": "Drawdown",
        "What it shows": "How far price or equity has fallen from its prior peak.",
        "Common use": "Use it to judge pain and recovery risk, not just return.",
        "Watch out": "A high-return strategy can still be hard to tolerate if drawdowns are deep or long.",
    },
    {
        "Indicator": "Correlation",
        "What it shows": "How similarly tickers move from period to period.",
        "Common use": "Portfolio tickers with lower correlation can diversify better.",
        "Watch out": "Correlation changes during stress periods.",
    },
]

STRATEGY_TUTORIAL_ROWS = [
    {
        "Strategy": "MA Crossover",
        "Idea": "Buy when the shorter trend improves relative to the longer trend.",
        "Good for": "Trend-following tests.",
        "Main setting": "Holding period and transaction fee.",
    },
    {
        "Strategy": "RSI Threshold",
        "Idea": "Buy oversold readings and exit overbought readings.",
        "Good for": "Simple momentum/mean-reversion comparison.",
        "Main setting": "RSI thresholds are built into the strategy.",
    },
    {
        "Strategy": "RSI Mean-Reversion",
        "Idea": "Watch RSI crossing the 50 midpoint as a recovery/weakness signal.",
        "Good for": "Cleaner entry and exit timing around momentum shifts.",
        "Main setting": "Holding period and transaction fee.",
    },
    {
        "Strategy": "Bollinger Bands",
        "Idea": "Use volatility bands to detect stretched price action.",
        "Good for": "Mean-reversion experiments.",
        "Main setting": "Holding period and transaction fee.",
    },
]

METRIC_TUTORIAL_ROWS = [
    {
        "Metric": "Total return",
        "Meaning": "How much the strategy or asset gained or lost over the selected period.",
        "How to read it": "Higher is better, but only after checking risk.",
    },
    {
        "Metric": "Sharpe ratio",
        "Meaning": "Return relative to volatility.",
        "How to read it": "Higher usually means smoother risk-adjusted performance.",
    },
    {
        "Metric": "Max drawdown",
        "Meaning": "Worst peak-to-trough decline.",
        "How to read it": "Shows the largest painful decline a user would have had to sit through.",
    },
    {
        "Metric": "Win rate",
        "Meaning": "Share of completed trades or periods that were profitable.",
        "How to read it": "Useful, but not enough alone because winners and losers can be different sizes.",
    },
    {
        "Metric": "VaR / CVaR",
        "Meaning": "Downside risk estimates.",
        "How to read it": "VaR is a threshold. CVaR estimates average loss beyond that threshold.",
    },
]

GUIDED_TOUR_STEPS = [
    {
        "title": "Pick a simple starting universe",
        "workflow": "Tutorial",
        "mode": "tutorial",
        "goal": "Start with a few familiar tickers so the rest of the app is easier to read.",
        "action": "Use the default symbols or choose a preset in the sidebar. Keep the list small while learning.",
        "look_for": "Ticker Symbols in the sidebar and loaded tickers in the data status strip.",
    },
    {
        "title": "Confirm the data source",
        "workflow": "Overview",
        "mode": "overview",
        "goal": "Make sure the chart and analysis are using the data you expect.",
        "action": "Use Auto unless you have a reason to force Yahoo Finance, Stooq daily data, or Demo dataset.",
        "look_for": "Requested source, actual source, latest bar, loaded tickers, and unavailable tickers.",
    },
    {
        "title": "Read price context first",
        "workflow": "Overview",
        "mode": "overview",
        "goal": "Understand the market before testing a strategy.",
        "action": "Look at price direction, moving averages, RSI, MACD, Bollinger Bands, volume, and drawdown.",
        "look_for": "Trend, momentum, stretched price action, and the worst decline from a prior high.",
    },
    {
        "title": "Run a basic backtest",
        "workflow": "Backtest",
        "mode": "backtesting",
        "goal": "See how a rule-based strategy behaved historically.",
        "action": "Choose MA Crossover first, keep default fees, run the backtest, then compare it with buy-and-hold.",
        "look_for": "Total return, Sharpe ratio, max drawdown, win rate, trade log, and benchmark comparison.",
    },
    {
        "title": "Practice a manual decision",
        "workflow": "Simulator",
        "mode": "simulator",
        "goal": "Learn how position size, fees, and timing change cash and equity.",
        "action": "Open the simulator setup, preview a small buy order, then step forward through candles.",
        "look_for": "Cash after trade, shares after trade, exposure, equity, and realized or unrealized P&L.",
    },
    {
        "title": "Review portfolio and risk",
        "workflow": "Risk",
        "mode": "risk",
        "goal": "Decide whether the result was worth the risk.",
        "action": "Check drawdown, VaR, CVaR, rolling volatility, monthly returns, and correlation if using multiple tickers.",
        "look_for": "Deep drawdowns, unstable Sharpe, high correlation, and weak months.",
    },
]

LEARNING_SCENARIOS = [
    {
        "name": "Starter Overview",
        "mode": "overview",
        "tickers": "AAPL,MSFT,NVDA,SPY",
        "selected_ticker": "AAPL",
        "strategy": "None",
        "portfolio_weights": "",
        "description": "Load a familiar tech-and-market basket and start with the Overview chart.",
    },
    {
        "name": "Trend Backtest",
        "mode": "backtesting",
        "tickers": "AAPL,SPY",
        "selected_ticker": "AAPL",
        "strategy": "MA Crossover",
        "portfolio_weights": "",
        "description": "Compare a simple moving-average trend strategy against buy-and-hold.",
    },
    {
        "name": "RSI Practice",
        "mode": "backtesting",
        "tickers": "TSLA,SPY",
        "selected_ticker": "TSLA",
        "strategy": "RSI (Mean-Reversion)",
        "portfolio_weights": "",
        "description": "Try a momentum recovery strategy on a higher-volatility stock.",
    },
    {
        "name": "Simulator Drill",
        "mode": "simulator",
        "tickers": "TSLA",
        "selected_ticker": "TSLA",
        "strategy": "None",
        "portfolio_weights": "",
        "description": "Practice manual orders, position size, cash, exposure, and P&L.",
    },
    {
        "name": "ETF Portfolio",
        "mode": "portfolio",
        "tickers": "SPY,QQQ,IWM,TLT,GLD",
        "selected_ticker": "SPY",
        "strategy": "None",
        "portfolio_weights": "SPY:0.35,QQQ:0.25,IWM:0.15,TLT:0.15,GLD:0.10",
        "description": "Review diversification, weights, correlation, and portfolio returns.",
    },
    {
        "name": "Risk Review",
        "mode": "risk",
        "tickers": "NVDA,SPY",
        "selected_ticker": "NVDA",
        "strategy": "None",
        "portfolio_weights": "",
        "description": "Inspect drawdown, VaR, CVaR, rolling risk, and monthly returns.",
    },
]

WORKFLOW_HELP = {
    "Overview": {
        "goal": "Use Overview to answer: what loaded, what moved, and how did the selected assets behave over the chosen period?",
        "steps": [
            "Check the data status strip first, especially source, latest bar, and unavailable tickers.",
            "Scan the summary table for period return and row count.",
            "Use the price chart below to compare trend, momentum, volume, and drawdown before testing a strategy.",
        ],
    },
    "Backtest": {
        "goal": "Use Backtest to run one rule-based strategy on one ticker and compare the result with buy-and-hold.",
        "steps": [
            "Pick a strategy and keep defaults at first.",
            "Set the backtest period and fees to match the kind of trading you want to test.",
            "After running, read return together with drawdown, trade count, and benchmark comparison.",
        ],
    },
    "Quant Lab": {
        "goal": "Use Quant Lab to validate a small custom strategy function and run it through the existing backtest engine.",
        "steps": [
            "Start from a template, then edit only the signal logic inside strategy(data).",
            "Validate before running so syntax, blocked operations, output shape, and timeout limits are checked.",
            "Review the explanation, assumptions, equity curve, and trade log before trusting the result.",
        ],
    },
    "Simulator": {
        "goal": "Use Simulator to practice manual buy and sell decisions without risking money.",
        "steps": [
            "Pick a short date range while learning.",
            "Preview each order before execution and watch cash, shares, equity, and exposure.",
            "Step forward slowly and write down why you would hold, buy, or sell.",
        ],
    },
    "Portfolio": {
        "goal": "Use Portfolio to test how several tickers work together instead of judging one asset alone.",
        "steps": [
            "Use weights that sum roughly to your intended allocation. The app normalizes them.",
            "Check whether returns improve without creating too much drawdown.",
            "Use correlation to see whether the portfolio is actually diversified.",
        ],
    },
    "Risk": {
        "goal": "Use Risk to decide whether the potential return looks worth the downside.",
        "steps": [
            "Read max drawdown and drawdown duration before focusing on return.",
            "Use VaR and CVaR as downside estimates, not guarantees.",
            "Check rolling volatility and monthly returns for unstable periods.",
        ],
    },
    "Settings": {
        "goal": "Use Settings to tune the experience without changing market data.",
        "steps": [
            "Simple mode keeps defaults quieter for learning.",
            "Expert mode exposes more controls for optimization and assumptions.",
            "Light and Dark mode should now change the full app surface and charts.",
        ],
    },
}

SHARPE_MODES = {
    "Daily (252 days/yr)": "1d",
    "Hourly": "1h",
    "5-Minute": "5m",
    "1-Minute": "1m",
}

CHART_INDICATOR_OPTIONS = ["SMA", "EMA", "Bollinger Bands", "Volume", "RSI", "MACD"]
COMMON_CHART_INDICATORS = ["SMA", "Volume", "RSI", "MACD"]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_ticker_data(data, ticker, start_date, end_date):
    """Extract single ticker data for backtest period."""
    if data is None or data.empty:
        raise ValueError("No data provided")
    
    if isinstance(data.columns, pd.MultiIndex):
        if ticker in data.columns.get_level_values(1):
            ticker_data = data.xs(ticker, level=1, axis=1)
        elif ticker in data.columns.get_level_values(0):
            ticker_data = data.xs(ticker, level=0, axis=1)
        else:
            raise ValueError(f"Ticker {ticker} not found in data")
    else:
        ticker_data = data
    
    if ticker_data.empty:
        raise ValueError(f"No data available for ticker {ticker}")
    
    start_date = pd.Timestamp(start_date).date()
    end_date = pd.Timestamp(end_date).date()
    mask = (ticker_data.index.date >= start_date) & (ticker_data.index.date <= end_date)
    filtered_data = ticker_data[mask]
    
    if len(filtered_data) < 10:  # Require minimum data points
        raise ValueError(f"Insufficient data for backtest period (need at least 10 data points, got {len(filtered_data)})")
    
    return filtered_data


def compute_all_indicators(close):
    """Pre-compute all indicators needed by strategies."""
    if close is None or close.empty or len(close) < 2:
        raise ValueError("Insufficient data for indicator computation (need at least 2 data points)")
    
    try:
        ma50, ma200 = moving_averages(close)
        rsi_vals = rsi(close)
        bb_upper, bb_lower = bollinger(close)
        
        return {
            'ma50': ma50,
            'ma200': ma200,
            'rsi': rsi_vals,
            'bb_upper': bb_upper,
            'bb_lower': bb_lower,
            'close': close
        }
    except Exception as e:
        raise ValueError(f"Failed to compute indicators: {str(e)}")


def get_strategy_instance(name, config):
    """Create strategy instance based on name and config."""
    strategies = {
        "MA Crossover": MovingAverageCrossover,
        "RSI (Threshold)": lambda **kw: RSIStrategy(mode="threshold", **kw),
        "RSI (Mean-Reversion)": lambda **kw: RSIStrategy(mode="mean_reversion", **kw),
        "Bollinger Bands": BollingerBandsStrategy,
    }
    
    if name not in strategies:
        raise ValueError(f"Unknown strategy: {name}")
    
    strategy_class = strategies[name]
    position_label = str(config['position_type']).lower()
    return strategy_class(
        holding_period=config['holding_period'],
        position_type="dynamic" if position_label == "dynamic" else "fixed",
        fee_pct=config['fee_pct']
    )


def run_single_backtest(strategy_name, price, indicators, config):
    """Execute backtest for single strategy."""
    strategy = get_strategy_instance(strategy_name, config)
    signals = strategy.generate_signals(price, indicators)
    results = strategy.compute_positions_and_equity(signals, price, initial_equity=100)
    metrics = strategy.compute_metrics(
        results['equity'],
        results['daily_return'],
        interval=config['interval'],
        risk_free_rate=0.02
    )
    return {**results, **metrics}


def create_backtest_key(strategy, start, end, ticker, holding_days, fee):
    """Create hashable key for caching backtest results."""
    return (strategy, str(start), str(end), ticker, holding_days, fee)


def manage_backtest_cache():
    """Manage backtest cache size to prevent memory issues."""
    max_cache_size = 50  # Limit cache to 50 entries
    if len(st.session_state.backtest_cache) > max_cache_size:
        # Remove oldest entries (simple FIFO)
        cache_items = list(st.session_state.backtest_cache.items())
        # Keep only the most recent half
        st.session_state.backtest_cache = dict(cache_items[-max_cache_size//2:])


def display_beginner_glossary():
    """Show compact metric explanations for newer users."""
    with st.expander("Metric glossary", expanded=False):
        st.markdown(
            """
            **Total return** shows the full percentage gain or loss over the selected period.

            **Sharpe ratio** compares return against volatility. Higher values usually mean smoother risk-adjusted performance.

            **Max drawdown** is the largest peak-to-trough decline. It helps show how painful a strategy could have felt.

            **Win rate** is the share of profitable trading periods or completed trades.

            **VaR and CVaR** estimate downside risk. CVaR focuses on the average loss after the VaR threshold is breached.
            """
        )


def load_data_with_status(
    tickers,
    start,
    end,
    interval,
    data_source: str | None = None,
    show_success: bool = False,
    emit_status: bool = True,
):
    """Load market data and show a clear status when demo data is used."""
    selected_source = data_source or st.session_state.get("data_source", DEFAULT_DATA_SOURCE)
    data, status = load_market_data(tickers, start, end, interval, source=selected_source)
    st.session_state.latest_data_status = status
    if not emit_status:
        return data

    if status.get("status") == "partial":
        unavailable = ", ".join(status.get("unavailable_tickers", []))
        st.warning(f"{status['message']}. Unavailable: {unavailable}")
    elif status.get("is_demo"):
        st.warning(status["message"])
    elif show_success:
        st.caption(status["message"])
    return data


def _fmt_money(value):
    return f"${float(value):,.2f}"


def _fmt_pct(value):
    return f"{float(value):.1f}%"


def merge_ticker_input(existing, additions, replace=False):
    """Merge ticker symbols into the comma-separated sidebar input."""
    if isinstance(additions, str):
        additions = [additions]

    merged = [] if replace else [
        ticker.strip().upper()
        for ticker in str(existing or "").replace(";", ",").split(",")
        if ticker.strip()
    ]
    for ticker in additions:
        symbol = str(ticker).strip().upper()
        if symbol and symbol not in merged:
            merged.append(symbol)

    return ",".join(merged)


def render_status_strip(items):
    """Render a compact label/value strip."""
    cells = []
    for label, value in items:
        cells.append(
            "<div class='qma-status-item'>"
            f"<div class='qma-status-label'>{html.escape(str(label))}</div>"
            f"<div class='qma-status-value'>{html.escape(str(value))}</div>"
            "</div>"
        )
    st.markdown(f"<div class='qma-status-strip'>{''.join(cells)}</div>", unsafe_allow_html=True)


def display_data_status(status):
    """Show a compact data status pill and summary near the active workflow."""
    if not status:
        return

    labels = {
        "live": "Live data",
        "demo": "Demo data",
        "partial": "Partial data",
        "unavailable": "Data unavailable",
    }
    state = status.get("status", "unavailable")
    label = labels.get(state, "Data status")
    loaded = ", ".join(status.get("loaded_tickers", [])) or "None"
    unavailable = ", ".join(status.get("unavailable_tickers", [])) or "None"

    st.markdown(
        f"<span class='qma-status qma-status-{html.escape(state)}'>{html.escape(label)}</span> "
        f"<span class='qma-muted'>{html.escape(status.get('message', ''))}</span>",
        unsafe_allow_html=True,
    )
    render_status_strip([
        ("Requested", status.get("requested_source", status.get("source", "N/A"))),
        ("Source", status.get("source", "N/A")),
        ("Rows", f"{status.get('row_count', 0):,}"),
        ("Latest", status.get("latest_bar", "N/A")),
        ("Date Range", f"{status.get('date_start', 'N/A')} to {status.get('date_end', 'N/A')}"),
        ("Interval", status.get("interval", "N/A")),
        ("Loaded", loaded),
        ("Unavailable", unavailable),
    ])

    if state == "demo":
        st.caption("Demo data is deterministic and intended for product exploration only. Charts and backtests are illustrative.")
    elif state == "partial":
        st.caption("Analysis continues with the loaded tickers. Unavailable symbols are excluded from charts and calculations.")


def display_order_preview(preview):
    """Render a compact order preview dictionary."""
    items = [
        ("Trade value", _fmt_money(preview.get("trade_value", 0.0))),
        ("Estimated fee", _fmt_money(preview.get("fee", 0.0))),
        ("Cash after", _fmt_money(preview.get("cash_after", 0.0))),
        ("Shares after", f"{preview.get('shares_after', 0):,}"),
        ("Exposure after", _fmt_pct(preview.get("exposure_after", 0.0))),
    ]
    if preview.get("action") == "SELL":
        items.append(("Realized P&L", _fmt_money(preview.get("realized_pnl", 0.0))))

    cells = []
    for label, value in items:
        cells.append(
            "<div class='qma-preview-item'>"
            f"<div class='qma-preview-label'>{html.escape(str(label))}</div>"
            f"<div class='qma-preview-value'>{html.escape(str(value))}</div>"
            "</div>"
        )
    st.markdown(f"<div class='qma-order-preview'>{''.join(cells)}</div>", unsafe_allow_html=True)
    if not preview.get("can_execute", False):
        st.caption(preview.get("reason", "Order cannot be executed."))


def normalize_chart_indicators(selected=None):
    """Return valid chart indicators, using common indicators by default."""
    if selected is None:
        selected = st.session_state.get("chart_indicators", COMMON_CHART_INDICATORS)
    return [indicator for indicator in selected if indicator in CHART_INDICATOR_OPTIONS]


def display_chart_indicator_controls():
    """Render indicator controls with quick all/common/off actions."""
    if "chart_indicators" not in st.session_state:
        st.session_state.chart_indicators = COMMON_CHART_INDICATORS.copy()

    st.markdown("**Chart Indicators**")
    common_col, all_col, off_col = st.columns(3)
    with common_col:
        if st.button("Common", key="chart_indicators_common", use_container_width=True):
            st.session_state.chart_indicators = COMMON_CHART_INDICATORS.copy()
            st.rerun()
    with all_col:
        if st.button("All", key="chart_indicators_all", use_container_width=True):
            st.session_state.chart_indicators = CHART_INDICATOR_OPTIONS.copy()
            st.rerun()
    with off_col:
        if st.button("Off", key="chart_indicators_off", use_container_width=True):
            st.session_state.chart_indicators = []
            st.rerun()

    return st.multiselect(
        "Visible Indicators",
        CHART_INDICATOR_OPTIONS,
        key="chart_indicators",
        help="Common loads SMA, Volume, RSI, and MACD. All and Off toggle the complete indicator stack.",
    )


def periods_per_year(interval):
    """Return annualization periods for the selected data interval."""
    return {
        "1d": TRADING_DAYS_PER_YEAR,
        "1h": TRADING_DAYS_PER_YEAR * HOURS_PER_TRADING_DAY,
        "15m": TRADING_DAYS_PER_YEAR * HOURS_PER_TRADING_DAY * 4,
        "5m": TRADING_DAYS_PER_YEAR * HOURS_PER_TRADING_DAY * 12,
        "1m": TRADING_DAYS_PER_YEAR * HOURS_PER_TRADING_DAY * 60,
    }.get(interval, TRADING_DAYS_PER_YEAR)


def rolling_sharpe_series(returns, interval="1d", window=63, risk_free_rate=0.02):
    """Compute rolling annualized Sharpe ratio."""
    returns = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return pd.Series(dtype=float)

    periods = periods_per_year(interval)
    excess = returns - (risk_free_rate / periods)
    rolling_std = returns.rolling(window).std()
    sharpe = (excess.rolling(window).mean() / rolling_std.replace(0, np.nan)) * np.sqrt(periods)
    return sharpe.replace([np.inf, -np.inf], np.nan).dropna()


def rolling_volatility_series(returns, interval="1d", window=63):
    """Compute rolling annualized volatility in percent."""
    returns = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return pd.Series(dtype=float)

    vol = returns.rolling(window).std() * np.sqrt(periods_per_year(interval)) * 100
    return vol.replace([np.inf, -np.inf], np.nan).dropna()


def drawdown_duration_stats(equity):
    """Return max and current drawdown duration measured in data periods."""
    equity = pd.to_numeric(equity, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if equity.empty:
        return 0, 0

    underwater = equity < equity.cummax()
    current = 0
    max_duration = 0
    for is_underwater in underwater:
        current = current + 1 if is_underwater else 0
        max_duration = max(max_duration, current)

    return max_duration, current


def monthly_returns_matrix(returns):
    """Return a year x month matrix of compounded monthly returns in percent."""
    returns = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return pd.DataFrame()

    monthly = (1 + returns).resample("M").prod() - 1
    monthly_df = pd.DataFrame({
        "year": monthly.index.year,
        "month": monthly.index.month,
        "return": monthly.values * 100,
    })
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    matrix = monthly_df.pivot(index="year", columns="month", values="return")
    return matrix.reindex(columns=range(1, 13)).rename(columns={i + 1: month for i, month in enumerate(month_names)})


def display_monthly_heatmap(returns, title="Monthly Returns"):
    """Display a compact monthly returns heatmap."""
    matrix = monthly_returns_matrix(returns)
    if matrix.empty:
        st.info("Not enough return history for a monthly heatmap.")
        return

    fig = go.Figure(data=go.Heatmap(
        z=matrix.values,
        x=matrix.columns,
        y=matrix.index.astype(str),
        colorscale="RdYlGn",
        zmid=0,
        colorbar=dict(title="%"),
        hovertemplate="%{y} %{x}: %{z:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        height=320,
        template=get_plotly_template(st.session_state.get('theme', 'dark')),
        xaxis_title="Month",
        yaxis_title="Year",
    )
    st.plotly_chart(fig, use_container_width=True)


def display_rolling_risk_charts(returns, interval="1d", title_prefix="Strategy"):
    """Display rolling Sharpe and rolling volatility charts."""
    returns = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(returns) < 10:
        st.info("Not enough return history for rolling risk charts.")
        return

    window = min(63, max(10, len(returns) // 3))
    rolling_sharpe = rolling_sharpe_series(returns, interval=interval, window=window)
    rolling_vol = rolling_volatility_series(returns, interval=interval, window=window)

    fig = sp.make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(f"{title_prefix} Rolling Sharpe", f"{title_prefix} Rolling Volatility"),
    )
    if not rolling_sharpe.empty:
        fig.add_trace(go.Scatter(x=rolling_sharpe.index, y=rolling_sharpe.values, name="Rolling Sharpe"), row=1, col=1)
    if not rolling_vol.empty:
        fig.add_trace(go.Scatter(x=rolling_vol.index, y=rolling_vol.values, name="Rolling Volatility"), row=2, col=1)

    fig.update_layout(
        height=480,
        template=get_plotly_template(st.session_state.get('theme', 'dark')),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Sharpe", row=1, col=1)
    fig.update_yaxes(title_text="Volatility (%)", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)


def display_strategy_assumptions(config, interval, starting_capital=100, risk_free_rate=0.02):
    """Show plain-language assumptions behind a strategy run."""
    render_status_strip([
        ("Fees", f"{config.get('fee_pct', 0) * 100:.2f}% per trade"),
        ("Interval", interval),
        ("Starting Capital", _fmt_money(starting_capital)),
        ("Risk-Free Rate", f"{risk_free_rate * 100:.1f}%"),
        ("Position Sizing", str(config.get('position_type', 'Fixed'))),
        ("Hold Days", config.get('holding_period', 0)),
    ])


def display_strategy_analytics(backtest_data, close, interval, config, benchmark_close=None, benchmark_label="SPY"):
    """Display strategy comparison, risk context, and return distribution views."""
    if not backtest_data or "equity" not in backtest_data:
        return
    config = config or {}

    equity = backtest_data["equity"].dropna()
    if equity.empty:
        return

    aligned_close = close.reindex(equity.index).dropna()
    strategy_equity = equity.reindex(aligned_close.index).dropna()
    if strategy_equity.empty:
        return
    buy_hold = buy_hold_equity(aligned_close, initial_equity=float(strategy_equity.iloc[0])) if not aligned_close.empty else pd.Series(dtype=float)

    st.markdown("**Strategy Comparison**")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=strategy_equity.index, y=strategy_equity.values, name="Strategy", line=dict(width=2)))
    if not buy_hold.empty:
        fig.add_trace(go.Scatter(x=buy_hold.index, y=buy_hold.values, name=f"{aligned_close.name or 'Ticker'} Buy & Hold", line=dict(dash="dash")))

    if benchmark_close is not None and not benchmark_close.empty:
        benchmark_aligned = benchmark_close.reindex(strategy_equity.index).dropna()
        benchmark_equity = buy_hold_equity(benchmark_aligned, initial_equity=float(strategy_equity.iloc[0]))
        if not benchmark_equity.empty:
            fig.add_trace(go.Scatter(x=benchmark_equity.index, y=benchmark_equity.values, name=f"{benchmark_label} Benchmark", line=dict(dash="dot")))

    fig.update_layout(
        height=420,
        yaxis_title="Equity",
        template=get_plotly_template(st.session_state.get('theme', 'dark')),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    max_duration, current_duration = drawdown_duration_stats(strategy_equity)
    st.caption(
        f"Max drawdown duration: {max_duration} periods. Current drawdown duration: {current_duration} periods."
    )

    display_strategy_assumptions(config, interval)
    display_rolling_risk_charts(backtest_data.get("daily_return", pd.Series(dtype=float)), interval=interval)
    display_monthly_heatmap(backtest_data.get("daily_return", pd.Series(dtype=float)), title="Strategy Monthly Returns")


# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def display_metrics_panel(metrics):
    """Show 4-column metrics dashboard."""
    metric_cols = st.columns(4)
    
    specs = [
        ("Total Return", f"{metrics['total_return']:.2f}%", "good" if metrics['total_return'] > 0 else "bad"),
        ("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}", "good" if metrics['sharpe_ratio'] > 1 else "neutral"),
        ("Max Drawdown", f"{metrics['max_drawdown']:.2f}%", "bad" if metrics['max_drawdown'] < -10 else "neutral"),
        ("Win Rate", f"{metrics['win_rate']:.1f}%", "good" if metrics['win_rate'] > 50 else "neutral"),
    ]
    
    for col, (label, value, delta_color) in zip(metric_cols, specs):
        col.metric(label, value)


def display_trade_log(backtest_data, strategy_name):
    """Show trade details and export option."""
    if not backtest_data or 'trades' not in backtest_data or len(backtest_data['trades']) == 0:
        st.info("No trades executed in backtest period.")
        return
    
    st.subheader("Trade Log")
    
    trades = backtest_data['trades']
    trades_df = pd.DataFrame(trades)
    
    # Format columns for display - handle missing data gracefully
    display_df = trades_df.copy()
    
    # Safe date formatting
    if 'entry_date' in display_df.columns:
        display_df['entry_date'] = pd.to_datetime(display_df['entry_date'], errors='coerce').dt.strftime('%Y-%m-%d')
    if 'exit_date' in display_df.columns:
        display_df['exit_date'] = pd.to_datetime(display_df['exit_date'], errors='coerce').dt.strftime('%Y-%m-%d')
    
    # Safe price formatting
    if 'entry_price' in display_df.columns:
        display_df['entry_price'] = display_df['entry_price'].apply(lambda x: f"${float(x):.2f}" if pd.notna(x) else "N/A")
    if 'exit_price' in display_df.columns:
        display_df['exit_price'] = display_df['exit_price'].apply(lambda x: f"${float(x):.2f}" if pd.notna(x) else "N/A")
    if 'return_pct' in display_df.columns:
        display_df['return_pct'] = display_df['return_pct'].apply(lambda x: f"{float(x):.2f}%" if pd.notna(x) else "N/A")
    if 'fees_pct' in display_df.columns:
        display_df['fees_pct'] = display_df['fees_pct'].apply(lambda x: f"{float(x):.2f}%" if pd.notna(x) else "N/A")
    
    # Only include columns that exist
    available_columns = [
        'entry_date', 'exit_date', 'entry_reason', 'exit_reason',
        'holding_periods', 'entry_price', 'exit_price', 'return_pct', 'fees_pct'
    ]
    display_columns = [col for col in available_columns if col in display_df.columns]
    display_df = display_df[display_columns]
    
    column_names = {
        'entry_date': 'Entry Date',
        'exit_date': 'Exit Date',
        'entry_reason': 'Entry Reason',
        'exit_reason': 'Exit Reason',
        'holding_periods': 'Holding Time',
        'entry_price': 'Entry Price',
        'exit_price': 'Exit Price',
        'return_pct': 'Return',
        'fees_pct': 'Fees',
    }
    display_df.columns = [column_names[col] for col in display_columns]
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # Trade statistics - handle missing data
    total_trades = len(trades)
    winning_trades = [t for t in trades if t.get('return_pct', 0) > 0]
    losing_trades = [t for t in trades if t.get('return_pct', 0) < 0]
    
    # Create columns for metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Trades", total_trades)
    with col2:
        st.metric("Winning Trades", len(winning_trades))
    with col3:
        st.metric("Losing Trades", len(losing_trades))
    
    if winning_trades:
        win_returns = [t.get('return_pct', 0) for t in winning_trades if t.get('return_pct') is not None]
        if win_returns:
            avg_win = np.mean(win_returns)
            max_win = max(win_returns)
            st.write(f"**Wins:** Avg {avg_win:.2f}% | Max {max_win:.2f}%")
    
    if losing_trades:
        loss_returns = [t.get('return_pct', 0) for t in losing_trades if t.get('return_pct') is not None]
        if loss_returns:
            avg_loss = np.mean(loss_returns)
            max_loss = min(loss_returns)
            st.write(f"**Losses:** Avg {avg_loss:.2f}% | Max {max_loss:.2f}%")
    
    # Export button
    csv_data = trades_df.to_csv(index=False)
    st.download_button(
        "Download Trades (CSV)",
        csv_data,
        f"trades_{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        "text/csv",
        help="Export trade log for external analysis"
    )


def display_advanced_chart(data, selected_ticker, backtest_data=None, backtest_signals=None, selected_indicators=None):
    """Show candlestick chart with selected indicators and optional equity curve."""
    df = get_ticker_frame(data, selected_ticker)
    price = df["Close"]
    selected_indicators = normalize_chart_indicators(selected_indicators)
    show_sma = "SMA" in selected_indicators
    show_ema = "EMA" in selected_indicators
    show_bollinger = "Bollinger Bands" in selected_indicators
    show_volume = "Volume" in selected_indicators
    show_macd = "MACD" in selected_indicators
    show_rsi = "RSI" in selected_indicators
    
    # Compute indicators
    ma50, ma200 = moving_averages(price)
    rsi_values = rsi(price)
    macd_line, signal = macd(price)
    upper, lower = bollinger(price)

    rows = [("Price Action", "price", 0.56)]
    if show_volume:
        rows.append(("Volume", "volume", 0.13))
    if show_macd:
        rows.append(("MACD", "macd", 0.16))
    if show_rsi:
        rows.append(("RSI", "rsi", 0.13))
    if backtest_data is not None:
        rows.append(("Equity Curve", "equity", 0.22))

    row_lookup = {key: idx + 1 for idx, (_, key, _) in enumerate(rows)}
    num_rows = len(rows)
    current_theme = st.session_state.get('theme', 'dark')
    colors = theme_tokens(current_theme)

    fig = sp.make_subplots(
        rows=num_rows, cols=1,
        shared_xaxes=True,
        row_heights=[weight for _, _, weight in rows],
        vertical_spacing=0.02,
        subplot_titles=[title for title, _, _ in rows],
    )
    
    # Row 1: Candlestick + MA + BB
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price",
            increasing_line_color=colors["success"],
            increasing_fillcolor=colors["success"],
            decreasing_line_color=colors["danger"],
            decreasing_fillcolor=colors["danger"],
        ),
        row=row_lookup["price"], col=1
    )
    
    if show_sma:
        fig.add_trace(go.Scatter(x=df.index, y=ma50, name="SMA 50", line=dict(color=colors["primary"], width=1.4)), row=row_lookup["price"], col=1)
        if ma200 is not None:
            fig.add_trace(go.Scatter(x=df.index, y=ma200, name="SMA 200", line=dict(color=colors["warning"], width=1.2)), row=row_lookup["price"], col=1)

    if show_ema:
        ema12 = price.ewm(span=12).mean()
        ema26 = price.ewm(span=26).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ema12, name="EMA 12", line=dict(color="#14b8a6", width=1.2)), row=row_lookup["price"], col=1)
        fig.add_trace(go.Scatter(x=df.index, y=ema26, name="EMA 26", line=dict(color="#8b5cf6", width=1.2)), row=row_lookup["price"], col=1)

    if show_bollinger and upper is not None and lower is not None:
        fig.add_trace(go.Scatter(x=df.index, y=upper, name="BB Upper", line=dict(color=colors["muted"], dash="dash", width=1)), row=row_lookup["price"], col=1)
        fig.add_trace(go.Scatter(x=df.index, y=lower, name="BB Lower", line=dict(color=colors["muted"], dash="dash", width=1), fill="tonexty", fillcolor="rgba(125, 139, 157, 0.08)"), row=row_lookup["price"], col=1)
    
    # Add entry/exit signals if backtest active
    if backtest_data is not None and backtest_signals is not None:
        entries_idx = backtest_signals['entries'][backtest_signals['entries'] > 0].index
        exits_idx = backtest_signals['exits'][backtest_signals['exits'] > 0].index
        entries_idx = entries_idx.intersection(df.index)
        exits_idx = exits_idx.intersection(df.index)
        
        if len(entries_idx) > 0:
            entry_lows = df.loc[entries_idx, "Low"]
            fig.add_trace(
                go.Scatter(x=entries_idx, y=entry_lows, mode="markers",
                          marker=dict(size=9, color=colors["success"], symbol="triangle-up"),
                          name="Buy", showlegend=True),
                row=row_lookup["price"], col=1
            )
        
        if len(exits_idx) > 0:
            exit_highs = df.loc[exits_idx, "High"]
            fig.add_trace(
                go.Scatter(x=exits_idx, y=exit_highs, mode="markers",
                          marker=dict(size=9, color=colors["danger"], symbol="triangle-down"),
                          name="Sell", showlegend=True),
                row=row_lookup["price"], col=1
            )
    
    if show_volume:
        volume_colors = np.where(df["Close"] >= df["Open"], colors["success"], colors["danger"])
        fig.add_trace(
            go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color=volume_colors, opacity=0.58),
            row=row_lookup["volume"], col=1,
        )
    
    if show_macd and macd_line is not None and signal is not None:
        histogram = macd_line - signal
        hist_colors = np.where(histogram >= 0, colors["success"], colors["danger"])
        fig.add_trace(go.Bar(x=df.index, y=histogram, name="MACD Hist", marker_color=hist_colors, opacity=0.5), row=row_lookup["macd"], col=1)
        fig.add_trace(go.Scatter(x=df.index, y=macd_line, name="MACD", line=dict(color=colors["primary"], width=1.4)), row=row_lookup["macd"], col=1)
        fig.add_trace(go.Scatter(x=df.index, y=signal, name="Signal", line=dict(color=colors["warning"], width=1.2)), row=row_lookup["macd"], col=1)
    
    if show_rsi and rsi_values is not None:
        fig.add_trace(go.Scatter(x=df.index, y=rsi_values, name="RSI", line=dict(color="#8b5cf6", width=1.3)), row=row_lookup["rsi"], col=1)
        fig.add_hline(y=70, line_dash="dash", line_color=colors["danger"], row=row_lookup["rsi"], col=1)
        fig.add_hline(y=30, line_dash="dash", line_color=colors["success"], row=row_lookup["rsi"], col=1)
    
    if backtest_data is not None:
        equity = backtest_data['equity']
        # Use the full price series for buy & hold calculation, aligned with equity dates
        try:
            aligned_index = equity.index.intersection(price.index)
            equity = equity.reindex(aligned_index).dropna()
            aligned_price = price.reindex(aligned_index).dropna()
            if equity.empty or aligned_price.empty:
                raise ValueError("Backtest equity is not aligned with selected price data")
            bh_equity = buy_hold_equity(aligned_price, initial_equity=100)
            
            fig.add_trace(
                go.Scatter(x=equity.index, y=equity.values, name="Strategy", line=dict(color=colors["primary"], width=2)),
                row=row_lookup["equity"], col=1
            )
            fig.add_trace(
                go.Scatter(x=bh_equity.index, y=bh_equity.values, name="Buy & Hold", 
                          line=dict(color=colors["muted"], width=2, dash="dash")),
                row=row_lookup["equity"], col=1
            )
        except Exception as e:
            st.warning(f"Could not display equity curve: {e}")
    
    # Layout
    template = get_plotly_template(current_theme)
    
    fig.update_layout(
        height=min(980, 430 + 120 * (num_rows - 1)),
        hovermode='x unified',
        template=template,
        legend=dict(orientation="h", y=1.03, x=0),
        margin=dict(l=38, r=18, t=46, b=28),
        xaxis_rangeslider_visible=False,
    )
    
    fig.update_yaxes(title_text="Price", row=row_lookup["price"], col=1)
    if show_volume:
        fig.update_yaxes(title_text="Vol", row=row_lookup["volume"], col=1)
    if show_macd:
        fig.update_yaxes(title_text="MACD", row=row_lookup["macd"], col=1)
    if show_rsi:
        fig.update_yaxes(title_text="RSI", row=row_lookup["rsi"], col=1, range=[0, 100])
    if backtest_data is not None:
        fig.update_yaxes(title_text="Equity", row=row_lookup["equity"], col=1)
    
    st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application function with comprehensive error handling."""
    try:
        # Initialize session state with validation
        required_session_keys = [
            'backtest_cache', 'show_welcome', 'ui_mode', 'theme', 'mode',
            'ticker_input', 'data_source', 'guided_tour_active', 'guided_tour_step', 'simulator'
        ]

        for key in required_session_keys:
            if key not in st.session_state:
                if key == 'backtest_cache':
                    st.session_state.backtest_cache = {}
                elif key == 'show_welcome':
                    st.session_state.show_welcome = True
                elif key == 'ui_mode':
                    st.session_state.ui_mode = 'simple'
                elif key == 'theme':
                    st.session_state.theme = 'dark'
                elif key == 'mode':
                    st.session_state.mode = 'backtesting'
                elif key == 'ticker_input':
                    st.session_state.ticker_input = DEFAULT_TICKERS
                elif key == 'data_source':
                    st.session_state.data_source = DEFAULT_DATA_SOURCE
                elif key == 'guided_tour_active':
                    st.session_state.guided_tour_active = False
                elif key == 'guided_tour_step':
                    st.session_state.guided_tour_step = 0
                elif key == 'simulator':
                    st.session_state.simulator = {
                        'active': False,
                        'engine': None,
                        'current_step': 0,
                        'total_steps': 0,
                        'is_playing': False
                    }

        apply_app_theme(st.session_state.get('theme', 'dark'))

        # Show welcome dashboard if needed
        if st.session_state.show_welcome:
            show_welcome_dashboard()
            return  # Exit early to show only welcome screen

        # Main application logic
        show_main_dashboard()

    except Exception as e:
        st.error(f"Application error: {str(e)}")
        st.info("Please refresh the page to restart the application.")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())


def show_simulator_mode(data, selected_ticker, start, end, interval):
    """Handle simulator mode logic."""
    try:
        # Initialize simulator
        create_simulator_session()
        simulator = get_simulator_engine()

        # Simulator settings
        st.subheader("Simulator")
        render_workflow_help("Simulator")

        if not st.session_state.simulator.get('autostarted'):
            st.session_state.simulator['active'] = True
            st.session_state.simulator['autostarted'] = True

        # Simulator controls
        simulator_active = st.toggle(
            "Simulator On",
            value=st.session_state.simulator.get('active', False),
            help="Turn the manual trading simulator on or off"
        )

        if simulator_active:
            st.session_state.simulator['active'] = True

            setup_expanded = not hasattr(simulator, 'sim_data') or simulator.sim_data is None
            with st.expander("Simulation Setup", expanded=setup_expanded):
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    sim_start = st.date_input(
                        "Start Date",
                        value=start,
                        key="sim_start",
                        help="When your trading simulation begins"
                    )
                with col2:
                    sim_end = st.date_input(
                        "End Date",
                        value=end,
                        key="sim_end",
                        help="When your trading simulation ends"
                    )
                with col3:
                    initial_equity = st.number_input(
                        "Starting Capital ($)",
                        value=10000,
                        min_value=1000,
                        max_value=1000000,
                        step=1000,
                        help="How much money you start with"
                    )
                with col4:
                    sim_fee = st.slider(
                        "Fee (%)",
                        min_value=0.0,
                        max_value=1.0,
                        value=0.1,
                        step=0.01,
                        help="Cost per trade (realistic trading costs)"
                    ) / 100

            # Initialize simulator with settings
            sim_config_key = (
                selected_ticker,
                str(sim_start),
                str(sim_end),
                interval,
                float(initial_equity),
                round(float(sim_fee), 6),
            )
            needs_init = (
                not hasattr(simulator, 'sim_data')
                or simulator.sim_data is None
                or st.session_state.simulator.get('config_key') != sim_config_key
            )
            if needs_init:
                try:
                    # Get data for the selected ticker
                    sim_data = load_data_with_status([selected_ticker], sim_start, sim_end, interval)

                    if len(sim_data) > 0:
                        simulator.reset()
                        simulator.transaction_fee = sim_fee
                        simulator.initial_equity = initial_equity
                        simulator.set_timeframe(sim_data, sim_start, sim_end)
                        st.session_state.simulator['config_key'] = sim_config_key
                        st.success(f"Simulation ready for {selected_ticker} with ${initial_equity:,.0f} starting capital.")
                    else:
                        st.error("No data available for the selected period")
                        simulator_active = False

                except Exception as e:
                    st.error(f"Failed to initialize simulator: {e}")
                    simulator_active = False

            # Trading controls
            if simulator_active and hasattr(simulator, 'sim_data'):
                if 'simulator_last_message' in st.session_state:
                    st.success(st.session_state.simulator_last_message)
                    del st.session_state.simulator_last_message

                state = simulator.get_current_state()
                current_price = float(state.get('price') or 0.0)
                shares_held = int(state.get('shares', 0))

                render_status_strip([
                    ("Date", state['date'].strftime('%Y-%m-%d')),
                    ("Cash", _fmt_money(state['cash'])),
                    ("Shares", f"{shares_held:,}"),
                    ("Equity", _fmt_money(state['total_equity'])),
                    ("Price", _fmt_money(current_price)),
                ])

                st.markdown("<div class='qma-section-title'>Trading Panel</div>", unsafe_allow_html=True)

                # Buy/Sell section with better layout
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**Buy**")
                    max_affordable_qty = simulator.max_affordable_quantity()
                    buy_size_mode = st.radio(
                        "Buy Size",
                        ["Max", "50% Cash", "25% Cash", "10% Cash", "Custom"],
                        horizontal=True,
                        key="buy_size_mode",
                    )
                    buy_fraction_by_mode = {
                        "Max": 1.0,
                        "50% Cash": 0.50,
                        "25% Cash": 0.25,
                        "10% Cash": 0.10,
                    }
                    buy_default = min(max_affordable_qty, 100)
                    if buy_size_mode in buy_fraction_by_mode:
                        buy_default = simulator.quantity_for_cash_fraction(buy_fraction_by_mode[buy_size_mode])
                        st.session_state.buy_qty = buy_default
                    if st.session_state.get("buy_qty", buy_default) > max_affordable_qty:
                        st.session_state.buy_qty = buy_default
                    st.caption(f"Max affordable shares: {max_affordable_qty:,}")
                    buy_qty = st.number_input(
                        "Quantity to Buy",
                        min_value=0,
                        max_value=max(max_affordable_qty, 1),
                        value=buy_default,
                        step=1,
                        disabled=max_affordable_qty == 0,
                        key="buy_qty"
                    )
                    buy_preview = simulator.preview_buy(buy_qty)
                    display_order_preview(buy_preview)

                    if st.button(
                        "Execute Buy",
                        type="primary",
                        use_container_width=True,
                        disabled=not buy_preview["can_execute"],
                    ):
                        if simulator.execute_buy(buy_qty):
                            st.session_state.simulator_last_message = (
                                f"Bought {buy_qty:,} shares at {_fmt_money(current_price)}. "
                                f"Cash is now {_fmt_money(buy_preview['cash_after'])}; "
                                f"shares held: {buy_preview['shares_after']:,}; "
                                f"exposure: {_fmt_pct(buy_preview['exposure_after'])}."
                            )
                            st.rerun()
                        else:
                            can_buy, reason = simulator.can_buy(buy_qty)
                            st.error(reason)

                with col2:
                    st.markdown("**Sell**")
                    if shares_held == 0:
                        st.caption("No shares are currently held.")
                    else:
                        st.caption(f"Shares available to sell: {shares_held:,}")
                    sell_size_mode = st.radio(
                        "Sell Size",
                        ["All", "50% Position", "25% Position", "Custom"],
                        horizontal=True,
                        key="sell_size_mode",
                        disabled=shares_held == 0,
                    )
                    sell_fraction_by_mode = {
                        "All": 1.0,
                        "50% Position": 0.50,
                        "25% Position": 0.25,
                    }
                    sell_default = min(shares_held, 100)
                    if sell_size_mode in sell_fraction_by_mode:
                        sell_default = shares_held if sell_size_mode == "All" else max(1, int(shares_held * sell_fraction_by_mode[sell_size_mode]))
                        st.session_state.sell_qty = sell_default
                    if st.session_state.get("sell_qty", sell_default) > shares_held:
                        st.session_state.sell_qty = sell_default
                    sell_qty = st.number_input(
                        "Quantity to Sell",
                        min_value=0,
                        max_value=max(shares_held, 1),
                        value=sell_default,
                        step=1,
                        disabled=shares_held == 0,
                        key="sell_qty"
                    )
                    sell_preview = simulator.preview_sell(sell_qty)
                    display_order_preview(sell_preview)

                    if st.button(
                        "Execute Sell",
                        type="primary",
                        use_container_width=True,
                        disabled=shares_held == 0 or not sell_preview["can_execute"],
                    ):
                        if simulator.execute_sell(sell_qty):
                            st.session_state.simulator_last_message = (
                                f"Sold {sell_qty:,} shares at {_fmt_money(current_price)}. "
                                f"Cash is now {_fmt_money(sell_preview['cash_after'])}; "
                                f"shares held: {sell_preview['shares_after']:,}; "
                                f"realized P&L: {_fmt_money(sell_preview['realized_pnl'])}."
                            )
                            st.rerun()
                        else:
                            can_sell, reason = simulator.can_sell(sell_qty)
                            st.error(reason)

                # Time Navigation Panel
                st.markdown("<div class='qma-section-title'>Time Navigation</div>", unsafe_allow_html=True)

                time_col1, time_col2, time_col3, time_col4, time_col5 = st.columns(5)

                with time_col1:
                    nav_step = st.selectbox("Step", [1, 5, 20], index=0, help="Number of bars to move per click")

                with time_col2:
                    if st.button("Start", help="Go to beginning", use_container_width=True):
                        simulator.go_to_date(simulator.sim_data.index[0])
                        st.rerun()

                with time_col3:
                    if st.button("Back", help="Go back by the selected step", use_container_width=True):
                        if simulator.advance_time(-int(nav_step)):
                            st.rerun()
                        else:
                            st.info("Already at start")

                with time_col4:
                    if st.button("Next", help="Advance by the selected step", use_container_width=True):
                        if simulator.advance_time(int(nav_step)):
                            st.rerun()
                        else:
                            st.info("End of simulation reached")

                with time_col5:
                    confirm_reset = st.checkbox("Confirm reset", key="sim_reset_confirm")
                    if st.button(
                        "Reset",
                        type="secondary",
                        help="Reset simulation",
                        use_container_width=True,
                        disabled=not confirm_reset,
                    ):
                        reset_simulator()
                        st.rerun()
        else:
            st.session_state.simulator['active'] = False
            st.info("Turn the simulator on to practice manual orders against the selected historical window.")

    except Exception as e:
        st.error(f"Simulator mode error: {e}")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())


def display_simulator_chart(data, selected_ticker):
    """Display simulator chart with trades."""
    try:
        if not hasattr(st.session_state.simulator['engine'], 'sim_data') or st.session_state.simulator['engine'].sim_data is None:
            st.info("Activate the simulator to see the trading chart")
            return

        simulator = st.session_state.simulator['engine']

        # Get data
        df = simulator.sim_data.copy()
        price = df["Close"]

        # Create subplots
        fig = sp.make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            row_heights=[0.7, 0.3],
            vertical_spacing=0.02,
            subplot_titles=("Price Action & Trades", "Equity Curve")
        )

        # Row 1: Candlestick + trades
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name="Price"
            ),
            row=1, col=1
        )

        # Add trade markers
        orders = getattr(simulator, 'orders', [])
        if not orders and hasattr(simulator, 'trades'):
            orders = simulator.trades

        if orders:
            buy_trades = pd.DataFrame([t for t in orders if t.get('action') == 'BUY'])
            sell_trades = pd.DataFrame([t for t in orders if t.get('action') == 'SELL'])

            if not buy_trades.empty:
                fig.add_trace(
                    go.Scatter(
                        x=buy_trades['date'],
                        y=buy_trades['price'],
                        mode="markers",
                        marker=dict(size=10, color="green", symbol="triangle-up"),
                        name="Buy Orders"
                    ),
                    row=1, col=1
                )

            if not sell_trades.empty:
                fig.add_trace(
                    go.Scatter(
                        x=sell_trades['date'],
                        y=sell_trades['price'],
                        mode="markers",
                        marker=dict(size=10, color="red", symbol="triangle-down"),
                        name="Sell Orders"
                    ),
                    row=1, col=1
                )

        # Row 2: Equity curve
        equity_curve = simulator.get_equity_curve()
        if not equity_curve.empty:
            fig.add_trace(
                go.Scatter(
                    x=equity_curve.index,
                    y=equity_curve.values,
                    name="Equity",
                    line=dict(color="purple", width=2)
                ),
                row=2, col=1
            )

            # Add buy-and-hold comparison
            bh_equity = buy_hold_equity(df["Close"], initial_equity=simulator.initial_equity)
            fig.add_trace(
                go.Scatter(
                    x=bh_equity.index,
                    y=bh_equity.values,
                    name="Buy & Hold",
                    line=dict(color="gray", dash="dash")
                ),
                row=2, col=1
            )

        # Get current theme
        current_theme = st.session_state.get('theme', 'dark')
        template = get_plotly_template(current_theme)

        fig.update_layout(height=600, showlegend=True, template=template)
        fig.update_xaxes(title_text="Date", row=2, col=1)
        fig.update_yaxes(title_text="Price ($)", row=1, col=1)
        fig.update_yaxes(title_text="Equity ($)", row=2, col=1)

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Chart display error: {e}")


def show_backtesting_mode(data, selected_ticker, start, end, interval, enable_portfolio, portfolio_weight_input, rebalance_period, enable_risk, stop_loss_pct, take_profit_pct, enable_optimizer, optimizer_strategy, optimizer_strat_hold, optimizer_strat_fee):
    """Handle backtesting mode logic."""
    try:
        st.subheader("Backtesting")
        render_workflow_help("Backtest")

        # Get data for selected ticker
        ticker_data = extract_ticker_data(data, selected_ticker, start, end)
        if ticker_data.empty:
            st.error("No data available for backtesting")
            return

        close = ticker_data["Close"]
        indicators = compute_all_indicators(close)

        # Strategy selection
        strategy_name = st.selectbox(
            "Select Strategy",
            STRATEGY_OPTIONS,
            index=STRATEGY_OPTIONS.index(st.session_state.get("backtest_strategy_select", "None"))
            if st.session_state.get("backtest_strategy_select", "None") in STRATEGY_OPTIONS
            else 0,
            key="backtest_strategy_select",
            help="Choose trading strategy to backtest"
        )

        if strategy_name != "None":
            # Quick presets
            preset = st.selectbox(
                "Quick Presets",
                ["Custom"] + list(TRADING_PRESETS.keys()),
                help="Pre-configured trading styles"
            )

            # Initialize config from preset or custom
            if preset != "Custom" and preset in TRADING_PRESETS:
                preset_config = TRADING_PRESETS[preset]
                default_hold = preset_config['holding_period']
                default_pos = preset_config['position_type']
                default_fee = preset_config['transaction_fee']
            else:
                default_hold, default_pos, default_fee = 0, "Fixed", 0.0

            # Backtesting date range
            st.markdown("**Backtest Period**")
            col1, col2 = st.columns(2)
            with col1:
                backtest_start = st.date_input(
                    "From",
                    value=DEFAULT_START,
                    key="backtest_start",
                    help="Start date for backtest"
                )
            with col2:
                backtest_end = st.date_input(
                    "To",
                    value=DEFAULT_END,
                    key="backtest_end"
                )

            if backtest_start >= backtest_end:
                st.error("Backtest start date must be before end date.")
                return

            backtest_ticker_data = extract_ticker_data(data, selected_ticker, backtest_start, backtest_end)
            close = backtest_ticker_data["Close"]
            close.name = selected_ticker
            indicators = compute_all_indicators(close)

            # Position & fees
            st.markdown("**Position Configuration**")
            col1, col2 = st.columns(2)

            with col1:
                position_type = st.radio(
                    "Position Sizing",
                    ["Fixed", "Dynamic"],
                    index=0 if default_pos == "Fixed" else 1,
                    horizontal=True,
                    help="Fixed=all-in | Dynamic=0-1"
                )

            with col2:
                holding_period = st.number_input(
                    "Hold Days",
                    value=default_hold,
                    min_value=0,
                    max_value=252,
                    help="0=day, 1-5=swing, 20+=position"
                )

            # Advanced options (only in expert mode)
            if st.session_state.ui_mode == 'expert':
                with st.expander("Advanced Options", expanded=False):
                    transaction_fee = st.slider(
                        "Transaction Fee (%)",
                        min_value=0.0,
                        max_value=1.0,
                        value=default_fee * 100,
                        step=0.01,
                        help="Per-trade cost"
                    ) / 100

                    sharpe_mode = st.selectbox(
                        "Sharpe Annualization",
                        list(SHARPE_MODES.keys()),
                    )
                    sharpe_interval = SHARPE_MODES[sharpe_mode]
            else:
                # Simple mode defaults
                transaction_fee = default_fee
                sharpe_interval = "1d"

            with st.expander("Analytics Options", expanded=False):
                benchmark_symbol = st.text_input(
                    "Benchmark",
                    value=st.session_state.get("benchmark_symbol", "SPY"),
                    help="Used for strategy comparison. SPY is the default broad-market benchmark.",
                    key="benchmark_symbol",
                ).strip().upper() or "SPY"
                enable_optimizer = st.checkbox("Run strategy optimizer", value=enable_optimizer)
                if enable_optimizer:
                    optimizer_strategy = st.selectbox(
                        "Optimizer Strategy",
                        [s for s in STRATEGY_OPTIONS if s != "None"],
                        index=0,
                        key="backtest_optimizer_strategy",
                    )
                    optimizer_strat_fee = st.slider(
                        "Optimizer Fee (%)",
                        min_value=0.0,
                        max_value=1.0,
                        value=optimizer_strat_fee * 100,
                        step=0.01,
                        key="backtest_optimizer_fee",
                    ) / 100

            config = {
                'position_type': position_type,
                'holding_period': int(holding_period),
                'fee_pct': transaction_fee,
                'interval': interval,
            }

            # Run backtest button
            if st.button("Run Backtest", type="primary"):
                with st.spinner("Running backtest..."):
                    try:
                        # Run backtest
                        backtest_result = run_single_backtest(strategy_name, close, indicators, config)
                        backtest_metrics = backtest_result

                        # Store results in session state
                        st.session_state.backtest_result = backtest_result
                        st.session_state.backtest_metrics = backtest_metrics
                        st.session_state.backtest_close = close
                        st.session_state.backtest_config = config
                        st.session_state.strategy_name = strategy_name
                        st.session_state.backtest_strategy_name = strategy_name
                        st.session_state.backtest_ticker = selected_ticker
                        st.session_state.backtest_date_range = (str(backtest_start), str(backtest_end))
                        st.session_state.backtest_benchmark_symbol = benchmark_symbol

                        benchmark_close = None
                        try:
                            if benchmark_symbol in available_tickers(data):
                                benchmark_close = get_ticker_frame(data, benchmark_symbol)["Close"]
                            else:
                                benchmark_data, benchmark_status = load_market_data(
                                    [benchmark_symbol],
                                    backtest_start,
                                    backtest_end,
                                    interval,
                                    source=st.session_state.get("data_source", DEFAULT_DATA_SOURCE),
                                )
                                if benchmark_data is not None and not benchmark_data.empty:
                                    benchmark_close = get_ticker_frame(benchmark_data, benchmark_symbol)["Close"]
                                    if benchmark_status.get("is_demo"):
                                        st.caption(f"{benchmark_symbol} benchmark is using demo data.")
                            st.session_state.backtest_benchmark_close = benchmark_close
                        except Exception as benchmark_error:
                            st.session_state.backtest_benchmark_close = None
                            st.caption(f"Benchmark comparison unavailable: {benchmark_error}")

                        st.success("Backtest completed!")

                        # Display metrics
                        display_metrics_panel(backtest_metrics)

                        with col2:
                            st.metric("Period", f"{(backtest_end - backtest_start).days}d")

                        st.divider()

                        # Trade log
                        display_trade_log(backtest_result, strategy_name)
                        display_strategy_analytics(
                            backtest_result,
                            close,
                            interval,
                            config,
                            benchmark_close=st.session_state.get("backtest_benchmark_close"),
                            benchmark_label=benchmark_symbol,
                        )
                        st.divider()

                    except Exception as e:
                        st.error(f"Backtest failed: {e}")

            # Display previous results if available
            stored_result_matches = (
                st.session_state.get("backtest_ticker") == selected_ticker
                and st.session_state.get("backtest_strategy_name") == strategy_name
            )
            if stored_result_matches and 'backtest_metrics' in st.session_state and st.session_state.backtest_metrics:
                st.subheader("Backtest Results")
                display_metrics_panel(st.session_state.backtest_metrics)

                # Trade log
                if 'backtest_result' in st.session_state:
                    display_trade_log(st.session_state.backtest_result, st.session_state.get('strategy_name', strategy_name))
                    display_strategy_analytics(
                        st.session_state.backtest_result,
                        st.session_state.get("backtest_close", close),
                        interval,
                        st.session_state.get("backtest_config", config),
                        benchmark_close=st.session_state.get("backtest_benchmark_close"),
                        benchmark_label=st.session_state.get("backtest_benchmark_symbol", "SPY"),
                    )

        # Phase 2: Strategy optimizer results
        if enable_optimizer and optimizer_strategy and strategy_name != 'None':
            st.subheader('Strategy Optimizer Results')
            try:
                param_grid = [
                    {'holding_period': h, 'position_type': 'fixed', 'fee_pct': optimizer_strat_fee}
                    for h in [0, 1, 2, 5, 10]
                ]
                optimizer_res = grid_search_strategy(
                    close,
                    indicators,
                    optimizer_strategy,
                    param_grid,
                    interval=interval
                )

                st.write('**Best optimizer config:**')
                st.json(optimizer_res['best'])
                st.write('**All tested cases:**')
                st.dataframe(optimizer_res['results'])

            except Exception as e:
                st.error(f'Optimizer failed: {e}')

    except Exception as e:
        st.error(f"Backtesting mode error: {e}")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())


def display_quant_lab_result(result, close, config, benchmark_close, benchmark_symbol, strategy_label):
    """Display Quant Lab results using the shared backtest views."""
    validation = result.get("validation")
    display_metrics_panel(result)

    status_items = [
        ("Rows Used", f"{result.get('rows_used', 0):,}"),
        ("Elapsed", f"{result.get('elapsed_seconds', 0):.2f}s"),
        ("Trades", len(result.get("trades", []))),
    ]
    if validation is not None:
        status_items.extend([
            ("Output", validation.output_kind),
            ("Signal Bars", f"{validation.signal_count:,}"),
        ])
    render_status_strip(status_items)

    if validation is not None:
        for warning in validation.warnings:
            st.warning(warning)

    explanation = explain_strategy_result(
        result,
        close,
        data_status=st.session_state.get("latest_data_status"),
        benchmark_close=benchmark_close,
        benchmark_label=benchmark_symbol,
        fee_pct=float(config.get("fee_pct", 0.0)),
    )
    st.markdown("**Plain-English Explanation**")
    st.info(explanation)

    display_trade_log(result, strategy_label)
    display_strategy_analytics(
        result,
        close,
        config.get("interval", "1d"),
        config,
        benchmark_close=benchmark_close,
        benchmark_label=benchmark_symbol,
    )


def show_quant_lab_workflow(data, selected_ticker, start, end, interval):
    """Advanced workflow for safe custom strategy validation and simulation."""
    st.subheader("Quant Lab")

    if st.session_state.get("ui_mode", "simple") != "expert":
        st.info("Quant Lab is available in Expert mode. Open Settings and switch Interface Mode to Expert.")
        return

    render_workflow_help("Quant Lab")

    with st.expander("Sandbox and validation rules", expanded=False):
        st.markdown(
            """
            Custom code must define exactly one `strategy(data)` function.
            Imports, files, network access, subprocesses, reflection helpers, and pandas write methods are blocked before execution.
            Strategy code runs in a separate process with a timeout and receives a copied, prepared market-data frame.
            """
        )

    template_list = template_names()
    selected_template = st.selectbox(
        "Strategy Template",
        template_list,
        index=template_list.index(st.session_state.get("quant_lab_template", DEFAULT_TEMPLATE_NAME))
        if st.session_state.get("quant_lab_template", DEFAULT_TEMPLATE_NAME) in template_list
        else 0,
        key="quant_lab_template",
    )
    template = get_template(selected_template)
    st.caption(template["description"])

    if "quant_lab_strategy_code" not in st.session_state:
        st.session_state.quant_lab_strategy_code = get_template_code(selected_template)

    load_col, validate_col, run_col = st.columns([1, 1, 1])
    with load_col:
        if st.button("Load Template", use_container_width=True):
            st.session_state.quant_lab_strategy_code = get_template_code(selected_template)
            st.rerun()

    code = st.text_area(
        "Strategy Code",
        height=280,
        key="quant_lab_strategy_code",
        help="Return (buy, sell), a DataFrame with buy/sell columns, or a Series named position.",
    )

    settings_col1, settings_col2, settings_col3, settings_col4 = st.columns(4)
    with settings_col1:
        quant_start = st.date_input("From", value=start, key="quant_lab_start")
    with settings_col2:
        quant_end = st.date_input("To", value=end, key="quant_lab_end")
    with settings_col3:
        initial_capital = st.number_input(
            "Starting Capital ($)",
            min_value=100.0,
            max_value=10_000_000.0,
            value=10_000.0,
            step=500.0,
            key="quant_lab_capital",
        )
    with settings_col4:
        benchmark_symbol = st.text_input(
            "Benchmark",
            value=st.session_state.get("quant_lab_benchmark", "SPY"),
            key="quant_lab_benchmark",
        ).strip().upper() or "SPY"

    config_col1, config_col2, config_col3 = st.columns(3)
    with config_col1:
        position_type = st.radio(
            "Position Sizing",
            ["Fixed", "Dynamic"],
            horizontal=True,
            key="quant_lab_position_type",
        )
    with config_col2:
        holding_period = st.number_input(
            "Hold Days",
            min_value=0,
            max_value=252,
            value=0,
            step=1,
            key="quant_lab_holding_period",
        )
    with config_col3:
        transaction_fee = st.slider(
            "Fee (%)",
            min_value=0.0,
            max_value=1.0,
            value=0.10,
            step=0.01,
            key="quant_lab_fee",
        ) / 100

    if quant_start >= quant_end:
        st.error("Quant Lab start date must be before end date.")
        return

    config = {
        "position_type": position_type,
        "holding_period": int(holding_period),
        "fee_pct": float(transaction_fee),
        "interval": interval,
        "initial_capital": float(initial_capital),
        "risk_free_rate": 0.02,
    }

    validate_requested = False
    run_requested = False
    with validate_col:
        validate_requested = st.button("Validate", use_container_width=True)
    with run_col:
        run_requested = st.button("Run Simulation", type="primary", use_container_width=True)

    if validate_requested:
        with st.spinner("Validating strategy safely..."):
            try:
                validate_strategy_code(code)
                ticker_data = extract_ticker_data(data, selected_ticker, quant_start, quant_end)
                prepared_data = build_strategy_data(ticker_data)
                validation_result = run_quant_lab_strategy(
                    code,
                    ticker_data,
                    config,
                    timeout_seconds=2.0,
                    max_rows=min(300, len(prepared_data)),
                )
                validation = validation_result["validation"]
                st.success("Strategy validated. Output shape and sandbox checks passed.")
                render_status_strip([
                    ("Output", validation.output_kind),
                    ("Rows Checked", f"{validation.rows_used:,}"),
                    ("Signal Bars", f"{validation.signal_count:,}"),
                    ("Elapsed", f"{validation_result.get('elapsed_seconds', 0):.2f}s"),
                ])
                for warning in validation.warnings:
                    st.warning(warning)
            except (StrategyValidationError, StrategyExecutionError, QuantLabError, ValueError) as exc:
                st.error(f"Validation failed: {exc}")

    if run_requested:
        with st.spinner("Running Quant Lab simulation..."):
            try:
                ticker_data = extract_ticker_data(data, selected_ticker, quant_start, quant_end)
                result = run_quant_lab_strategy(code, ticker_data, config, timeout_seconds=2.0)
                close = result["strategy_data"]["close"].reindex(result["equity"].index).dropna()
                close.name = selected_ticker

                benchmark_close = None
                try:
                    if benchmark_symbol in available_tickers(data):
                        benchmark_close = get_ticker_frame(data, benchmark_symbol)["Close"]
                    else:
                        benchmark_data, benchmark_status = load_market_data(
                            [benchmark_symbol],
                            quant_start,
                            quant_end,
                            interval,
                            source=st.session_state.get("data_source", DEFAULT_DATA_SOURCE),
                        )
                        if benchmark_data is not None and not benchmark_data.empty:
                            benchmark_close = get_ticker_frame(benchmark_data, benchmark_symbol)["Close"]
                            if benchmark_status.get("is_demo"):
                                st.caption(f"{benchmark_symbol} benchmark is using demo data.")
                except Exception as benchmark_error:
                    st.caption(f"Benchmark comparison unavailable: {benchmark_error}")

                strategy_label = f"Quant Lab - {selected_template}"
                st.session_state.quant_lab_result = result
                st.session_state.quant_lab_close = close
                st.session_state.quant_lab_config = config
                st.session_state.quant_lab_strategy_label = strategy_label
                st.session_state.quant_lab_ticker = selected_ticker
                st.session_state.quant_lab_benchmark_close = benchmark_close
                st.session_state.quant_lab_benchmark_symbol = benchmark_symbol

                st.session_state.backtest_result = result
                st.session_state.backtest_metrics = result
                st.session_state.backtest_close = close
                st.session_state.backtest_config = config
                st.session_state.backtest_ticker = selected_ticker
                st.session_state.backtest_strategy_name = strategy_label
                st.session_state.strategy_name = strategy_label
                st.session_state.backtest_benchmark_close = benchmark_close
                st.session_state.backtest_benchmark_symbol = benchmark_symbol

                st.success("Quant Lab simulation completed.")
                display_quant_lab_result(result, close, config, benchmark_close, benchmark_symbol, strategy_label)
            except (StrategyValidationError, StrategyExecutionError, QuantLabError, ValueError) as exc:
                st.error(f"Simulation failed safely: {exc}")

    stored_result_matches = (
        not run_requested
        and st.session_state.get("quant_lab_ticker") == selected_ticker
        and st.session_state.get("quant_lab_result") is not None
    )
    if stored_result_matches:
        st.subheader("Latest Quant Lab Result")
        display_quant_lab_result(
            st.session_state.quant_lab_result,
            st.session_state.get("quant_lab_close", pd.Series(dtype=float)),
            st.session_state.get("quant_lab_config", config),
            st.session_state.get("quant_lab_benchmark_close"),
            st.session_state.get("quant_lab_benchmark_symbol", "SPY"),
            st.session_state.get("quant_lab_strategy_label", "Quant Lab"),
        )


def show_main_content(data, selected_ticker, start, end, interval, mode, enable_portfolio, portfolio_weight_input, rebalance_period, enable_risk, stop_loss_pct, take_profit_pct, enable_optimizer, optimizer_strategy, optimizer_strat_hold, optimizer_strat_fee):
    """Display main content based on selected mode."""
    try:
        if mode == "Analysis":
            show_analysis_mode(data, selected_ticker, start, end, interval)
        elif mode == "Backtesting":
            show_backtesting_mode(data, selected_ticker, start, end, interval, enable_portfolio, portfolio_weight_input, rebalance_period, enable_risk, stop_loss_pct, take_profit_pct, enable_optimizer, optimizer_strategy, optimizer_strat_hold, optimizer_strat_fee)
        elif mode == "Simulator":
            show_simulator_mode(data, selected_ticker, start, end, interval)
        else:
            st.error(f"Unknown mode: {mode}")

    except Exception as e:
        st.error(f"Main content error: {e}")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())


def show_analysis_mode(data, selected_ticker, start, end, interval):
    """Handle analysis mode logic with stock discovery."""
    try:
        st.subheader("Stock Discovery & Analysis")

        # Stock search section
        st.markdown("### Find Stocks")
        
        # Search functionality
        search_col1, search_col2 = st.columns([3, 1])
        with search_col1:
            search_query = st.text_input(
                "Search stocks by symbol or name",
                placeholder="e.g., AAPL, Apple, TSLA...",
                help="Enter stock symbol or company name"
            )
        
        with search_col2:
            if st.button("Search", type="secondary"):
                if search_query:
                    with st.spinner("Searching..."):
                        try:
                            search_results = search_stocks(search_query)
                            if search_results:
                                st.session_state.search_results = search_results
                                st.success(f"Found {len(search_results)} results")
                            else:
                                st.warning("No stocks found matching your search")
                        except Exception as e:
                            st.error(f"Search failed: {e}")
                else:
                    st.warning("Please enter a search term")

        # Display search results
        if 'search_results' in st.session_state and st.session_state.search_results:
            st.markdown("### Search Results")
            
            # Create a table of results
            results_df = pd.DataFrame(st.session_state.search_results)
            if not results_df.empty:
                # Add selection column
                results_df['Select'] = False
                
                # Display editable dataframe
                edited_df = st.data_editor(
                    results_df[['symbol', 'name', 'Select']],
                    column_config={
                        "Select": st.column_config.CheckboxColumn(
                            "Select for Analysis",
                            help="Check to analyze this stock",
                            default=False,
                        )
                    },
                    disabled=["symbol", "name"],
                    hide_index=True,
                    key="stock_selection"
                )
                
                # Get selected stocks
                selected_stocks = edited_df[edited_df['Select']]['symbol'].tolist()
                
                if selected_stocks:
                    if len(selected_stocks) == 1:
                        selected_ticker = selected_stocks[0]
                        st.session_state.selected_analysis_ticker = selected_ticker
                        st.success(f"Selected: {selected_ticker}")
                    else:
                        st.info(f"Selected {len(selected_stocks)} stocks for analysis")
                        selected_ticker = selected_stocks[0]  # Use first one for now
                        st.session_state.selected_analysis_ticker = selected_ticker

        # Popular stocks section
        st.markdown("### Popular Stocks")
        try:
            popular_symbols = get_popular_stocks()
            if popular_symbols:
                # Get info for popular stocks
                popular_stocks = []
                for symbol in popular_symbols[:8]:  # Show top 8
                    try:
                        info = get_stock_info(symbol)
                        if info:
                            popular_stocks.append({
                                'symbol': symbol,
                                'name': info.get('name', symbol)
                            })
                    except:
                        popular_stocks.append({
                            'symbol': symbol,
                            'name': symbol
                        })
                
                cols = st.columns(4)
                for i, stock in enumerate(popular_stocks):
                    with cols[i % 4]:
                        if st.button(f"{stock['symbol']}\n{stock['name']}", key=f"popular_{i}_{stock['symbol']}"):
                            selected_ticker = stock['symbol']
                            st.session_state.selected_analysis_ticker = selected_ticker
                            st.success(f"Selected: {selected_ticker}")
                            st.rerun()
        except Exception as e:
            st.warning(f"Could not load popular stocks: {e}")

        # Analysis settings (only show if we have a selected ticker)
        selected_ticker = st.session_state.get('selected_analysis_ticker', selected_ticker)
        
        if selected_ticker:
            st.markdown("---")
            st.markdown("### Technical Analysis Settings")

            # Indicator selection
            col1, col2 = st.columns(2)
            with col1:
                if "analysis_indicators" not in st.session_state:
                    st.session_state.analysis_indicators = COMMON_CHART_INDICATORS.copy()
                action_cols = st.columns(3)
                with action_cols[0]:
                    if st.button("Common", key="analysis_indicators_common", use_container_width=True):
                        st.session_state.analysis_indicators = COMMON_CHART_INDICATORS.copy()
                        st.rerun()
                with action_cols[1]:
                    if st.button("All", key="analysis_indicators_all", use_container_width=True):
                        st.session_state.analysis_indicators = CHART_INDICATOR_OPTIONS.copy()
                        st.rerun()
                with action_cols[2]:
                    if st.button("Off", key="analysis_indicators_off", use_container_width=True):
                        st.session_state.analysis_indicators = []
                        st.rerun()
                selected_indicators = st.multiselect(
                    "Technical Indicators",
                    CHART_INDICATOR_OPTIONS,
                    key="analysis_indicators",
                    help="Select indicators to display on the chart"
                )

            with col2:
                chart_type = st.selectbox(
                    "Chart Type",
                    ["Candlestick", "Line", "OHLC"],
                    index=0,
                    help="Choose how to display price data"
                )

            # Generate analysis
            if st.button("Run Analysis", type="primary"):
                with st.spinner("Analyzing data..."):
                    try:
                        # Get data for selected ticker
                        raw_analysis_data = load_data_with_status([selected_ticker], start, end, interval)

                        if raw_analysis_data is None or len(raw_analysis_data) == 0:
                            st.error("No data available for analysis")
                            return

                        analysis_data = extract_ticker_data(raw_analysis_data, selected_ticker, start, end)

                        # Calculate indicators
                        indicators_data = {}
                        for indicator in selected_indicators:
                            try:
                                if indicator == "SMA":
                                    ma50, ma200 = moving_averages(analysis_data["Close"])
                                    if ma50 is not None:
                                        indicators_data["SMA_50"] = ma50
                                    if ma200 is not None:
                                        indicators_data["SMA_200"] = ma200
                                elif indicator == "EMA":
                                    # Calculate EMA manually since not available
                                    if len(analysis_data) >= 12:
                                        indicators_data["EMA_12"] = analysis_data["Close"].ewm(span=12).mean()
                                    if len(analysis_data) >= 26:
                                        indicators_data["EMA_26"] = analysis_data["Close"].ewm(span=26).mean()
                                elif indicator == "RSI":
                                    rsi_values = rsi(analysis_data["Close"])
                                    if not rsi_values.empty:
                                        indicators_data["RSI"] = rsi_values
                                elif indicator == "MACD":
                                    macd_line, signal = macd(analysis_data["Close"])
                                    if macd_line is not None and signal is not None:
                                        indicators_data["MACD"] = macd_line
                                        indicators_data["Signal"] = signal
                                        indicators_data["Histogram"] = macd_line - signal
                                elif indicator == "Bollinger Bands":
                                    upper, lower = bollinger(analysis_data["Close"])
                                    if upper is not None and lower is not None:
                                        indicators_data["BB_Upper"] = upper
                                        indicators_data["BB_Middle"] = analysis_data["Close"].rolling(20).mean()
                                        indicators_data["BB_Lower"] = lower
                                elif indicator == "Volume":
                                    indicators_data["Volume"] = analysis_data["Volume"]
                            except Exception as e:
                                st.warning(f"Could not calculate {indicator}: {e}")

                        # Display chart
                        display_analysis_chart(analysis_data, indicators_data, chart_type, selected_indicators)

                        # Summary statistics
                        st.markdown("### Summary Statistics")
                        col1, col2, col3, col4 = st.columns(4)

                        with col1:
                            st.metric("Period", f"{len(analysis_data)} days")
                        with col2:
                            start_price = analysis_data["Close"].iloc[0]
                            end_price = analysis_data["Close"].iloc[-1]
                            change = ((end_price - start_price) / start_price) * 100
                            st.metric("Total Return", f"{change:.2f}%")
                        with col3:
                            st.metric("Max Price", f"${analysis_data['High'].max():.2f}")
                        with col4:
                            st.metric("Min Price", f"${analysis_data['Low'].min():.2f}")

                    except Exception as e:
                        st.error(f"Analysis failed: {e}")
        else:
            st.info("Select a stock above to begin technical analysis")

    except Exception as e:
        st.error(f"Analysis mode error: {e}")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())


def display_analysis_chart(data, indicators, chart_type, selected_indicators):
    """Display analysis chart with indicators."""
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if "Close" in data.columns.get_level_values(0):
                data = data.xs(data.columns.get_level_values(1)[0], level=1, axis=1)
            elif "Close" in data.columns.get_level_values(1):
                data = data.xs(data.columns.get_level_values(0)[0], level=0, axis=1)

        # Create subplots based on indicators
        subplot_count = 1
        if "Volume" in selected_indicators:
            subplot_count = 2
        if "RSI" in selected_indicators:
            subplot_count += 1
        if "MACD" in selected_indicators:
            subplot_count += 1

        heights = [0.6] + [0.4 / (subplot_count - 1)] * (subplot_count - 1) if subplot_count > 1 else [1.0]

        fig = sp.make_subplots(
            rows=subplot_count, cols=1,
            shared_xaxes=True,
            row_heights=heights,
            vertical_spacing=0.02,
            subplot_titles=["Price & Indicators"] + ["Volume"] * ("Volume" in selected_indicators) + ["RSI"] * ("RSI" in selected_indicators) + ["MACD"] * ("MACD" in selected_indicators)
        )

        # Main price chart
        if chart_type == "Candlestick":
            fig.add_trace(
                go.Candlestick(
                    x=data.index,
                    open=data["Open"],
                    high=data["High"],
                    low=data["Low"],
                    close=data["Close"],
                    name="Price"
                ),
                row=1, col=1
            )
        elif chart_type == "Line":
            fig.add_trace(
                go.Scatter(x=data.index, y=data["Close"], name="Close Price", line=dict(color="blue")),
                row=1, col=1
            )
        else:  # OHLC
            fig.add_trace(
                go.Ohlc(
                    x=data.index,
                    open=data["Open"],
                    high=data["High"],
                    low=data["Low"],
                    close=data["Close"],
                    name="Price"
                ),
                row=1, col=1
            )

        # Add indicators to main chart
        for indicator_name, indicator_data in indicators.items():
            if indicator_name not in ["Volume", "RSI", "MACD", "Signal", "Histogram"]:
                if isinstance(indicator_data, pd.Series):
                    fig.add_trace(
                        go.Scatter(
                            x=indicator_data.index,
                            y=indicator_data.values,
                            name=indicator_name,
                            line=dict(width=1.5)
                        ),
                        row=1, col=1
                    )

        # Add Bollinger Bands
        if "BB_Upper" in indicators and "BB_Lower" in indicators:
            fig.add_trace(
                go.Scatter(
                    x=indicators["BB_Upper"].index,
                    y=indicators["BB_Upper"].values,
                    name="BB Upper",
                    line=dict(color="gray", dash="dash")
                ),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(
                    x=indicators["BB_Lower"].index,
                    y=indicators["BB_Lower"].values,
                    name="BB Lower",
                    line=dict(color="gray", dash="dash")
                ),
                row=1, col=1
            )

        current_row = 2

        # Volume subplot
        if "Volume" in indicators:
            fig.add_trace(
                go.Bar(
                    x=data.index,
                    y=indicators["Volume"].values,
                    name="Volume",
                    marker_color="lightblue"
                ),
                row=current_row, col=1
            )
            current_row += 1

        # RSI subplot
        if "RSI" in indicators:
            fig.add_trace(
                go.Scatter(
                    x=indicators["RSI"].index,
                    y=indicators["RSI"].values,
                    name="RSI",
                    line=dict(color="purple")
                ),
                row=current_row, col=1
            )
            # Add RSI levels
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=current_row, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=current_row, col=1)
            current_row += 1

        # MACD subplot
        if "MACD" in indicators and "Signal" in indicators and "Histogram" in indicators:
            fig.add_trace(
                go.Scatter(
                    x=indicators["MACD"].index,
                    y=indicators["MACD"].values,
                    name="MACD",
                    line=dict(color="blue")
                ),
                row=current_row, col=1
            )
            fig.add_trace(
                go.Scatter(
                    x=indicators["Signal"].index,
                    y=indicators["Signal"].values,
                    name="Signal",
                    line=dict(color="red")
                ),
                row=current_row, col=1
            )
            fig.add_trace(
                go.Bar(
                    x=indicators["Histogram"].index,
                    y=indicators["Histogram"].values,
                    name="Histogram",
                    marker_color="gray"
                ),
                row=current_row, col=1
            )

        # Get current theme
        current_theme = st.session_state.get('theme', 'dark')
        template = get_plotly_template(current_theme)

        fig.update_layout(height=600, showlegend=True, template=template)
        fig.update_xaxes(title_text="Date", row=subplot_count, col=1)

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Chart display error: {e}")


def parse_portfolio_weights(weight_input, tickers):
    """Parse portfolio weights from text, defaulting to equal weights."""
    tickers = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    if not tickers:
        return {}

    if not weight_input.strip():
        equal_weight = 1 / len(tickers)
        return {ticker: equal_weight for ticker in tickers}

    weights = {}
    for item in weight_input.split(","):
        if ":" not in item:
            continue
        symbol, value = item.split(":", 1)
        symbol = symbol.strip().upper()
        if symbol:
            weights[symbol] = float(value.strip())

    if not weights:
        equal_weight = 1 / len(tickers)
        return {ticker: equal_weight for ticker in tickers}

    total = sum(weights.values())
    if total <= 0:
        raise ValueError("Portfolio weights must sum to a positive value")

    return {symbol: value / total for symbol, value in weights.items()}


def tutorial_table(rows, height=None):
    """Render tutorial rows as a compact dataframe."""
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=height)


def apply_learning_scenario(scenario: dict):
    """Apply an optional learning scenario to session state."""
    workflow_by_mode = {
        "overview": "Overview",
        "tutorial": "Tutorial",
        "backtesting": "Backtest",
        "simulator": "Simulator",
        "portfolio": "Portfolio",
        "risk": "Risk",
        "settings": "Settings",
    }
    st.session_state.ticker_input = scenario["tickers"]
    st.session_state.data_source = DEFAULT_DATA_SOURCE
    st.session_state.mode = scenario["mode"]
    st.session_state.workflow_selector = workflow_by_mode.get(scenario["mode"], "Overview")
    st.session_state.selected_workflow_ticker = scenario["selected_ticker"]
    st.session_state.backtest_strategy_select = scenario["strategy"]
    st.session_state.portfolio_weight_input = scenario.get("portfolio_weights", "")
    st.session_state.scenario_message = f"Loaded scenario: {scenario['name']}. {scenario['description']}"
    st.session_state.show_welcome = False


def queue_learning_scenario(scenario: dict):
    """Queue a scenario so it can be applied before widgets are created."""
    st.session_state.pending_learning_scenario = scenario["name"]
    st.session_state.show_welcome = False


def apply_pending_learning_scenario():
    """Apply a queued scenario before Streamlit widgets are instantiated."""
    scenario_name = st.session_state.pop("pending_learning_scenario", None)
    if not scenario_name:
        return

    scenario = next((item for item in LEARNING_SCENARIOS if item["name"] == scenario_name), None)
    if scenario is not None:
        apply_learning_scenario(scenario)


def render_learning_scenarios():
    """Render optional scenario launchers for guided examples."""
    st.markdown("**Learning scenarios**")
    st.caption("These are optional presets. They set tickers and the target workflow, then you can adjust anything.")

    scenario_rows = [
        {
            "Scenario": scenario["name"],
            "Tickers": scenario["tickers"],
            "Workflow": scenario["mode"].title(),
            "Purpose": scenario["description"],
        }
        for scenario in LEARNING_SCENARIOS
    ]
    tutorial_table(scenario_rows, height=245)

    cols = st.columns(3)
    for idx, scenario in enumerate(LEARNING_SCENARIOS):
        with cols[idx % 3]:
            st.markdown(f"**{scenario['name']}**")
            st.caption(scenario["description"])
            if st.button(f"Load {scenario['name']}", key=f"scenario_{idx}", use_container_width=True):
                queue_learning_scenario(scenario)
                st.rerun()


def render_workflow_help(workflow: str):
    """Render optional contextual help for a workflow."""
    help_data = WORKFLOW_HELP.get(workflow)
    if not help_data:
        return

    with st.expander(f"How to use {workflow}", expanded=False):
        st.markdown(f"**Goal:** {help_data['goal']}")
        for step in help_data["steps"]:
            st.markdown(f"- {step}")


def start_guided_tour(step: int = 0, mode: str = "tutorial"):
    """Start the optional guided walkthrough."""
    st.session_state.guided_tour_active = True
    st.session_state.guided_tour_step = max(0, min(int(step), len(GUIDED_TOUR_STEPS) - 1))
    st.session_state.mode = mode
    st.session_state.show_welcome = False


def stop_guided_tour():
    """Stop the optional guided walkthrough."""
    st.session_state.guided_tour_active = False


def guided_tour_step_index() -> int:
    """Return a valid guided tour step index."""
    raw_step = st.session_state.get("guided_tour_step", 0)
    try:
        step = int(raw_step)
    except (TypeError, ValueError):
        step = 0
    step = max(0, min(step, len(GUIDED_TOUR_STEPS) - 1))
    st.session_state.guided_tour_step = step
    return step


def render_guided_tour_launcher():
    """Render the optional walkthrough launcher."""
    if st.session_state.get("guided_tour_active", False):
        st.success("Guided walkthrough is on. Use the walkthrough panel above each workflow to continue or end it.")
        return

    st.markdown("**Optional guided walkthrough**")
    st.caption(
        "Turn this on if you want the app to guide you one step at a time. "
        "It will not start unless you choose it, and you can end it any time."
    )
    if st.button("Start Guided Walkthrough", type="primary", key="start_guided_walkthrough"):
        start_guided_tour()
        st.rerun()


def render_guided_tour_panel(current_workflow: str):
    """Render the active guided walkthrough panel."""
    if not st.session_state.get("guided_tour_active", False):
        return

    step_index = guided_tour_step_index()
    step = GUIDED_TOUR_STEPS[step_index]
    total_steps = len(GUIDED_TOUR_STEPS)
    target_workflow = step["workflow"]
    is_target_workflow = current_workflow == target_workflow

    st.markdown(
        f"""
        <div class='qma-panel' style='margin: 0.75rem 0;'>
            <span class='qma-status'>Guided Walkthrough</span>
            <h3 style='margin: 0.55rem 0 0.25rem;'>Step {step_index + 1} of {total_steps}: {html.escape(step['title'])}</h3>
            <p class='qma-muted' style='margin: 0 0 0.6rem;'>{html.escape(step['goal'])}</p>
            <p style='margin: 0.2rem 0;'><strong>Do this:</strong> {html.escape(step['action'])}</p>
            <p style='margin: 0.2rem 0;'><strong>Look for:</strong> {html.escape(step['look_for'])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_status_strip([
        ("Progress", f"{step_index + 1} of {total_steps}"),
        ("You Are In", current_workflow),
        ("Suggested Workflow", target_workflow),
        ("Status", "You are here" if is_target_workflow else "Jump available"),
    ])

    prev_col, go_col, next_col, end_col = st.columns(4)
    with prev_col:
        if st.button("Previous Step", disabled=step_index == 0, key="guided_prev"):
            st.session_state.guided_tour_step = max(0, step_index - 1)
            st.rerun()
    with go_col:
        if st.button(f"Go to {target_workflow}", disabled=is_target_workflow, key="guided_go"):
            st.session_state.mode = step["mode"]
            st.rerun()
    with next_col:
        next_label = "Finish Tour" if step_index == total_steps - 1 else "Next Step"
        if st.button(next_label, type="primary", key="guided_next"):
            if step_index == total_steps - 1:
                stop_guided_tour()
            else:
                st.session_state.guided_tour_step = step_index + 1
            st.rerun()
    with end_col:
        if st.button("End Tour", key="guided_end"):
            stop_guided_tour()
            st.rerun()


def show_tutorial_workflow(data, tickers, selected_ticker, interval):
    """Show an in-app guide for stocks, indicators, workflows, and simulator use."""
    st.subheader("Tutorial")

    loaded = available_tickers(data)
    status = st.session_state.get("latest_data_status", {})
    render_status_strip([
        ("Current Ticker", selected_ticker),
        ("Loaded Tickers", ", ".join(loaded) if loaded else "None"),
        ("Interval", interval),
        ("Data Source", status.get("source", st.session_state.get("data_source", DEFAULT_DATA_SOURCE))),
        ("Latest Bar", status.get("latest_bar", "N/A")),
    ])

    st.caption(
        "Use this guide as a map for the app. It explains the market terms, the indicators on the chart, "
        "and the workflow order for research, backtesting, manual simulation, portfolio review, and risk checks."
    )

    start_tab, scenarios_tab, stocks_tab, indicators_tab, backtest_tab, simulator_tab, risk_tab = st.tabs([
        "Start Here",
        "Scenarios",
        "Stocks & Data",
        "Indicators",
        "Backtesting",
        "Simulator",
        "Risk & Metrics",
    ])

    with start_tab:
        render_guided_tour_launcher()
        st.divider()
        st.markdown("**A good first session**")
        tutorial_table(TUTORIAL_STEPS, height=255)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                """
                **Beginner path**

                1. Keep the default ticker list.
                2. Keep `Auto` as the data source.
                3. Open `Overview` and inspect the price chart.
                4. Open `Backtest`, pick `MA Crossover`, and run it.
                5. Compare the strategy line against buy-and-hold.
                """
            )
        with col2:
            st.markdown(
                """
                **Practice path**

                1. Choose one ticker.
                2. Open `Simulator`.
                3. Use the order preview before buying or selling.
                4. Step through time and watch cash, shares, equity, and P&L.
                5. Review drawdown and risk afterward.
                """
            )

    with scenarios_tab:
        render_learning_scenarios()

    with stocks_tab:
        st.markdown("**Stock market basics used by this app**")
        tutorial_table(STOCK_TUTORIAL_ROWS, height=245)

        st.markdown("**Data sources**")
        tutorial_table(DATA_SOURCE_TUTORIAL_ROWS, height=180)
        st.info(
            "Recent data can still be delayed or unavailable depending on the provider, ticker, interval, and market schedule. "
            "Always check the status strip before interpreting a chart or backtest."
        )

    with indicators_tab:
        st.markdown("**Indicators on the chart**")
        tutorial_table(INDICATOR_TUTORIAL_ROWS, height=330)

        st.markdown(
            """
            **How to combine indicators**

            - Use price trend first: is the chart making higher highs, lower lows, or moving sideways?
            - Use moving averages for trend context.
            - Use RSI and MACD for momentum context.
            - Use Bollinger Bands for volatility and stretched price context.
            - Use volume to check whether a move has participation.
            - Treat indicators as evidence, not guarantees.
            """
        )

    with backtest_tab:
        st.markdown("**Strategies available in Backtest**")
        tutorial_table(STRATEGY_TUTORIAL_ROWS, height=220)

        st.markdown(
            """
            **How to run a backtest**

            1. Choose the ticker in `Ticker for single-asset workflows`.
            2. Open `Backtest`.
            3. Pick a strategy.
            4. Choose the backtest period.
            5. Set position sizing, holding period, and fees.
            6. Run the backtest.
            7. Read total return, Sharpe ratio, drawdown, win rate, trade log, and strategy comparison.

            A backtest is a historical experiment. It does not prove a strategy will keep working.
            """
        )

    with simulator_tab:
        st.markdown(
            """
            **What the simulator is for**

            The simulator is a risk-free practice mode. It uses historical candles and lets you decide when to buy,
            sell, step forward, or reset. It is useful for learning position sizing, patience, and how quickly a trade
            can change cash, exposure, and P&L.
            """
        )

        simulator_rows = [
            {
                "Control": "Simulation Setup",
                "Purpose": "Pick the period, starting capital, and transaction fee.",
                "Tip": "Use a shorter period while learning so the session moves quickly.",
            },
            {
                "Control": "Buy / Sell",
                "Purpose": "Place manual trades with a preview before execution.",
                "Tip": "Check trade value, fee, cash after, shares after, and exposure before submitting.",
            },
            {
                "Control": "Step controls",
                "Purpose": "Move through historical candles.",
                "Tip": "Pause after large moves and decide whether your plan changed.",
            },
            {
                "Control": "Reset",
                "Purpose": "Restart the simulation.",
                "Tip": "Use reset when you want to test a different decision path on the same data.",
            },
        ]
        tutorial_table(simulator_rows, height=200)

    with risk_tab:
        st.markdown("**Metrics you will see across the app**")
        tutorial_table(METRIC_TUTORIAL_ROWS, height=230)

        st.markdown(
            """
            **Risk review checklist**

            - Compare return against drawdown, not just against other returns.
            - Check whether a strategy only wins because of one lucky period.
            - Use correlation before assuming a group of tickers is diversified.
            - Use rolling volatility and rolling Sharpe to see whether behavior changes over time.
            - Use monthly returns to spot streaks, weak seasons, and outlier months.
            """
        )


def show_overview_workflow(data, tickers, selected_ticker, interval):
    """Show a compact landing workflow with market snapshot and setup state."""
    st.subheader("Overview")
    render_workflow_help("Overview")

    loaded_tickers = available_tickers(data)
    if not loaded_tickers:
        st.info("Choose at least one valid ticker in the sidebar to begin.")
        return

    close = get_close_prices(data)
    close_df = close.to_frame(selected_ticker) if isinstance(close, pd.Series) else close
    summary_rows = []
    for ticker in loaded_tickers:
        if ticker not in close_df.columns:
            continue
        prices = pd.to_numeric(close_df[ticker], errors="coerce").dropna()
        if prices.empty:
            continue
        total_return = (prices.iloc[-1] / prices.iloc[0] - 1) * 100 if prices.iloc[0] else 0.0
        summary_rows.append({
            "Ticker": ticker,
            "Last Price": f"${prices.iloc[-1]:.2f}",
            "Period Return": f"{total_return:.2f}%",
            "Rows": len(prices),
        })

    if summary_rows:
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.caption("Use the top workflow selector to move from market context into backtesting, manual simulation, portfolio analysis, or risk review.")


def show_portfolio_workflow(data, tickers, interval):
    """Show portfolio-specific settings and results."""
    st.subheader("Portfolio")
    render_workflow_help("Portfolio")
    loaded_tickers = available_tickers(data)
    if len(loaded_tickers) < 2:
        st.info("Portfolio analysis needs at least two loaded tickers. Add more symbols in the sidebar.")
        return

    default_weights = ",".join(f"{ticker}:{1 / len(loaded_tickers):.2f}" for ticker in loaded_tickers)
    col1, col2 = st.columns([3, 1])
    with col1:
        weight_input = st.text_input(
            "Portfolio Weights",
            value=st.session_state.get("portfolio_weight_input", default_weights),
            help="Format: AAPL:0.25,MSFT:0.25,SPY:0.50. Values are normalized automatically.",
            key="portfolio_weight_input",
        )
    with col2:
        rebalance_period = st.selectbox("Rebalance", ["monthly", "weekly", "daily"], index=0)

    try:
        weights = parse_portfolio_weights(weight_input, loaded_tickers)
        close = get_close_prices(data)
        prices = close.to_frame(loaded_tickers[0]) if isinstance(close, pd.Series) else close
        prices = prices[[ticker for ticker in loaded_tickers if ticker in prices.columns]].dropna(how="all")
        result = portfolio_backtest(prices, weights, rebalance=rebalance_period)

        render_status_strip([
            ("Sharpe", f"{result['sharpe_ratio']:.2f}"),
            ("Max Drawdown", f"{result['max_drawdown']:.2f}%"),
            ("Win Rate", f"{result['win_rate']:.1f}%"),
            ("Rebalance", rebalance_period.title()),
        ])

        weights_df = pd.DataFrame([
            {"Ticker": ticker, "Weight": f"{weights.get(ticker, 0) * 100:.1f}%"}
            for ticker in loaded_tickers
        ])
        st.dataframe(weights_df, use_container_width=True, hide_index=True)

        nav = result["nav"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=nav.index, y=nav.values, name="Portfolio NAV", line=dict(width=2)))
        fig.update_layout(
            height=420,
            yaxis_title="NAV",
            template=get_plotly_template(st.session_state.get('theme', 'dark')),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
        display_rolling_risk_charts(result["returns"], interval=interval, title_prefix="Portfolio")
        display_monthly_heatmap(result["returns"], title="Portfolio Monthly Returns")
    except Exception as e:
        st.error(f"Portfolio workflow failed: {e}")


def show_risk_workflow(data, selected_ticker, interval):
    """Show risk metrics and rolling risk charts for the selected ticker."""
    st.subheader("Risk")
    render_workflow_help("Risk")
    try:
        ticker_data = get_ticker_frame(data, selected_ticker)
        close = pd.to_numeric(ticker_data["Close"], errors="coerce").dropna()
        returns = close.pct_change().dropna()
        if returns.empty:
            st.info("Not enough price history to calculate risk metrics.")
            return

        var_95 = value_at_risk(returns, confidence=0.95)
        cvar_95 = conditional_value_at_risk(returns, confidence=0.95)
        dd = max_drawdown(close)
        max_duration, current_duration = drawdown_duration_stats(close)

        render_status_strip([
            ("VaR 95%", f"{var_95 * 100:.2f}%"),
            ("CVaR 95%", f"{cvar_95 * 100:.2f}%"),
            ("Max Drawdown", f"{dd:.2f}%"),
            ("Max DD Duration", f"{max_duration} periods"),
            ("Current DD Duration", f"{current_duration} periods"),
        ])
        st.caption("VaR estimates a downside threshold. CVaR estimates the average loss after that threshold is breached.")

        stop_loss_pct = st.slider("Stop Loss (%)", min_value=0.0, max_value=20.0, value=5.0, step=0.5)
        take_profit_pct = st.slider("Take Profit (%)", min_value=0.0, max_value=50.0, value=10.0, step=0.5)
        st.caption(f"Scenario guardrails: stop loss {stop_loss_pct:.1f}%, take profit {take_profit_pct:.1f}%.")

        display_rolling_risk_charts(returns, interval=interval, title_prefix=selected_ticker)
        display_monthly_heatmap(returns, title=f"{selected_ticker} Monthly Returns")
    except Exception as e:
        st.error(f"Risk workflow failed: {e}")


def show_settings_workflow():
    """Show app preferences in a top-level workflow."""
    st.subheader("Settings")
    render_workflow_help("Settings")
    col1, col2 = st.columns(2)
    with col1:
        ui_mode = st.radio(
            "Interface Mode",
            ["Simple", "Expert"],
            index=0 if st.session_state.get("ui_mode", "simple") == "simple" else 1,
            horizontal=True,
        )
        st.session_state.ui_mode = ui_mode.lower()
    with col2:
        theme = st.radio(
            "Theme",
            ["Dark", "Light"],
            index=0 if st.session_state.get("theme", "dark") == "dark" else 1,
            horizontal=True,
        )
        if st.session_state.get("theme") != theme.lower():
            st.session_state.theme = theme.lower()
            st.rerun()

    display_beginner_glossary()
    if st.button("Reset App Settings", type="secondary"):
        st.session_state.clear()
        st.rerun()


def show_main_dashboard():
    """Main dashboard display function."""
    try:
        apply_pending_learning_scenario()

        # Sidebar configuration
        with st.sidebar:
            sidebar_params = show_sidebar()
            if not sidebar_params:
                return

        # Extract parameters
        tickers = sidebar_params['tickers']
        start = sidebar_params['start']
        end = sidebar_params['end']
        interval = sidebar_params['interval']
        data_source = sidebar_params.get('data_source', st.session_state.get("data_source", DEFAULT_DATA_SOURCE))
        show_price = sidebar_params['show_price']
        chart_indicators = sidebar_params.get('chart_indicators', COMMON_CHART_INDICATORS)
        show_drawdown = sidebar_params['show_drawdown']
        show_corr = sidebar_params['show_corr']

        # Download data
        with st.spinner("Downloading market data..."):
            try:
                data = load_data_with_status(tickers, start, end, interval, data_source=data_source, emit_status=False)
                if data is None or len(data) == 0:
                    st.error("No data available for the selected period and tickers")
                    return
            except Exception as e:
                st.error(f"Failed to download data: {e}")
                return

        if st.session_state.get("scenario_message"):
            st.success(st.session_state.scenario_message)
            del st.session_state.scenario_message

        loaded_tickers = available_tickers(data)
        if not loaded_tickers:
            st.error("No tickers loaded")
            return

        with st.sidebar:
            st.divider()
            st.subheader("Watchlist")
            st.dataframe(watchlist_snapshot(data, loaded_tickers), use_container_width=True, hide_index=True)

        workflow_options = ["Overview", "Tutorial", "Backtest", "Simulator", "Portfolio", "Risk", "Settings"]
        if st.session_state.get("ui_mode", "simple") == "expert":
            workflow_options.insert(5, "Quant Lab")
        mode_to_workflow = {
            "overview": "Overview",
            "analysis": "Overview",
            "tutorial": "Tutorial",
            "backtesting": "Backtest",
            "simulator": "Simulator",
            "portfolio": "Portfolio",
            "quant_lab": "Quant Lab",
            "risk": "Risk",
            "settings": "Settings",
        }
        current_workflow = mode_to_workflow.get(st.session_state.get("mode", "backtesting"), "Backtest")
        if current_workflow not in workflow_options:
            current_workflow = "Backtest"
        workflow = st.radio(
            "Workflow",
            workflow_options,
            index=workflow_options.index(current_workflow),
            horizontal=True,
            key="workflow_selector",
        )
        workflow_to_mode = {
            "Overview": "overview",
            "Tutorial": "tutorial",
            "Backtest": "backtesting",
            "Simulator": "simulator",
            "Portfolio": "portfolio",
            "Quant Lab": "quant_lab",
            "Risk": "risk",
            "Settings": "settings",
        }
        st.session_state.mode = workflow_to_mode[workflow]
        is_simulator_mode = workflow == "Simulator"

        render_top_bar(
            "Quant Market Analytics",
            loaded_tickers,
            workflow,
            st.session_state.get("latest_data_status"),
            st.session_state.get("ui_mode", "simple"),
            st.session_state.get("theme", "dark"),
        )
        display_data_status(st.session_state.get("latest_data_status"))
        display_beginner_glossary()

        render_guided_tour_panel(workflow)

        selected_index = 0
        if tickers and tickers[0] in loaded_tickers:
            selected_index = loaded_tickers.index(tickers[0])
        if st.session_state.get("selected_workflow_ticker") not in loaded_tickers:
            st.session_state.selected_workflow_ticker = loaded_tickers[selected_index]
        selected_ticker = st.selectbox(
            "Ticker for single-asset workflows",
            loaded_tickers,
            index=selected_index,
            key="selected_workflow_ticker",
        )
        render_quote_header(data, selected_ticker, st.session_state.get("latest_data_status"))

        if workflow == "Overview":
            show_overview_workflow(data, loaded_tickers, selected_ticker, interval)
        elif workflow == "Tutorial":
            show_tutorial_workflow(data, loaded_tickers, selected_ticker, interval)
        elif workflow == "Backtest":
            show_backtesting_mode(
                data,
                selected_ticker,
                start,
                end,
                interval,
                False,
                "",
                "monthly",
                False,
                5.0,
                10.0,
                False,
                None,
                2,
                0.001,
            )
        elif workflow == "Simulator":
            show_simulator_mode(data, selected_ticker, start, end, interval)
        elif workflow == "Portfolio":
            show_portfolio_workflow(data, loaded_tickers, interval)
        elif workflow == "Quant Lab":
            show_quant_lab_workflow(data, selected_ticker, start, end, interval)
        elif workflow == "Risk":
            show_risk_workflow(data, selected_ticker, interval)
        elif workflow == "Settings":
            show_settings_workflow()

        # Display additional charts if enabled
        if show_price and workflow in {"Overview", "Backtest", "Quant Lab"}:
            st.subheader("Price Action & Technical Indicators")
            backtest_signals = None
            chart_backtest_result = None
            if (
                'backtest_result' in st.session_state
                and st.session_state.backtest_result
                and st.session_state.get("backtest_ticker") == selected_ticker
            ):
                chart_backtest_result = st.session_state.backtest_result
                backtest_signals = {
                    'entries': chart_backtest_result['entries'],
                    'exits': chart_backtest_result['exits']
                }
            display_advanced_chart(data, selected_ticker, chart_backtest_result, backtest_signals, chart_indicators)
        elif show_price and is_simulator_mode:
            st.subheader("Simulator Chart")
            display_simulator_chart(data, selected_ticker)

        if show_drawdown and workflow in {"Overview", "Backtest", "Quant Lab"}:
            st.subheader("Drawdown Analysis")
            close_data = get_ticker_frame(data, selected_ticker)["Close"]
            dd = close_data / close_data.cummax() - 1
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dd.index, y=dd.values * 100, fill='tozeroy', name='Drawdown'))
            fig.update_layout(
                title="Portfolio Drawdown",
                yaxis_title="Drawdown (%)",
                template=get_plotly_template(st.session_state.get('theme', 'dark')),
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)

        if show_corr and workflow in {"Overview", "Backtest", "Quant Lab", "Portfolio"}:
            st.subheader("Correlation Matrix")
            close_for_corr = get_close_prices(data)
            returns = compute_returns(close_for_corr)
            corr_matrix = correlation_matrix(returns.to_frame() if isinstance(returns, pd.Series) else returns)

            if corr_matrix is not None and not corr_matrix.empty:
                fig = go.Figure(data=go.Heatmap(
                    z=corr_matrix.values,
                    x=corr_matrix.columns,
                    y=corr_matrix.index,
                    colorscale='RdBu',
                    zmid=0
                ))
                fig.update_layout(
                    title="Asset Correlation Matrix",
                    height=500,
                    template=get_plotly_template(st.session_state.get('theme', 'dark'))
                )
                st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Dashboard error: {str(e)}")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())


def show_sidebar():
    """Display sidebar with proper error handling."""
    try:
        # Stock search section
        st.subheader("Stock Search")

        search_query = st.text_input(
            "Search stocks",
            placeholder="e.g., Apple, AAPL, TSLA",
            help="Search by company name or ticker symbol"
        )

        if search_query:
            with st.spinner("Searching..."):
                search_results = search_stocks(search_query, limit=5)

            if search_results:
                st.write("**Search Results:**")
                for stock in search_results:
                    if st.button(
                        f"Add {stock['symbol']} - {stock['name'][:24]}",
                        key=f"search_{stock['symbol']}",
                        help=f"Sector: {stock['sector']}"
                    ):
                        st.session_state.ticker_input = merge_ticker_input(
                            st.session_state.ticker_input,
                            stock['symbol'],
                        )
                        st.rerun()
            else:
                st.info("No stocks found. Try a different search term.")

        # Popular stocks
        st.markdown("**Popular Stocks:**")
        category = st.selectbox(
            "Category",
            get_stock_categories(),
            index=0,
            key="popular_category"
        )

        popular_stocks = get_popular_stocks(category)
        selected_popular_stocks = st.multiselect(
            "Category Symbols",
            popular_stocks,
            default=popular_stocks[: min(5, len(popular_stocks))],
            help="Choose symbols from the selected category before adding or replacing the ticker list.",
            key=f"category_symbols_{category}",
        )
        category_action_cols = st.columns(3)
        with category_action_cols[0]:
            if st.button("Use Category", key=f"use_category_{category}", use_container_width=True):
                st.session_state.ticker_input = merge_ticker_input("", selected_popular_stocks or popular_stocks[:12], replace=True)
                st.rerun()
        with category_action_cols[1]:
            if st.button("Add Category", key=f"add_category_{category}", use_container_width=True):
                st.session_state.ticker_input = merge_ticker_input(st.session_state.ticker_input, selected_popular_stocks or popular_stocks[:12])
                st.rerun()
        with category_action_cols[2]:
            if st.button("Clear", key="clear_tickers", use_container_width=True):
                st.session_state.ticker_input = ""
                st.rerun()

        with st.expander("Single-symbol quick add", expanded=False):
            cols = st.columns(3)
            for i, symbol in enumerate(popular_stocks[:18]):
                with cols[i % 3]:
                    if st.button(symbol, key=f"sidebar_popular_{i}_{symbol}"):
                        st.session_state.ticker_input = merge_ticker_input(st.session_state.ticker_input, symbol)
                        st.rerun()

        st.sidebar.divider()

        # Data section
        st.subheader("Data Selection")

        # Use session state for ticker input to persist selections
        tickers_input = st.text_input(
            "Ticker Symbols",
            st.session_state.ticker_input,
            help="Comma-separated list (e.g., AAPL,MSFT,NVDA)"
        )

        # Update session state when user types
        st.session_state.ticker_input = tickers_input

        preset = st.selectbox(
            "Ticker Preset",
            get_stock_presets(),
            index=0,
            help="Load a curated list into the ticker box"
        )
        preset_symbols = get_stock_preset_symbols(preset)
        preset_col1, preset_col2 = st.columns(2)
        with preset_col1:
            if st.button("Use Preset", use_container_width=True):
                st.session_state.ticker_input = merge_ticker_input("", preset_symbols, replace=True)
                st.rerun()
        with preset_col2:
            if st.button("Add Preset", use_container_width=True):
                st.session_state.ticker_input = merge_ticker_input(st.session_state.ticker_input, preset_symbols)
                st.rerun()

        interval = st.selectbox(
            "Interval",
            INTERVALS,
            index=4,
            help="Candle frequency for analysis"
        )

        saved_source = st.session_state.get("data_source", DEFAULT_DATA_SOURCE)
        if saved_source not in DATA_SOURCE_OPTIONS:
            saved_source = DEFAULT_DATA_SOURCE
        data_source = st.selectbox(
            "Data Source",
            DATA_SOURCE_OPTIONS,
            index=DATA_SOURCE_OPTIONS.index(saved_source),
            help="Auto tries Yahoo first for recent/intraday data, then Stooq for daily data, then demo data if real data is unavailable.",
        )
        st.session_state.data_source = data_source
        if data_source == DATA_SOURCE_STOOQ and interval != "1d":
            st.caption("Stooq is available for daily candles here. Choose 1d for real Stooq data.")

        col1, col2 = st.columns(2)
        with col1:
            start = st.date_input("Start Date", value=DEFAULT_START, key="data_start")
        with col2:
            end = st.date_input("End Date", value=DEFAULT_END, key="data_end")

        # Validate dates
        if start >= end:
            st.error("Start date must be before end date")
            return

        tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

        if not tickers:
            st.error("Please enter at least one ticker symbol")
            return

        st.sidebar.divider()

        # Display options
        st.subheader("Display Options")

        col1, col2, col3 = st.columns(3)
        with col1:
            show_price = st.toggle("Chart", value=True)
        with col2:
            show_drawdown = st.toggle("Drawdown", value=True)
        with col3:
            show_corr = st.toggle("Correlation", value=True)
        chart_indicators = display_chart_indicator_controls() if show_price else []

        # Workflow-specific settings now live in the relevant top-level workflow.
        enable_portfolio = False
        portfolio_weight_input = ""
        rebalance_period = "monthly"
        enable_risk = False
        stop_loss_pct = 5.0
        take_profit_pct = 10.0
        enable_optimizer = False
        optimizer_strategy = None
        optimizer_strat_hold = 2
        optimizer_strat_fee = 0.001
        is_simulator_mode = st.session_state.get('mode') == 'simulator'

        st.sidebar.divider()

        # Persistence options
        st.markdown("### Workspace")
        if st.button("Save Workspace"):
            try:
                workspace_data = {
                    'tickers': tickers_input,
                    'start_date': str(start),
                    'end_date': str(end),
                    'interval': interval,
                    'data_source': data_source,
                    'mode': st.session_state.mode,
                    'show_price': show_price,
                    'show_drawdown': show_drawdown,
                    'show_corr': show_corr,
                    'enable_portfolio': enable_portfolio,
                    'portfolio_weights': portfolio_weight_input,
                    'rebalance_period': rebalance_period,
                    'enable_risk': enable_risk,
                    'stop_loss': stop_loss_pct,
                    'take_profit': take_profit_pct,
                    'enable_optimizer': enable_optimizer,
                    'optimizer_strategy': optimizer_strategy,
                    'optimizer_hold': optimizer_strat_hold if enable_optimizer else 2,
                    'optimizer_fee': optimizer_strat_fee if enable_optimizer else 0.001,
                    'timestamp': str(pd.Timestamp.now())
                }
                save_workspace("workspace.json", workspace_data)
                st.success("Workspace saved!")
            except Exception as e:
                st.error(f"Failed to save workspace: {e}")

        if st.button("Load Workspace"):
            try:
                workspace_data = load_workspace("workspace.json")
                if workspace_data:
                    # Restore settings
                    st.session_state.ticker_input = workspace_data.get('tickers', DEFAULT_TICKERS)
                    st.session_state.data_source = workspace_data.get('data_source', DEFAULT_DATA_SOURCE)
                    st.session_state.mode = workspace_data.get('mode', 'backtesting')
                    st.success("Workspace loaded!")
                    st.rerun()
                else:
                    st.warning("No saved workspace found")
            except Exception as e:
                st.error(f"Failed to load workspace: {e}")

        # Return all the sidebar variables
        return {
            'tickers': tickers,
            'start': start,
            'end': end,
            'interval': interval,
            'data_source': data_source,
            'show_price': show_price,
            'chart_indicators': chart_indicators,
            'show_drawdown': show_drawdown,
            'show_corr': show_corr,
            'is_simulator_mode': is_simulator_mode,
            'enable_portfolio': enable_portfolio,
            'portfolio_weight_input': portfolio_weight_input,
            'rebalance_period': rebalance_period,
            'enable_risk': enable_risk,
            'stop_loss_pct': stop_loss_pct,
            'take_profit_pct': take_profit_pct,
            'enable_optimizer': enable_optimizer,
            'optimizer_strategy': optimizer_strategy,
            'optimizer_strat_hold': optimizer_strat_hold if enable_optimizer else 2,
            'optimizer_strat_fee': optimizer_strat_fee if enable_optimizer else 0.001
        }

    except Exception as e:
        st.error(f"Sidebar error: {e}")
        return None


def show_main_content_v2():
    """Display main content area - alternative implementation."""
    try:
        # Get sidebar data
        sidebar_data = show_sidebar()
        if sidebar_data is None:
            return

        # Unpack sidebar data
        tickers = sidebar_data['tickers']
        start = sidebar_data['start']
        end = sidebar_data['end']
        interval = sidebar_data['interval']
        show_price = sidebar_data['show_price']
        show_drawdown = sidebar_data['show_drawdown']
        show_corr = sidebar_data['show_corr']
        is_simulator_mode = sidebar_data['is_simulator_mode']
        enable_portfolio = sidebar_data['enable_portfolio']
        portfolio_weight_input = sidebar_data['portfolio_weight_input']
        rebalance_period = sidebar_data['rebalance_period']
        enable_risk = sidebar_data['enable_risk']
        stop_loss_pct = sidebar_data['stop_loss_pct']
        take_profit_pct = sidebar_data['take_profit_pct']
        enable_optimizer = sidebar_data['enable_optimizer']
        optimizer_strategy = sidebar_data['optimizer_strategy']
        optimizer_strat_hold = sidebar_data['optimizer_strat_hold']
        optimizer_strat_fee = sidebar_data['optimizer_strat_fee']

        # ========================================================================
        # MAIN CONTENT
        # ========================================================================

        st.title("Quant Market Analytics")
        st.markdown("*Professional quantitative trading analysis and backtesting platform*")

        # Download data
        with st.spinner("Downloading market data..."):
            data = load_data_with_status(tickers, start, end, interval)

        if data is None:
            st.error("Failed to download market data. Please check your ticker symbols and date range.")
            return

        if data.empty:
            st.error("No data available for the selected tickers and date range.")
            return

        # Process data
        returns = compute_returns(data.xs(tickers[0], level=1, axis=1)["Close"]) if len(data.columns.names) > 1 else compute_returns(data["Close"])
        dd = data.xs(tickers[0], level=1, axis=1)["Close"] / data.xs(tickers[0], level=1, axis=1)["Close"].cummax() - 1 if len(data.columns.names) > 1 else data["Close"] / data["Close"].cummax() - 1

        # Ticker selector
        selected_ticker = st.selectbox("Select Ticker for Analysis", tickers, key="selected_ticker")

        # ========================================================================
        # ANALYSIS LOGIC (Backtesting or Simulator)
        # ========================================================================

        backtest_result = None
        backtest_metrics = None
        simulator_metrics = None
        simulator_trades_df = None

        if not is_simulator_mode:
            # BACKTESTING MODE
            show_backtesting_mode(
                data, selected_ticker, start, end, interval,
                enable_portfolio, portfolio_weight_input, rebalance_period,
                enable_risk, stop_loss_pct, take_profit_pct,
                enable_optimizer, optimizer_strategy, optimizer_strat_hold, optimizer_strat_fee
            )
        else:
            # SIMULATOR MODE
            show_simulator_mode(data, selected_ticker, start, end, interval)

        # ========================================================================
        # CHARTS (Both modes)
        # ========================================================================

        # Advanced chart
        if show_price:
            if not is_simulator_mode:
                st.subheader("Price Action & Technical Indicators")

                backtest_signals = None
                if 'backtest_result' in st.session_state and st.session_state.backtest_result:
                    backtest_signals = {
                        'entries': st.session_state.backtest_result['entries'],
                        'exits': st.session_state.backtest_result['exits']
                    }

                display_advanced_chart(data, selected_ticker, st.session_state.get('backtest_result'), backtest_signals)
            else:
                # Simulator chart
                st.subheader("Simulator Chart")
                display_simulator_chart(data, selected_ticker)

        # Drawdown chart
        if show_drawdown and not is_simulator_mode:
            st.subheader("Drawdown Analysis")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dd.index, y=dd.values * 100, fill='tozeroy', name='Drawdown'))
            fig.update_layout(
                title="Portfolio Drawdown",
                yaxis_title="Drawdown (%)",
                template=get_plotly_template(st.session_state.get('theme', 'dark')),
                height=400
            )

            st.plotly_chart(fig, use_container_width=True)
            st.divider()

        # Correlation heatmap
        if show_corr and not is_simulator_mode:
            st.subheader("Correlation Matrix")
            corr_matrix = correlation_matrix(returns.to_frame() if isinstance(returns, pd.Series) else returns)

            if corr_matrix is not None and not corr_matrix.empty:
                fig = go.Figure(data=go.Heatmap(
                    z=corr_matrix.values,
                    x=corr_matrix.columns,
                    y=corr_matrix.index,
                    colorscale='RdBu',
                    zmid=0
                ))
                fig.update_layout(
                    title="Asset Correlation Matrix",
                    height=500,
                    template=get_plotly_template(st.session_state.get('theme', 'dark'))
                )

                st.plotly_chart(fig, use_container_width=True)

        # Footer
        st.divider()
        st.markdown(
            """
            <div style='text-align: center; color: gray; font-size: 12px;'>
            Quant Market Analytics v1.1.2 | Data from selected source | Not financial advice
            </div>
            """,
            unsafe_allow_html=True
        )

    except Exception as e:
        st.error(f"Main content error: {e}")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())
        
        # Use session state for ticker input to persist selections
        if 'ticker_input' not in st.session_state:
            st.session_state.ticker_input = DEFAULT_TICKERS
            
        tickers_input = st.text_input(
            "Ticker Symbols",
            st.session_state.ticker_input,
            help="Comma-separated list (e.g., AAPL,MSFT,NVDA)"
        )
        
        # Update session state when user types
        st.session_state.ticker_input = tickers_input
        
        interval = st.selectbox(
            "Interval",
            INTERVALS,
            index=4,
            help="Candle frequency for analysis"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            start = st.date_input("Start Date", value=DEFAULT_START, key="data_start")
        with col2:
            end = st.date_input("End Date", value=DEFAULT_END, key="data_end")
        
        tickers = [t.strip().upper() for t in tickers_input.split(",")]
        
        st.sidebar.divider()
        
        # Display options
        st.subheader("Display Options")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            show_price = st.toggle("Chart", value=True)
        with col2:
            show_drawdown = st.toggle("Drawdown", value=True)
        with col3:
            show_corr = st.toggle("Correlation", value=True)
        
        st.sidebar.divider()
        
        # Mode selection
        st.subheader("Mode Selection")
        
        # Get current mode from session state
        current_mode = st.session_state.get('mode', 'backtesting')
        
        # Map session state mode to radio options
        mode_options = ["Backtesting", "Simulator"]
        mode_index = 1 if current_mode == 'simulator' else 0
        
        mode = st.radio(
            "Select Mode",
            mode_options,
            index=mode_index,
            help="Backtesting: Test strategies automatically | Simulator: Trade manually",
            key="mode_radio"
        )
        
        # Update session state mode based on selection
        selected_mode = "simulator" if "Simulator" in mode else "backtesting"
        if st.session_state.get('mode') != selected_mode:
            st.session_state.mode = selected_mode
        is_simulator_mode = "Simulator" in mode

        # Phase 2 Enhancements - only show in backtesting mode
        if not is_simulator_mode:
            st.subheader("Advanced Options")
            enable_portfolio = st.checkbox("Enable Portfolio Backtesting", value=False)
            if enable_portfolio:
                portfolio_weight_input = st.text_input(
                    "Portfolio Weights (symbol:weight,...)",
                    "AAPL:0.2,MSFT:0.2,NVDA:0.2,TSLA:0.2,SPY:0.2"
                )
                rebalance_period = st.selectbox("Rebalance Period", ["monthly", "weekly", "daily"], index=0)
            else:
                portfolio_weight_input = ""
                rebalance_period = "monthly"

            enable_risk = st.checkbox("Enable Risk Management Metrics", value=True)
            with st.expander("Risk Management Settings", expanded=False):
                stop_loss_pct = st.slider("Stop Loss (%)", min_value=0.0, max_value=20.0, value=5.0, step=0.5)
                take_profit_pct = st.slider("Take Profit (%)", min_value=0.0, max_value=50.0, value=10.0, step=0.5)

            enable_optimizer = st.checkbox("Enable Strategy Optimizer", value=False)
            if enable_optimizer:
                optimizer_strategy = st.selectbox(
                    "Optimizer Strategy",
                    [s for s in STRATEGY_OPTIONS if s != "None"]
                )
                optimizer_strat_hold = st.number_input("Optimizer Holding Period", min_value=0, max_value=50, value=2)
                optimizer_strat_fee = st.slider("Optimizer Fee (%)", min_value=0.0, max_value=1.0, value=0.1, step=0.01) / 100
            else:
                optimizer_strategy = None
        else:
            # Set default values for simulator mode
            enable_portfolio = False
            portfolio_weight_input = ""
            rebalance_period = "monthly"
            enable_risk = False
            stop_loss_pct = 5.0
            take_profit_pct = 10.0
            enable_optimizer = False
            optimizer_strategy = None

        st.sidebar.divider()
        
        # Persistence options
        st.markdown("### Workspace")
        if st.button("Save Workspace"):
            state = {
                'ticker_input': st.session_state.ticker_input,
                'mode': mode,
                'strategy_name': st.session_state.get('strategy_name', ''),
                'backtest_start': st.session_state.get('backtest_start', str(DEFAULT_START.date())),
                'backtest_end': st.session_state.get('backtest_end', str(DEFAULT_END.date())),
                'interval': st.session_state.get('interval', DEFAULT_INTERVAL)
            }
            save_workspace('workspace_state.json', state)
            st.success('Workspace saved.')
        if st.button("Load Workspace"):
            state = load_workspace('workspace_state.json')
            if state:
                st.session_state.ticker_input = state.get('ticker_input', st.session_state.ticker_input)
                st.session_state.mode = state.get('mode', st.session_state.mode)
                st.success('Workspace loaded. Please rerun app.')

        # Initialize variables for backtesting
        strategy_name = "None"
        backtest_start = None
        backtest_end = None
        config = None
        
        if not is_simulator_mode:
            st.subheader("Backtesting")
            
            strategy_name = st.selectbox(
                "Select Strategy",
                STRATEGY_OPTIONS,
                help="Choose trading strategy to backtest"
            )
        
        if strategy_name != "None":
            # Quick presets
            preset = st.selectbox(
                "Quick Presets",
                ["Custom"] + list(TRADING_PRESETS.keys()),
                help="Pre-configured trading styles"
            )
            
            # Initialize config from preset or custom
            if preset != "Custom" and preset in TRADING_PRESETS:
                preset_config = TRADING_PRESETS[preset]
                default_hold = preset_config['holding_period']
                default_pos = preset_config['position_type']
                default_fee = preset_config['transaction_fee']
            else:
                default_hold, default_pos, default_fee = 0, "Fixed", 0.0
            
            # Backtesting date range
            st.markdown("**Backtest Period**")
            col1, col2 = st.columns(2)
            with col1:
                backtest_start = st.date_input(
                    "From",
                    value=DEFAULT_START,
                    key="backtest_start",
                    help="Start date for backtest"
                )
            with col2:
                backtest_end = st.date_input(
                    "To",
                    value=DEFAULT_END,
                    key="backtest_end"
                )
            
            # Position & fees
            st.markdown("**Position Configuration**")
            col1, col2 = st.columns(2)
            
            with col1:
                position_type = st.radio(
                    "Position Sizing",
                    ["Fixed", "Dynamic"],
                    index=0 if default_pos == "Fixed" else 1,
                    horizontal=True,
                    help="Fixed=all-in | Dynamic=0-1"
                )
            
            with col2:
                holding_period = st.number_input(
                    "Hold Days",
                    value=default_hold,
                    min_value=0,
                    max_value=252,
                    help="0=day, 1-5=swing, 20+=position"
                )
            
            # Advanced options (only in expert mode)
            if st.session_state.ui_mode == 'expert':
                with st.expander("Advanced Options", expanded=False):
                    transaction_fee = st.slider(
                        "Transaction Fee (%)",
                        min_value=0.0,
                        max_value=1.0,
                        value=default_fee * 100,
                        step=0.01,
                        help="Per-trade cost"
                    ) / 100
                    
                    sharpe_mode = st.selectbox(
                        "Sharpe Annualization",
                        list(SHARPE_MODES.keys()),
                    )
                    sharpe_interval = SHARPE_MODES[sharpe_mode]
            else:
                # Simple mode defaults
                transaction_fee = default_fee
                sharpe_interval = "1d"
            
            config = {
                'position_type': position_type,
                'holding_period': int(holding_period),
                'fee_pct': transaction_fee,
                'interval': interval,
            }
        
        # Simulator section
        else:
            st.subheader("Trading Simulator")
            
            # Initialize simulator
            create_simulator_session()
            simulator = get_simulator_engine()
            
            # Simulator controls
            simulator_active = st.toggle(
                "Activate Simulator",
                value=st.session_state.simulator.get('active', False),
                help="Enable manual trading simulation"
            )
            
            if simulator_active:
                st.session_state.simulator['active'] = True
                
                # Simulator settings in a more organized layout
                st.markdown("### Simulation Settings")

                # Date range selection
                col1, col2 = st.columns(2)
                with col1:
                    sim_start = st.date_input(
                        "Start Date",
                        value=DEFAULT_START,
                        key="sim_start",
                        help="When your trading simulation begins"
                    )
                with col2:
                    sim_end = st.date_input(
                        "End Date",
                        value=DEFAULT_END,
                        key="sim_end",
                        help="When your trading simulation ends"
                    )

                # Capital and fees
                col1, col2 = st.columns(2)
                with col1:
                    initial_equity = st.number_input(
                        "Starting Capital ($)",
                        value=10000,
                        min_value=1000,
                        max_value=1000000,
                        step=1000,
                        help="How much money you start with"
                    )
                with col2:
                    sim_fee = st.slider(
                        "Transaction Fee (%)",
                        min_value=0.0,
                        max_value=1.0,
                        value=0.1,
                        step=0.01,
                        help="Cost per trade (realistic trading costs)"
                    ) / 100
                
                # Initialize simulator with settings
                if not hasattr(simulator, 'sim_data') or simulator.sim_data is None:
                    try:
                        # Get data for the selected ticker
                        selected_ticker = tickers[0] if tickers else "AAPL"
                        sim_data = load_data_with_status([selected_ticker], sim_start, sim_end, interval)

                        if len(sim_data) > 0:
                            simulator.reset()
                            simulator.transaction_fee = sim_fee
                            simulator.initial_equity = initial_equity
                            simulator.set_timeframe(sim_data, sim_start, sim_end)
                            st.success(f"**Simulation Ready!** Trading **{selected_ticker}** from {sim_start.strftime('%B %d, %Y')} to {sim_end.strftime('%B %d, %Y')} with ${initial_equity:,.0f} starting capital")
                            st.info("Use the Trading Panel below to buy and sell shares. Navigate through time to practice your trading strategy!")
                        else:
                            st.error("No market data available for the selected period. Try different dates or ticker.")
                            simulator_active = False

                    except Exception as e:
                        st.error(f"Failed to initialize simulator: {e}")
                        st.info("Make sure you have selected a valid ticker symbol in the sidebar.")
                        simulator_active = False
                
                # Trading controls
                if simulator_active and hasattr(simulator, 'sim_data'):
                    st.markdown("---")

                    # Current state display - prominent metrics
                    st.markdown("### Current Position")
                    state = simulator.get_current_state()

                    # Main metrics in a nice grid
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Current Date", state['date'].strftime('%Y-%m-%d'))
                    with col2:
                        st.metric("Available Cash", f"${state['cash']:.2f}")
                    with col3:
                        st.metric("Shares Held", state['positions'])
                    with col4:
                        st.metric("Total Equity", f"${state['total_equity']:.2f}")

                    # Current price display
                    if hasattr(simulator, 'current_price'):
                        st.metric("Current Price", f"${simulator.current_price:.2f}")

                    st.markdown("---")

                    # Trading Panel
                    st.markdown("### Trading Panel")

                    # Buy/Sell section with better layout
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("#### Buy")
                        buy_qty = st.number_input(
                            "Quantity to Buy",
                            min_value=1,
                            max_value=10000,
                            value=100,
                            step=10,
                            key="buy_qty"
                        )
                        buy_cost = buy_qty * simulator.current_price if hasattr(simulator, 'current_price') else 0
                        st.info(f"Cost: ${buy_cost:.2f}")

                        if st.button("Execute Buy", type="primary", use_container_width=True):
                            if simulator.execute_buy(buy_qty):
                                st.success(f"Bought {buy_qty} shares at ${simulator.current_price:.2f}")
                                st.rerun()
                            else:
                                can_buy, reason = simulator.can_buy(buy_qty)
                                st.error(reason)

                    with col2:
                        st.markdown("#### Sell")
                        sell_qty = st.number_input(
                            "Quantity to Sell",
                            min_value=1,
                            max_value=10000,
                            value=100,
                            step=10,
                            key="sell_qty"
                        )
                        sell_value = sell_qty * simulator.current_price if hasattr(simulator, 'current_price') else 0
                        st.info(f"Value: ${sell_value:.2f}")

                        if st.button("Execute Sell", type="primary", use_container_width=True):
                            if simulator.execute_sell(sell_qty):
                                st.success(f"Sold {sell_qty} shares at ${simulator.current_price:.2f}")
                                st.rerun()
                            else:
                                can_sell, reason = simulator.can_sell(sell_qty)
                                st.error(reason)

                    st.markdown("---")

                    # Time Navigation Panel
                    st.markdown("### Time Navigation")

                    time_col1, time_col2, time_col3, time_col4, time_col5 = st.columns(5)

                    with time_col1:
                        if st.button("Start", help="Go to beginning", use_container_width=True):
                            simulator.go_to_date(simulator.sim_data.index[0])
                            st.rerun()

                    with time_col2:
                        if st.button("Previous Day", help="Go back 1 day", use_container_width=True):
                            if simulator.advance_time(-1):
                                st.rerun()
                            else:
                                st.info("Already at start")

                    with time_col3:
                        if st.button("Next Day", help="Advance 1 day", use_container_width=True):
                            if simulator.advance_time(1):
                                st.rerun()
                            else:
                                st.info("End of simulation reached")

                    with time_col4:
                        if st.button("Advance 5 Days", help="Advance 5 days", use_container_width=True):
                            if simulator.advance_time(5):
                                st.rerun()
                            else:
                                st.info("End of simulation reached")

                    with time_col5:
                        if st.button("Reset", type="secondary", help="Reset simulation", use_container_width=True):
                            reset_simulator()
                            st.rerun()
            else:
                st.session_state.simulator['active'] = False
                st.info("**Ready to start trading?** Toggle 'Activate Simulator' above to begin your trading simulation!")
                st.markdown("""
                **What you can do:**
                - Practice buying and selling stocks
                - Learn trading without risking real money
                - Test different strategies over historical data
                - Track your performance in real-time
                """)
    
    # ========================================================================
    # MAIN CONTENT
    # ========================================================================
    
    st.title("Quant Market Analytics")
    st.markdown("*Professional quantitative trading analysis and backtesting platform*")
    
    # Download data
    try:
        with st.spinner("Downloading market data..."):
            data = load_data_with_status(tickers, start, end, interval)
    except Exception as e:
        st.error(f"Failed to download data: {e}")
        st.info("Check that ticker symbols are valid (e.g., AAPL not Apple)")
        st.stop()
    
    if data is None or data.empty:
        st.error("No data available for the selected period and tickers")
        st.stop()
    
    close = data["Close"]
    returns = compute_returns(close)
    dd = close / close.cummax() - 1
    
    # Ticker selector
    selected_ticker = st.selectbox("Select Ticker for Analysis", tickers, key="selected_ticker")
    
    # ========================================================================
    # ANALYSIS LOGIC (Backtesting or Simulator)
    # ========================================================================
    
    backtest_result = None
    backtest_metrics = None
    simulator_metrics = None
    simulator_trades_df = None
    
    if not is_simulator_mode:
        # BACKTESTING MODE
        if strategy_name and strategy_name != "None" and config is not None:
            try:
                with st.spinner("Running backtest..."):
                    # Extract data
                    ticker_data = extract_ticker_data(data, selected_ticker, backtest_start, backtest_end)
                    
                    if len(ticker_data) == 0:
                        st.warning(f"No data for {selected_ticker} in range {backtest_start} to {backtest_end}")
                    else:
                        # Prepare indicators
                        indicators = compute_all_indicators(ticker_data["Close"])
                        
                        # Check cache
                        cache_key = create_backtest_key(
                            strategy_name, backtest_start, backtest_end, 
                            selected_ticker, config['holding_period'], config['fee_pct']
                        )
                        
                        if cache_key in st.session_state.backtest_cache:
                            backtest_result = st.session_state.backtest_cache[cache_key]
                        else:
                            backtest_result = run_single_backtest(strategy_name, ticker_data["Close"], indicators, config)
                            st.session_state.backtest_cache[cache_key] = backtest_result
                            manage_backtest_cache()  # Manage cache size
                        
                        # Extract metrics
                        backtest_metrics = {k: backtest_result[k] for k in 
                                          ['total_return', 'sharpe_ratio', 'max_drawdown', 'win_rate']}
            
            except ValueError as e:
                st.error(f"Configuration error: {e}")
            except Exception as e:
                st.error(f"Backtest failed: {e}")
                with st.expander("Debug Info"):
                    st.write(f"Error: {str(e)}")
    
    else:
        # SIMULATOR MODE
        if st.session_state.simulator.get('active', False) and hasattr(simulator, 'sim_data'):
            simulator_metrics = simulator.get_metrics()
            simulator_trades_df = simulator.get_trades_df()
    
    # ========================================================================
    # DISPLAY RESULTS
    # ========================================================================

    # Phase 2: Portfolio and risk analytics
    if enable_risk and not is_simulator_mode:
        st.subheader("Risk Management Summary")
        # Extract selected ticker's returns for risk metrics
        if isinstance(returns, pd.DataFrame):
            ticker_returns = returns[selected_ticker]
        else:
            ticker_returns = returns
        var_val = value_at_risk(ticker_returns, confidence=0.95)
        cvar_val = conditional_value_at_risk(ticker_returns, confidence=0.95)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("VaR 95%", f"{var_val:.2%}")
        with col2:
            st.metric("CVaR 95%", f"{cvar_val:.2%}")
        with col3:
            st.metric("Total Volatility", f"{ticker_returns.std():.2%}")

    if enable_portfolio and not is_simulator_mode:
        st.subheader("Portfolio Backtest")
        try:
            weights = {}
            for item in portfolio_weight_input.split(','):
                key, val = item.strip().split(':')
                weights[key.strip().upper()] = float(val.strip())
            # Only selected tickers
            common_tickers = [t for t in tickers if t in weights]
            if len(common_tickers) < 2:
                st.warning('Need at least 2 portfolio tickers from weights input.')
            else:
                use_prices = data['Close'][common_tickers]
                port_res = portfolio_backtest(use_prices, weights, rebalance=rebalance_period)

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Portfolio Return", f"{port_res['returns'].cumsum().iloc[-1]*100:.2f}%")
                with col2:
                    st.metric("Portfolio Sharpe", f"{port_res['sharpe_ratio']:.2f}")
                with col3:
                    st.metric("Portfolio Max Drawdown", f"{port_res['max_drawdown']:.2f}%")
                with col4:
                    st.metric("Portfolio Win Rate", f"{port_res['win_rate']:.1f}%")

                port_fig = go.Figure()
                port_fig.add_trace(go.Scatter(x=port_res['nav'].index, y=port_res['nav'].values, name='Portfolio NAV'))
                st.plotly_chart(port_fig, use_container_width=True)

        except Exception as e:
            st.error(f"Portfolio backtest failed: {e}")

    if not is_simulator_mode:
        # Backtesting results
        if backtest_metrics is not None:
            # apply stop/take profit to trade log if any
            if backtest_result is not None and 'trades' in backtest_result:
                backtest_result['trades'] = apply_stop_loss_take_profit(
                    backtest_result['trades'],
                    stop_loss=stop_loss_pct/100,
                    take_profit=take_profit_pct/100
                )

            st.divider()
            col1, col2 = st.columns([3, 1])
            
            with col1:
                display_metrics_panel(backtest_metrics)
            
            with col2:
                st.metric("Period", f"{(backtest_end - backtest_start).days}d")
            
            st.divider()
            
            # Trade log
            display_trade_log(backtest_result, strategy_name)
            st.divider()
    
    else:
        # Simulator results
        if simulator_metrics is not None:
            st.divider()
            st.subheader("Simulator Performance")
            
            # Current state
            state = simulator.get_current_state()
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Cash", f"${state['cash']:.2f}")
            with col2:
                st.metric("Positions", state['positions'])
            with col3:
                st.metric("Total Equity", f"${state['total_equity']:.2f}")
            with col4:
                st.metric("Unrealized P&L", f"${state['unrealized_pnl']:.2f}")
            
            # Performance metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Return", f"{simulator_metrics['total_return']:.2f}%")
            with col2:
                st.metric("Sharpe Ratio", f"{simulator_metrics['sharpe_ratio']:.2f}")
            with col3:
                st.metric("Max Drawdown", f"{simulator_metrics['max_drawdown']:.2f}%")
            with col4:
                st.metric("Win Rate", f"{simulator_metrics['win_rate']:.1f}%")
            
            # Trade log
            if not simulator_trades_df.empty:
                st.divider()
                st.subheader("Trade History")
                
                # Trade statistics
                total_trades = len(simulator_trades_df)
                winning_trades = len(simulator_trades_df[simulator_trades_df['realized_pnl'] > 0])
                losing_trades = total_trades - winning_trades
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Trades", total_trades)
                with col2:
                    st.metric("Wins", winning_trades)
                with col3:
                    st.metric("Losses", losing_trades)
                
                # Trade table
                st.dataframe(
                    simulator_trades_df[[
                        'action', 'quantity', 'price', 'proceeds', 
                        'cost_basis', 'realized_pnl', 'fee'
                    ]].round(2),
                    use_container_width=True
                )
                
                # CSV export
                csv = simulator_trades_df.to_csv(index=True)
                st.download_button(
                    "Export Trades (CSV)",
                    csv,
                    "simulator_trades.csv",
                    "text/csv"
                )
            
            st.divider()

            # Phase 2: Strategy optimizer results
            if enable_optimizer and optimizer_strategy and strategy_name != 'None':
                st.subheader('Strategy Optimizer Results')
                try:
                    param_grid = [
                        {'holding_period': h, 'position_type': 'fixed', 'fee_pct': optimizer_strat_fee}
                        for h in [0, 1, 2, 5, 10]
                    ]
                    optimizer_res = grid_search_strategy(
                        ticker_data['Close'] if 'ticker_data' in locals() else close,
                        indicators if 'indicators' in locals() else compute_all_indicators(close),
                        optimizer_strategy,
                        param_grid,
                        interval=interval
                    )

                    st.write('**Best optimizer config:**')
                    st.json(optimizer_res['best'])
                    st.write('**All tested cases:**')
                    st.dataframe(optimizer_res['results'])

                except Exception as e:
                    st.error(f'Optimizer failed: {e}')

    # ========================================================================
    # CHARTS (Both modes)
    # ========================================================================
    
    # Advanced chart
    if show_price:
        if not is_simulator_mode:
            st.subheader("Price Action & Technical Indicators")
            
            backtest_signals = None
            if backtest_result is not None:
                backtest_signals = {
                    'entries': backtest_result['entries'],
                    'exits': backtest_result['exits']
                }
            
            display_advanced_chart(data, selected_ticker, backtest_result, backtest_signals)
        else:
            # Simulator chart
            st.subheader("Simulator Chart")
            
            if hasattr(simulator, 'sim_data') and simulator.sim_data is not None:
                # Create simulator-specific chart
                sim_data = simulator.sim_data.copy()
                
                # Add equity curve
                equity_curve = simulator.get_equity_curve()
                
                fig = sp.make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    row_heights=[0.7, 0.3],
                    vertical_spacing=0.05,
                    subplot_titles=("Price & Manual Trades", "Equity Curve")
                )
                
                # Price chart with manual trade markers
                fig.add_trace(
                    go.Candlestick(
                        x=sim_data.index,
                        open=sim_data["Open"],
                        high=sim_data["High"],
                        low=sim_data["Low"],
                        close=sim_data["Close"],
                        name="Price"
                    ),
                    row=1, col=1
                )
                
                # Add current position marker
                current_date = simulator.current_date
                current_price = simulator.current_price
                
                fig.add_trace(
                    go.Scatter(
                        x=[current_date],
                        y=[current_price],
                        mode="markers",
                        marker=dict(size=15, color="blue", symbol="diamond"),
                        name="Current Position"
                    ),
                    row=1, col=1
                )
                
                # Add buy/sell markers from trades
                if simulator_trades_df is not None and not simulator_trades_df.empty:
                    buy_trades = simulator_trades_df[simulator_trades_df['action'] == 'BUY']
                    sell_trades = simulator_trades_df[simulator_trades_df['action'] == 'SELL']
                    
                    if not buy_trades.empty:
                        fig.add_trace(
                            go.Scatter(
                                x=buy_trades.index,
                                y=buy_trades['price'],
                                mode="markers",
                                marker=dict(size=10, color="green", symbol="triangle-up"),
                                name="Buy Orders"
                            ),
                            row=1, col=1
                        )
                    
                    if not sell_trades.empty:
                        fig.add_trace(
                            go.Scatter(
                                x=sell_trades.index,
                                y=sell_trades['price'],
                                mode="markers",
                                marker=dict(size=10, color="red", symbol="triangle-down"),
                                name="Sell Orders"
                            ),
                            row=1, col=1
                        )
                
                # Equity curve
                fig.add_trace(
                    go.Scatter(
                        x=equity_curve.index,
                        y=equity_curve.values,
                        name="Equity",
                        line=dict(color="purple", width=2)
                    ),
                    row=2, col=1
                )
                
                # Add buy-and-hold comparison
                bh_equity = buy_hold_equity(sim_data["Close"], initial_equity=simulator.initial_equity)
                fig.add_trace(
                    go.Scatter(
                        x=bh_equity.index,
                        y=bh_equity.values,
                        name="Buy & Hold",
                        line=dict(color="gray", dash="dash")
                    ),
                    row=2, col=1
                )
                
                current_theme = st.session_state.get('theme', 'dark')
                template = get_plotly_template(current_theme)
                
                fig.update_layout(height=600, showlegend=True, template=template)
                fig.update_xaxes(title_text="Date", row=2, col=1)
                fig.update_yaxes(title_text="Price ($)", row=1, col=1)
                fig.update_yaxes(title_text="Equity ($)", row=2, col=1)
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Activate the simulator to see the trading chart")
        
        st.divider()
        st.divider()
    
    # Drawdown chart
    if show_drawdown and not is_simulator_mode:
        st.subheader("Drawdown Analysis")
        
        drawdown_fig = go.Figure()
        for ticker in tickers:
            drawdown_fig.add_trace(
                go.Scatter(x=dd.index, y=dd[ticker] * 100, name=ticker, mode='lines')
            )
        
        drawdown_fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Drawdown (%)",
            hovermode='x unified',
            template=get_plotly_template(st.session_state.get('theme', 'dark')),
            height=400
        )
        
        st.plotly_chart(drawdown_fig, use_container_width=True)
        st.divider()
    
    # Correlation heatmap
    if show_corr and not is_simulator_mode:
        st.subheader("Correlation Matrix")
        
        corr = correlation_matrix(returns)
        
        corr_fig = go.Figure(
            data=go.Heatmap(
                z=corr,
                x=corr.columns,
                y=corr.columns,
                colorscale="RdBu",
                zmid=0,
                zmin=-1,
                zmax=1
            )
        )
        
        corr_fig.update_layout(
            height=500,
            template=get_plotly_template(st.session_state.get('theme', 'dark'))
        )
        
        st.plotly_chart(corr_fig, use_container_width=True)
    
    # Footer
    st.divider()
    st.markdown(
        f"""
        <div style='text-align: center; color: gray; font-size: 12px;'>
        Quant Market Analytics v{__version__} | Data from selected source | Not financial advice
        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================================
# WELCOME DASHBOARD
# ============================================================================

def show_welcome_dashboard():
    """Display welcome screen with guided onboarding."""
    
    # Hero section
    st.markdown("""
    <div class='qma-panel' style='margin-bottom: 1rem;'>
        <span class='qma-status'>Ready</span>
        <h1 style='font-size: 2.1rem; margin: 0.75rem 0 0.25rem;'>Quant Market Analytics</h1>
        <p class='qma-muted' style='font-size: 1rem; margin: 0;'>
            Backtest strategies, compare portfolios, and learn market risk with historical data.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Quick start options
    st.markdown("### Quick Start")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        **Backtesting Mode**
        - Test trading strategies automatically
        - Analyze historical performance
        - Compare against buy-and-hold
        """)
        
        if st.button("Start Backtesting", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.session_state.mode = "backtesting"
            st.rerun()
    
    with col2:
        st.markdown("""
        **Trading Simulator**
        - Practice manual trading
        - Real-time P&L tracking
        - Risk-free learning environment
        """)
        
        if st.button("Start Simulator", type="primary", use_container_width=True):
            from modules.simulator import create_simulator_session
            create_simulator_session()
            st.session_state.show_welcome = False
            st.session_state.mode = "simulator"
            # Ensure simulator is properly initialized
            if 'simulator' in st.session_state:
                st.session_state.simulator['active'] = True
            st.rerun()
    
    with col3:
        st.markdown("""
        **Stock Discovery**
        - Search and analyze stocks
        - Technical indicators
        - Market correlation analysis
        """)
        
        if st.button("Explore Stocks", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.session_state.mode = "analysis"
            st.rerun()

    with col4:
        st.markdown("""
        **Tutorial**
        - Learn the app workflow
        - Understand indicators
        - Read risk metrics
        """)

        if st.button("Open Tutorial", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.session_state.mode = "tutorial"
            st.rerun()

        if st.button("Start Guided Tour", use_container_width=True):
            start_guided_tour()
            st.rerun()
    
    st.divider()
    
    # Features overview
    st.markdown("### Key Features")
    
    features_col1, features_col2 = st.columns(2)
    
    with features_col1:
        st.markdown("""
        **Advanced Strategies**
        - Moving Average Crossover
        - RSI Mean-Reversion & Threshold
        - Bollinger Bands Breakout
        
        **Technical Analysis**
        - Multiple timeframes (1m to 1d)
        - 50+ technical indicators
        - Interactive charts with Plotly
        
        **Professional Tools**
        - Sharpe ratio, max drawdown
        - Win rate analysis
        - Trade logging & export
        """)
    
    with features_col2:
        st.markdown("""
        **Trading Simulator**
        - Manual buy/sell orders
        - Real-time portfolio tracking
        - Performance metrics
        
        **Risk Management**
        - Position sizing options
        - Transaction cost modeling
        - Drawdown analysis
        
        **Market Analysis**
        - Multi-asset correlation
        - Sector analysis
        - Popular stocks discovery
        """)
    
    st.divider()
    
    # Settings
    st.markdown("### Preferences")
    display_beginner_glossary()
    
    settings_col1, settings_col2, settings_col3 = st.columns(3)
    
    with settings_col1:
        ui_mode = st.radio(
            "Interface Mode",
            ["Simple", "Expert"],
            index=0 if st.session_state.get("ui_mode", "simple") == "simple" else 1,
            help="Simple: Guided experience | Expert: Full controls"
        )
        st.session_state.ui_mode = ui_mode.lower()
    
    with settings_col2:
        theme = st.radio(
            "Theme",
            ["Dark", "Light"],
            index=0 if st.session_state.get("theme", "dark") == "dark" else 1,
            help="Chart and interface theme"
        )
        if st.session_state.get('theme') != theme.lower():
            st.session_state.theme = theme.lower()
            st.rerun()  # Refresh to apply theme changes
    
    with settings_col3:
        if st.button("Reset All Settings", type="secondary"):
            # Reset to defaults
            st.session_state.clear()
            st.rerun()
    
    # Skip option
    st.divider()
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Go to Dashboard", type="secondary", use_container_width=True):
            st.session_state.show_welcome = False
            st.rerun()


# ============================================================================
# STOCK ANALYSIS MODE
# ============================================================================

def show_stock_analysis_mode():
    """Display stock discovery and analysis mode."""
    st.title("Stock Discovery & Analysis")
    st.markdown("*Search, explore, and analyze individual stocks*")
    
    st.divider()
    
    # Search section
    col1, col2 = st.columns([2, 1])
    
    with col1:
        search_query = st.text_input(
            "Search Stocks",
            placeholder="Search by company name or ticker (e.g., Apple, AAPL)",
            key="analysis_search"
        )
    
    with col2:
        if st.button("Search", use_container_width=True):
            if search_query:
                with st.spinner("Searching..."):
                    results = search_stocks(search_query, limit=10)
                if results:
                    st.success(f"Found {len(results)} stocks")
                    for stock in results:
                        col_sym, col_name, col_sector, col_select = st.columns([1, 2, 1, 1])
                        with col_sym:
                            st.write(f"**{stock['symbol']}**")
                        with col_name:
                            st.write(stock['name'][:40])
                        with col_sector:
                            st.write(stock['sector'])
                        with col_select:
                            if st.button("View", key=f"view_{stock['symbol']}"):
                                st.session_state.ticker_input = stock['symbol']
                                st.session_state.mode = 'backtesting'
                                st.rerun()
                else:
                    st.warning("No stocks found. Try a different search.")
    
    st.divider()
    
    # Popular stocks
    st.subheader("Popular Stocks")
    
    category = st.selectbox(
        "Select Category",
        get_stock_categories(),
        key="analysis_category"
    )
    
    popular_stocks = get_popular_stocks(category)
    
    cols = st.columns(6)
    for i, symbol in enumerate(popular_stocks[:12]):
        with cols[i % 6]:
            if st.button(symbol, key=f"popular_view_{symbol}", use_container_width=True):
                st.session_state.ticker_input = symbol
                st.session_state.mode = 'backtesting'
                st.rerun()
    
    st.divider()
    
    # Stock info
    if st.session_state.get('ticker_input'):
        try:
            ticker = st.session_state.ticker_input.split(',')[0].strip().upper()
            with st.spinner(f"Loading {ticker} data..."):
                info = get_stock_info(ticker)
                raw_data = load_data_with_status(ticker, '2023-01-01', pd.to_datetime('today'), '1d')
                data = extract_ticker_data(raw_data, ticker, '2023-01-01', pd.to_datetime('today'))
            
            if info and len(data) > 0:
                st.subheader(f"{ticker} - {info.get('name', 'Stock')}")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Sector", info.get('sector', 'N/A'))
                with col2:
                    st.metric("Market Cap", format_market_cap(info.get('market_cap', 0)))
                with col3:
                    st.metric("Current Price", format_price(info.get('current_price', 0)))
                with col4:
                    change = info.get('price_change_percent', 0)
                    st.metric("Change", f"{change:.2f}%")
                
                # Price chart
                close_prices = data['Close']
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=close_prices.index, y=close_prices.values, name=ticker))
                fig.update_layout(
                    title=f"{ticker} Price Chart",
                    xaxis_title="Date",
                    yaxis_title="Price ($)",
                    hovermode="x unified",
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Link to backtesting
                st.divider()
                if st.button("Analyze with Backtest", type="primary", use_container_width=True):
                    st.session_state.mode = 'backtesting'
                    st.rerun()
        except Exception as e:
            st.error(f"Error loading stock data: {e}")
    
    # Back to welcome
    st.divider()
    if st.button("Back to Welcome", type="secondary", use_container_width=True):
        st.session_state.show_welcome = True
        st.rerun()

    # ========================================================================

if __name__ == "__main__":
    main()
