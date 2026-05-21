"""
Stock Backtester - Quant Market Analytics Dashboard
A Streamlit-based dashboard for analyzing market data and backtesting trading strategies.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.subplots as sp
import numpy as np
from datetime import datetime, timedelta
import traceback

from modules.data import download_data
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
    get_stock_categories, format_market_cap, format_price
)
from modules.simulator import (
    TradingSimulator, create_simulator_session, get_simulator_engine, 
    reset_simulator
)

try:
    from . import __version__
except ImportError:
    __version__ = "1.1.2"

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

st.set_page_config(layout="wide", page_title="Quant Market Analytics", page_icon="📊")

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

SHARPE_MODES = {
    "Daily (252 days/yr)": "1d",
    "Hourly": "1h",
    "5-Minute": "5m",
    "1-Minute": "1m",
}

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


# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def display_metrics_panel(metrics):
    """Show 4-column metrics dashboard."""
    metric_cols = st.columns(4)
    
    specs = [
        ("📈 Total Return", f"{metrics['total_return']:.2f}%", "good" if metrics['total_return'] > 0 else "bad"),
        ("⚖️ Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}", "good" if metrics['sharpe_ratio'] > 1 else "neutral"),
        ("📉 Max Drawdown", f"{metrics['max_drawdown']:.2f}%", "bad" if metrics['max_drawdown'] < -10 else "neutral"),
        ("🎯 Win Rate", f"{metrics['win_rate']:.1f}%", "good" if metrics['win_rate'] > 50 else "neutral"),
    ]
    
    for col, (label, value, delta_color) in zip(metric_cols, specs):
        col.metric(label, value)


def display_trade_log(backtest_data, strategy_name):
    """Show trade details and export option."""
    if not backtest_data or 'trades' not in backtest_data or len(backtest_data['trades']) == 0:
        st.info("ℹ️ No trades executed in backtest period.")
        return
    
    st.subheader("📋 Trade Log")
    
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
    
    # Only include columns that exist
    available_columns = ['entry_date', 'entry_price', 'exit_date', 'exit_price', 'return_pct']
    display_columns = [col for col in available_columns if col in display_df.columns]
    display_df = display_df[display_columns]
    
    column_names = ['Entry Date', 'Entry Price', 'Exit Date', 'Exit Price', 'Return %']
    display_df.columns = column_names[:len(display_columns)]
    
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
            st.write(f"**📈 Wins:** Avg {avg_win:.2f}% | Max {max_win:.2f}%")
    
    if losing_trades:
        loss_returns = [t.get('return_pct', 0) for t in losing_trades if t.get('return_pct') is not None]
        if loss_returns:
            avg_loss = np.mean(loss_returns)
            max_loss = min(loss_returns)
            st.write(f"**📉 Losses:** Avg {avg_loss:.2f}% | Max {max_loss:.2f}%")
    
    # Export button
    csv_data = trades_df.to_csv(index=False)
    st.download_button(
        "📥 Download Trades (CSV)",
        csv_data,
        f"trades_{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        "text/csv",
        help="Export trade log for external analysis"
    )


def display_advanced_chart(data, selected_ticker, backtest_data=None, backtest_signals=None):
    """Show candlestick chart with indicators and equity curve."""
    df = data.xs(selected_ticker, level=1, axis=1) if len(data.columns.names) > 1 else data
    price = df["Close"]
    
    # Compute indicators
    ma50, ma200 = moving_averages(price)
    rsi_values = rsi(price)
    macd_line, signal = macd(price)
    upper, lower = bollinger(price)
    
    # Determine chart rows
    num_rows = 5 if backtest_data is not None else 4
    row_heights = [0.4, 0.12, 0.15, 0.1, 0.23] if num_rows == 5 else [0.5, 0.15, 0.2, 0.15]
    
    fig = sp.make_subplots(
        rows=num_rows, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.02,
        subplot_titles=("Price Action", "Volume", "MACD", "RSI", "Equity Curve") if num_rows == 5 
                      else ("Price Action", "Volume", "MACD", "RSI")
    )
    
    # Row 1: Candlestick + MA + BB
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
    
    fig.add_trace(go.Scatter(x=df.index, y=ma50, name="MA50", line=dict(color="orange")), row=1, col=1)
    if ma200 is not None:
        fig.add_trace(go.Scatter(x=df.index, y=ma200, name="MA200", line=dict(color="red")), row=1, col=1)
    if upper is not None and lower is not None:
        fig.add_trace(go.Scatter(x=df.index, y=upper, name="BB Upper", line=dict(color="gray", dash="dash")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=lower, name="BB Lower", line=dict(color="gray", dash="dash")), row=1, col=1)
    
    # Add entry/exit signals if backtest active
    if backtest_data is not None and backtest_signals is not None:
        entries_idx = backtest_signals['entries'][backtest_signals['entries'] > 0].index
        exits_idx = backtest_signals['exits'][backtest_signals['exits'] > 0].index
        
        if len(entries_idx) > 0:
            entry_lows = df.loc[entries_idx, "Low"]
            fig.add_trace(
                go.Scatter(x=entries_idx, y=entry_lows, mode="markers",
                          marker=dict(size=10, color="green", symbol="diamond"),
                          name="Buy", showlegend=True),
                row=1, col=1
            )
        
        if len(exits_idx) > 0:
            exit_highs = df.loc[exits_idx, "High"]
            fig.add_trace(
                go.Scatter(x=exits_idx, y=exit_highs, mode="markers",
                          marker=dict(size=10, color="red", symbol="x"),
                          name="Sell", showlegend=True),
                row=1, col=1
            )
    
    # Row 2: Volume
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color="lightblue"), row=2, col=1)
    
    # Row 3: MACD
    if macd_line is not None and signal is not None:
        fig.add_trace(go.Scatter(x=df.index, y=macd_line, name="MACD", line=dict(color="blue")), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=signal, name="Signal", line=dict(color="red")), row=3, col=1)
    
    # Row 4: RSI
    if rsi_values is not None:
        fig.add_trace(go.Scatter(x=df.index, y=rsi_values, name="RSI", line=dict(color="purple")), row=4, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1, annotation_text="Overbought")
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1, annotation_text="Oversold")
    
    # Row 5: Equity curve (if backtest active)
    if backtest_data is not None:
        equity = backtest_data['equity']
        # Use the full price series for buy & hold calculation, aligned with equity dates
        try:
            bh_equity = buy_hold_equity(price.loc[equity.index], initial_equity=100)
            
            fig.add_trace(
                go.Scatter(x=equity.index, y=equity.values, name="Strategy", line=dict(color="blue", width=2)),
                row=num_rows, col=1
            )
            fig.add_trace(
                go.Scatter(x=bh_equity.index, y=bh_equity.values, name="Buy & Hold", 
                          line=dict(color="gray", width=2, dash="dash")),
                row=num_rows, col=1
            )
        except Exception as e:
            st.warning(f"Could not display equity curve: {e}")
    
    # Layout
    current_theme = st.session_state.get('theme', 'dark')
    template = 'plotly_white' if current_theme == 'light' else 'plotly_dark'
    
    fig.update_layout(
        height=900 if num_rows == 4 else 1100,
        hovermode='x unified',
        template=template
    )
    
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_yaxes(title_text="MACD", row=3, col=1)
    fig.update_yaxes(title_text="RSI", row=4, col=1)
    if num_rows == 5:
        fig.update_yaxes(title_text="Equity ($)", row=5, col=1)
    
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
            'ticker_input', 'simulator'
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
                elif key == 'simulator':
                    st.session_state.simulator = {
                        'active': False,
                        'engine': None,
                        'current_step': 0,
                        'total_steps': 0,
                        'is_playing': False
                    }

        # Show welcome dashboard if needed
        if st.session_state.show_welcome:
            show_welcome_dashboard()
            return  # Exit early to show only welcome screen

        # Main application logic
        show_main_dashboard()

    except Exception as e:
        st.error(f"❌ Application error: {str(e)}")
        st.info("💡 Please refresh the page to restart the application.")
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
        st.subheader("🎮 Trading Simulator")

        # Simulator controls
        simulator_active = st.toggle(
            "🎮 Activate Simulator",
            value=st.session_state.simulator.get('active', False),
            help="Enable manual trading simulation"
        )

        if simulator_active:
            st.session_state.simulator['active'] = True

            # Simulator settings in a more organized layout
            st.markdown("### ⚙️ Simulation Settings")

            # Date range selection
            col1, col2 = st.columns(2)
            with col1:
                sim_start = st.date_input(
                    "📅 Start Date",
                    value=start,
                    key="sim_start",
                    help="When your trading simulation begins"
                )
            with col2:
                sim_end = st.date_input(
                    "📅 End Date",
                    value=end,
                    key="sim_end",
                    help="When your trading simulation ends"
                )

            # Capital and fees
            col1, col2 = st.columns(2)
            with col1:
                initial_equity = st.number_input(
                    "💰 Starting Capital ($)",
                    value=10000,
                    min_value=1000,
                    max_value=1000000,
                    step=1000,
                    help="How much money you start with"
                )
            with col2:
                sim_fee = st.slider(
                    "💸 Transaction Fee (%)",
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
                    sim_data = download_data([selected_ticker], sim_start, sim_end, interval)

                    if len(sim_data) > 0:
                        simulator.reset()
                        simulator.transaction_fee = sim_fee
                        simulator.initial_equity = initial_equity
                        simulator.set_timeframe(sim_data, sim_start, sim_end)
                        st.success(f"🎯 **Simulation Ready!** Trading **{selected_ticker}** from {sim_start.strftime('%B %d, %Y')} to {sim_end.strftime('%B %d, %Y')} with ${initial_equity:,.0f} starting capital")
                        st.info("💡 Use the Trading Panel below to buy and sell shares. Navigate through time to practice your trading strategy!")
                    else:
                        st.error("❌ No data available for the selected period")
                        simulator_active = False

                except Exception as e:
                    st.error(f"❌ Failed to initialize simulator: {e}")
                    simulator_active = False

            # Trading controls
            if simulator_active and hasattr(simulator, 'sim_data'):
                st.markdown("---")

                # Current state display - prominent metrics
                st.markdown("### 📊 Current Position")
                state = simulator.get_current_state()

                # Main metrics in a nice grid
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📅 Current Date", state['date'].strftime('%Y-%m-%d'))
                with col2:
                    st.metric("💰 Available Cash", f"${state['cash']:.2f}")
                with col3:
                    st.metric("📊 Shares Held", state['positions'])
                with col4:
                    st.metric("💎 Total Equity", f"${state['total_equity']:.2f}")

                # Current price display
                if hasattr(simulator, 'current_price'):
                    st.metric("📈 Current Price", f"${simulator.current_price:.2f}")

                st.markdown("---")

                # Trading Panel
                st.markdown("### 🏪 Trading Panel")

                # Buy/Sell section with better layout
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("#### 🟢 BUY")
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

                    if st.button("🟢 EXECUTE BUY", type="primary", use_container_width=True):
                        if simulator.execute_buy(buy_qty):
                            price_str = f"${simulator.current_price:.2f}" if hasattr(simulator, 'current_price') else "N/A"
                            st.success(f"✅ Bought {buy_qty} shares at {price_str}")
                            st.rerun()
                        else:
                            can_buy, reason = simulator.can_buy(buy_qty)
                            st.error(f"❌ {reason}")

                with col2:
                    st.markdown("#### 🔴 SELL")
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

                    if st.button("🔴 EXECUTE SELL", type="primary", use_container_width=True):
                        if simulator.execute_sell(sell_qty):
                            price_str = f"${simulator.current_price:.2f}" if hasattr(simulator, 'current_price') else "N/A"
                            st.success(f"✅ Sold {sell_qty} shares at {price_str}")
                            st.rerun()
                        else:
                            can_sell, reason = simulator.can_sell(sell_qty)
                            st.error(f"❌ {reason}")

                st.markdown("---")

                # Time Navigation Panel
                st.markdown("### ⏰ Time Navigation")

                time_col1, time_col2, time_col3, time_col4, time_col5 = st.columns(5)

                with time_col1:
                    if st.button("⏮️ START", help="Go to beginning", use_container_width=True):
                        simulator.go_to_date(simulator.sim_data.index[0])
                        st.rerun()

                with time_col2:
                    if st.button("◀️ -1 DAY", help="Go back 1 day", use_container_width=True):
                        if simulator.advance_time(-1):
                            st.rerun()
                        else:
                            st.info("Already at start")

                with time_col3:
                    if st.button("▶️ +1 DAY", help="Advance 1 day", use_container_width=True):
                        if simulator.advance_time(1):
                            st.rerun()
                        else:
                            st.info("End of simulation reached")

                with time_col4:
                    if st.button("⏭️ +5 DAYS", help="Advance 5 days", use_container_width=True):
                        if simulator.advance_time(5):
                            st.rerun()
                        else:
                            st.info("End of simulation reached")

                with time_col5:
                    if st.button("🔄 RESET", type="secondary", help="Reset simulation", use_container_width=True):
                        reset_simulator()
                        st.rerun()
        else:
            st.session_state.simulator['active'] = False
            st.info("🎮 **Ready to start trading?** Toggle 'Activate Simulator' above to begin your trading simulation!")
            st.markdown("""
            **What you can do:**
            - Practice buying and selling stocks
            - Learn trading without risking real money
            - Test different strategies over historical data
            - Track your performance in real-time
            """)

    except Exception as e:
        st.error(f"❌ Simulator mode error: {e}")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())


def display_simulator_chart(data, selected_ticker):
    """Display simulator chart with trades."""
    try:
        if not hasattr(st.session_state.simulator['engine'], 'sim_data') or st.session_state.simulator['engine'].sim_data is None:
            st.info("💡 Activate the simulator to see the trading chart")
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
        if hasattr(simulator, 'trades') and simulator.trades:
            buy_trades = pd.DataFrame([t for t in simulator.trades if t['action'] == 'BUY'])
            sell_trades = pd.DataFrame([t for t in simulator.trades if t['action'] == 'SELL'])

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
        template = 'plotly_white' if current_theme == 'light' else 'plotly_dark'

        fig.update_layout(height=600, showlegend=True, template=template)
        fig.update_xaxes(title_text="Date", row=2, col=1)
        fig.update_yaxes(title_text="Price ($)", row=1, col=1)
        fig.update_yaxes(title_text="Equity ($)", row=2, col=1)

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Chart display error: {e}")


def show_backtesting_mode(data, selected_ticker, start, end, interval, enable_portfolio, portfolio_weight_input, rebalance_period, enable_risk, stop_loss_pct, take_profit_pct, enable_optimizer, optimizer_strategy, optimizer_strat_hold, optimizer_strat_fee):
    """Handle backtesting mode logic."""
    try:
        st.subheader("🤖 Backtesting")

        # Get data for selected ticker
        ticker_data = extract_ticker_data(data, selected_ticker, start, end)
        if ticker_data.empty:
            st.error("❌ No data available for backtesting")
            return

        close = ticker_data["Close"]
        indicators = compute_all_indicators(close)

        # Strategy selection
        strategy_name = st.selectbox(
            "Select Strategy",
            STRATEGY_OPTIONS,
            help="Choose trading strategy to backtest"
        )

        if strategy_name != "None":
            # Quick presets
            preset = st.selectbox(
                "📋 Quick Presets",
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
                with st.expander("⚙️ Advanced Options", expanded=False):
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

            # Run backtest button
            if st.button("🚀 Run Backtest", type="primary"):
                with st.spinner("Running backtest..."):
                    try:
                        # Run backtest
                        backtest_result = run_single_backtest(strategy_name, close, indicators, config)
                        backtest_metrics = backtest_result

                        # Store results in session state
                        st.session_state.backtest_result = backtest_result
                        st.session_state.backtest_metrics = backtest_metrics

                        st.success("✅ Backtest completed!")

                        # Display metrics
                        display_metrics_panel(backtest_metrics)

                        with col2:
                            st.metric("📅 Period", f"{(end - start).days}d")

                        st.divider()

                        # Trade log
                        display_trade_log(backtest_result, strategy_name)
                        st.divider()

                    except Exception as e:
                        st.error(f"❌ Backtest failed: {e}")

            # Display previous results if available
            if 'backtest_metrics' in st.session_state and st.session_state.backtest_metrics:
                st.subheader("📊 Backtest Results")
                display_metrics_panel(st.session_state.backtest_metrics)

                # Trade log
                if 'backtest_result' in st.session_state:
                    display_trade_log(st.session_state.backtest_result, st.session_state.get('strategy_name', strategy_name))

        # Phase 2: Strategy optimizer results
        if enable_optimizer and optimizer_strategy and strategy_name != 'None':
            st.subheader('🧪 Strategy Optimizer Results')
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
        st.error(f"❌ Backtesting mode error: {e}")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())


def show_main_content(data, selected_ticker, start, end, interval, mode, enable_portfolio, portfolio_weight_input, rebalance_period, enable_risk, stop_loss_pct, take_profit_pct, enable_optimizer, optimizer_strategy, optimizer_strat_hold, optimizer_strat_fee):
    """Display main content based on selected mode."""
    try:
        if mode == "📊 Analysis":
            show_analysis_mode(data, selected_ticker, start, end, interval)
        elif mode == "📈 Backtesting":
            show_backtesting_mode(data, selected_ticker, start, end, interval, enable_portfolio, portfolio_weight_input, rebalance_period, enable_risk, stop_loss_pct, take_profit_pct, enable_optimizer, optimizer_strategy, optimizer_strat_hold, optimizer_strat_fee)
        elif mode == "🎮 Simulator":
            show_simulator_mode(data, selected_ticker, start, end, interval)
        else:
            st.error(f"❌ Unknown mode: {mode}")

    except Exception as e:
        st.error(f"❌ Main content error: {e}")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())


def show_analysis_mode(data, selected_ticker, start, end, interval):
    """Handle analysis mode logic with stock discovery."""
    try:
        st.subheader("🔍 Stock Discovery & Analysis")

        # Stock search section
        st.markdown("### 🔎 Find Stocks")
        
        # Search functionality
        search_col1, search_col2 = st.columns([3, 1])
        with search_col1:
            search_query = st.text_input(
                "Search stocks by symbol or name",
                placeholder="e.g., AAPL, Apple, TSLA...",
                help="Enter stock symbol or company name"
            )
        
        with search_col2:
            if st.button("🔍 Search", type="secondary"):
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
            st.markdown("### 📋 Search Results")
            
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
        st.markdown("### ⭐ Popular Stocks")
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
            st.markdown("### ⚙️ Technical Analysis Settings")

            # Indicator selection
            col1, col2 = st.columns(2)
            with col1:
                selected_indicators = st.multiselect(
                    "📈 Technical Indicators",
                    ["SMA", "EMA", "RSI", "MACD", "Bollinger Bands", "Volume"],
                    default=["SMA", "RSI"],
                    help="Select indicators to display on the chart"
                )

            with col2:
                chart_type = st.selectbox(
                    "📊 Chart Type",
                    ["Candlestick", "Line", "OHLC"],
                    index=0,
                    help="Choose how to display price data"
                )

            # Generate analysis
            if st.button("🔍 Run Analysis", type="primary"):
                with st.spinner("Analyzing data..."):
                    try:
                        # Get data for selected ticker
                        raw_analysis_data = download_data([selected_ticker], start, end, interval)

                        if raw_analysis_data is None or len(raw_analysis_data) == 0:
                            st.error("❌ No data available for analysis")
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
                                st.warning(f"⚠️ Could not calculate {indicator}: {e}")

                        # Display chart
                        display_analysis_chart(analysis_data, indicators_data, chart_type, selected_indicators)

                        # Summary statistics
                        st.markdown("### 📈 Summary Statistics")
                        col1, col2, col3, col4 = st.columns(4)

                        with col1:
                            st.metric("📅 Period", f"{len(analysis_data)} days")
                        with col2:
                            start_price = analysis_data["Close"].iloc[0]
                            end_price = analysis_data["Close"].iloc[-1]
                            change = ((end_price - start_price) / start_price) * 100
                            st.metric("📈 Total Return", f"{change:.2f}%")
                        with col3:
                            st.metric("💰 Max Price", f"${analysis_data['High'].max():.2f}")
                        with col4:
                            st.metric("💰 Min Price", f"${analysis_data['Low'].min():.2f}")

                    except Exception as e:
                        st.error(f"❌ Analysis failed: {e}")
        else:
            st.info("💡 Select a stock above to begin technical analysis")

    except Exception as e:
        st.error(f"❌ Analysis mode error: {e}")
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
        template = 'plotly_white' if current_theme == 'light' else 'plotly_dark'

        fig.update_layout(height=600, showlegend=True, template=template)
        fig.update_xaxes(title_text="Date", row=subplot_count, col=1)

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Chart display error: {e}")


def show_main_dashboard():
    """Main dashboard display function."""
    try:
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
        show_price = sidebar_params['show_price']
        show_drawdown = sidebar_params['show_drawdown']
        show_corr = sidebar_params['show_corr']
        is_simulator_mode = sidebar_params['is_simulator_mode']
        enable_portfolio = sidebar_params['enable_portfolio']
        portfolio_weight_input = sidebar_params['portfolio_weight_input']
        rebalance_period = sidebar_params['rebalance_period']
        enable_risk = sidebar_params['enable_risk']
        stop_loss_pct = sidebar_params['stop_loss_pct']
        take_profit_pct = sidebar_params['take_profit_pct']
        enable_optimizer = sidebar_params['enable_optimizer']
        optimizer_strategy = sidebar_params['optimizer_strategy']
        optimizer_strat_hold = sidebar_params['optimizer_strat_hold']
        optimizer_strat_fee = sidebar_params['optimizer_strat_fee']

        # Determine mode from session state and simulator flag
        current_mode = st.session_state.get('mode', 'backtesting')
        if current_mode == 'analysis':
            mode = "📊 Analysis"
        elif is_simulator_mode or current_mode == 'simulator':
            mode = "🎮 Simulator"
        else:
            mode = "📈 Backtesting"

        # Download data
        with st.spinner("📊 Downloading market data..."):
            try:
                data = download_data(tickers, start, end, interval)
                if data is None or len(data) == 0:
                    st.error("❌ No data available for the selected period and tickers")
                    return
            except Exception as e:
                st.error(f"❌ Failed to download data: {e}")
                return

        # Select ticker for single-ticker operations
        if not tickers or len(tickers) == 0:
            st.error("❌ No tickers selected")
            return
        selected_ticker = tickers[0]

        # Display main content based on mode
        show_main_content(data, selected_ticker, start, end, interval, mode, enable_portfolio, portfolio_weight_input, rebalance_period, enable_risk, stop_loss_pct, take_profit_pct, enable_optimizer, optimizer_strategy, optimizer_strat_hold, optimizer_strat_fee)

        # Display additional charts if enabled
        if show_price and not is_simulator_mode:
            st.subheader("📈 Price Action & Technical Indicators")
            backtest_signals = None
            if 'backtest_result' in st.session_state and st.session_state.backtest_result:
                backtest_signals = {
                    'entries': st.session_state.backtest_result['entries'],
                    'exits': st.session_state.backtest_result['exits']
                }
            display_advanced_chart(data, selected_ticker, st.session_state.get('backtest_result'), backtest_signals)

        if show_drawdown and not is_simulator_mode:
            st.subheader("📉 Drawdown Analysis")
            close_data = data.xs(selected_ticker, level=1, axis=1)["Close"] if len(data.columns.names) > 1 else data["Close"]
            dd = close_data / close_data.cummax() - 1
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dd.index, y=dd.values * 100, fill='tozeroy', name='Drawdown'))
            fig.update_layout(
                title="Portfolio Drawdown",
                yaxis_title="Drawdown (%)",
                template='plotly_white' if st.session_state.get('theme', 'dark') == 'light' else 'plotly_dark',
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)

        if show_corr and not is_simulator_mode:
            st.subheader("🔗 Correlation Matrix")
            close_for_corr = data["Close"] if isinstance(data.columns, pd.MultiIndex) and "Close" in data.columns.get_level_values(0) else data["Close"]
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
                    template='plotly_white' if st.session_state.get('theme', 'dark') == 'light' else 'plotly_dark'
                )
                st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Dashboard error: {str(e)}")
        with st.expander("Debug Information"):
            st.code(f"Error: {str(e)}")
            st.code(traceback.format_exc())


def show_sidebar():
    """Display sidebar with proper error handling."""
    try:
        # Stock search section
        st.subheader("🔍 Stock Search")

        search_query = st.text_input(
            "Search stocks",
            placeholder="e.g., Apple, AAPL, TSLA",
            help="Search by company name or ticker symbol"
        )

        if search_query:
            with st.spinner("🔍 Searching..."):
                search_results = search_stocks(search_query, limit=5)

            if search_results:
                st.write("**Search Results:**")
                for stock in search_results:
                    if st.button(
                        f"{stock['symbol']} - {stock['name'][:30]}",
                        key=f"search_{stock['symbol']}",
                        help=f"Sector: {stock['sector']}"
                    ):
                        # Update ticker input with selected stock
                        st.session_state.ticker_input = stock['symbol']
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
        cols = st.columns(3)
        for i, symbol in enumerate(popular_stocks[:9]):  # Show first 9
            with cols[i % 3]:
                if st.button(symbol, key=f"sidebar_popular_{i}_{symbol}"):
                    st.session_state.ticker_input = symbol
                    st.rerun()

        st.sidebar.divider()

        # Data section
        st.subheader("📈 Data Selection")

        # Use session state for ticker input to persist selections
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

        # Validate dates
        if start >= end:
            st.error("❌ Start date must be before end date")
            return

        tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

        if not tickers:
            st.error("❌ Please enter at least one ticker symbol")
            return

        st.sidebar.divider()

        # Display options
        st.subheader("👁️ Display Options")

        col1, col2, col3 = st.columns(3)
        with col1:
            show_price = st.toggle("📊 Chart", value=True)
        with col2:
            show_drawdown = st.toggle("📉 Drawdown", value=True)
        with col3:
            show_corr = st.toggle("🔗 Correlation", value=True)

        st.sidebar.divider()

        # Mode selection
        st.subheader("🎮 Mode Selection")

        # Get current mode from session state
        current_mode = st.session_state.get('mode', 'backtesting')

        # Handle analysis mode differently - don't show mode selection
        if current_mode == 'analysis':
            st.info("📊 **Analysis Mode**: Use the controls below to explore technical indicators and charts.")
            mode = "📊 Analysis"
            is_simulator_mode = False
        else:
            # Map session state mode to radio options
            mode_options = ["📊 Backtesting", "🎮 Simulator"]
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
            st.subheader("🧩 Phase 2 Enhancements")
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
        st.markdown("### 💾 Workspace")
        if st.button("Save Workspace"):
            try:
                workspace_data = {
                    'tickers': tickers_input,
                    'start_date': str(start),
                    'end_date': str(end),
                    'interval': interval,
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
                st.success("✅ Workspace saved!")
            except Exception as e:
                st.error(f"❌ Failed to save workspace: {e}")

        if st.button("Load Workspace"):
            try:
                workspace_data = load_workspace("workspace.json")
                if workspace_data:
                    # Restore settings
                    st.session_state.ticker_input = workspace_data.get('tickers', DEFAULT_TICKERS)
                    st.session_state.mode = workspace_data.get('mode', 'backtesting')
                    st.success("✅ Workspace loaded!")
                    st.rerun()
                else:
                    st.warning("⚠️ No saved workspace found")
            except Exception as e:
                st.error(f"❌ Failed to load workspace: {e}")

        # Return all the sidebar variables
        return {
            'tickers': tickers,
            'start': start,
            'end': end,
            'interval': interval,
            'show_price': show_price,
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
        st.error(f"❌ Sidebar error: {e}")
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

        st.title("📊 Quant Market Analytics")
        st.markdown("*Professional quantitative trading analysis and backtesting platform*")

        # Download data
        with st.spinner("📥 Downloading market data..."):
            data = download_data(tickers, start, end, interval)

        if data is None:
            st.error("❌ Failed to download market data. Please check your ticker symbols and date range.")
            return

        if data.empty:
            st.error("❌ No data available for the selected tickers and date range.")
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
                st.subheader("📈 Price Action & Technical Indicators")

                backtest_signals = None
                if 'backtest_result' in st.session_state and st.session_state.backtest_result:
                    backtest_signals = {
                        'entries': st.session_state.backtest_result['entries'],
                        'exits': st.session_state.backtest_result['exits']
                    }

                display_advanced_chart(data, selected_ticker, st.session_state.get('backtest_result'), backtest_signals)
            else:
                # Simulator chart
                st.subheader("📈 Simulator Chart")
                display_simulator_chart(data, selected_ticker)

        # Drawdown chart
        if show_drawdown and not is_simulator_mode:
            st.subheader("📉 Drawdown Analysis")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dd.index, y=dd.values * 100, fill='tozeroy', name='Drawdown'))
            fig.update_layout(
                title="Portfolio Drawdown",
                yaxis_title="Drawdown (%)",
                template='plotly_dark',
                height=400
            )

            st.plotly_chart(fig, use_container_width=True)
            st.divider()

        # Correlation heatmap
        if show_corr and not is_simulator_mode:
            st.subheader("🔗 Correlation Matrix")
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
                    template='plotly_dark'
                )

                st.plotly_chart(fig, use_container_width=True)

        # Footer
        st.divider()
        st.markdown(
            """
            <div style='text-align: center; color: gray; font-size: 12px;'>
            📊 Quant Market Analytics v1.1.2 | Data from Yahoo Finance | Not financial advice
            </div>
            """,
            unsafe_allow_html=True
        )

    except Exception as e:
        st.error(f"❌ Main content error: {e}")
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
        st.subheader("👁️ Display Options")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            show_price = st.toggle("📊 Chart", value=True)
        with col2:
            show_drawdown = st.toggle("📉 Drawdown", value=True)
        with col3:
            show_corr = st.toggle("🔗 Correlation", value=True)
        
        st.sidebar.divider()
        
        # Mode selection
        st.subheader("🎮 Mode Selection")
        
        # Get current mode from session state
        current_mode = st.session_state.get('mode', 'backtesting')
        
        # Map session state mode to radio options
        mode_options = ["📊 Backtesting", "🎮 Simulator"]
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
            st.subheader("🧩 Phase 2 Enhancements")
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
        st.markdown("### 💾 Workspace")
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
            st.subheader("🤖 Backtesting")
            
            strategy_name = st.selectbox(
                "Select Strategy",
                STRATEGY_OPTIONS,
                help="Choose trading strategy to backtest"
            )
        
        if strategy_name != "None":
            # Quick presets
            preset = st.selectbox(
                "📋 Quick Presets",
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
                with st.expander("⚙️ Advanced Options", expanded=False):
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
            st.subheader("🎮 Trading Simulator")
            
            # Initialize simulator
            create_simulator_session()
            simulator = get_simulator_engine()
            
            # Simulator controls
            simulator_active = st.toggle(
                "🎮 Activate Simulator", 
                value=st.session_state.simulator.get('active', False),
                help="Enable manual trading simulation"
            )
            
            if simulator_active:
                st.session_state.simulator['active'] = True
                
                # Simulator settings in a more organized layout
                st.markdown("### ⚙️ Simulation Settings")

                # Date range selection
                col1, col2 = st.columns(2)
                with col1:
                    sim_start = st.date_input(
                        "📅 Start Date",
                        value=DEFAULT_START,
                        key="sim_start",
                        help="When your trading simulation begins"
                    )
                with col2:
                    sim_end = st.date_input(
                        "📅 End Date",
                        value=DEFAULT_END,
                        key="sim_end",
                        help="When your trading simulation ends"
                    )

                # Capital and fees
                col1, col2 = st.columns(2)
                with col1:
                    initial_equity = st.number_input(
                        "💰 Starting Capital ($)",
                        value=10000,
                        min_value=1000,
                        max_value=1000000,
                        step=1000,
                        help="How much money you start with"
                    )
                with col2:
                    sim_fee = st.slider(
                        "💸 Transaction Fee (%)",
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
                        sim_data = download_data([selected_ticker], sim_start, sim_end, interval)

                        if len(sim_data) > 0:
                            simulator.reset()
                            simulator.transaction_fee = sim_fee
                            simulator.initial_equity = initial_equity
                            simulator.set_timeframe(sim_data, sim_start, sim_end)
                            st.success(f"🎯 **Simulation Ready!** Trading **{selected_ticker}** from {sim_start.strftime('%B %d, %Y')} to {sim_end.strftime('%B %d, %Y')} with ${initial_equity:,.0f} starting capital")
                            st.info("💡 Use the Trading Panel below to buy and sell shares. Navigate through time to practice your trading strategy!")
                        else:
                            st.error("❌ No market data available for the selected period. Try different dates or ticker.")
                            simulator_active = False

                    except Exception as e:
                        st.error(f"❌ Failed to initialize simulator: {e}")
                        st.info("💡 Make sure you have selected a valid ticker symbol in the sidebar.")
                        simulator_active = False
                
                # Trading controls
                if simulator_active and hasattr(simulator, 'sim_data'):
                    st.markdown("---")

                    # Current state display - prominent metrics
                    st.markdown("### 📊 Current Position")
                    state = simulator.get_current_state()

                    # Main metrics in a nice grid
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("📅 Current Date", state['date'].strftime('%Y-%m-%d'))
                    with col2:
                        st.metric("💰 Available Cash", f"${state['cash']:.2f}")
                    with col3:
                        st.metric("📊 Shares Held", state['positions'])
                    with col4:
                        st.metric("💎 Total Equity", f"${state['total_equity']:.2f}")

                    # Current price display
                    if hasattr(simulator, 'current_price'):
                        st.metric("📈 Current Price", f"${simulator.current_price:.2f}")

                    st.markdown("---")

                    # Trading Panel
                    st.markdown("### 🏪 Trading Panel")

                    # Buy/Sell section with better layout
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("#### 🟢 BUY")
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

                        if st.button("🟢 EXECUTE BUY", type="primary", use_container_width=True):
                            if simulator.execute_buy(buy_qty):
                                st.success(f"✅ Bought {buy_qty} shares at ${simulator.current_price:.2f}")
                                st.rerun()
                            else:
                                can_buy, reason = simulator.can_buy(buy_qty)
                                st.error(f"❌ {reason}")

                    with col2:
                        st.markdown("#### 🔴 SELL")
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

                        if st.button("🔴 EXECUTE SELL", type="primary", use_container_width=True):
                            if simulator.execute_sell(sell_qty):
                                st.success(f"✅ Sold {sell_qty} shares at ${simulator.current_price:.2f}")
                                st.rerun()
                            else:
                                can_sell, reason = simulator.can_sell(sell_qty)
                                st.error(f"❌ {reason}")

                    st.markdown("---")

                    # Time Navigation Panel
                    st.markdown("### ⏰ Time Navigation")

                    time_col1, time_col2, time_col3, time_col4, time_col5 = st.columns(5)

                    with time_col1:
                        if st.button("⏮️ START", help="Go to beginning", use_container_width=True):
                            simulator.go_to_date(simulator.sim_data.index[0])
                            st.rerun()

                    with time_col2:
                        if st.button("◀️ -1 DAY", help="Go back 1 day", use_container_width=True):
                            if simulator.advance_time(-1):
                                st.rerun()
                            else:
                                st.info("Already at start")

                    with time_col3:
                        if st.button("▶️ +1 DAY", help="Advance 1 day", use_container_width=True):
                            if simulator.advance_time(1):
                                st.rerun()
                            else:
                                st.info("End of simulation reached")

                    with time_col4:
                        if st.button("⏭️ +5 DAYS", help="Advance 5 days", use_container_width=True):
                            if simulator.advance_time(5):
                                st.rerun()
                            else:
                                st.info("End of simulation reached")

                    with time_col5:
                        if st.button("🔄 RESET", type="secondary", help="Reset simulation", use_container_width=True):
                            reset_simulator()
                            st.rerun()
            else:
                st.session_state.simulator['active'] = False
                st.info("🎮 **Ready to start trading?** Toggle 'Activate Simulator' above to begin your trading simulation!")
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
    
    st.title("📊 Quant Market Analytics")
    st.markdown("*Professional quantitative trading analysis and backtesting platform*")
    
    # Download data
    try:
        with st.spinner("📥 Downloading market data..."):
            data = download_data(tickers, start, end, interval)
    except Exception as e:
        st.error(f"❌ Failed to download data: {e}")
        st.info("💡 Check that ticker symbols are valid (e.g., AAPL not Apple)")
        st.stop()
    
    if data is None or data.empty:
        st.error("❌ No data available for the selected period and tickers")
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
                with st.spinner("⚙️ Running backtest..."):
                    # Extract data
                    ticker_data = extract_ticker_data(data, selected_ticker, backtest_start, backtest_end)
                    
                    if len(ticker_data) == 0:
                        st.warning(f"⚠️ No data for {selected_ticker} in range {backtest_start} to {backtest_end}")
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
                st.error(f"❌ Configuration error: {e}")
            except Exception as e:
                st.error(f"❌ Backtest failed: {e}")
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
        st.subheader("📌 Risk Management Summary")
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
        st.subheader("📂 Portfolio Backtest")
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
                st.metric("📅 Period", f"{(backtest_end - backtest_start).days}d")
            
            st.divider()
            
            # Trade log
            display_trade_log(backtest_result, strategy_name)
            st.divider()
    
    else:
        # Simulator results
        if simulator_metrics is not None:
            st.divider()
            st.subheader("📊 Simulator Performance")
            
            # Current state
            state = simulator.get_current_state()
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("💰 Cash", f"${state['cash']:.2f}")
            with col2:
                st.metric("📊 Positions", state['positions'])
            with col3:
                st.metric("💎 Total Equity", f"${state['total_equity']:.2f}")
            with col4:
                st.metric("📈 Unrealized P&L", f"${state['unrealized_pnl']:.2f}")
            
            # Performance metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                color = "🟢" if simulator_metrics['total_return'] > 0 else "🔴"
                st.metric("💰 Total Return", f"{color} {simulator_metrics['total_return']:.2f}%")
            with col2:
                st.metric("📊 Sharpe Ratio", f"{simulator_metrics['sharpe_ratio']:.2f}")
            with col3:
                st.metric("📉 Max Drawdown", f"{simulator_metrics['max_drawdown']:.2f}%")
            with col4:
                st.metric("🎯 Win Rate", f"{simulator_metrics['win_rate']:.1f}%")
            
            # Trade log
            if not simulator_trades_df.empty:
                st.divider()
                st.subheader("📋 Trade History")
                
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
                    "📥 Export Trades (CSV)",
                    csv,
                    "simulator_trades.csv",
                    "text/csv"
                )
            
            st.divider()

            # Phase 2: Strategy optimizer results
            if enable_optimizer and optimizer_strategy and strategy_name != 'None':
                st.subheader('🧪 Strategy Optimizer Results')
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
            st.subheader("📈 Price Action & Technical Indicators")
            
            backtest_signals = None
            if backtest_result is not None:
                backtest_signals = {
                    'entries': backtest_result['entries'],
                    'exits': backtest_result['exits']
                }
            
            display_advanced_chart(data, selected_ticker, backtest_result, backtest_signals)
        else:
            # Simulator chart
            st.subheader("📈 Simulator Chart")
            
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
                template = 'plotly_white' if current_theme == 'light' else 'plotly_dark'
                
                fig.update_layout(height=600, showlegend=True, template=template)
                fig.update_xaxes(title_text="Date", row=2, col=1)
                fig.update_yaxes(title_text="Price ($)", row=1, col=1)
                fig.update_yaxes(title_text="Equity ($)", row=2, col=1)
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("💡 Activate the simulator to see the trading chart")
        
        st.divider()
        st.divider()
    
    # Drawdown chart
    if show_drawdown and not is_simulator_mode:
        st.subheader("📉 Drawdown Analysis")
        
        drawdown_fig = go.Figure()
        for ticker in tickers:
            drawdown_fig.add_trace(
                go.Scatter(x=dd.index, y=dd[ticker] * 100, name=ticker, mode='lines')
            )
        
        drawdown_fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Drawdown (%)",
            hovermode='x unified',
            template='plotly_white' if st.session_state.get('theme', 'dark') == 'light' else 'plotly_dark',
            height=400
        )
        
        st.plotly_chart(drawdown_fig, use_container_width=True)
        st.divider()
    
    # Correlation heatmap
    if show_corr and not is_simulator_mode:
        st.subheader("🔗 Correlation Matrix")
        
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
            template='plotly_white' if st.session_state.get('theme', 'dark') == 'light' else 'plotly_dark'
        )
        
        st.plotly_chart(corr_fig, use_container_width=True)
    
    # Footer
    st.divider()
    st.markdown(
        f"""
        <div style='text-align: center; color: gray; font-size: 12px;'>
        📊 Quant Market Analytics v{__version__} | Data from Yahoo Finance | Not financial advice
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
    <div style='text-align: center; padding: 2rem 0;'>
        <h1 style='color: #1f77b4; font-size: 3rem; margin-bottom: 0.5rem;'>📊 Quant Market Analytics</h1>
        <p style='font-size: 1.2rem; color: #666; margin-bottom: 2rem;'>Professional quantitative trading analysis and backtesting platform</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Quick start options
    st.markdown("### 🚀 Quick Start")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        **📈 Backtesting Mode**
        - Test trading strategies automatically
        - Analyze historical performance
        - Compare against buy-and-hold
        """)
        
        if st.button("🎯 Start Backtesting", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.session_state.mode = "backtesting"
            st.rerun()
    
    with col2:
        st.markdown("""
        **🎮 Trading Simulator**
        - Practice manual trading
        - Real-time P&L tracking
        - Risk-free learning environment
        """)
        
        if st.button("🎲 Start Simulator", type="primary", use_container_width=True):
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
        **🔍 Stock Discovery**
        - Search and analyze stocks
        - Technical indicators
        - Market correlation analysis
        """)
        
        if st.button("🔎 Explore Stocks", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.session_state.mode = "analysis"
            st.rerun()
    
    st.divider()
    
    # Features overview
    st.markdown("### ✨ Key Features")
    
    features_col1, features_col2 = st.columns(2)
    
    with features_col1:
        st.markdown("""
        **🤖 Advanced Strategies**
        - Moving Average Crossover
        - RSI Mean-Reversion & Threshold
        - Bollinger Bands Breakout
        
        **📊 Technical Analysis**
        - Multiple timeframes (1m to 1d)
        - 50+ technical indicators
        - Interactive charts with Plotly
        
        **⚙️ Professional Tools**
        - Sharpe ratio, max drawdown
        - Win rate analysis
        - Trade logging & export
        """)
    
    with features_col2:
        st.markdown("""
        **🎮 Trading Simulator**
        - Manual buy/sell orders
        - Real-time portfolio tracking
        - Performance metrics
        
        **📈 Risk Management**
        - Position sizing options
        - Transaction cost modeling
        - Drawdown analysis
        
        **🔗 Market Analysis**
        - Multi-asset correlation
        - Sector analysis
        - Popular stocks discovery
        """)
    
    st.divider()
    
    # Settings
    st.markdown("### ⚙️ Preferences")
    
    settings_col1, settings_col2, settings_col3 = st.columns(3)
    
    with settings_col1:
        ui_mode = st.radio(
            "Interface Mode",
            ["Simple", "Expert"],
            index=0,
            help="Simple: Guided experience | Expert: Full controls"
        )
        st.session_state.ui_mode = ui_mode.lower()
    
    with settings_col2:
        theme = st.radio(
            "Theme",
            ["Dark", "Light"],
            index=0,
            help="Chart and interface theme"
        )
        if st.session_state.get('theme') != theme.lower():
            st.session_state.theme = theme.lower()
            st.rerun()  # Refresh to apply theme changes
    
    with settings_col3:
        if st.button("🔄 Reset All Settings", type="secondary"):
            # Reset to defaults
            st.session_state.clear()
            st.rerun()
    
    # Skip option
    st.divider()
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("⏭️ Skip Welcome - Go to Dashboard", type="secondary", use_container_width=True):
            st.session_state.show_welcome = False
            st.rerun()


# ============================================================================
# STOCK ANALYSIS MODE
# ============================================================================

def show_stock_analysis_mode():
    """Display stock discovery and analysis mode."""
    st.title("🔍 Stock Discovery & Analysis")
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
        if st.button("🔎 Search", use_container_width=True):
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
    st.subheader("📊 Popular Stocks")
    
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
                raw_data = download_data(ticker, '2023-01-01', pd.to_datetime('today'), '1d')
                data = extract_ticker_data(raw_data, ticker, '2023-01-01', pd.to_datetime('today'))
            
            if info and len(data) > 0:
                st.subheader(f"📈 {ticker} - {info.get('name', 'Stock')}")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Sector", info.get('sector', 'N/A'))
                with col2:
                    st.metric("Market Cap", format_market_cap(info.get('market_cap', 0)))
                with col3:
                    st.metric("Current Price", format_price(info.get('current_price', 0)))
                with col4:
                    change = info.get('price_change_percent', 0)
                    color = "🟢" if change > 0 else "🔴"
                    st.metric("Change", f"{color} {change:.2f}%")
                
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
                if st.button("📊 Analyze with Backtest", type="primary", use_container_width=True):
                    st.session_state.mode = 'backtesting'
                    st.rerun()
        except Exception as e:
            st.error(f"Error loading stock data: {e}")
    
    # Back to welcome
    st.divider()
    if st.button("🏠 Back to Welcome", type="secondary", use_container_width=True):
        st.session_state.show_welcome = True
        st.rerun()

    # ========================================================================

if __name__ == "__main__":
    main()
